import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from operator import attrgetter

from sqlalchemy.ext.asyncio import AsyncSession

from ..exceptions import NotFoundError, StationFullError, VehicleNotAvailableError
from ..models import Rental, RentalStatus, Vehicle, VehicleStatus
from . import station_service

RATE_PER_HOUR = 5.0
MIN_BILLABLE_HOURS = 1


def calculate_cost(
    started_at: datetime, ended_at: datetime, rate_per_hour: float = RATE_PER_HOUR
) -> float:
    duration_hours = (ended_at - started_at).total_seconds() / 3600
    billable_hours = max(math.ceil(duration_hours), MIN_BILLABLE_HOURS)
    return round(billable_hours * rate_per_hour, 2)


async def start_rental(db: AsyncSession, renter_id: int, vehicle_id: int) -> Rental:
    vehicle = await db.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise NotFoundError(f"Vehicle {vehicle_id} not found")
    if vehicle.status != VehicleStatus.AVAILABLE:
        raise VehicleNotAvailableError(f"Vehicle {vehicle_id} is not available")

    rental = Rental(
        renter_id=renter_id,
        vehicle_id=vehicle_id,
        start_station_id=vehicle.station_id,
        status=RentalStatus.ACTIVE,
    )
    vehicle.status = VehicleStatus.RENTED

    db.add(rental)
    await db.commit()
    await db.refresh(rental)
    return rental


async def end_rental(db: AsyncSession, rental_id: int, end_station_id: int) -> Rental:
    rental = await db.get(Rental, rental_id)
    if rental is None:
        raise NotFoundError(f"Rental {rental_id} not found")
    if rental.status != RentalStatus.ACTIVE:
        raise VehicleNotAvailableError(f"Rental {rental_id} is not active")

    if not await station_service.has_free_slot(db, end_station_id):
        raise StationFullError(f"Station {end_station_id} has no free slots")

    vehicle = await db.get(Vehicle, rental.vehicle_id)

    rental.ended_at = datetime.utcnow()
    rental.end_station_id = end_station_id
    rental.status = RentalStatus.COMPLETED
    vehicle.status = VehicleStatus.AVAILABLE
    vehicle.station_id = end_station_id

    await db.commit()
    await db.refresh(rental)
    return rental


ZONE_DISCOUNTS = {"center": 1, "suburb": -1}


def _vip_discount(rental_count: int, vehicle_type: str) -> float:
    if rental_count > 10:
        return 5 if vehicle_type == "premium" else 10
    return 2 if vehicle_type == "premium" else 5


def _regular_discount(rental_count: int, has_coupon: bool) -> float:
    if rental_count > 20:
        return 3
    if rental_count <= 5:
        return 0
    return 4 if has_coupon else 1


def _weekend_zone_discount(station_zones: list[str]) -> float:
    return sum(ZONE_DISCOUNTS.get(zone, 0) for zone in station_zones)


def _holiday_discount(has_coupon: bool) -> float:
    return 2 if has_coupon else 1


def calculate_discount(
    rental_count: int,
    is_vip: bool,
    vehicle_type: str,
    station_zones: list[str],
    has_coupon: bool,
    is_weekend: bool,
    is_holiday: bool,
) -> float:
    discount = (
        _vip_discount(rental_count, vehicle_type)
        if is_vip
        else _regular_discount(rental_count, has_coupon)
    )

    if is_weekend:
        discount += _weekend_zone_discount(station_zones)
    if is_holiday:
        discount += _holiday_discount(has_coupon)

    return discount


@dataclass(frozen=True)
class RentalEligibilityContext:
    renter_is_blacklisted: bool
    license_expired: bool
    has_unpaid_fees: bool
    active_rental_count: int
    vehicle_status: VehicleStatus
    station_is_open: bool
    is_weekend: bool
    weekend_requires_deposit: bool
    has_deposit_on_file: bool

    @property
    def deposit_missing(self) -> bool:
        return self.is_weekend and self.weekend_requires_deposit and not self.has_deposit_on_file

    def unpaid_fees_with_active_rental(self) -> bool:
        return self.has_unpaid_fees and self.active_rental_count > 0

    def unpaid_fees_without_deposit(self) -> bool:
        return self.has_unpaid_fees and self.deposit_missing

    def vehicle_unavailable(self) -> bool:
        return self.vehicle_status != VehicleStatus.AVAILABLE

    def station_closed(self) -> bool:
        return not self.station_is_open


EligibilityRule = tuple[Callable[[RentalEligibilityContext], bool], str]

# Ordered by priority: the first violated rule determines the rejection reason.
ELIGIBILITY_RULES: tuple[EligibilityRule, ...] = (
    (attrgetter("renter_is_blacklisted"), "Renter is blacklisted"),
    (attrgetter("license_expired"), "License expired"),
    (RentalEligibilityContext.unpaid_fees_with_active_rental, "Unpaid fees with an active rental"),
    (
        RentalEligibilityContext.unpaid_fees_without_deposit,
        "Deposit required for unpaid fees on weekend",
    ),
    (RentalEligibilityContext.vehicle_unavailable, "Vehicle not available"),
    (RentalEligibilityContext.station_closed, "Station is closed"),
    (attrgetter("deposit_missing"), "Deposit required on weekend"),
)


def validate_rental_eligibility(
    renter_is_blacklisted: bool,
    license_expired: bool,
    has_unpaid_fees: bool,
    active_rental_count: int,
    vehicle_status: VehicleStatus,
    station_is_open: bool,
    is_weekend: bool,
    weekend_requires_deposit: bool,
    has_deposit_on_file: bool,
) -> tuple[bool, str]:
    ctx = RentalEligibilityContext(
        renter_is_blacklisted=renter_is_blacklisted,
        license_expired=license_expired,
        has_unpaid_fees=has_unpaid_fees,
        active_rental_count=active_rental_count,
        vehicle_status=vehicle_status,
        station_is_open=station_is_open,
        is_weekend=is_weekend,
        weekend_requires_deposit=weekend_requires_deposit,
        has_deposit_on_file=has_deposit_on_file,
    )
    for is_violated, reason in ELIGIBILITY_RULES:
        if is_violated(ctx):
            return False, reason
    return True, "OK"

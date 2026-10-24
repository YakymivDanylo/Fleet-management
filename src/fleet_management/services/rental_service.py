import math
from bisect import bisect_left
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

# Discount policy as data: keys are the evaluated conditions, values are the discounts.
VIP_DISCOUNT = {  # (more than 10 rentals, premium vehicle)
    (True, True): 5,
    (True, False): 10,
    (False, True): 2,
    (False, False): 5,
}
REGULAR_TIER_BOUNDS = (5, 20)  # bisect_left: <=5 -> tier 0, 6..20 -> tier 1, >20 -> tier 2
REGULAR_DISCOUNT = {  # (rental-count tier, has coupon)
    (0, False): 0,
    (0, True): 0,
    (1, False): 1,
    (1, True): 4,
    (2, False): 3,
    (2, True): 3,
}
HOLIDAY_DISCOUNT = {True: 2, False: 1}  # keyed by has_coupon


def _vip_discount(rental_count: int, vehicle_type: str) -> float:
    return VIP_DISCOUNT[(rental_count > 10, vehicle_type == "premium")]


def _regular_discount(rental_count: int, has_coupon: bool) -> float:
    return REGULAR_DISCOUNT[(bisect_left(REGULAR_TIER_BOUNDS, rental_count), has_coupon)]


def _weekend_zone_discount(station_zones: list[str]) -> float:
    return sum(ZONE_DISCOUNTS.get(zone, 0) for zone in station_zones)


def _holiday_discount(has_coupon: bool) -> float:
    return HOLIDAY_DISCOUNT[has_coupon]


@dataclass(frozen=True)
class DiscountContext:
    rental_count: int
    is_vip: bool
    vehicle_type: str
    station_zones: list[str]
    has_coupon: bool
    is_weekend: bool
    is_holiday: bool
    is_corporate: bool
    is_night: bool
    trip_hours: float
    is_birthday: bool
    returned_charged: bool


Amount = Callable[[DiscountContext], float]
ConditionKey = Callable[[DiscountContext], tuple]


def _flat(amount: float) -> Amount:
    return lambda _ctx: amount


_NO_DISCOUNT = _flat(0)

BASE_DISCOUNT: dict[bool, Amount] = {  # keyed by is_vip
    True: lambda c: _vip_discount(c.rental_count, c.vehicle_type),
    False: lambda c: _regular_discount(c.rental_count, c.has_coupon),
}

# Each rule: a key function evaluating the rule's conditions, and a truth table that maps the
# keys that earn a discount to its amount. Every other key falls back to _NO_DISCOUNT.
SURCHARGE_RULES: tuple[tuple[ConditionKey, dict[tuple, Amount]], ...] = (
    (
        lambda c: (c.is_weekend,),
        {(True,): lambda c: _weekend_zone_discount(c.station_zones)},
    ),
    (
        lambda c: (c.is_holiday,),
        {(True,): lambda c: _holiday_discount(c.has_coupon)},
    ),
    (  # corporate account, more than 5 rentals, non-premium vehicle
        lambda c: (c.is_corporate, c.rental_count > 5, c.vehicle_type != "premium"),
        {(True, True, True): _flat(3)},
    ),
    (  # night trip of 3+ hours without a coupon
        lambda c: (c.is_night, c.trip_hours >= 3, c.has_coupon),
        {(True, True, False): _flat(4)},
    ),
    (  # birthday for VIPs or renters with more than 3 rentals
        lambda c: (c.is_birthday, c.is_vip, c.rental_count > 3),
        {
            (True, True, True): _flat(6),
            (True, True, False): _flat(6),
            (True, False, True): _flat(6),
        },
    ),
    (  # electric vehicle returned charged after more than an hour
        lambda c: (c.returned_charged, c.vehicle_type == "electric", c.trip_hours > 1),
        {(True, True, True): _flat(2)},
    ),
)


def calculate_discount(
    rental_count: int,
    is_vip: bool,
    vehicle_type: str,
    station_zones: list[str],
    has_coupon: bool,
    is_weekend: bool,
    is_holiday: bool,
    *,
    is_corporate: bool = False,
    is_night: bool = False,
    trip_hours: float = 0.0,
    is_birthday: bool = False,
    returned_charged: bool = False,
) -> float:
    ctx = DiscountContext(
        rental_count,
        is_vip,
        vehicle_type,
        station_zones,
        has_coupon,
        is_weekend,
        is_holiday,
        is_corporate,
        is_night,
        trip_hours,
        is_birthday,
        returned_charged,
    )
    return BASE_DISCOUNT[is_vip](ctx) + sum(
        table.get(key(ctx), _NO_DISCOUNT)(ctx) for key, table in SURCHARGE_RULES
    )


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

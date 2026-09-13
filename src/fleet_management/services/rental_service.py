import math
from datetime import datetime

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

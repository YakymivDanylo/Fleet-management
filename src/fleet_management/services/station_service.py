from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..exceptions import NotFoundError
from ..models import Station, Vehicle, VehicleStatus
from ..schemas import StationAvailability


async def get_station(db: AsyncSession, station_id: int) -> Station:
    station = await db.get(Station, station_id)
    if station is None:
        raise NotFoundError(f"Station {station_id} not found")
    return station


async def count_parked_vehicles(db: AsyncSession, station_id: int) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(Vehicle)
        .where(Vehicle.station_id == station_id, Vehicle.status != VehicleStatus.RENTED)
    )
    return result.scalar_one()


async def has_free_slot(db: AsyncSession, station_id: int) -> bool:
    station = await get_station(db, station_id)
    parked = await count_parked_vehicles(db, station_id)
    return parked < station.capacity


async def count_available_vehicles(db: AsyncSession, station_id: int) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(Vehicle)
        .where(Vehicle.station_id == station_id, Vehicle.status == VehicleStatus.AVAILABLE)
    )
    return result.scalar_one()


async def get_availability(db: AsyncSession, station_id: int) -> StationAvailability:
    station = await get_station(db, station_id)
    parked = await count_parked_vehicles(db, station_id)
    return StationAvailability(
        station_id=station.id,
        capacity=station.capacity,
        parked_vehicles=parked,
        free_slots=max(station.capacity - parked, 0),
        available_vehicles=await count_available_vehicles(db, station_id),
    )

"""Stations: lookup, occupancy and availability (read side of the station-based carsharing)."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..exceptions import NotFoundError
from ..models import Station, Vehicle, VehicleStatus
from ..schemas import StationAvailability


async def get_station(db: AsyncSession, station_id: int) -> Station:
    """Return the station or raise ``NotFoundError`` (HTTP 404)."""
    station = await db.get(Station, station_id)
    if station is None:
        raise NotFoundError(f"Station {station_id} not found")
    return station


async def count_parked_vehicles(db: AsyncSession, station_id: int) -> int:
    """Count vehicles that occupy a slot: every status except ``rented``."""
    result = await db.execute(
        select(func.count())
        .select_from(Vehicle)
        .where(Vehicle.station_id == station_id, Vehicle.status != VehicleStatus.RENTED)
    )
    return result.scalar_one()


async def has_free_slot(db: AsyncSession, station_id: int) -> bool:
    """True if a returning vehicle can be parked: parked vehicles < capacity."""
    station = await get_station(db, station_id)
    parked = await count_parked_vehicles(db, station_id)
    return parked < station.capacity


async def count_available_vehicles(db: AsyncSession, station_id: int) -> int:
    """Count vehicles with status ``available`` (ready to rent)."""
    result = await db.execute(
        select(func.count())
        .select_from(Vehicle)
        .where(Vehicle.station_id == station_id, Vehicle.status == VehicleStatus.AVAILABLE)
    )
    return result.scalar_one()


async def get_availability(db: AsyncSession, station_id: int) -> StationAvailability:
    """Live availability of a station, always computed from PostgreSQL (no cache).

    Args:
        db: Open database session.
        station_id: Station to inspect.

    Returns:
        Capacity, parked vehicles, ``free_slots = max(capacity - parked, 0)`` and available vehicles
        — the ``StationAvailability`` schema of the API contract.

    Raises:
        NotFoundError: The station does not exist (HTTP 404).
    """
    station = await get_station(db, station_id)
    parked = await count_parked_vehicles(db, station_id)
    return StationAvailability(
        station_id=station.id,
        capacity=station.capacity,
        parked_vehicles=parked,
        free_slots=max(station.capacity - parked, 0),
        available_vehicles=await count_available_vehicles(db, station_id),
    )

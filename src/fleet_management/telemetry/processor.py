from datetime import datetime

from redis.asyncio import Redis
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..exceptions import NotFoundError
from ..models import TelemetryReading, Vehicle
from .schemas import TelemetryMessage


def vehicle_state_key(vehicle_id: int) -> str:
    return f"vehicle:{vehicle_id}:state"


async def save_reading(db: AsyncSession, message: TelemetryMessage) -> bool:
    """Store a reading; return False if the same reading was already stored."""
    if await db.get(Vehicle, message.vehicle_id) is None:
        raise NotFoundError(f"Vehicle {message.vehicle_id} not found")

    statement = (
        insert(TelemetryReading)
        .values(**message.model_dump())
        .on_conflict_do_nothing(constraint="uq_telemetry_vehicle_recorded_at")
    )
    result = await db.execute(statement)
    await db.commit()
    return result.rowcount == 1


async def update_vehicle_state(redis: Redis, message: TelemetryMessage) -> bool:
    """Cache the latest vehicle state; return False if the cache already has newer data."""
    key = vehicle_state_key(message.vehicle_id)
    cached_at = await redis.hget(key, "recorded_at")
    if cached_at is not None and datetime.fromisoformat(cached_at) >= message.recorded_at:
        return False

    await redis.hset(
        key,
        mapping={
            "recorded_at": message.recorded_at.isoformat(),
            "latitude": message.latitude,
            "longitude": message.longitude,
            "fuel_level": message.fuel_level,
            "is_locked": int(message.is_locked),
        },
    )
    return True

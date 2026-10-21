import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from datetime import datetime

from redis import exceptions as redis_errors
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..exceptions import DependencyUnavailableError, NotFoundError
from ..models import TelemetryReading, Vehicle
from ..resilience import RetryExhaustedError, RetryPolicy, call_with_retry
from ..schemas import FleetPositionsRead, VehiclePositionRead, VehicleStateRead
from ..telemetry.processor import vehicle_state_key

logger = logging.getLogger("fleet_management.vehicle_state")

REDIS_TRANSIENT_ERRORS = (redis_errors.ConnectionError, redis_errors.TimeoutError)


def _from_cache(vehicle_id: int, cached: dict[str, str]) -> VehicleStateRead:
    return VehicleStateRead(
        vehicle_id=vehicle_id,
        recorded_at=datetime.fromisoformat(cached["recorded_at"]),
        latitude=float(cached["latitude"]),
        longitude=float(cached["longitude"]),
        fuel_level=float(cached["fuel_level"]),
        is_locked=cached["is_locked"] == "1",
        source="cache",
    )


def _from_reading(reading: TelemetryReading, degraded: bool) -> VehicleStateRead:
    return VehicleStateRead(
        vehicle_id=reading.vehicle_id,
        recorded_at=reading.recorded_at,
        latitude=reading.latitude,
        longitude=reading.longitude,
        fuel_level=reading.fuel_level,
        is_locked=reading.is_locked,
        source="database",
        degraded=degraded,
    )


async def latest_reading(db: AsyncSession, vehicle_id: int) -> TelemetryReading | None:
    result = await db.execute(
        select(TelemetryReading)
        .where(TelemetryReading.vehicle_id == vehicle_id)
        .order_by(TelemetryReading.recorded_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_vehicle_state(
    db: AsyncSession,
    redis: Redis,
    vehicle_id: int,
    policy: RetryPolicy | None,
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    rand: Callable[[], float] = random.random,
) -> VehicleStateRead:
    """Current vehicle state: Redis hot cache first, Postgres as the source of truth.

    With ``policy=None`` (resilience disabled) a Redis failure propagates
    unhandled. With a policy the Redis read is retried with backoff, and when
    retries are exhausted the last reading from Postgres is served as a
    degraded answer.
    """
    key = vehicle_state_key(vehicle_id)

    if policy is None:
        cached = await redis.hgetall(key)
    else:
        try:
            cached = await call_with_retry(
                lambda: redis.hgetall(key),
                policy,
                retry_on=REDIS_TRANSIENT_ERRORS,
                name="redis.hgetall",
                sleep=sleep,
                rand=rand,
            )
        except RetryExhaustedError as exc:
            logger.error(
                "Redis unavailable for vehicle %d after %d attempts (%r); "
                "serving degraded state from Postgres",
                vehicle_id,
                exc.attempts,
                exc.last_error,
            )
            reading = await latest_reading(db, vehicle_id)
            if reading is None:
                raise DependencyUnavailableError(
                    f"State of vehicle {vehicle_id} is temporarily unavailable"
                ) from exc
            return _from_reading(reading, degraded=True)

    if cached:
        return _from_cache(vehicle_id, cached)

    reading = await latest_reading(db, vehicle_id)
    if reading is None:
        raise NotFoundError(f"No telemetry for vehicle {vehicle_id}")
    return _from_reading(reading, degraded=False)


async def _latest_readings(db: AsyncSession, vehicle_ids: list[int]) -> dict[int, TelemetryReading]:
    if not vehicle_ids:
        return {}
    # DISTINCT ON keeps the newest reading per vehicle in a single query.
    result = await db.execute(
        select(TelemetryReading)
        .where(TelemetryReading.vehicle_id.in_(vehicle_ids))
        .order_by(TelemetryReading.vehicle_id, TelemetryReading.recorded_at.desc())
        .distinct(TelemetryReading.vehicle_id)
    )
    return {reading.vehicle_id: reading for reading in result.scalars().all()}


async def _cached_states(redis: Redis, vehicle_ids: list[int]) -> dict[int, dict[str, str]]:
    pipe = redis.pipeline(transaction=False)
    for vehicle_id in vehicle_ids:
        pipe.hgetall(vehicle_state_key(vehicle_id))
    results = await pipe.execute()
    return {vid: cached for vid, cached in zip(vehicle_ids, results, strict=True) if cached}


def _position(vehicle: Vehicle, state: VehicleStateRead) -> VehiclePositionRead:
    return VehiclePositionRead(
        vehicle_id=vehicle.id,
        license_plate=vehicle.license_plate,
        model=vehicle.model,
        status=vehicle.status,
        station_id=vehicle.station_id,
        recorded_at=state.recorded_at,
        latitude=state.latitude,
        longitude=state.longitude,
        fuel_level=state.fuel_level,
        is_locked=state.is_locked,
        source=state.source,
    )


async def get_fleet_positions(db: AsyncSession, redis: Redis) -> FleetPositionsRead:
    """Latest known position of every vehicle for the live map.

    One Redis pipeline round trip for the hot state; vehicles missing from the cache
    (or all of them, if Redis is down) are filled from Postgres in one query.
    """
    vehicles = (await db.execute(select(Vehicle).order_by(Vehicle.id))).scalars().all()
    ids = [vehicle.id for vehicle in vehicles]

    degraded = False
    try:
        cached = await _cached_states(redis, ids) if ids else {}
    except REDIS_TRANSIENT_ERRORS as exc:
        logger.error("Redis unavailable for fleet positions (%r); serving from Postgres", exc)
        cached, degraded = {}, True

    readings = await _latest_readings(db, [vid for vid in ids if vid not in cached])

    positions, without_telemetry = [], []
    for vehicle in vehicles:
        if vehicle.id in cached:
            positions.append(_position(vehicle, _from_cache(vehicle.id, cached[vehicle.id])))
        elif vehicle.id in readings:
            state = _from_reading(readings[vehicle.id], degraded=degraded)
            positions.append(_position(vehicle, state))
        else:
            without_telemetry.append(vehicle.id)
    return FleetPositionsRead(
        positions=positions, without_telemetry=without_telemetry, degraded=degraded
    )

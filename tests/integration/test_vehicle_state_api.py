from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from redis import exceptions as redis_errors

from fleet_management.cache import get_redis, get_retry_policy
from fleet_management.main import app
from fleet_management.models import Station, TelemetryReading, Vehicle
from fleet_management.resilience import RetryPolicy
from fleet_management.telemetry.processor import vehicle_state_key

# Same attempt count as production, tiny pauses so the suite stays fast.
FAST_POLICY = RetryPolicy(max_attempts=3, attempt_timeout=0.2, base_delay=0.001, max_delay=0.004)


class DownRedis:
    """Stub of a Redis that refuses every connection (deterministic HTTP-level fault)."""

    def __init__(self):
        self.calls = 0

    async def hgetall(self, key: str):
        self.calls += 1
        raise redis_errors.ConnectionError("Connection refused (fault injected)")


@pytest.fixture
async def vehicle_id(session_factory) -> int:
    async with session_factory() as db:
        station = Station(address="Lviv, Rynok 1", capacity=5)
        db.add(station)
        await db.flush()
        vehicle = Vehicle(license_plate="BC7777AA", model="Skoda Fabia", station_id=station.id)
        db.add(vehicle)
        await db.commit()
        return vehicle.id


async def add_reading(session_factory, vehicle_id: int) -> None:
    async with session_factory() as db:
        db.add(
            TelemetryReading(
                vehicle_id=vehicle_id,
                recorded_at=datetime(2026, 9, 26, 9, 55, tzinfo=UTC),
                latitude=49.8,
                longitude=24.0,
                fuel_level=60.0,
                is_locked=False,
            )
        )
        await db.commit()


def use_redis(redis) -> None:
    app.dependency_overrides[get_redis] = lambda: redis
    app.dependency_overrides[get_retry_policy] = lambda: FAST_POLICY


async def test_state_is_served_from_redis_cache(client: AsyncClient, redis_client, vehicle_id):
    await redis_client.hset(
        vehicle_state_key(vehicle_id),
        mapping={
            "recorded_at": "2026-09-26T10:00:00+00:00",
            "latitude": 49.8397,
            "longitude": 24.0297,
            "fuel_level": 72.5,
            "is_locked": 1,
        },
    )
    use_redis(redis_client)

    response = await client.get(f"/vehicles/{vehicle_id}/state")

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "cache"
    assert body["degraded"] is False
    assert body["fuel_level"] == 72.5


async def test_redis_outage_returns_degraded_state_from_postgres(
    client: AsyncClient, session_factory, vehicle_id
):
    await add_reading(session_factory, vehicle_id)
    redis = DownRedis()
    use_redis(redis)

    response = await client.get(f"/vehicles/{vehicle_id}/state")

    assert response.status_code == 200
    assert response.json() == {
        "vehicle_id": vehicle_id,
        "recorded_at": "2026-09-26T09:55:00Z",
        "latitude": 49.8,
        "longitude": 24.0,
        "fuel_level": 60.0,
        "is_locked": False,
        "source": "database",
        "degraded": True,
    }
    assert redis.calls == 3


async def test_redis_outage_without_fallback_data_returns_503(client: AsyncClient, vehicle_id):
    redis = DownRedis()
    use_redis(redis)

    response = await client.get(f"/vehicles/{vehicle_id}/state")

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "5"
    assert response.json() == {
        "detail": f"State of vehicle {vehicle_id} is temporarily unavailable"
    }
    assert redis.calls == 3

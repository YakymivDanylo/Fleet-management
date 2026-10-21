from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from redis import exceptions as redis_errors

from fleet_management.cache import get_redis
from fleet_management.main import app
from fleet_management.models import Station, TelemetryReading, UserRole, Vehicle
from fleet_management.services import user_service
from fleet_management.telemetry.processor import vehicle_state_key

PASSWORD = "correct-horse-battery"


class DownRedisPipeline:
    def hgetall(self, key: str):
        return self

    async def execute(self):
        raise redis_errors.ConnectionError("Connection refused (fault injected)")


class DownRedis:
    def pipeline(self, transaction: bool = True):
        return DownRedisPipeline()


async def headers_for(client: AsyncClient, session_factory, email: str, role: UserRole) -> dict:
    async with session_factory() as db:
        await user_service.create_user(db, email, PASSWORD, "Someone", role=role)
    response = await client.post("/auth/login", data={"username": email, "password": PASSWORD})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
async def admin_headers(client: AsyncClient, session_factory) -> dict:
    return await headers_for(client, session_factory, "admin@example.com", UserRole.ADMIN)


@pytest.fixture
async def vehicle_ids(session_factory) -> list[int]:
    async with session_factory() as db:
        station = Station(address="Kyiv, Khreshchatyk 1", capacity=5)
        db.add(station)
        await db.flush()
        vehicles = [
            Vehicle(license_plate=f"AA000{i}KA", model="Zoe", station_id=station.id)
            for i in range(3)
        ]
        db.add_all(vehicles)
        await db.commit()
        return [vehicle.id for vehicle in vehicles]


async def add_reading(session_factory, vehicle_id: int, minute: int, latitude: float) -> None:
    async with session_factory() as db:
        db.add(
            TelemetryReading(
                vehicle_id=vehicle_id,
                recorded_at=datetime(2026, 10, 21, 12, minute, tzinfo=UTC),
                latitude=latitude,
                longitude=30.5,
                fuel_level=70.0,
                is_locked=True,
            )
        )
        await db.commit()


@pytest.fixture
def real_redis(redis_client):
    app.dependency_overrides[get_redis] = lambda: redis_client
    return redis_client


async def test_positions_require_authentication(client: AsyncClient):
    assert (await client.get("/vehicles/positions")).status_code == 401


async def test_positions_are_forbidden_for_regular_users(client: AsyncClient, session_factory):
    headers = await headers_for(client, session_factory, "user@example.com", UserRole.USER)
    assert (await client.get("/vehicles/positions", headers=headers)).status_code == 403


async def test_positions_merge_cache_and_database(
    client: AsyncClient, session_factory, admin_headers, vehicle_ids, real_redis
):
    cached_id, db_id, silent_id = vehicle_ids
    await real_redis.hset(
        vehicle_state_key(cached_id),
        mapping={
            "recorded_at": "2026-10-21T12:30:00+00:00",
            "latitude": 50.45,
            "longitude": 30.52,
            "fuel_level": 55.5,
            "is_locked": 0,
        },
    )
    await add_reading(session_factory, db_id, minute=1, latitude=50.1)
    await add_reading(session_factory, db_id, minute=5, latitude=50.2)

    response = await client.get("/vehicles/positions", headers=admin_headers)

    assert response.status_code == 200
    body = response.json()
    by_id = {p["vehicle_id"]: p for p in body["positions"]}
    assert by_id[cached_id]["source"] == "cache"
    assert by_id[cached_id]["latitude"] == 50.45
    assert by_id[cached_id]["is_locked"] is False
    assert by_id[cached_id]["license_plate"] == "AA0000KA"
    # Only the newest reading per vehicle is used.
    assert by_id[db_id]["source"] == "database"
    assert by_id[db_id]["latitude"] == 50.2
    assert body["without_telemetry"] == [silent_id]
    assert body["degraded"] is False


async def test_positions_fall_back_to_database_when_redis_is_down(
    client: AsyncClient, session_factory, admin_headers, vehicle_ids
):
    await add_reading(session_factory, vehicle_ids[0], minute=1, latitude=50.3)
    app.dependency_overrides[get_redis] = lambda: DownRedis()

    response = await client.get("/vehicles/positions", headers=admin_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["degraded"] is True
    assert [p["vehicle_id"] for p in body["positions"]] == [vehicle_ids[0]]
    assert body["positions"][0]["source"] == "database"


async def test_positions_route_does_not_shadow_vehicle_by_id(client: AsyncClient, vehicle_ids):
    response = await client.get(f"/vehicles/{vehicle_ids[0]}")
    assert response.status_code == 200

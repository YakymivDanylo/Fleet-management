import json

import pytest
from redis.asyncio import Redis
from sqlalchemy import func, select

from fleet_management.models import Station, TelemetryReading, Vehicle
from fleet_management.telemetry import worker
from fleet_management.telemetry.processor import vehicle_state_key


class FakeMessage:
    """Stands in for an aio-pika message: records how the worker settled it."""

    def __init__(self, body: bytes):
        self.body = body
        self.outcome = None

    async def ack(self):
        self.outcome = "ack"

    async def reject(self, requeue: bool = False):
        self.outcome = ("reject", requeue)

    async def nack(self, requeue: bool = True):
        self.outcome = ("nack", requeue)


def telemetry_body(vehicle_id: int, recorded_at: str = "2026-09-15T10:00:00+00:00", **overrides):
    payload = {
        "vehicle_id": vehicle_id,
        "recorded_at": recorded_at,
        "latitude": 49.8397,
        "longitude": 24.0297,
        "fuel_level": 72.5,
        "is_locked": True,
    }
    payload.update(overrides)
    return json.dumps(payload).encode()


@pytest.fixture
async def vehicle_id(session_factory) -> int:
    async with session_factory() as db:
        station = Station(address="Lviv, Svobody 1", capacity=5)
        db.add(station)
        await db.flush()
        vehicle = Vehicle(license_plate="BC1234AA", model="Skoda Octavia", station_id=station.id)
        db.add(vehicle)
        await db.commit()
        return vehicle.id


async def count_readings(session_factory) -> int:
    async with session_factory() as db:
        return await db.scalar(select(func.count()).select_from(TelemetryReading))


async def test_valid_message_is_stored_cached_and_acked(session_factory, redis_client, vehicle_id):
    message = FakeMessage(telemetry_body(vehicle_id))

    await worker.handle_message(message, session_factory, redis_client)

    assert message.outcome == "ack"
    assert await count_readings(session_factory) == 1
    state = await redis_client.hgetall(vehicle_state_key(vehicle_id))
    assert state == {
        "recorded_at": "2026-09-15T10:00:00+00:00",
        "latitude": "49.8397",
        "longitude": "24.0297",
        "fuel_level": "72.5",
        "is_locked": "1",
    }


async def test_invalid_message_is_rejected_without_requeue(session_factory, redis_client):
    message = FakeMessage(b"not json")

    await worker.handle_message(message, session_factory, redis_client)

    assert message.outcome == ("reject", False)
    assert await count_readings(session_factory) == 0


async def test_unknown_vehicle_is_rejected_without_requeue(session_factory, redis_client):
    message = FakeMessage(telemetry_body(vehicle_id=999))

    await worker.handle_message(message, session_factory, redis_client)

    assert message.outcome == ("reject", False)
    assert await redis_client.exists(vehicle_state_key(999)) == 0


async def test_duplicate_message_is_stored_once(session_factory, redis_client, vehicle_id):
    for _ in range(2):
        message = FakeMessage(telemetry_body(vehicle_id))
        await worker.handle_message(message, session_factory, redis_client)
        assert message.outcome == "ack"

    assert await count_readings(session_factory) == 1


async def test_older_message_does_not_overwrite_cached_state(
    session_factory, redis_client, vehicle_id
):
    newer = FakeMessage(telemetry_body(vehicle_id, "2026-09-15T10:05:00+00:00", fuel_level=70))
    older = FakeMessage(telemetry_body(vehicle_id, "2026-09-15T10:00:00+00:00", fuel_level=75))

    await worker.handle_message(newer, session_factory, redis_client)
    await worker.handle_message(older, session_factory, redis_client)

    assert older.outcome == "ack"
    assert await count_readings(session_factory) == 2
    state = await redis_client.hgetall(vehicle_state_key(vehicle_id))
    assert state["fuel_level"] == "70.0"


async def test_infrastructure_failure_requeues_message(session_factory, vehicle_id, monkeypatch):
    monkeypatch.setattr(worker, "NACK_DELAY_SECONDS", 0)
    unreachable_redis = Redis.from_url("redis://localhost:1/0", decode_responses=True)
    message = FakeMessage(telemetry_body(vehicle_id))

    await worker.handle_message(message, session_factory, unreachable_redis)

    assert message.outcome == ("nack", True)
    await unreachable_redis.aclose()

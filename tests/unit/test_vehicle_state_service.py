import logging
from datetime import UTC, datetime

import pytest
from redis import exceptions as redis_errors

from fleet_management.exceptions import DependencyUnavailableError, NotFoundError
from fleet_management.models import TelemetryReading
from fleet_management.resilience import RetryPolicy
from fleet_management.services import vehicle_state_service

POLICY = RetryPolicy(max_attempts=3, attempt_timeout=0.2, base_delay=0.05, max_delay=0.4)
VEHICLE_ID = 7
CACHED_STATE = {
    "recorded_at": "2026-09-26T10:00:00+00:00",
    "latitude": "49.8397",
    "longitude": "24.0297",
    "fuel_level": "72.5",
    "is_locked": "1",
}
DB_READING = TelemetryReading(
    vehicle_id=VEHICLE_ID,
    recorded_at=datetime(2026, 9, 26, 9, 55, tzinfo=UTC),
    latitude=49.8,
    longitude=24.0,
    fuel_level=60.0,
    is_locked=False,
)


class FakeRedis:
    """Test double for the Redis dependency: fails ``failures`` times, then serves ``state``."""

    def __init__(self, state: dict[str, str] | None = None, failures: int = 0):
        self.state = state or {}
        self.failures = failures
        self.calls = 0

    async def hgetall(self, key: str) -> dict[str, str]:
        self.calls += 1
        if self.calls <= self.failures:
            raise redis_errors.ConnectionError("Connection refused (fault injected)")
        return dict(self.state)


class RecordingSleep:
    def __init__(self):
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


class FakeLatestReading:
    """Replaces the Postgres lookup and records whether the fallback path touched it."""

    def __init__(self, reading: TelemetryReading | None):
        self.reading = reading
        self.calls = 0

    async def __call__(self, db, vehicle_id: int) -> TelemetryReading | None:
        self.calls += 1
        return self.reading


@pytest.fixture
def sleep():
    return RecordingSleep()


def use_db_reading(monkeypatch, reading: TelemetryReading | None) -> FakeLatestReading:
    fake = FakeLatestReading(reading)
    monkeypatch.setattr(vehicle_state_service, "latest_reading", fake)
    return fake


async def get_state(redis: FakeRedis, sleep: RecordingSleep, policy: RetryPolicy | None = POLICY):
    return await vehicle_state_service.get_vehicle_state(
        db=None, redis=redis, vehicle_id=VEHICLE_ID, policy=policy, sleep=sleep, rand=lambda: 1.0
    )


async def test_healthy_redis_serves_cache_and_fallback_is_not_used(monkeypatch, sleep):
    db = use_db_reading(monkeypatch, DB_READING)
    redis = FakeRedis(state=CACHED_STATE)

    state = await get_state(redis, sleep)

    assert state.model_dump(mode="json") == {
        "vehicle_id": VEHICLE_ID,
        "recorded_at": "2026-09-26T10:00:00Z",
        "latitude": 49.8397,
        "longitude": 24.0297,
        "fuel_level": 72.5,
        "is_locked": True,
        "source": "cache",
        "degraded": False,
    }
    assert redis.calls == 1
    assert sleep.delays == []
    assert db.calls == 0


async def test_single_redis_blip_is_absorbed_by_retry(monkeypatch, sleep):
    db = use_db_reading(monkeypatch, DB_READING)
    redis = FakeRedis(state=CACHED_STATE, failures=1)

    state = await get_state(redis, sleep)

    assert state.source == "cache"
    assert state.degraded is False
    assert redis.calls == 2
    assert sleep.delays == pytest.approx([0.05])
    assert db.calls == 0


async def test_redis_outage_degrades_gracefully_to_postgres(monkeypatch, sleep, caplog):
    db = use_db_reading(monkeypatch, DB_READING)
    redis = FakeRedis(state=CACHED_STATE, failures=100)

    with caplog.at_level(logging.WARNING):
        state = await get_state(redis, sleep)

    assert state.model_dump(mode="json") == {
        "vehicle_id": VEHICLE_ID,
        "recorded_at": "2026-09-26T09:55:00Z",
        "latitude": 49.8,
        "longitude": 24.0,
        "fuel_level": 60.0,
        "is_locked": False,
        "source": "database",
        "degraded": True,
    }
    assert redis.calls == POLICY.max_attempts == 3
    assert sleep.delays == pytest.approx([0.05, 0.1])
    assert db.calls == 1
    retry_warnings = [r for r in caplog.records if r.name == "fleet_management.resilience"]
    assert len(retry_warnings) == 3
    fallback_logs = [r for r in caplog.records if r.name == "fleet_management.vehicle_state"]
    assert len(fallback_logs) == 1
    assert fallback_logs[0].levelno == logging.ERROR
    assert "serving degraded state from Postgres" in fallback_logs[0].getMessage()


async def test_redis_outage_without_fallback_data_is_a_controlled_error(monkeypatch, sleep):
    use_db_reading(monkeypatch, None)
    redis = FakeRedis(failures=100)

    with pytest.raises(DependencyUnavailableError, match="temporarily unavailable"):
        await get_state(redis, sleep)

    assert redis.calls == 3


async def test_cache_miss_reads_postgres_without_degraded_flag(monkeypatch, sleep):
    db = use_db_reading(monkeypatch, DB_READING)

    state = await get_state(FakeRedis(state={}), sleep)

    assert state.source == "database"
    assert state.degraded is False
    assert db.calls == 1


async def test_unknown_vehicle_is_not_found(monkeypatch, sleep):
    use_db_reading(monkeypatch, None)

    with pytest.raises(NotFoundError):
        await get_state(FakeRedis(state={}), sleep)


async def test_baseline_without_policy_lets_redis_failure_escape(monkeypatch, sleep):
    """Documents the unprotected "before" behaviour: no retry, no fallback."""
    db = use_db_reading(monkeypatch, DB_READING)
    redis = FakeRedis(state=CACHED_STATE, failures=1)

    with pytest.raises(redis_errors.ConnectionError):
        await get_state(redis, sleep, policy=None)

    assert redis.calls == 1
    assert db.calls == 0

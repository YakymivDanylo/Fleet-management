"""Lab 11: rental timestamps follow the API contract (RFC 3339 date-time with an offset)."""

from datetime import UTC, datetime, timedelta, timezone

from fleet_management.models import RentalStatus
from fleet_management.schemas import RentalRead


def rental(**overrides) -> RentalRead:
    values = {
        "id": 1,
        "renter_id": 2,
        "vehicle_id": 3,
        "start_station_id": 4,
        "end_station_id": None,
        "started_at": datetime(2026, 11, 20, 9, 15),
        "ended_at": None,
        "status": RentalStatus.ACTIVE,
        **overrides,
    }
    return RentalRead(**values)


def test_naive_timestamps_are_emitted_as_utc():
    body = rental(ended_at=datetime(2026, 11, 20, 11, 2)).model_dump(mode="json")
    assert body["started_at"] == "2026-11-20T09:15:00Z"
    assert body["ended_at"] == "2026-11-20T11:02:00Z"


def test_missing_end_stays_null():
    assert rental().model_dump(mode="json")["ended_at"] is None


def test_aware_timestamps_keep_their_offset():
    kyiv = timezone(timedelta(hours=2))
    started = datetime(2026, 11, 20, 11, 15, tzinfo=kyiv)
    body = rental(started_at=started).model_dump(mode="json")
    assert body["started_at"] == "2026-11-20T11:15:00+02:00"
    assert datetime.fromisoformat(body["started_at"]).astimezone(UTC).hour == 9

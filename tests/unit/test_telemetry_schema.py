from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from fleet_management.telemetry.schemas import TelemetryMessage

VALID = {
    "vehicle_id": 1,
    "recorded_at": "2026-09-15T10:00:00Z",
    "latitude": 49.8397,
    "longitude": 24.0297,
    "fuel_level": 72.5,
    "is_locked": True,
}


def test_valid_message_is_parsed():
    message = TelemetryMessage.model_validate(VALID)

    assert message.vehicle_id == 1
    assert message.recorded_at == datetime(2026, 9, 15, 10, 0, tzinfo=UTC)
    assert message.is_locked is True


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("vehicle_id", 0),
        ("recorded_at", "2026-09-15T10:00:00"),
        ("latitude", 90.1),
        ("longitude", -180.1),
        ("fuel_level", -1),
        ("fuel_level", 100.1),
        ("is_locked", "maybe"),
    ],
)
def test_invalid_field_is_rejected(field, value):
    with pytest.raises(ValidationError):
        TelemetryMessage.model_validate({**VALID, field: value})


def test_unknown_field_is_rejected():
    with pytest.raises(ValidationError):
        TelemetryMessage.model_validate({**VALID, "speed": 90})


def test_missing_field_is_rejected():
    payload = {key: value for key, value in VALID.items() if key != "fuel_level"}

    with pytest.raises(ValidationError):
        TelemetryMessage.model_validate(payload)

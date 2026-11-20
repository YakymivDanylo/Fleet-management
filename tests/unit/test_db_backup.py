"""Lab 12: restore drill verdict (scripts/db_backup.py, runbook RB-001)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import db_backup  # noqa: E402

BEFORE = {"stations": 5, "rentals": 17, "telemetry_readings": 100}
AFTER = {"stations": 5, "rentals": 17, "telemetry_readings": 110}


def test_identical_restore_passes():
    assert db_backup.compare(dict(AFTER), BEFORE, AFTER) == []


def test_append_only_table_may_be_between_before_and_after():
    restored = {**BEFORE, "telemetry_readings": 105}
    assert db_backup.compare(restored, BEFORE, AFTER) == []


def test_append_only_table_outside_range_fails():
    restored = {**BEFORE, "telemetry_readings": 99}
    assert db_backup.compare(restored, BEFORE, AFTER) == [
        "telemetry_readings: restored 99 not within source [100, 110]"
    ]


def test_regular_table_must_match_exactly():
    restored = {**AFTER, "rentals": 16}
    assert db_backup.compare(restored, BEFORE, AFTER) == ["rentals: restored 16 != source 17"]


def test_missing_table_fails():
    restored = {k: v for k, v in AFTER.items() if k != "stations"}
    problems = db_backup.compare(restored, BEFORE, AFTER)
    assert problems == ["stations: missing on one side (restored=None, source=5)"]

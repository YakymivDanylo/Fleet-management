"""Lab 12, CAPA-2: verdict of the telemetry pipeline check (alert ALR-05)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import telemetry_check as tc  # noqa: E402


def test_healthy_pipeline_passes():
    assert tc.evaluate(ready=0, lag_s=2, max_ready=500, max_lag=60) == []


def test_stale_telemetry_alerts_even_with_empty_queue():
    assert tc.evaluate(ready=0, lag_s=95, max_ready=500, max_lag=60) == [
        "newest reading is 95 s old > 60 s (SLI-3)"
    ]


def test_backlog_alerts():
    assert tc.evaluate(ready=501, lag_s=1, max_ready=500, max_lag=60) == [
        "queue backlog 501 > 500 ready messages"
    ]


def test_unknown_state_is_an_alert_not_a_pass():
    problems = tc.evaluate(ready=None, lag_s=None, max_ready=500, max_lag=60)
    assert len(problems) == 2

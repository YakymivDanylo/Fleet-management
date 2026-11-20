"""Lab 12, CAPA-2: alert ALR-05 TelemetryQueueBacklog — health of the telemetry pipeline.

    python scripts/telemetry_check.py [--project fleet_sandbox --env-file .env.sandbox]
                                      [--max-ready 500 --max-lag 60]

Exit 1 (alert) when the RabbitMQ queue ``telemetry`` holds more than ``--max-ready`` ready messages
or the newest reading in PostgreSQL is older than ``--max-lag`` seconds (SLI-3 telemetry freshness,
docs/slo.yaml). Meant for cron / a monitoring agent every minute; runbook: docs/runbooks/RB-002.md.
"""

import argparse
import sys

from incident_probe import ROOT, db_lag, env_values, queue_depth


def evaluate(ready: int | None, lag_s: int | None, max_ready: int, max_lag: int) -> list[str]:
    problems = []
    if ready is None:
        problems.append("queue depth unknown (RabbitMQ management API unreachable)")
    elif ready > max_ready:
        problems.append(f"queue backlog {ready} > {max_ready} ready messages")
    if lag_s is None or lag_s < 0:
        problems.append("telemetry freshness unknown (no readings or DB unreachable)")
    elif lag_s > max_lag:
        problems.append(f"newest reading is {lag_s} s old > {max_lag} s (SLI-3)")
    return problems


def _int(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project", default="fleet_sandbox")
    parser.add_argument("--env-file", default=".env.sandbox")
    parser.add_argument("--max-ready", type=int, default=500)
    parser.add_argument("--max-lag", type=int, default=60)
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    env = env_values(ROOT / args.env_file)
    base = ["docker", "compose", "-p", args.project, "--env-file", args.env_file]
    queue = queue_depth(
        env["RABBITMQ_DEFAULT_USER"],
        env["RABBITMQ_DEFAULT_PASS"],
        env.get("RABBITMQ_MGMT_PORT", "15672"),
    ).split()
    rows_and_lag = db_lag(base).split()
    ready = _int(queue[0])
    lag_s = _int(rows_and_lag[-1]) if rows_and_lag else None
    problems = evaluate(ready, lag_s, args.max_ready, args.max_lag)
    print(f"queue_ready={queue[0]} newest_reading_lag_s={lag_s}")
    for problem in problems:
        print(f"ALERT TelemetryQueueBacklog: {problem}")
    print(f"telemetry pipeline: {'FAIL' if problems else 'PASS'}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())

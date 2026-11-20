"""Lab 12: incident probe — one UTC-stamped line per sample for the telemetry pipeline.

    python scripts/incident_probe.py --seconds 600 --every 15 > docs/lab12/evidence/probe.log

Columns (all measured, nothing estimated):

* ``queue_ready`` / ``queue_unacked`` — RabbitMQ management API, queue ``telemetry``;
* ``db_rows`` / ``db_lag_s`` — PostgreSQL: count of ``telemetry_readings`` and seconds since the
  newest ``recorded_at`` (SLI-3 telemetry freshness, threshold 60 s);
* ``api`` — ``GET /vehicles/1/state``: HTTP status, ``source``, ``degraded`` and the age of the
  returned reading;
* ``redis`` / ``worker`` — container state from ``docker compose ps``.

Credentials come from the compose env file; the script only reads.
"""

import argparse
import base64
import json
import subprocess
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAG_SQL = (
    "SELECT count(*), coalesce(extract(epoch FROM now() - max(recorded_at)), -1)::int "
    "FROM telemetry_readings"
)


def env_values(env_file: Path) -> dict[str, str]:
    values = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def queue_depth(user: str, password: str, port: str) -> str:
    url = f"http://localhost:{port}/api/queues/%2F/telemetry"
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    request = urllib.request.Request(url, headers={"Authorization": f"Basic {token}"})
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            data = json.load(response)
        return f"{data.get('messages_ready', 0)} {data.get('messages_unacknowledged', 0)}"
    except OSError as exc:
        return f"? ? ({exc.__class__.__name__})"


def compose(base: list[str], *args: str) -> str:
    result = subprocess.run([*base, *args], capture_output=True, text=True, timeout=20)
    return result.stdout.strip()


def db_lag(base: list[str]) -> str:
    out = compose(
        base,
        "exec",
        "-T",
        "db",
        "sh",
        "-c",
        f'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -F " " -c "{LAG_SQL}"',
    )
    return out or "? ?"


def api_state(api: str) -> str:
    try:
        with urllib.request.urlopen(f"{api}/vehicles/1/state", timeout=5) as response:
            body = json.load(response)
            status = response.status
    except urllib.error.HTTPError as exc:
        return f"{exc.code} - - -"
    except OSError as exc:
        return f"ERR({exc.__class__.__name__}) - - -"
    recorded = datetime.fromisoformat(body["recorded_at"])
    age = int((datetime.now(UTC) - recorded).total_seconds())
    return f"{status} {body['source']} degraded={str(body['degraded']).lower()} age={age}s"


def states(base: list[str]) -> str:
    rows = compose(base, "ps", "-a", "--format", "{{.Service}}={{.State}}").splitlines()
    wanted = dict(row.split("=", 1) for row in rows if "=" in row)
    return f"redis={wanted.get('redis', 'absent')} worker={wanted.get('worker', 'absent')}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project", default="fleet_sandbox")
    parser.add_argument("--env-file", default=".env.sandbox")
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--seconds", type=int, default=600)
    parser.add_argument("--every", type=int, default=15)
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    env = env_values(ROOT / args.env_file)
    base = ["docker", "compose", "-p", args.project, "--env-file", args.env_file]
    user, password = env["RABBITMQ_DEFAULT_USER"], env["RABBITMQ_DEFAULT_PASS"]
    port = env.get("RABBITMQ_MGMT_PORT", "15672")
    print(
        "utc queue_ready queue_unacked db_rows db_lag_s api_status source degraded age containers"
    )
    deadline = time.monotonic() + args.seconds
    while time.monotonic() < deadline:
        stamp = datetime.now(UTC).strftime("%H:%M:%S")
        line = " ".join(
            [
                stamp,
                queue_depth(user, password, port),
                db_lag(base),
                api_state(args.api),
                states(base),
            ]
        )
        print(line)
        time.sleep(args.every)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Prometheus exporter for container CPU/RAM, read from `docker stats` (Lab 8).

cAdvisor cannot identify containers on Docker Desktop (containerd image store), so the
host-side exporter publishes what `docker stats` reports, on http://0.0.0.0:9101/metrics:

    python scripts/docker_exporter.py --prefix fleet_sandbox-

cpu_percent is relative to one core (as in docker stats); the cpu limit and the memory
limit are exported too, so dashboards can show utilisation against the container quota.
"""

import argparse
import json
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UNITS = {
    "B": 1,
    "KiB": 1024,
    "MiB": 1024**2,
    "GiB": 1024**3,
    "kB": 1000,
    "MB": 1000**2,
    "GB": 1000**3,
}
CPU_LIMITS = {"api1": 2.0, "api2": 2.0, "api3": 2.0, "k6": 2.0}  # compose `deploy.resources`
_lock = threading.Lock()
_snapshot: list[dict] = []


def to_bytes(value: str) -> float:
    value = value.strip()
    for unit in sorted(UNITS, key=len, reverse=True):
        if value.endswith(unit):
            return float(value[: -len(unit)]) * UNITS[unit]
    return float(value)


def collect(prefix: str) -> list[dict]:
    output = subprocess.run(
        ["docker", "stats", "--no-stream", "--format", "{{json .}}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    rows = []
    for line in output.splitlines():
        stat = json.loads(line)
        if not stat["Name"].startswith(prefix):
            continue
        used, _, limit = stat["MemUsage"].partition("/")
        service = stat["Name"].removeprefix(prefix).rsplit("-", 1)[0]
        rows.append(
            {
                "service": service,
                "cpu": float(stat["CPUPerc"].rstrip("%")),
                "mem": to_bytes(used),
                "mem_limit": to_bytes(limit),
                "pids": int(stat["PIDs"]),
            }
        )
    return rows


def poll(prefix: str) -> None:
    global _snapshot
    while True:
        try:
            rows = collect(prefix)
            with _lock:
                _snapshot = rows
        except Exception as error:  # keep serving the last snapshot
            print("poll failed:", error, flush=True)
        time.sleep(1)


def render() -> str:
    lines = [
        "# TYPE container_cpu_percent gauge",
        "# TYPE container_memory_bytes gauge",
        "# TYPE container_memory_limit_bytes gauge",
        "# TYPE container_cpu_limit_cores gauge",
        "# TYPE container_pids gauge",
    ]
    with _lock:
        rows = list(_snapshot)
    for row in rows:
        label = f'{{service="{row["service"]}"}}'
        lines.append(f"container_cpu_percent{label} {row['cpu']}")
        lines.append(f"container_memory_bytes{label} {row['mem']}")
        lines.append(f"container_memory_limit_bytes{label} {row['mem_limit']}")
        lines.append(f"container_pids{label} {row['pids']}")
        if row["service"] in CPU_LIMITS:
            lines.append(f"container_cpu_limit_cores{label} {CPU_LIMITS[row['service']]}")
    return "\n".join(lines) + "\n"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = render().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--prefix", default="fleet_sandbox-", help="compose project name + '-'")
    parser.add_argument("--port", type=int, default=9101)
    args = parser.parse_args()
    threading.Thread(target=poll, args=(args.prefix,), daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", args.port), Handler).serve_forever()  # noqa: S104


if __name__ == "__main__":
    main()

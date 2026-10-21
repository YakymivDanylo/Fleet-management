"""Sample CPU and RAM of the compose containers into a CSV while a load test runs.

    python scripts/docker_stats.py --out loadtest/results/lab4/resources.csv --duration 480

Each `docker stats --no-stream` call takes about two seconds, which is also the sample step.
"""

import argparse
import csv
import json
import subprocess
import time
from datetime import UTC, datetime

UNITS = {"B": 1, "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3, "kB": 1000, "MB": 1000**2}


def to_mib(value: str) -> float:
    for unit in sorted(UNITS, key=len, reverse=True):
        if value.endswith(unit):
            return float(value[: -len(unit)]) * UNITS[unit] / 1024**2
    return float(value) / 1024**2


def sample(prefix: str) -> list[dict]:
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
        rows.append(
            {
                "container": stat["Name"].removeprefix(prefix).rsplit("-", 1)[0],
                "cpu_percent": float(stat["CPUPerc"].rstrip("%")),
                "mem_mib": round(to_mib(stat["MemUsage"].split("/")[0].strip()), 1),
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True)
    parser.add_argument("--duration", type=float, default=480, help="seconds to sample")
    parser.add_argument("--prefix", default="fleet_lab5-", help="compose project name + '-'")
    args = parser.parse_args()

    deadline = time.monotonic() + args.duration
    with open(args.out, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, ["timestamp", "container", "cpu_percent", "mem_mib"])
        writer.writeheader()
        while time.monotonic() < deadline:
            now = datetime.now(UTC).timestamp()
            for row in sample(args.prefix):
                writer.writerow({"timestamp": round(now, 1), **row})
            file.flush()


if __name__ == "__main__":
    main()

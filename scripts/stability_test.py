"""Stability crash test of the p95 latency gate (Lab 5, task 3, experiment 2).

The same build and the same k6 profile (loadtest/vehicle_state.js, PROFILE=peak, 300 rps) run under
different *infrastructure* conditions while the code stays byte-identical:

    isolated-1/2   api pinned to --cpus=2, nothing else running         -> expected PASS
    noise-gzip     + N containers doing `gzip -9` "log compression"      -> noisy neighbour
    throttled      api squeezed to --cpus=0.25 via `docker update`       -> runner CPU quota

For each run it stores the k6 summary, the k6 exit code (99 = thresholds crossed) and
`docker stats` samples of the api container, then writes a Markdown table and an SVG chart.

    API_PORT=8001 python scripts/stability_test.py --project fleet_qe5
"""

import argparse
import json
import subprocess
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "lab5-quality-governance" / "outputs" / "stability"
K6_RESULTS = ROOT / "loadtest" / "results" / "lab5"
NOISE_IMAGE = "alpine:3.22"
API_CPUS = "2"
THROTTLED_CPUS = "0.25"


def _docker(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=check)


def _percent(value: str) -> float:
    return float(value.rstrip("%"))


def _mib(usage: str) -> float:
    used = usage.split("/")[0].strip()
    for unit, factor in (("GiB", 1024), ("MiB", 1), ("KiB", 1 / 1024)):
        if used.endswith(unit):
            return float(used[: -len(unit)]) * factor
    return float(used.rstrip("B")) / 1024 / 1024


class StatsSampler(threading.Thread):
    def __init__(self, container: str):
        super().__init__(daemon=True)
        self.container = container
        self.samples: list[tuple[float, float]] = []
        self._stop = threading.Event()

    def run(self) -> None:
        while not self._stop.is_set():
            result = _docker(
                "stats", "--no-stream", "--format", "{{json .}}", self.container, check=False
            )
            if result.returncode == 0 and result.stdout.strip():
                row = json.loads(result.stdout)
                self.samples.append((_percent(row["CPUPerc"]), _mib(row["MemUsage"])))

    def stop(self) -> None:
        self._stop.set()
        self.join()


def _start_noise(project: str, workers: int) -> list[str]:
    names = [f"{project}-noise-{i}" for i in range(workers)]
    for name in names:
        _docker(
            "run",
            "-d",
            "--rm",
            "--name",
            name,
            NOISE_IMAGE,
            "sh",
            "-c",
            "while :; do head -c 268435456 /dev/urandom | gzip -9 > /dev/null; done",
        )
    return names


def _stop_noise(names: list[str]) -> None:
    if names:
        _docker("rm", "-f", *names, check=False)


def _run_k6(project: str, name: str, steady: str, peak_rps: int) -> int:
    K6_RESULTS.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-p",
            project,
            "--profile",
            "loadtest",
            "run",
            "--rm",
            "--no-deps",
            "-e",
            "PROFILE=peak",
            "-e",
            f"PEAK_RPS={peak_rps}",
            "-e",
            f"STEADY={steady}",
            "k6",
            "run",
            "--quiet",
            "--summary-export",
            f"/scripts/results/lab5/{name}.json",
            "/scripts/vehicle_state.js",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode


def _summarize(name: str, exit_code: int, samples: list[tuple[float, float]]) -> dict:
    metrics = json.loads((K6_RESULTS / f"{name}.json").read_text(encoding="utf-8"))["metrics"]
    duration = metrics["http_req_duration"]
    cpu = sorted(s[0] for s in samples) or [0.0]
    return {
        "scenario": name,
        "requests": metrics["http_reqs"]["count"],
        "avg_ms": round(duration["avg"], 2),
        "med_ms": round(duration["med"], 2),
        "p95_ms": round(duration["p(95)"], 2),
        "p99_ms": round(duration["p(99)"], 2),
        "max_ms": round(duration["max"], 2),
        "error_rate": round(metrics["http_req_failed"]["value"], 4),
        "api_cpu_median_pct": round(cpu[len(cpu) // 2], 1),
        "api_ram_max_mib": round(max((s[1] for s in samples), default=0.0), 1),
        "k6_exit": exit_code,
        "gate": "PASS" if exit_code == 0 else "FAIL",
    }


def _markdown(rows: list[dict]) -> str:
    header = (
        "| Scenario | Requests | avg, ms | median, ms | p95, ms | p99, ms | max, ms | "
        "Error rate | api CPU median, % | api RAM max, MiB | Gate (p95<100 AND err<1%) |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|\n"
    )
    lines = [
        f"| {r['scenario']} | {r['requests']} | {r['avg_ms']} | {r['med_ms']} | {r['p95_ms']} | "
        f"{r['p99_ms']} | {r['max_ms']} | {r['error_rate']:.2%} | {r['api_cpu_median_pct']} | "
        f"{r['api_ram_max_mib']} | **{r['gate']}** |"
        for r in rows
    ]
    return header + "\n".join(lines) + "\n"


def _svg(rows: list[dict], threshold: float = 100.0) -> str:
    width, height, left, bottom, bar = 640, 300, 60, 40, 70
    top_value = max(max(r["p95_ms"] for r in rows), threshold) * 1.15
    plot_h = height - bottom - 30

    def y(value: float) -> float:
        return height - bottom - value / top_value * plot_h

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        'font-family="sans-serif" font-size="12">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{width / 2}" y="18" text-anchor="middle" font-size="14">'
        "p95 GET /vehicles/{id}/state, ms (same code, different infrastructure)</text>",
        f'<line x1="{left}" y1="{y(0)}" x2="{width - 10}" y2="{y(0)}" stroke="black"/>',
    ]
    step = (width - left - 20) / len(rows)
    for i, r in enumerate(rows):
        x = left + i * step + (step - bar) / 2
        color = "#2e7d32" if r["gate"] == "PASS" else "#c62828"
        parts += [
            f'<rect x="{x}" y="{y(r["p95_ms"])}" width="{bar}" '
            f'height="{y(0) - y(r["p95_ms"])}" fill="{color}"/>',
            f'<text x="{x + bar / 2}" y="{y(r["p95_ms"]) - 4}" text-anchor="middle">'
            f"{r['p95_ms']} ({r['gate']})</text>",
            f'<text x="{x + bar / 2}" y="{height - bottom + 16}" text-anchor="middle">'
            f"{r['scenario']}</text>",
        ]
    parts += [
        f'<line x1="{left}" y1="{y(threshold)}" x2="{width - 10}" y2="{y(threshold)}" '
        'stroke="#ef6c00" stroke-dasharray="6 4"/>',
        f'<text x="{left + 4}" y="{y(threshold) - 4}" fill="#ef6c00">'
        f"Quality Gate: p95 &lt; {threshold:.0f} ms</text>",
        "</svg>",
    ]
    return "\n".join(parts) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project", default="fleet_qe5")
    parser.add_argument("--steady", default="40s")
    parser.add_argument("--peak-rps", type=int, default=300)
    parser.add_argument("--noise-workers", type=int, default=12)
    args = parser.parse_args()

    api = f"{args.project}-api-1"
    scenarios = [
        ("isolated-1", API_CPUS, 0),
        ("isolated-2", API_CPUS, 0),
        ("noise-gzip", API_CPUS, args.noise_workers),
        ("throttled", THROTTLED_CPUS, 0),
    ]
    _docker("pull", "-q", NOISE_IMAGE)
    rows = []
    for name, cpus, workers in scenarios:
        print(f"[{name}] api --cpus={cpus}, noise workers={workers}", flush=True)
        _docker("update", "--cpus", cpus, api)
        noise = _start_noise(args.project, workers)
        try:
            time.sleep(5 if workers else 1)
            sampler = StatsSampler(api)
            sampler.start()
            exit_code = _run_k6(args.project, name, args.steady, args.peak_rps)
            sampler.stop()
        finally:
            _stop_noise(noise)
            _docker("update", "--cpus", API_CPUS, api)
        rows.append(_summarize(name, exit_code, sampler.samples))
        print(
            f"    p95={rows[-1]['p95_ms']} ms err={rows[-1]['error_rate']:.2%} "
            f"gate={rows[-1]['gate']}",
            flush=True,
        )
        time.sleep(10)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "stability.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    (OUT / "stability.md").write_text(_markdown(rows), encoding="utf-8")
    (OUT / "p95.svg").write_text(_svg(rows), encoding="utf-8")
    print(_markdown(rows))


if __name__ == "__main__":
    main()

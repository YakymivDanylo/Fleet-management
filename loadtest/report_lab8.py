"""Lab 8 report: final metrics (k6 summary) + time series from Prometheus -> report.md + SVG charts.

    python loadtest/report_lab8.py --run soak --start 2026-11-08T08:00:00Z \
        --end 2026-11-08T09:00:00Z --out loadtest/results/lab8/soak

Needs the monitoring stack (Prometheus on localhost:9090) and <out>_summary.json written by
soak.js. Standard library only; charts reuse loadtest/report.py::svg_chart.
"""

import argparse
import json
import statistics
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from report import svg_chart

PROM = "http://localhost:9090/api/v1/query_range"
API = "api."
OTHER = "db|redis|rabbitmq|nginx|worker"


def ts(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def query(expr: str, start: float, end: float, step: int) -> dict[str, list[tuple[float, float]]]:
    url = (
        PROM
        + "?"
        + urllib.parse.urlencode({"query": expr, "start": start, "end": end, "step": step})
    )
    with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310 (local Prometheus)
        data = json.load(response)["data"]["result"]
    series = {}
    for item in data:
        metric = item["metric"]
        label = metric.get("service") or metric.get("instance") or "value"
        series[label] = [(float(t) - start, float(v)) for t, v in item["values"] if v != "NaN"]
    return series


def minutes(points):
    return [(x / 60, y) for x, y in points]


def slope_per_hour(points) -> float:
    """Least-squares slope of y(t) in units per hour (leak indicator)."""
    if len(points) < 3:
        return 0.0
    xs = [x / 3600 for x, _ in points]
    ys = [y for _, y in points]
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    denom = sum((x - mx) ** 2 for x in xs) or 1
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / denom


def window_mean(points, lo, hi) -> float:
    values = [y for x, y in points if lo <= x <= hi]
    return statistics.fmean(values) if values else 0.0


def table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def stats_row(name, series, digits=0, limit=None, slope_digits=1):
    values = [y for _, y in series]
    vs_limit = f"{max(values) / limit * 100:.0f} % of {limit:.0f}" if limit else ""
    return (
        name,
        f"{statistics.fmean(values):.{digits}f}",
        f"{max(values):.{digits}f}",
        vs_limit,
        f"{slope_per_hour(series):+.{slope_digits}f}/h",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--out", required=True, type=Path, help="prefix, e.g. results/lab8/soak")
    parser.add_argument("--step", type=int, default=15)
    args = parser.parse_args()
    start, end = ts(args.start), ts(args.end)
    out = str(args.out)
    run = f'run="{args.run}"'

    def q(expr):
        return query(expr, start, end, args.step)

    load = f'{run},phase="load"'
    rps = q(f"sum(rate(k6_http_reqs_total{{{load}}}[30s]))")["value"]
    server_rps = q("sum(rate(http_requests_total[30s]))")["value"]
    # Windowed (1 min) server-side latency from the API histogram, all endpoints together:
    # k6's own p95/p99 are cumulative since the start of the test and would hide a slow drift.
    hist = "http_request_duration_seconds"
    lat = {"avg": q(f"1000*sum(rate({hist}_sum[1m]))/sum(rate({hist}_count[1m]))")["value"]}
    for n, quantile in (("p95", 0.95), ("p99", 0.99)):
        lat[n] = q(f"1000*histogram_quantile({quantile}, sum by (le)(rate({hist}_bucket[1m])))")[
            "value"
        ]
    lat["max"] = q(f"1000*max(k6_http_req_duration_max{{{load}}})")["value"]
    err = q(
        f'100*(sum(rate(k6_http_reqs_total{{{load},status!="200"}}[30s])) or vector(0))/'
        f"sum(rate(k6_http_reqs_total{{{load}}}[30s]))"
    )["value"]
    cpu_api = q(f'container_cpu_percent{{service=~"{API}"}} / 2')  # % of the 2-CPU quota
    ram_api = q(f'container_memory_bytes{{service=~"{API}"}}/1048576')
    ram_other = q(f'container_memory_bytes{{service=~"{OTHER}"}}/1048576')
    cpu_other = q(f'container_cpu_percent{{service=~"{OTHER}"}} / 8')  # % of the 8-core host
    rss = q('process_resident_memory_bytes{job="api"}/1048576')
    fds = q('process_open_fds{job="api"}')

    def chart(name, title, series, label, right=None):
        svg_chart(
            title,
            "minutes",
            [(k, minutes(v)) for k, v in series],
            (label, label),
            Path(f"{out}_{name}.svg"),
            right=right,
        )

    chart("rps", "Throughput (requests/s)", [("k6", rps), ("servers", server_rps)], "req/s")
    chart(
        "latency",
        "Latency per 1-min window, server side (ms); k6 max on right axis",
        [(n, p) for n, p in lat.items() if n != "max"],
        "ms",
        right=[("max", minutes(lat["max"]))],
    )
    chart("errors", "Error rate (%)", [("failed requests", err)], "%")
    chart("cpu", "CPU of API replicas (% of 2-CPU quota)", sorted(cpu_api.items()), "%")
    chart("ram_api", "RAM of API replicas (limit 512 MiB)", sorted(ram_api.items()), "MiB")
    chart("ram_other", "RAM of the other services", sorted(ram_other.items()), "MiB")
    chart("cpu_other", "CPU of the other services (% of host)", sorted(cpu_other.items()), "%")

    duration = (end - start) / 60
    edge = max(duration / 6, 1)
    drift = [
        (
            f"{n}, ms",
            f"{window_mean(minutes(p), 2, 2 + edge):.0f}",
            f"{window_mean(minutes(p), duration - edge, duration):.0f}",
        )
        for n, p in lat.items()
        if n in ("avg", "p95", "p99")
    ]
    rows = [stats_row(f"{k} RAM, MiB", v, limit=512) for k, v in sorted(ram_api.items())]
    rows += [stats_row(f"{k} CPU, % of quota", v) for k, v in sorted(cpu_api.items())]
    rows += [stats_row(f"{k} process RSS, MiB", v) for k, v in sorted(rss.items())]
    rows += [stats_row(f"{k} open FDs", v, slope_digits=2) for k, v in sorted(fds.items())]
    rows += [stats_row(f"{k} RAM, MiB", v) for k, v in sorted(ram_other.items())]
    rows += [
        stats_row(f"{k} CPU, % of host", v, digits=1, slope_digits=2)
        for k, v in sorted(cpu_other.items())
    ]

    parts = [
        "## Resource usage (Prometheus, 15-s samples)\n",
        table(["Metric", "Mean", "Max", "Max vs limit", "Trend"], rows),
        f"\n## Latency drift: minutes 2-{2 + edge:.0f} vs the last {edge:.0f} minutes\n",
        table(["Metric", "Start", "End"], drift),
    ]
    summary_path = Path(f"{out}_summary.json")
    if summary_path.exists():
        m = json.loads(summary_path.read_text(encoding="utf-8"))["metrics"]
        d = m["http_req_duration{phase:load}"]["values"]
        reqs, failed = m["http_reqs"]["values"], m["http_req_failed{phase:load}"]["values"]
        parts.insert(
            0,
            "## Final metrics (k6, load phase)\n\n"
            + table(
                ["Metric", "Value"],
                [
                    ("Requests (incl. setup)", int(reqs["count"])),
                    ("RPS (mean)", f"{reqs['rate']:.1f}"),
                    ("Latency avg, ms", f"{d['avg']:.1f}"),
                    ("Latency min, ms", f"{d['min']:.2f}"),
                    ("Latency median, ms", f"{d['med']:.1f}"),
                    ("Latency max, ms", f"{d['max']:.1f}"),
                    ("Latency p90, ms", f"{d['p(90)']:.1f}"),
                    ("Latency p95, ms", f"{d['p(95)']:.1f}"),
                    ("Latency p99, ms", f"{d['p(99)']:.1f}"),
                    ("Failed requests", int(failed["passes"])),
                    ("Error rate, %", f"{failed['rate'] * 100:.4f}"),
                    ("Iterations (sessions)", int(m["iterations"]["values"]["count"])),
                    ("Peak VUs", int(m["vus_max"]["values"]["max"])),
                ],
            )
            + "\n",
        )
    report = Path(f"{out}_report.md")
    report.write_text("\n".join(parts) + "\n", encoding="utf-8")
    print(report.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()

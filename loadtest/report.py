"""Turn a k6 CSV run (and optional docker stats CSV) into a metrics summary and SVG charts.

    python loadtest/report.py --k6 loadtest/results/lab4/k6.csv \
        --resources loadtest/results/lab4/resources.csv --out loadtest/results/lab4

Writes summary.md (tables for the report) and latency.svg, throughput.svg, resources.svg.
Standard library only, so it runs with any Python 3.11+ without installing a plotting stack.
"""

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path

BUCKET_SECONDS = 5
COLORS = ["#2563eb", "#dc2626", "#16a34a", "#9333ea", "#ea580c"]
COLUMNS = ["Requests", "RPS", "Avg, ms", "Min, ms", "Max, ms", "p95, ms", "Errors, %"]


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(math.ceil(p / 100 * len(ordered)) - 1, 0)
    return ordered[rank]


def load_k6(path: Path) -> tuple[list[dict], dict[int, float]]:
    durations, failures = [], []
    vus: dict[int, float] = {}
    with path.open(encoding="utf-8") as file:
        for row in csv.DictReader(file):
            metric, ts = row["metric_name"], int(float(row["timestamp"]))
            if metric == "vus":
                vus[ts] = float(row["metric_value"])
            elif row["name"] == "setup":
                continue
            elif metric == "http_req_duration":
                durations.append({"ts": ts, "name": row["name"], "ms": float(row["metric_value"])})
            elif metric == "http_req_failed":
                failures.append(int(float(row["metric_value"])))
    # k6 writes all metrics of one request together, so the n-th duration and the n-th
    # failure flag belong to the same request.
    if len(durations) != len(failures):
        raise ValueError(f"{len(durations)} durations vs {len(failures)} failure flags")
    for row, failed in zip(durations, failures, strict=True):
        row["failed"] = failed
    return durations, vus


def summarize(rows: list[dict], seconds: float) -> dict:
    durations = [r["ms"] for r in rows]
    return {
        "requests": len(rows),
        "rps": len(rows) / seconds if seconds else 0,
        "avg": sum(durations) / len(durations) if durations else 0,
        "min": min(durations, default=0),
        "max": max(durations, default=0),
        "p95": percentile(durations, 95),
        "errors": sum(r["failed"] for r in rows) / len(rows) * 100 if rows else 0,
    }


def buckets(rows: list[dict], vus: dict[int, float], start: int) -> list[dict]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["ts"] - start) // BUCKET_SECONDS].append(row)
    result = []
    for index in range(max(grouped, default=-1) + 1):
        items = grouped.get(index, [])
        t0 = start + index * BUCKET_SECONDS
        window_vus = [vus[t] for t in range(t0, t0 + BUCKET_SECONDS) if t in vus]
        stats = summarize(items, BUCKET_SECONDS)
        stats["t"] = index * BUCKET_SECONDS
        stats["vus"] = max(window_vus, default=0)
        stats["errors_per_s"] = sum(r["failed"] for r in items) / BUCKET_SECONDS
        result.append(stats)
    return result


def svg_chart(title, x_label, series, y_label, path, right=None):
    """series / right: list of (label, [(x, y)]); `right` is drawn against a second axis."""
    width, height, left, top, bottom, margin_right = 900, 380, 70, 40, 50, 70
    plot_w, plot_h = width - left - margin_right, height - top - bottom
    all_x = [x for _, points in series + (right or []) for x, _ in points] or [0, 1]
    x_max = max(all_x) or 1

    def axis_max(groups):
        top_value = max((y for _, points in groups for _, y in points), default=1) or 1
        return top_value * 1.1

    y_max, r_max = axis_max(series), axis_max(right or [])

    def sx(x):
        return left + x / x_max * plot_w

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'font-family="sans-serif" font-size="12">',
        f'<rect width="{width}" height="{height}" fill="white"/>',
        f'<text x="{width / 2}" y="22" text-anchor="middle" font-size="15" '
        f'font-weight="bold">{title}</text>',
    ]
    for i in range(6):
        y = top + plot_h - i * plot_h / 5
        parts.append(f'<line x1="{left}" y1="{y}" x2="{left + plot_w}" y2="{y}" stroke="#e5e7eb"/>')
        parts.append(
            f'<text x="{left - 6}" y="{y + 4}" text-anchor="end">{y_max * i / 5:.0f}</text>'
        )
        if right:
            parts.append(
                f'<text x="{left + plot_w + 6}" y="{y + 4}" fill="#6b7280">'
                f"{r_max * i / 5:.0f}</text>"
            )
    for i in range(7):
        x = left + i * plot_w / 6
        parts.append(
            f'<text x="{x}" y="{top + plot_h + 18}" text-anchor="middle">{x_max * i / 6:.0f}</text>'
        )
    parts.append(
        f'<text x="{left + plot_w / 2}" y="{height - 10}" text-anchor="middle">{x_label}</text>'
    )
    parts.append(
        f'<text transform="translate(16 {top + plot_h / 2}) rotate(-90)" '
        f'text-anchor="middle">{y_label[0]}</text>'
    )
    if right:
        parts.append(
            f'<text transform="translate({width - 14} {top + plot_h / 2}) rotate(90)" '
            f'text-anchor="middle" fill="#6b7280">{y_label[1]}</text>'
        )

    def polyline(points, scale, color, dashed=False):
        coords = " ".join(f"{sx(x):.1f},{top + plot_h - y / scale * plot_h:.1f}" for x, y in points)
        dash = ' stroke-dasharray="6 4"' if dashed else ""
        return f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="2"{dash}/>'

    legend = []
    for i, (label, points) in enumerate(series):
        parts.append(polyline(points, y_max, COLORS[i % len(COLORS)]))
        legend.append((label, COLORS[i % len(COLORS)], False))
    for label, points in right or []:
        parts.append(polyline(points, r_max, "#6b7280", dashed=True))
        legend.append((label, "#6b7280", True))
    for i, (label, color, dashed) in enumerate(legend):
        x = left + 10 + i * 170
        dash = ' stroke-dasharray="6 4"' if dashed else ""
        parts.append(
            f'<line x1="{x}" y1="{top + 8}" x2="{x + 24}" y2="{top + 8}" stroke="{color}" '
            f'stroke-width="2"{dash}/><text x="{x + 30}" y="{top + 12}">{label}</text>'
        )
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def load_resources(path: Path) -> dict[str, list[tuple[float, float, float]]]:
    series = defaultdict(list)
    with path.open(encoding="utf-8") as file:
        for row in csv.DictReader(file):
            series[row["container"]].append(
                (float(row["timestamp"]), float(row["cpu_percent"]), float(row["mem_mib"]))
            )
    return series


def table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return "\n".join(lines)


def fmt(stats):
    return [
        stats["requests"],
        f"{stats['rps']:.1f}",
        f"{stats['avg']:.1f}",
        f"{stats['min']:.1f}",
        f"{stats['max']:.1f}",
        f"{stats['p95']:.1f}",
        f"{stats['errors']:.2f}",
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--k6", required=True, type=Path)
    parser.add_argument("--resources", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    rows, vus = load_k6(args.k6)
    start = min(r["ts"] for r in rows)
    end = max(r["ts"] for r in rows)
    seconds = end - start + 1
    timeline = buckets(rows, vus, start)

    headers = ["Endpoint", *COLUMNS]
    per_endpoint = defaultdict(list)
    for row in rows:
        per_endpoint[row["name"]].append(row)
    lines = ["## Overall", "", table(headers, [["**all**", *fmt(summarize(rows, seconds))]])]
    lines += ["", "## Per endpoint", ""]
    lines.append(
        table(headers, [[n, *fmt(summarize(r, seconds))] for n, r in sorted(per_endpoint.items())])
    )

    # One row per load step: the windows where the VU count was at a plateau.
    steps = defaultdict(list)
    for row in rows:
        level = vus.get(row["ts"])
        if level is not None:
            steps[int(level)].append(row)
    plateau = {}
    for level, items in steps.items():
        span = len({r["ts"] for r in items})
        if span >= 20:
            plateau[level] = summarize(items, span)
    lines += ["", "## Per load step (plateaus of >= 20 s)", ""]
    lines.append(table(["VUs", *COLUMNS], [[lvl, *fmt(s)] for lvl, s in sorted(plateau.items())]))

    peak_rps = max(timeline, key=lambda b: b["rps"])
    lines += [
        "",
        f"Duration: {seconds} s; peak RPS ({BUCKET_SECONDS}-s window): "
        f"{peak_rps['rps']:.1f} at t={peak_rps['t']} s ({peak_rps['vus']:.0f} VUs)",
    ]

    vus_line = [("VUs", [(b["t"], b["vus"]) for b in timeline])]
    svg_chart(
        "Response time over time",
        "time since start, s",
        [
            ("avg, ms", [(b["t"], b["avg"]) for b in timeline]),
            ("p95, ms", [(b["t"], b["p95"]) for b in timeline]),
        ],
        ("latency, ms", "virtual users"),
        args.out / "latency.svg",
        right=vus_line,
    )
    svg_chart(
        "Throughput over time",
        "time since start, s",
        [
            ("requests/s", [(b["t"], b["rps"]) for b in timeline]),
            ("errors/s", [(b["t"], b["errors_per_s"]) for b in timeline]),
        ],
        ("requests per second", "virtual users"),
        args.out / "throughput.svg",
        right=vus_line,
    )

    if args.resources:
        resources = load_resources(args.resources)
        t0 = min(t for samples in resources.values() for t, _, _ in samples)
        k6_offset = start - t0

        def shift(t):  # seconds on the k6 time axis
            return t - t0 - k6_offset

        cpu = [
            (name, [(shift(t), c) for t, c, _ in samples if shift(t) >= 0])
            for name, samples in sorted(resources.items())
        ]
        mem = [
            (name, [(shift(t), m) for t, _, m in samples if shift(t) >= 0])
            for name, samples in sorted(resources.items())
        ]
        svg_chart(
            "CPU usage per container",
            "time since start, s",
            cpu,
            ("CPU, % of one core", ""),
            args.out / "cpu.svg",
        )
        svg_chart(
            "Memory usage per container",
            "time since start, s",
            mem,
            ("RAM, MiB", ""),
            args.out / "memory.svg",
        )
        res_rows = []
        for name, samples in sorted(resources.items()):
            cpus = [c for _, c, _ in samples]
            mems = [m for _, _, m in samples]
            res_rows.append(
                [
                    name,
                    f"{sum(cpus) / len(cpus):.1f}",
                    f"{max(cpus):.1f}",
                    f"{sum(mems) / len(mems):.0f}",
                    f"{max(mems):.0f}",
                ]
            )
        lines += ["", "## Server resources (docker stats, ~2 s samples)", ""]
        lines.append(
            table(
                ["Container", "CPU avg, %", "CPU max, %", "RAM avg, MiB", "RAM max, MiB"], res_rows
            )
        )

    (args.out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()

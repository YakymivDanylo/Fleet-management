"""Lab 7: BEFORE/AFTER comparison of two k6 runs (tables and SVG charts).

    python loadtest/compare.py --before loadtest/results/lab7/before \
        --after loadtest/results/lab7/after --out loadtest/results/lab7

Reads k6.csv and resources.csv from both run folders; writes comparison.md,
compare_latency.svg and compare_throughput.svg. Standard library only.
"""

import argparse
from collections import defaultdict
from pathlib import Path

from report import buckets, load_k6, load_resources, summarize, svg_chart, table


def load_run(folder: Path) -> dict:
    rows, vus = load_k6(folder / "k6.csv")
    start = min(r["ts"] for r in rows)
    seconds = max(r["ts"] for r in rows) - start + 1
    steps = defaultdict(list)
    for row in rows:
        level = vus.get(row["ts"])
        if level is not None:
            steps[int(level)].append(row)
    plateau = {
        lvl: summarize(items, len({r["ts"] for r in items}))
        for lvl, items in steps.items()
        if len({r["ts"] for r in items}) >= 20
    }
    names = defaultdict(list)
    for row in rows:
        names[row["name"]].append(row)
    resources = load_resources(folder / "resources.csv")
    cpu_ram = {
        name: (
            sum(c for _, c, _ in s) / len(s),
            max(c for _, c, _ in s),
            sum(m for _, _, m in s) / len(s),
            max(m for _, _, m in s),
        )
        for name, s in resources.items()
    }
    return {
        "overall": summarize(rows, seconds),
        "timeline": buckets(rows, vus, start),
        "plateau": plateau,
        "endpoints": {n: summarize(r, seconds) for n, r in names.items()},
        "resources": cpu_ram,
    }


def change(before: float, after: float) -> str:
    if not before:
        return "-"
    return f"{(after - before) / before * 100:+.0f}%"


def row(label, before, after, key, fmt="{:.1f}"):
    return [label, fmt.format(before[key]), fmt.format(after[key]), change(before[key], after[key])]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--before", required=True, type=Path)
    parser.add_argument("--after", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    before, after = load_run(args.before), load_run(args.after)
    head = ["Metric", "Before", "After", "Change"]

    peak = {k: max(r["rps"] for r in run["timeline"]) for k, run in (("b", before), ("a", after))}
    overall = [
        row("Requests", before["overall"], after["overall"], "requests", "{}"),
        row("RPS (mean)", before["overall"], after["overall"], "rps"),
        [
            "RPS (peak, 5-s window)",
            f"{peak['b']:.1f}",
            f"{peak['a']:.1f}",
            change(peak["b"], peak["a"]),
        ],
        row("Latency avg, ms", before["overall"], after["overall"], "avg"),
        row("Latency p95, ms", before["overall"], after["overall"], "p95"),
        row("Latency max, ms", before["overall"], after["overall"], "max"),
        row("Error rate, %", before["overall"], after["overall"], "errors", "{:.2f}"),
    ]
    for name in ("api1", "db", "redis"):
        if name in before["resources"] and name in after["resources"]:
            b, a = before["resources"][name], after["resources"][name]
            overall.append([f"CPU {name} avg, %", f"{b[0]:.1f}", f"{a[0]:.1f}", change(b[0], a[0])])
            overall.append(
                [f"RAM {name} avg, MiB", f"{b[2]:.0f}", f"{a[2]:.0f}", change(b[2], a[2])]
            )

    lines = ["## Overall", "", table(head, overall), "", "## Per endpoint (avg / p95, ms)", ""]
    ep = []
    for name in sorted(before["endpoints"]):
        b, a = before["endpoints"][name], after["endpoints"][name]
        ep.append(
            [
                name,
                f"{b['avg']:.0f} / {b['p95']:.0f}",
                f"{a['avg']:.0f} / {a['p95']:.0f}",
                change(b["avg"], a["avg"]),
                change(b["p95"], a["p95"]),
            ]
        )
    lines.append(table(["Endpoint", "Before", "After", "avg", "p95"], ep))

    lines += ["", "## Per load step (RPS; avg / p95, ms)", ""]
    steps = []
    for level in sorted(before["plateau"]):
        b, a = before["plateau"][level], after["plateau"].get(level)
        if a:
            steps.append(
                [
                    level,
                    f"{b['rps']:.1f}",
                    f"{a['rps']:.1f}",
                    f"{b['avg']:.0f} / {b['p95']:.0f}",
                    f"{a['avg']:.0f} / {a['p95']:.0f}",
                ]
            )
    lines.append(table(["VUs", "RPS before", "RPS after", "Before", "After"], steps))
    (args.out / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def series(run, key, label):
        return (label, [(b["t"], b[key]) for b in run["timeline"]])

    vus = [("VUs", [(b["t"], b["vus"]) for b in before["timeline"]])]
    svg_chart(
        "Latency: before vs after",
        "time since start, s",
        [
            series(before, "avg", "avg before"),
            series(after, "avg", "avg after"),
            series(before, "p95", "p95 before"),
            series(after, "p95", "p95 after"),
        ],
        ("latency, ms", "virtual users"),
        args.out / "compare_latency.svg",
        right=vus,
    )
    svg_chart(
        "Throughput: before vs after",
        "time since start, s",
        [series(before, "rps", "RPS before"), series(after, "rps", "RPS after")],
        ("requests per second", "virtual users"),
        args.out / "compare_throughput.svg",
        right=vus,
    )
    print("\n".join(lines))


if __name__ == "__main__":
    main()

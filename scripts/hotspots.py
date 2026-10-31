"""Synergy matrix of Lab 7: static complexity (radon JSON) x process dynamics (git churn).

Usage (from the repo root, full git history available):

    radon cc src -j > complexity.json
    python scripts/hotspots.py --radon-json complexity.json --out-dir hotspots-report

Complexity of a file is the sum of the cyclomatic complexity of its blocks (a size-aware measure:
a repository gated at CC <= 10 per block has no single block above 10, so the per-block maximum
cannot separate files). Churn is the number of commits that touched the file in the window.
"""

import argparse
import csv
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

CATEGORIES = {
    (True, True): "Hotspot",
    (True, False): "Sleeping",
    (False, True): "Active",
    (False, False): "Stable",
}
ZONES = {"Hotspot": "red", "Sleeping": "yellow", "Active": "green", "Stable": "grey"}


@dataclass(frozen=True)
class FileRisk:
    file: str
    total_cc: int
    max_cc: int
    churn: int
    category: str

    @property
    def zone(self) -> str:
        return ZONES[self.category]


def classify(total_cc: int, churn: int, cc_threshold: int, churn_threshold: int) -> str:
    return CATEGORIES[(total_cc >= cc_threshold, churn >= churn_threshold)]


def read_complexity(radon_json: Path) -> dict[str, tuple[int, int]]:
    """Map posix file path -> (sum of block CC, max block CC)."""
    report = json.loads(radon_json.read_text(encoding="utf-8"))
    blocks = {
        path.replace("\\", "/").removeprefix("./"): [b["complexity"] for b in found]
        for path, found in report.items()
    }
    return {path: (sum(cc), max(cc, default=0)) for path, cc in blocks.items()}


def read_churn(since: str, rev: str = "HEAD") -> dict[str, int]:
    """Commits per file: the output of `git log --name-only | sort | uniq -c`, as a dict."""
    log = subprocess.run(
        ["git", "log", rev, f"--since={since}", "--format=format:", "--name-only"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    names = [line for line in log.splitlines() if line]
    return {name: names.count(name) for name in set(names)}


def build_matrix(
    complexity: dict[str, tuple[int, int]],
    churn: dict[str, int],
    cc_threshold: int,
    churn_threshold: int,
) -> list[FileRisk]:
    rows = [
        FileRisk(
            path,
            total,
            peak,
            churn.get(path, 0),
            classify(total, churn.get(path, 0), cc_threshold, churn_threshold),
        )
        for path, (total, peak) in complexity.items()
    ]
    return sorted(rows, key=lambda r: (r.total_cc * r.churn, r.total_cc), reverse=True)


def to_markdown(rows: list[FileRisk], cc_threshold: int, churn_threshold: int) -> str:
    lines = [
        f"Thresholds: total CC >= {cc_threshold} is complex; "
        f"churn >= {churn_threshold} is volatile.",
        "",
        "| File | Total CC | Max CC | Commits (window) | Category |",
        "|---|---:|---:|---:|---|",
    ]
    lines += [
        f"| `{r.file}` | {r.total_cc} | {r.max_cc} | {r.churn} | {r.category} ({r.zone}) |"
        for r in rows
    ]
    return "\n".join(lines) + "\n"


def write_reports(rows: list[FileRisk], out_dir: Path, cc_threshold: int, churn_threshold: int):
    out_dir.mkdir(parents=True, exist_ok=True)
    records = [{**asdict(r), "zone": r.zone} for r in rows]
    (out_dir / "hotspots.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    with (out_dir / "hotspots.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[*FileRisk.__dataclass_fields__, "zone"])
        writer.writeheader()
        writer.writerows(records)
    markdown = to_markdown(rows, cc_threshold, churn_threshold)
    (out_dir / "hotspots.md").write_text(markdown, encoding="utf-8")
    return markdown


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--radon-json", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=Path("hotspots-report"))
    parser.add_argument("--since", default="90 days ago")
    parser.add_argument("--cc-threshold", type=int, default=25)
    parser.add_argument("--churn-threshold", type=int, default=5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = build_matrix(
        read_complexity(args.radon_json),
        read_churn(args.since),
        args.cc_threshold,
        args.churn_threshold,
    )
    print(write_reports(rows, args.out_dir, args.cc_threshold, args.churn_threshold))


if __name__ == "__main__":
    main()

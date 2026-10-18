"""Balanced Quality Gate (Lab 5, Task 2): Line Coverage AND Mutation Score.

    PASS  <=>  (Line Coverage >= 90 %)  AND  (Mutation Score >= 75 %)

Both metrics are computed over the same scope - the `source_paths` of [tool.mutmut]:
- Line Coverage  = covered statements / all statements      (coverage.json, pytest-cov)
- Mutation Score = killed / (killed + survived + timeout)   (mutmut-cicd-stats.json)

The Mutation Score counts only mutants that some test executed ("covered code" score, as in
Stryker). That is what makes the pair a check-and-balance: a test without asserts turns
uncovered mutants ("no tests") into covered-but-surviving ones, so every point of coverage
bought that way strictly lowers the Mutation Score: K / (K + S + k) < K / (K + S).

Usage (inside the pinned fleet-metrics image, after `pytest --cov-report=json` and
`mutmut run && mutmut export-cicd-stats`):
    python scripts/quality_gate.py [--coverage coverage.json]
                                   [--mutation mutants/mutmut-cicd-stats.json]
"""

import argparse
import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIN_LINE_COVERAGE = 90.0
MIN_MUTATION_SCORE = 75.0


def _scope() -> list[str]:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return config["tool"]["mutmut"]["source_paths"]


def line_coverage(report: Path, scope: list[str]) -> float:
    files = json.loads(report.read_text(encoding="utf-8"))["files"]
    covered = total = 0
    for path in scope:
        summary = files[path]["summary"]
        covered += summary["covered_lines"]
        total += summary["num_statements"]
    return 100.0 * covered / total


def mutation_score(stats_file: Path) -> tuple[float, dict]:
    stats = json.loads(stats_file.read_text(encoding="utf-8"))
    executed = stats["killed"] + stats["survived"] + stats["timeout"]
    return 100.0 * stats["killed"] / executed, stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--coverage", type=Path, default=ROOT / "coverage.json")
    parser.add_argument("--mutation", type=Path, default=ROOT / "mutants/mutmut-cicd-stats.json")
    args = parser.parse_args()

    scope = _scope()
    coverage = line_coverage(args.coverage, scope)
    score, stats = mutation_score(args.mutation)
    coverage_ok = coverage >= MIN_LINE_COVERAGE
    score_ok = score >= MIN_MUTATION_SCORE

    print(f"Scope: {', '.join(scope)}")
    print(
        f"Mutants: total={stats['total']} killed={stats['killed']} "
        f"survived={stats['survived']} no_tests={stats['no_tests']} timeout={stats['timeout']}"
    )
    print(
        f"Line Coverage  {coverage:6.2f} %  (>= {MIN_LINE_COVERAGE:.0f})  "
        f"{'PASS' if coverage_ok else 'FAIL'}"
    )
    print(
        f"Mutation Score {score:6.2f} %  (>= {MIN_MUTATION_SCORE:.0f})  "
        f"{'PASS' if score_ok else 'FAIL'}"
    )
    passed = coverage_ok and score_ok
    print(f"Balanced Quality Gate: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())

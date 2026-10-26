"""Pre-commit quality gate: block commits that contain a function with CC > 10.

pre-commit passes only the staged Python files as arguments, so just the changed files are
scanned. The radon CLI is run with JSON output; every function or method whose cyclomatic
complexity exceeds LIMIT is reported in red and the script exits with code 1, which makes Git
abort the commit. A file radon cannot parse also blocks the commit, so a broken file never
slips through silently.

    python scripts/complexity_gate.py src/fleet_management/services/rental_service.py
"""

import json
import subprocess
import sys
from collections.abc import Iterator

LIMIT = 10
RED = "\033[1;31m"
RESET = "\033[0m"


def run_radon(files: list[str]) -> dict:
    result = subprocess.run(
        [sys.executable, "-m", "radon", "cc", "-j", *files],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        sys.exit(f"{RED}radon failed:{RESET} {result.stderr.strip()}")
    return json.loads(result.stdout or "{}")


def walk_blocks(blocks: list[dict]) -> Iterator[dict]:
    """Yields functions and methods, including nested closures; classes are only containers."""
    for block in blocks:
        if block["type"] != "class":
            yield block
        yield from walk_blocks(block.get("methods", []) + block.get("closures", []))


def find_problems(report: dict) -> list[str]:
    problems = []
    for file, blocks in report.items():
        if isinstance(blocks, dict):  # radon reports unparsable files as {"error": ...}
            problems.append(f"{file}: cannot analyse ({blocks.get('error')})")
            continue
        for block in walk_blocks(blocks):
            if block["complexity"] > LIMIT:
                problems.append(
                    f"{file}:{block['lineno']} {block['name']}() has CC={block['complexity']} "
                    f"(rank {block['rank']}), limit is {LIMIT}"
                )
    return problems


def main(files: list[str]) -> int:
    if not files:
        return 0
    problems = find_problems(run_radon(files))
    if not problems:
        print(f"complexity gate: OK, every function in {len(files)} file(s) has CC <= {LIMIT}")
        return 0
    print(f"{RED}COMPLEXITY GATE FAILED: commit blocked{RESET}")
    for problem in problems:
        print(f"{RED}  {problem}{RESET}")
    print(f"Refactor (e.g. replace if/else chains with a lookup table) to get CC <= {LIMIT}.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

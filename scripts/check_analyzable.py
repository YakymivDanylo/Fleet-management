"""Fail-closed guard for the complexity gate (Lab 5, task 3).

`xenon` only logs a WARNING and exits 0 when radon cannot parse a file (UTF-8 BOM, a
non-UTF-8 encoding, a syntax error), so an unreadable file silently PASSes the gate with no
metrics at all. This check makes every file under the given paths either measurable or a FAIL.

    python scripts/check_analyzable.py src
"""

import json
import subprocess
import sys


def main() -> int:
    paths = sys.argv[1:] or ["src"]
    report = json.loads(
        subprocess.run(
            ["radon", "cc", "-j", *paths], capture_output=True, text=True, check=True
        ).stdout
    )
    broken = {path: blocks["error"] for path, blocks in report.items() if "error" in blocks}
    for path, error in broken.items():
        print(f"NOT ANALYZABLE {path}: {error}")
    print(f"{len(report) - len(broken)}/{len(report)} files analyzable")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())

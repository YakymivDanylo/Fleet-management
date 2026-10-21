"""Collect static metrics of one source file with the analyzers' own CLIs (Lab 5, task 3).

Runs inside an analyzer container and prints one JSON object, so scripts/reliability_test.py
can compare the numbers across line endings, encodings, interpreter and tool versions.
A tool that crashes or is not installed is reported as its error text instead of numbers.
"""

import csv
import io
import json
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


def _run(*cmd: str) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip().splitlines()[-1]
        raise RuntimeError(ANSI_ESCAPE.sub("", message))
    return result.stdout


def _version(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:
        return "-"


def radon_metrics(path: str) -> dict:
    raw = json.loads(_run("radon", "raw", "-j", path))[path]
    if "error" in raw:
        raise RuntimeError(raw["error"])
    blocks = json.loads(_run("radon", "cc", "-j", path))[path]
    if isinstance(blocks, dict):
        raise RuntimeError(blocks["error"])
    mi = json.loads(_run("radon", "mi", "-j", path))[path]
    return {
        "loc": raw["loc"],
        "sloc": raw["sloc"],
        "lloc": raw["lloc"],
        "comments": raw["comments"],
        "blank": raw["blank"],
        "cc_max": max(b["complexity"] for b in blocks),
        "cc_sum": sum(b["complexity"] for b in blocks),
        "mi": round(mi["mi"], 2),
    }


def lizard_metrics(path: str) -> dict:
    rows = list(csv.reader(io.StringIO(_run("lizard", "--csv", path))))
    return {
        "functions": len(rows),
        "nloc": sum(int(r[0]) for r in rows),
        "ccn_sum": sum(int(r[1]) for r in rows),
        "tokens": sum(int(r[2]) for r in rows),
    }


def complexipy_metrics(path: str) -> dict:
    if shutil.which("complexipy") is None:
        raise RuntimeError("complexipy not installed")
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "report.json"
        _run("complexipy", path, "-q", "-i", "--output-format", "json", "--output", str(report))
        functions = json.loads(report.read_text(encoding="utf-8"))
    return {"cognitive_sum": sum(f["complexity"] for f in functions)}


def _safe(collect, path: str) -> dict:
    try:
        return collect(path)
    except Exception as exc:  # the probe documents failures, it must not stop the matrix
        return {"error": str(exc)[:160]}


def main() -> None:
    path = sys.argv[1]
    print(
        json.dumps(
            {
                "python": platform.python_version(),
                "tools": {t: _version(t) for t in ("radon", "lizard", "complexipy")},
                "radon": _safe(radon_metrics, path),
                "lizard": _safe(lizard_metrics, path),
                "complexipy": _safe(complexipy_metrics, path),
            }
        )
    )


if __name__ == "__main__":
    main()

"""Reliability test of the static analyzers (Lab 5, task 3, experiment 1).

The same source file (its committed git blob, so the result does not depend on the
developer's core.autocrlf) is rewritten in several byte-level forms that do not change the
algorithm - scenario A (line endings / encoding) - and scanned in several runner images -
scenario B (interpreter and analyzer versions). Every cell runs scripts/metrics_probe.py.

    python scripts/reliability_test.py [--file src/...py] [--out docs/.../reliability.json]
"""

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FILE = "src/fleet_management/privacy/logging_setup.py"
DEFAULT_OUT = ROOT / "docs" / "lab5-quality-governance" / "outputs" / "reliability.json"
PINNED_TOOLS = "radon==6.0.1 lizard==1.24.1 complexipy==8.0.1"

# Scenario A: byte-level forms of one and the same program.
VARIANTS = {
    "utf8-lf": lambda text: text.encode("utf-8"),
    "utf8-crlf": lambda text: text.replace("\n", "\r\n").encode("utf-8"),
    "utf8-cr": lambda text: text.replace("\n", "\r").encode("utf-8"),
    "utf8-bom-lf": lambda text: text.encode("utf-8-sig"),
    "cp1251-lf": lambda text: text.encode("cp1251"),
}

# Scenario B: runner images (interpreter) x analyzer versions.
ENVIRONMENTS = {
    "py3.9 + pinned tools": ("python:3.9-slim", PINNED_TOOLS),
    "py3.13 + pinned tools": ("python:3.13.16-slim", PINNED_TOOLS),
    "py3.14 + pinned tools": ("python:3.14-slim", PINNED_TOOLS),
    "py3.13 + old tools": ("python:3.13.16-slim", "radon==5.1.0 lizard==1.17.10"),
}


def _committed_source(path: str) -> str:
    blob = subprocess.run(
        ["git", "show", f"HEAD:{path}"], cwd=ROOT, capture_output=True, check=True
    ).stdout
    return blob.decode("utf-8")


def _scan(image: str, tools: str, workdir: Path) -> dict:
    probes = " ".join(
        f"echo '{name}'; python /work/metrics_probe.py /work/{name}.py;" for name in VARIANTS
    )
    script = f"pip install -q --root-user-action=ignore {tools} >/dev/null 2>&1; {probes}"
    output = subprocess.run(
        ["docker", "run", "--rm", "-v", f"{workdir}:/work", image, "sh", "-c", script],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    return {output[i]: json.loads(output[i + 1]) for i in range(0, len(output), 2)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", default=DEFAULT_FILE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    source = _committed_source(args.file)
    results = {"file": args.file, "environments": {}}
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        (workdir / "metrics_probe.py").write_bytes((ROOT / "scripts/metrics_probe.py").read_bytes())
        for name, encode in VARIANTS.items():
            (workdir / f"{name}.py").write_bytes(encode(source))
        for env, (image, tools) in ENVIRONMENTS.items():
            print(f"Scanning in {env} ({image}) ...", flush=True)
            results["environments"][env] = {
                "image": image,
                "variants": _scan(image, tools, workdir),
            }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Saved {args.out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

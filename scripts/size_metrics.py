"""Lab 9 (QE): functional size (IFPUG FPA, Karner UCP) and reverse calibration of productivity.

    python scripts/size_metrics.py --fpa docs/lab9/fpa_ifpug.csv --ucp docs/lab9/ucp_karner.csv \
        --effort docs/lab9/evidence/git_effort_users.json

FPA: every row has the category (ILF/EIF/EI/EO/EQ) and the counted RET (data) or FTR
(transactions) and DET; complexity and weight are derived from the IFPUG CPM 4.3 matrices.
UCP: actors (simple/average/complex -> 1/2/3) and use cases (transactions <=3 / 4-7 / >7 ->
5/10/15); UCP = (UAW + UUCW) * TCF * ECF. PF = effort hours / UCP.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

WEIGHTS = {
    "ILF": {"Low": 7, "Average": 10, "High": 15},
    "EIF": {"Low": 5, "Average": 7, "High": 10},
    "EI": {"Low": 3, "Average": 4, "High": 6},
    "EO": {"Low": 4, "Average": 5, "High": 7},
    "EQ": {"Low": 3, "Average": 4, "High": 6},
}
GRID = [["Low", "Low", "Average"], ["Low", "Average", "High"], ["Average", "High", "High"]]
ACTOR_WEIGHTS = {"simple": 1, "average": 2, "complex": 3}


def _band(value: int, edges: tuple[int, int]) -> int:
    return 0 if value <= edges[0] else 1 if value <= edges[1] else 2


def complexity(category: str, ret_ftr: int, det: int) -> str:
    """IFPUG matrices: rows = RET/FTR band, columns = DET band."""
    if category in ("ILF", "EIF"):
        return GRID[_band(ret_ftr, (1, 5))][_band(det, (19, 50))]
    if category == "EI":
        return GRID[_band(ret_ftr, (1, 2))][_band(det, (4, 15))]
    if category in ("EO", "EQ"):
        return GRID[_band(ret_ftr, (1, 3))][_band(det, (5, 19))]
    raise ValueError(f"unknown FPA category {category!r}")


def use_case_weight(transactions: int) -> int:
    return 5 if transactions <= 3 else 10 if transactions <= 7 else 15


def fpa(rows: list[dict]) -> tuple[list[dict], dict[str, int]]:
    out, totals = [], dict.fromkeys(WEIGHTS, 0)
    for r in rows:
        cx = complexity(r["category"], int(r["ret_ftr"]), int(r["det"]))
        weight = WEIGHTS[r["category"]][cx]
        totals[r["category"]] += weight
        out.append({**r, "complexity": cx, "weight": weight})
    return out, totals


def ucp(rows: list[dict], tcf: float = 1.0, ecf: float = 1.0) -> dict:
    actors = [
        {**r, "weight": ACTOR_WEIGHTS[r["type_or_transactions"]]}
        for r in rows
        if r["kind"] == "actor"
    ]
    cases = [
        {**r, "weight": use_case_weight(int(r["type_or_transactions"]))}
        for r in rows
        if r["kind"] == "usecase"
    ]
    uaw, uucw = sum(a["weight"] for a in actors), sum(c["weight"] for c in cases)
    return {
        "actors": actors,
        "use_cases": cases,
        "UAW": uaw,
        "UUCW": uucw,
        "UUCP": uaw + uucw,
        "TCF": tcf,
        "ECF": ecf,
        "UCP": round((uaw + uucw) * tcf * ecf, 2),
    }


def _read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--fpa", type=Path, required=True)
    p.add_argument("--ucp", type=Path, required=True)
    p.add_argument("--effort", type=Path, required=True, help="git_effort.py JSON")
    p.add_argument("--json", type=Path)
    a = p.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")

    fpa_rows, totals = fpa(_read(a.fpa))
    ufp = sum(totals.values())
    print("## FPA (IFPUG)\n| ID | Cat | Function | RET/FTR | DET | Complexity | Weight |")
    print("|---|---|---|---|---|---|---|")
    for r in fpa_rows:
        print(
            f"| {r['id']} | {r['category']} | {r['function']} | {r['ret_ftr']} | {r['det']} |"
            f" {r['complexity']} | {r['weight']} |"
        )
    counts = {c: sum(1 for r in fpa_rows if r["category"] == c) for c in WEIGHTS}
    print("\n| Category | Count | FP |\n|---|---|---|")
    for c in WEIGHTS:
        print(f"| {c} | {counts[c]} | {totals[c]} |")
    print(f"| **UFP** | {len(fpa_rows)} | **{ufp}** |")

    u = ucp(_read(a.ucp))
    print("\n## UCP (Karner)\n| ID | Name | Type / transactions | Weight |\n|---|---|---|---|")
    for r in u["actors"] + u["use_cases"]:
        print(f"| {r['id']} | {r['name']} | {r['type_or_transactions']} | {r['weight']} |")
    print(
        f"\nUAW={u['UAW']} UUCW={u['UUCW']} UUCP={u['UUCP']} TCF={u['TCF']} ECF={u['ECF']}"
        f" UCP={u['UCP']}"
    )

    hours = json.loads(a.effort.read_text(encoding="utf-8"))["hours"]
    pf = hours / u["UCP"]
    print(f"\n## Calibration\neffort={hours} h  PF={pf:.2f} h/UCP  FP-rate={hours / ufp:.2f} h/FP")
    if a.json:
        a.json.write_text(
            json.dumps(
                {
                    "fpa": fpa_rows,
                    "fpa_totals": totals,
                    "UFP": ufp,
                    "ucp": u,
                    "effort_hours": hours,
                    "PF": round(pf, 2),
                    "hours_per_fp": round(hours / ufp, 2),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

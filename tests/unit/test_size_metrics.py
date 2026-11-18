"""Lab 9: IFPUG complexity matrices and Karner UCP weights."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import size_metrics as sm  # noqa: E402


@pytest.mark.parametrize(
    ("category", "ret_ftr", "det", "expected"),
    [
        ("ILF", 1, 19, "Low"),
        ("ILF", 2, 20, "Average"),
        ("ILF", 6, 51, "High"),
        ("EIF", 1, 51, "Average"),
        ("EI", 1, 15, "Low"),
        ("EI", 2, 5, "Average"),
        ("EI", 3, 4, "Average"),
        ("EI", 3, 5, "High"),
        ("EO", 2, 5, "Low"),
        ("EO", 2, 6, "Average"),
        ("EO", 4, 6, "High"),
        ("EQ", 1, 20, "Average"),
        ("EQ", 4, 1, "Average"),
    ],
)
def test_ifpug_matrices(category, ret_ftr, det, expected):
    assert sm.complexity(category, ret_ftr, det) == expected


@pytest.mark.parametrize(("transactions", "weight"), [(3, 5), (4, 10), (7, 10), (8, 15)])
def test_karner_use_case_weights(transactions, weight):
    assert sm.use_case_weight(transactions) == weight


def _csv(path: Path, lines: list[str]) -> Path:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_fpa_totals_from_csv(tmp_path):
    fpa_csv = _csv(
        tmp_path / "fpa.csv",
        [
            "id,category,function,source,ret_ftr,det",
            "D1,ILF,Token,models.py,1,11",
            "D2,EIF,ContentType,contenttypes,1,3",
            "T1,EI,Create permission,POST,4,8",
            "T2,EO,Group list with count,GET,2,5",
            "T3,EQ,View users,GET,2,12",
        ],
    )
    rows, totals = sm.fpa(sm._read(fpa_csv))
    assert [r["weight"] for r in rows] == [7, 5, 6, 4, 4]
    assert sum(totals.values()) == 26


def test_ucp_totals_from_csv(tmp_path):
    ucp_csv = _csv(
        tmp_path / "ucp.csv",
        [
            "id,kind,name,source,type_or_transactions",
            "A1,actor,User,GUI,complex",
            "A2,actor,API client,HTTP,average",
            "UC1,usecase,Log in,views,6",
            "UC2,usecase,Manage tokens,views,9",
        ],
    )
    u = sm.ucp(sm._read(ucp_csv))
    assert (u["UAW"], u["UUCW"], u["UCP"]) == (5, 25, 30)

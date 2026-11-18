"""Lab 9: IFPUG complexity matrices and Karner UCP weights."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import size_metrics as sm  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


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


def test_lab9_netbox_users_totals():
    _, totals = sm.fpa(sm._read(ROOT / "docs/lab9/fpa_ifpug.csv"))
    assert sum(totals.values()) == 144
    u = sm.ucp(sm._read(ROOT / "docs/lab9/ucp_karner.csv"))
    assert (u["UAW"], u["UUCW"], u["UCP"]) == (9, 85, 94)

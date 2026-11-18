"""Lab 9: the SQALE -> Principal / Cost of Delay / NPV simulator."""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import financial_simulator as fs  # noqa: E402

ENV = {"HOURLY_RATE": "40", "OVERLOAD_COEFF": "1.3", "DISCOUNT_RATE": "0.01"}


def _report(tmp_path: Path, ncloc="99839", sqale_index="9114", rating="1.0") -> Path:
    measures = [
        {"metric": "ncloc", "value": ncloc},
        {"metric": "sqale_index", "value": sqale_index},
        {"metric": "sqale_rating", "value": rating},
    ]
    path = tmp_path / "report.json"
    component = {"key": "demo", "name": "demo", "measures": measures}
    path.write_text(json.dumps({"component": component}))
    return path


def test_baseline_is_parsed_from_json(tmp_path):
    b = fs.load_baseline(_report(tmp_path))
    assert (b.ncloc, b.sqale_index, b.sqale_rating) == (99839, 9114, "A")
    assert b.debt_hours == pytest.approx(151.9)
    assert b.debt_days == pytest.approx(18.9875)


def test_principal_and_cost_of_delay_formulas(tmp_path):
    sim = fs.simulate(fs.load_baseline(_report(tmp_path)), fs.load_economics(ENV))
    assert sim.principal == pytest.approx(151.9 * 40 * 1.3)
    assert sim.cost_of_delay == pytest.approx(998.39 * 40 * 1.3)


def test_npv_is_cumulative_and_discounted(tmp_path):
    sim = fs.simulate(fs.load_baseline(_report(tmp_path)), fs.load_economics(ENV))
    expected = -sim.principal + sum(sim.cost_of_delay / 1.01**k for k in range(1, 7))
    assert sim.flows[-1].cumulative_npv == pytest.approx(expected)
    assert sim.flows[1].discount_factor == pytest.approx(1 / 1.01**2)
    assert sim.payback_month == 1 and sim.passed


def test_payback_month_is_first_positive_npv(tmp_path):
    # debt 4 h per 100 LOC: principal = 4 * CoD -> NPV turns positive on month 5 (r = 1 %)
    sim = fs.simulate(fs.load_baseline(_report(tmp_path, "1000", "2400")), fs.load_economics(ENV))
    assert [f.cumulative_npv > 0 for f in sim.flows] == [False] * 4 + [True] * 2
    assert sim.payback_month == 5


def test_heavy_debt_fails_the_gate(tmp_path):
    # debt 10 h per 100 LOC > 6 months of savings
    sim = fs.simulate(fs.load_baseline(_report(tmp_path, "1000", "6000")), fs.load_economics(ENV))
    assert sim.payback_month is None and not sim.passed
    text = fs.render_ledger(sim, "report.json", datetime(2026, 1, 1, tzinfo=UTC))
    assert "**FAIL**" in text and "Архітектурне попередження" in text


@pytest.mark.parametrize(
    "env",
    [
        {**ENV, "HOURLY_RATE": "60"},
        {**ENV, "OVERLOAD_COEFF": "0.5"},
        {**ENV, "DISCOUNT_RATE": "abc"},
        {k: v for k, v in ENV.items() if k != "DISCOUNT_RATE"},
    ],
)
def test_invalid_environment_is_rejected(env):
    with pytest.raises(fs.LedgerError):
        fs.load_economics(env)


def test_missing_metric_is_rejected(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({"component": {"key": "x", "measures": []}}))
    with pytest.raises(fs.LedgerError, match="missing"):
        fs.load_baseline(path)


def test_main_writes_ledger(tmp_path, monkeypatch, capsys):
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    out = tmp_path / "FINANCIAL_LEDGER.md"
    assert fs.main([str(_report(tmp_path)), "--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert "**PASS**" in text and "| 6 |" in text
    assert "quality_gate=PASS" in capsys.readouterr().out

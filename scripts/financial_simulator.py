"""Lab 9 (QE): Software Economics simulator — SQALE debt -> Principal, Cost of Delay, NPV, payback.

Reads the raw SonarCloud ``api/measures/component`` JSON (``report.json``) and three environment
variables, then writes ``FINANCIAL_LEDGER.md`` with the discounted cash-flow table and the quality
gate verdict.

    HOURLY_RATE=40 OVERLOAD_COEFF=1.3 DISCOUNT_RATE=0.01 \
        python scripts/financial_simulator.py docs/lab9/report.json

Model (all money in USD):

    Principal      = (sqale_index / 60) * HOURLY_RATE * OVERLOAD_COEFF
    CostOfDelay    = (ncloc / 100) * 1 h * HOURLY_RATE * OVERLOAD_COEFF          (per month)
    DF_t           = 1 / (1 + DISCOUNT_RATE) ** t
    NPV_t          = -Principal + sum_{k=1..t} CostOfDelay * DF_k

The refactoring "income" of month t is the Cost of Delay the company stops paying after the debt is
repaid. Quality gate: PASS when NPV_t > 0 for some t <= HORIZON_MONTHS, FAIL otherwise.
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

HORIZON_MONTHS = 6
MINUTES_PER_HOUR = 60
HOURS_PER_DAY = 8
LOC_PER_LOST_HOUR = 100  # every 100 ncloc cost 1 engineer-hour per month of regression fighting
RATE_RANGE = (35.0, 50.0)
SQALE_LETTERS = {1: "A", 2: "B", 3: "C", 4: "D", 5: "E"}


class LedgerError(ValueError):
    """Invalid input: broken report.json or an out-of-range environment variable."""


@dataclass(frozen=True)
class Baseline:
    key: str
    name: str
    ncloc: int
    sqale_index: int  # minutes
    sqale_rating: str

    @property
    def debt_hours(self) -> float:
        return self.sqale_index / MINUTES_PER_HOUR

    @property
    def debt_days(self) -> float:
        return self.debt_hours / HOURS_PER_DAY


@dataclass(frozen=True)
class Economics:
    hourly_rate: float
    overload_coeff: float
    discount_rate: float

    @property
    def loaded_rate(self) -> float:
        return self.hourly_rate * self.overload_coeff


@dataclass(frozen=True)
class CashFlow:
    month: int
    discount_factor: float
    monthly_gain: float  # discounted Cost of Delay avoided in this month
    cumulative_npv: float


@dataclass(frozen=True)
class Simulation:
    baseline: Baseline
    economics: Economics
    principal: float
    cost_of_delay: float
    flows: list[CashFlow]
    payback_month: int | None

    @property
    def passed(self) -> bool:
        return self.payback_month is not None


def load_baseline(path: Path) -> Baseline:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        component = payload["component"]
        measures = {m["metric"]: m["value"] for m in component["measures"]}
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise LedgerError(f"{path}: not a SonarCloud measures/component response ({exc})") from exc
    missing = {"ncloc", "sqale_index", "sqale_rating"} - measures.keys()
    if missing:
        raise LedgerError(f"{path}: metrics missing from the response: {sorted(missing)}")
    ncloc, sqale_index = int(measures["ncloc"]), int(measures["sqale_index"])
    if ncloc <= 0 or sqale_index < 0:
        raise LedgerError(f"{path}: ncloc must be > 0 and sqale_index >= 0")
    rating = SQALE_LETTERS.get(round(float(measures["sqale_rating"])), measures["sqale_rating"])
    return Baseline(
        component["key"], component.get("name", component["key"]), ncloc, sqale_index, rating
    )


def _env_float(env: dict[str, str], name: str) -> float:
    raw = env.get(name)
    if raw is None:
        raise LedgerError(f"environment variable {name} is not set")
    try:
        return float(raw)
    except ValueError as exc:
        raise LedgerError(f"{name}={raw!r} is not a number") from exc


def load_economics(env: dict[str, str]) -> Economics:
    rate = _env_float(env, "HOURLY_RATE")
    overload = _env_float(env, "OVERLOAD_COEFF")
    discount = _env_float(env, "DISCOUNT_RATE")
    if not RATE_RANGE[0] <= rate <= RATE_RANGE[1]:
        raise LedgerError(f"HOURLY_RATE must be in {RATE_RANGE[0]:.0f}..{RATE_RANGE[1]:.0f} $/h")
    if overload < 1:
        raise LedgerError("OVERLOAD_COEFF must be >= 1")
    if not 0 <= discount < 1:
        raise LedgerError("DISCOUNT_RATE must be in [0, 1)")
    return Economics(rate, overload, discount)


def simulate(baseline: Baseline, economics: Economics, horizon: int = HORIZON_MONTHS) -> Simulation:
    principal = baseline.debt_hours * economics.loaded_rate
    cost_of_delay = baseline.ncloc / LOC_PER_LOST_HOUR * economics.loaded_rate
    npv = -principal
    flows: list[CashFlow] = []
    payback: int | None = None
    for t in range(1, horizon + 1):
        factor = 1 / (1 + economics.discount_rate) ** t
        gain = cost_of_delay * factor
        npv += gain
        flows.append(CashFlow(t, factor, gain, npv))
        if npv > 0 and payback is None:
            payback = t
    return Simulation(baseline, economics, principal, cost_of_delay, flows, payback)


def _money(value: float) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.2f}"


def render_ledger(sim: Simulation, source: str, generated_at: datetime) -> str:
    b, e = sim.baseline, sim.economics
    tdd = b.debt_hours / (b.ncloc * 0.5) * 100
    rows = "\n".join(
        f"| {f.month} | {f.discount_factor:.6f} | {_money(f.monthly_gain)} | "
        f"{_money(f.cumulative_npv)} | {'✅ > 0' if f.cumulative_npv > 0 else '❌ ≤ 0'} |"
        for f in sim.flows
    )
    if sim.passed:
        verdict = (
            f"Точка виходу в нуль (Payback Period): окупність настає на "
            f"**{sim.payback_month}-му місяці** після рефакторингу; "
            f"NPV за {len(sim.flows)} міс. = "
            f"{_money(sim.flows[-1].cumulative_npv)}."
        )
        gate = "## 5. СТАТУС ВОРІТ ЯКОСТІ (Quality Gate): **PASS** ✅"
    else:
        verdict = (
            f"Окупність **не настає** на горизонті {len(sim.flows)} міс.: NPV = "
            f"{_money(sim.flows[-1].cumulative_npv)}."
        )
        gate = (
            "## 5. СТАТУС ВОРІТ ЯКОСТІ (Quality Gate): **FAIL** ❌\n\n"
            "> ⚠️ Архітектурне попередження: тіло боргу перевищує дисконтовану економію за "
            "6 місяців — потрібна поетапна (інкрементальна) стратегія погашення боргу."
        )
    debt = f"{b.sqale_index:,} хв = {b.debt_hours:,.2f} люд.-год = {b.debt_days:,.2f} люд.-днів"
    principal_row = (
        "| Тіло боргу (вартість рефакторингу) | (sqale_index / 60) × rate × "
        f"overload | **{_money(sim.principal)}** |"
    )
    cod_row = (
        "| Cost of Delay (щомісячні збитки бездіяльності) | (ncloc / 100) × 1 год × rate × "
        f"overload | **{_money(sim.cost_of_delay)} / міс.** |"
    )
    flow_head = (
        "| Місяць t | Коефіцієнт дисконтування 1/(1+r)^t | Щомісячний прибуток (дисконт.) "
        "| Кумулятивний NPV | NPV > 0 |"
    )
    return f"""# SOFTWARE ECONOMICS & FINANCIAL QUALITY LEDGER

> Згенеровано автоматично `scripts/financial_simulator.py` {generated_at:%Y-%m-%d %H:%M} UTC
> з файлу `{source}`. Не редагувати вручну.

## 1. Вхідні параметри аудиту (System Baseline)

| Параметр | Значення |
|---|---|
| Проєкт (Key) | `{b.key}` ({b.name}) |
| Масштаб системи (NCLOC) | {b.ncloc:,} |
| Початковий технічний борг (SQALE Index) | {debt} |
| TDD (SQALE debt ratio) | {tdd:.3f} % (рейтинг SonarCloud: {b.sqale_rating}) |
| HOURLY_RATE | ${e.hourly_rate:.2f}/год |
| OVERLOAD_COEFF | {e.overload_coeff} |
| DISCOUNT_RATE | {e.discount_rate} / місяць |

## 2. Капіталізація інвестиційних маркерів

| Маркер | Формула | Значення |
|---|---|---|
{principal_row}
{cod_row}

## 3. Динаміка окупності інвестицій у часі ({len(sim.flows)} ітерацій)

NPV₀ = −{_money(sim.principal)} (інвестиція в рефакторинг у момент t = 0).

{flow_head}
|---|---|---|---|---|
{rows}

## 4. Фінальний інженерно-економічний вердикт

{verdict}

{gate}
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("report", type=Path, help="raw SonarCloud measures JSON (report.json)")
    parser.add_argument("--out", type=Path, default=Path("FINANCIAL_LEDGER.md"))
    args = parser.parse_args(argv)
    try:
        baseline = load_baseline(args.report)
        economics = load_economics(dict(os.environ))
    except LedgerError as exc:
        print(f"[ledger] ERROR: {exc}", file=sys.stderr)
        return 2
    sim = simulate(baseline, economics)
    print(
        f"[ledger] project={baseline.key} ncloc={baseline.ncloc}"
        f" sqale_index={baseline.sqale_index} min"
        f" ({baseline.debt_hours:.2f} h / {baseline.debt_days:.2f} d)"
    )
    print(
        f"[ledger] principal={_money(sim.principal)}"
        f" cost_of_delay={_money(sim.cost_of_delay)}/month"
    )
    for f in sim.flows:
        print(
            f"[ledger] t={f.month} DF={f.discount_factor:.6f} gain={_money(f.monthly_gain)}"
            f" NPV={_money(f.cumulative_npv)}"
        )
    source = args.report.as_posix()
    args.out.write_text(render_ledger(sim, source, datetime.now(UTC)), encoding="utf-8")
    status = "PASS" if sim.passed else "FAIL"
    payback = f"month {sim.payback_month}" if sim.passed else "not reached"
    print(f"[ledger] payback={payback} quality_gate={status}")
    print(f"[ledger] OK: financial ledger written to {args.out.resolve()}")
    return 0 if sim.passed else 1


if __name__ == "__main__":
    sys.exit(main())

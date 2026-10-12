"""Sections 10/11/18.1 - Economic ledger and rolling/calendar window aggregation (``aggregate_windows``).

Every transaction becomes a ledger line of probability-weighted Decimal buckets. All windowed and
monthly aggregates are sums of ledger lines, so every aggregate is traceable to transaction IDs.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from se_income_engine.common.money import ZERO, weighted
from se_income_engine.common.stats import DAYS_PER_MONTH, quantile
from se_income_engine.config.parameters import IncomeParameters, RoleParameters
from se_income_engine.contracts.account import Transaction
from se_income_engine.contracts.entity import EntityHypothesis
from se_income_engine.contracts.role import RolePrediction
from se_income_engine.services.m2_role_classifier.s05_entity_resolution import ClusterStatistics
from se_income_engine.services.supporting.ledger_operating_cash.s10_operating_inflow_reconstruction import compute_inflow_features, p_operating
from se_income_engine.services.supporting.ledger_operating_cash.s11_operating_outflow_reconstruction import compute_outflow_features

CREDIT_BUCKETS = {
    "financing_in": ("C05",), "internal_in": ("C04",), "owner_capital_in": ("C06",),
    "investment_in": ("C07",), "refund_in": ("C08",), "statutory_refund_in": ("C09",),
    "interest_in": ("C10",), "personal_in": ("C11",), "pass_through_in": ("C12",), "unknown_in": ("C13",),
}
DEBIT_BUCKETS = {
    "direct_cost": ("D01",), "payroll": ("D02",), "rent": ("D03",), "utilities": ("D04",), "logistics": ("D05",),
    "other_opex": ("D06",), "statutory": ("D07",), "debt_interest": ("D08",), "debt_principal": ("D09",),
    "capex": ("D10",), "maintenance_capex": ("D11",), "owner_draw": ("D12",), "personal_expense": ("D13",),
    "internal_out": ("D14",), "refund_out": ("D15",), "business_cash_withdrawal": ("D16",),
    "pass_through_out": ("D17",), "bank_fee": ("D18",), "unknown_out": ("D19",),
}
ALL_BUCKETS = ["gross_credits", "gross_debits", "eoc_credit", "eoc_hc_credit", "cash_deposit_non_eligible",
               "cor_debit", "non_recurring_cor", *CREDIT_BUCKETS, *DEBIT_BUCKETS]

NON_RECURRING_MIN_AMOUNT = Decimal("50000")


@dataclass
class LedgerLine:
    txn_id: str
    account_id: str
    booking_date: date
    is_credit: bool
    amount: Decimal
    p_operating: float
    uncertainty: float
    buckets: dict[str, Decimal]


@dataclass
class WindowAggregate:
    label: str
    start: date
    end: date
    covered_days: int
    months: float
    totals: dict[str, Decimal]
    inflow: dict[str, float | None] = field(default_factory=dict)
    outflow: dict[str, float | None] = field(default_factory=dict)

    def monthly(self, key: str) -> Decimal:
        if self.months <= 0:
            return ZERO
        return self.totals[key] / Decimal(repr(self.months))


@dataclass
class MonthlyAggregate:
    month: str
    start: date
    end: date
    coverage: float
    totals: dict[str, Decimal]

    @property
    def complete(self) -> bool:
        return self.coverage >= 0.9


@dataclass
class AccountFeatures:
    as_of: date
    statement_start: date
    statement_end: date
    history_months: float
    windows: dict[str, WindowAggregate]
    monthly: list[MonthlyAggregate]
    full_period: WindowAggregate
    eoc_by_account: dict[str, Decimal]
    cor_by_account: dict[str, Decimal]
    ledger: dict[str, LedgerLine]


def non_recurring_outflow_ids(txns: list[Transaction], predictions: dict[str, RolePrediction],
                              hypotheses: dict[str, EntityHypothesis],
                              cluster_stats: dict[str, ClusterStatistics]) -> set[str]:
    """Section 11.1 COR is the core *recurring* requirement: an atypically large, unrepeated debit whose
    operating probability is below one half is not recurring. Its residual operating mass is carried as
    unresolved downside (Section 22.2) instead of distorting monthly COR."""
    out: set[str] = set()
    by_account: dict[str, list[float]] = {}
    for t in txns:
        if not t.is_credit:
            by_account.setdefault(t.account_id, []).append(float(t.amount))
    p99 = {aid: quantile(v, 0.99) or 0.0 for aid, v in by_account.items()}
    for t in txns:
        if t.is_credit or t.amount < max(NON_RECURRING_MIN_AMOUNT, Decimal(repr(p99[t.account_id]))):
            continue
        cs = cluster_stats.get(hypotheses[t.transaction_id].cluster_id)
        if cs is not None and len(cs.amounts) > 1:
            continue
        if predictions[t.transaction_id].p("D01", "D02", "D03", "D04", "D05", "D06") < 0.5:
            out.add(t.transaction_id)
    return out


def build_economic_ledger(txns: list[Transaction], predictions: dict[str, RolePrediction],
                          cash_eligibility: dict[str, float], income: IncomeParameters,
                          roles: RoleParameters, non_recurring: set[str] | None = None) -> dict[str, LedgerLine]:
    non_recurring = non_recurring or set()
    ledger: dict[str, LedgerLine] = {}
    for t in txns:
        pred = predictions[t.transaction_id]
        b = {k: ZERO for k in ALL_BUCKETS}
        uncertainty = max(pred.entropy, pred.p("C13", "D19"))
        if t.is_credit:
            elig = cash_eligibility.get(t.transaction_id, 0.5)
            p_op = p_operating(pred, elig)
            b["gross_credits"] = t.amount
            b["eoc_credit"] = weighted(t.amount, p_op)
            if p_op >= roles.high_confidence_threshold:
                b["eoc_hc_credit"] = b["eoc_credit"]
            b["cash_deposit_non_eligible"] = weighted(t.amount, (1 - elig) * pred.p("C03"))
            for bucket, rs in CREDIT_BUCKETS.items():
                b[bucket] = weighted(t.amount, pred.p(*rs))
        else:
            p_op = 0.0
            b["gross_debits"] = t.amount
            for bucket, rs in DEBIT_BUCKETS.items():
                b[bucket] = weighted(t.amount, pred.p(*rs))
            core = pred.p("D01", "D02", "D03", "D04", "D05", "D06")
            if income.statutory_in_cor:
                core += pred.p("D07")
            if income.include_bank_fees_in_cor:
                core += pred.p("D18")
            if income.business_cash_withdrawal_in_cor:
                core += pred.p("D16")
            if t.transaction_id in non_recurring:
                b["non_recurring_cor"] = weighted(t.amount, core)
            else:
                b["cor_debit"] = weighted(t.amount, core)
        ledger[t.transaction_id] = LedgerLine(t.transaction_id, t.account_id, t.booking_date, t.is_credit,
                                              t.amount, p_op, uncertainty, b)
    return ledger


def _sum_lines(lines: list[LedgerLine]) -> dict[str, Decimal]:
    totals = {k: ZERO for k in ALL_BUCKETS}
    for ln in lines:
        for k, v in ln.buckets.items():
            totals[k] += v
    retained_pass_through = max(ZERO, totals["pass_through_in"] - totals["pass_through_out"])
    totals["retained_pass_through"] = retained_pass_through
    totals["eoc"] = totals["eoc_credit"] + retained_pass_through
    totals["eoc_hc"] = totals["eoc_hc_credit"]
    totals["cor"] = totals["cor_debit"]
    totals["roc"] = totals["eoc"] - totals["cor"]
    totals["debt_service"] = totals["debt_interest"] + totals["debt_principal"]
    return totals


def _window(label: str, lines: list[LedgerLine], start: date, end: date, stmt_start: date, stmt_end: date,
            predictions, hypotheses, cluster_stats) -> WindowAggregate:
    eff_start, eff_end = max(start, stmt_start), min(end, stmt_end)
    covered = max(0, (eff_end - eff_start).days + 1)
    in_window = [ln for ln in lines if start <= ln.booking_date <= end]
    totals = _sum_lines(in_window)
    months = covered / DAYS_PER_MONTH
    w = WindowAggregate(label, start, end, covered, months, totals)
    w.inflow = compute_inflow_features(in_window, predictions, hypotheses, cluster_stats, totals["eoc"],
                                       totals["eoc_hc"], totals["gross_credits"])
    w.outflow = compute_outflow_features(in_window, totals, months, hypotheses, cluster_stats, totals["gross_debits"])
    return w


def _calendar_months(start: date, end: date):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        first = date(y, m, 1)
        last = date(y, m, calendar.monthrange(y, m)[1])
        yield f"{y:04d}-{m:02d}", first, last
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def aggregate_windows(txns: list[Transaction], predictions: dict[str, RolePrediction],
                      hypotheses: dict[str, EntityHypothesis], cluster_stats: dict[str, ClusterStatistics],
                      cash_eligibility: dict[str, float], as_of: date, statement_start: date, statement_end: date,
                      windows_days: tuple[int, ...], income: IncomeParameters, roles: RoleParameters) -> AccountFeatures:
    ledger = build_economic_ledger(txns, predictions, cash_eligibility, income, roles,
                                   non_recurring_outflow_ids(txns, predictions, hypotheses, cluster_stats))
    lines = sorted(ledger.values(), key=lambda ln: ln.booking_date)
    anchor = min(as_of, statement_end)

    windows = {}
    for d in windows_days:
        start = anchor - timedelta(days=d - 1)
        windows[f"{d}D"] = _window(f"{d}D", lines, start, anchor, statement_start, statement_end,
                                   predictions, hypotheses, cluster_stats)
    full = _window("FULL", lines, statement_start, anchor, statement_start, statement_end,
                   predictions, hypotheses, cluster_stats)

    monthly = []
    for label, first, last in _calendar_months(statement_start, anchor):
        eff_first, eff_last = max(first, statement_start), min(last, anchor)
        coverage = ((eff_last - eff_first).days + 1) / ((last - first).days + 1)
        totals = _sum_lines([ln for ln in lines if first <= ln.booking_date <= last])
        monthly.append(MonthlyAggregate(label, first, last, coverage, totals))

    eoc_by_account: dict[str, Decimal] = {}
    cor_by_account: dict[str, Decimal] = {}
    for ln in lines:
        eoc_by_account[ln.account_id] = eoc_by_account.get(ln.account_id, ZERO) + ln.buckets["eoc_credit"]
        cor_by_account[ln.account_id] = cor_by_account.get(ln.account_id, ZERO) + ln.buckets["cor_debit"]

    return AccountFeatures(
        as_of=anchor,
        statement_start=statement_start,
        statement_end=statement_end,
        history_months=full.months,
        windows=windows,
        monthly=monthly,
        full_period=full,
        eoc_by_account=eoc_by_account,
        cor_by_account=cor_by_account,
        ledger=ledger,
    )

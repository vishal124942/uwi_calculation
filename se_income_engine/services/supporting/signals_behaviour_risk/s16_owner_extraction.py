"""Section 16.1 - Owner extraction (OWN01-OWN08). Corroborates, never defines, income."""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from se_income_engine.common.money import ZERO, weighted
from se_income_engine.common.stats import mad, median, safe_div
from se_income_engine.contracts.account import Transaction
from se_income_engine.contracts.role import RolePrediction
from se_income_engine.services.supporting.ledger_operating_cash.s10_s11_window_aggregation import AccountFeatures


@dataclass
class OwnerExtractionResult:
    features: dict[str, float | None]
    owner_draw_monthly: Decimal


class _DailyPrefix:
    """Cumulative daily sums for O(log n) window queries."""

    def __init__(self, daily: dict[date, Decimal]):
        self.days = sorted(daily)
        self.cum = []
        acc = ZERO
        for d in self.days:
            acc += daily[d]
            self.cum.append(acc)

    def sum_between(self, start: date, end_exclusive: date) -> Decimal:
        lo = bisect.bisect_left(self.days, start)
        hi = bisect.bisect_left(self.days, end_exclusive)
        if hi <= lo:
            return ZERO
        return self.cum[hi - 1] - (self.cum[lo - 1] if lo > 0 else ZERO)


def compute_owner_extraction(txns: list[Transaction], predictions: dict[str, RolePrediction],
                             af: AccountFeatures) -> OwnerExtractionResult:
    monthly = [float(m.totals["owner_draw"]) for m in af.monthly if m.complete]
    complete_months = max(1, len(monthly))
    eoc_monthly = median([float(m.totals["eoc"]) for m in af.monthly if m.complete]) or 0.0
    materiality = max(1000.0, 0.02 * eoc_monthly)

    op_daily: dict[date, Decimal] = {}
    fin_daily: dict[date, Decimal] = {}
    balances: dict[str, list[tuple[date, int, Decimal]]] = {}
    for t in txns:
        ln = af.ledger[t.transaction_id]
        if t.is_credit:
            op_daily[t.booking_date] = op_daily.get(t.booking_date, ZERO) + ln.buckets["eoc_credit"]
            fin_daily[t.booking_date] = fin_daily.get(t.booking_date, ZERO) + ln.buckets["financing_in"]
        if t.balance_after is not None:
            balances.setdefault(t.account_id, []).append((t.booking_date, t.sequence_no, t.balance_after))
    op_prefix, fin_prefix = _DailyPrefix(op_daily), _DailyPrefix(fin_daily)
    for series in balances.values():
        series.sort()

    supported = total_draw = ZERO
    liquidity_deltas = []
    for t in txns:
        if t.is_credit:
            continue
        p_draw = predictions[t.transaction_id].p("D12")
        if p_draw < 0.3:
            continue
        draw = weighted(t.amount, p_draw)
        start = t.booking_date - timedelta(days=30)
        op_in = op_prefix.sum_between(start, t.booking_date)
        fin_in = fin_prefix.sum_between(start, t.booking_date)
        share = op_in / (op_in + fin_in) if (op_in + fin_in) > 0 else Decimal("0.5")
        supported += draw * share
        total_draw += draw
        series = balances.get(t.account_id)
        if t.balance_before and series:
            horizon = t.booking_date + timedelta(days=7)
            idx = bisect.bisect_right(series, (horizon, 10 ** 12, Decimal("Infinity"))) - 1
            if idx >= 0 and series[idx][0] > t.booking_date:
                liquidity_deltas.append(float((series[idx][2] - t.balance_before) / abs(t.balance_before)))

    features = {
        "OWN01_ExpectedOwnerDraw": float(af.full_period.totals["owner_draw"]),
        "OWN02_OwnerDrawMedianMonthly": median(monthly),
        "OWN03_OwnerDrawMAD": mad(monthly),
        "OWN04_OwnerDrawActiveMonths": safe_div(sum(1 for v in monthly if v >= materiality), complete_months, None),
        "OWN05_OwnerDrawFundingQuality": safe_div(float(supported), float(total_draw), None),
        "OWN06_DrawToSBCIRatio": None,  # filled after SBCI
        "OWN07_PostDrawLiquidityChange": median(liquidity_deltas),
        "OWN08_UnsustainableDrawFlag": None,  # filled after SBCI
    }
    owner_monthly = Decimal(repr(median(monthly) or 0.0)).quantize(Decimal("0.01"))
    return OwnerExtractionResult(features, owner_monthly)


def finalise_owner_against_sbci(owner: OwnerExtractionResult, af: AccountFeatures, sbci: Decimal) -> None:
    sbci_f = float(sbci)
    owner.features["OWN06_DrawToSBCIRatio"] = safe_div(float(owner.owner_draw_monthly), sbci_f, None)
    monthly = [float(m.totals["owner_draw"]) for m in af.monthly if m.complete]
    owner.features["OWN08_UnsustainableDrawFlag"] = float(
        sbci_f > 0 and sum(1 for v in monthly if v > 1.25 * sbci_f) >= 3)

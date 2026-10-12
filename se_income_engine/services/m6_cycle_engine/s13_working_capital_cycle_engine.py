"""Section 13 - Working-capital and cash-cycle engine (M6 Cycle engine), WC01-WC14.

A peak lag is a behavioural cash-cycle proxy, not accounting inventory or receivable days. When evidence
is insufficient the engine returns WEAK_OR_UNIDENTIFIED - never a forced 30-day default.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from se_income_engine.common.stats import DAYS_PER_MONTH, clamp, mean, median, safe_div, spearman, stdev
from se_income_engine.config.parameters import CycleParameters
from se_income_engine.contracts.enums import CycleStatus
from se_income_engine.services.supporting.ledger_operating_cash.s10_s11_window_aggregation import AccountFeatures
from se_income_engine.versions import COMPONENT_VERSIONS


@dataclass
class CycleResult:
    status: CycleStatus
    features: dict[str, float | None]
    lag_profile_out_to_in: dict[int, float | None]
    lag_profile_in_to_out: dict[int, float | None]
    conversion_ratio: float | None
    build_normalisation_amount: Decimal = Decimal("0")
    liquidation_normalisation_amount: Decimal = Decimal("0")
    phase_start: date | None = None
    phase_end: date | None = None
    normal_monthly_eoc: float = 0.0
    model_version: str = COMPONENT_VERSIONS["cycle_logic"]
    notes: list[str] = field(default_factory=list)


def _daily_series(af: AccountFeatures) -> tuple[list[date], list[float], list[float], list[float]]:
    days = [af.statement_start + timedelta(days=i) for i in range((af.as_of - af.statement_start).days + 1)]
    idx = {d: i for i, d in enumerate(days)}
    oi, do, fo = [0.0] * len(days), [0.0] * len(days), [0.0] * len(days)
    for ln in af.ledger.values():
        i = idx.get(ln.booking_date)
        if i is None:
            continue
        b = ln.buckets
        oi[i] += float(b["eoc_credit"])
        do[i] += float(b["direct_cost"] + b["logistics"])
        fo[i] += float(b["payroll"] + b["rent"] + b["utilities"] + b["other_opex"] + b["statutory"])
    return days, oi, do, fo


def _weekly(series: list[float]) -> list[float]:
    """Weeks aligned to end on the as-of date; a leading partial week is dropped."""
    start = len(series) % 7
    return [sum(series[i:i + 7]) for i in range(start, len(series), 7)]


def _lag_profile(x: list[float], y: list[float], max_lag: int) -> dict[int, float | None]:
    out = {}
    for lag in range(max_lag + 1):
        if len(x) - lag < 6:
            out[lag] = None
            continue
        out[lag] = spearman(x[: len(x) - lag], y[lag:])
    return out


def _qualified_peak(profile: dict[int, float | None], p: CycleParameters) -> tuple[int | None, float | None, float | None]:
    valid = {k: v for k, v in profile.items() if v is not None}
    if not valid:
        return None, None, None
    lag = max(valid, key=valid.get)
    strength = valid[lag]
    neighbours = [valid[k] for k in (lag - 2, lag - 1, lag + 1, lag + 2) if k in valid]
    prominence = strength - (mean(neighbours) if neighbours else 0.0)
    if strength < p.min_strength or (neighbours and prominence < p.min_prominence):
        return None, strength, prominence
    return lag, strength, prominence


def _max_drawdown(net: list[float]) -> float:
    cum = peak = worst = 0.0
    for v in net:
        cum += v
        peak = max(peak, cum)
        worst = max(worst, peak - cum)
    return worst


def infer_operating_cycle(af: AccountFeatures, financing_events: list[tuple[date, float]], archetype_code: str,
                          p: CycleParameters) -> CycleResult:
    days, oi, do, fo = _daily_series(af)
    w_oi, w_do = _weekly(oi), _weekly(do)
    nonzero = min(sum(1 for v in w_oi if v > 0), sum(1 for v in w_do if v > 0))
    out_in = _lag_profile(w_do, w_oi, p.max_lag_weeks)
    in_out = _lag_profile(w_oi, w_do, p.max_lag_weeks)

    enough = nonzero >= p.min_nonzero_periods
    lag_oi, strength, prominence = _qualified_peak(out_in, p) if enough else (None, None, None)
    lag_io, strength_io, _ = _qualified_peak(in_out, p) if enough else (None, None, None)
    status = CycleStatus.IDENTIFIED if lag_oi is not None else CycleStatus.WEAK_OR_UNIDENTIFIED

    half = len(w_do) // 2
    stability = None
    if lag_oi is not None and half >= 8:
        l1, *_ = _qualified_peak(_lag_profile(w_do[:half], w_oi[:half], min(p.max_lag_weeks, half - 6)), p)
        l2, *_ = _qualified_peak(_lag_profile(w_do[half:], w_oi[half:], min(p.max_lag_weeks, half - 6)), p)
        if l1 is not None and l2 is not None:
            stability = 1 - abs(l1 - l2) / max(1, p.max_lag_weeks)

    total_oi, total_do = sum(oi), sum(do)
    conversion = safe_div(total_oi, total_do, None) if total_do > 0 else None
    complete_eoc = [float(m.totals["eoc"]) for m in af.monthly if m.complete]
    normal_eoc = median(complete_eoc) or (total_oi / max(af.history_months, 1e-9) if af.history_months else 0.0)

    quarter_conv = []
    for i in range(0, len(days), 91):
        s_do = sum(do[i:i + 91])
        if s_do > 0:
            quarter_conv.append(sum(oi[i:i + 91]) / s_do)
    conv_consistency = None
    if len(quarter_conv) >= 2 and mean(quarter_conv):
        conv_consistency = clamp(1 - (stdev(quarter_conv) or 0.0) / mean(quarter_conv))

    result = CycleResult(status, {}, out_in, in_out, conversion, normal_monthly_eoc=normal_eoc or 0.0)
    lag_days = lag_oi * 7 if lag_oi is not None else None
    build_score = liquidation_score = None
    if status == CycleStatus.IDENTIFIED and conversion and 1.0 <= conversion <= 3.0 and normal_eoc:
        r = max(lag_days, 14)
        oi_r, do_r = sum(oi[-r:]), sum(do[-r:])
        expected_future_collection = conversion * do_r
        build_score = clamp(max(0.0, expected_future_collection - oi_r) / normal_eoc, 0.0, p.score_cap)
        liquidation_score = clamp(max(0.0, oi_r - expected_future_collection) / normal_eoc, 0.0, p.score_cap)
        cap = p.adjustment_cap_fraction_of_eoc * normal_eoc * (r / DAYS_PER_MONTH)
        excess_outflow = max(0.0, do_r - oi_r / conversion)
        excess_collection = max(0.0, oi_r - conversion * do_r)
        result.build_normalisation_amount = Decimal(str(round(min(cap, excess_outflow), 2)))
        result.liquidation_normalisation_amount = Decimal(str(round(min(cap, excess_collection / conversion), 2)))
        result.phase_start, result.phase_end = days[-r], days[-1]
    elif status == CycleStatus.IDENTIFIED:
        result.notes.append("Cycle identified but conversion ratio outside guarded range; no normalisation applied")
    if lag_oi == 0:
        result.notes.append("Peak lag below weekly resolution: contemporaneous purchase/collection turnover")

    monthly_do = [float(m.totals["direct_cost"] + m.totals["logistics"]) for m in af.monthly if m.complete]
    recent_do = sum(do[-30:])
    recent_oi = sum(oi[-30:])
    net = [do[i] + fo[i] - oi[i] for i in range(len(days))]
    day_idx = {d: i for i, d in enumerate(days)}
    funded = 0.0
    for d, amt in financing_events:
        i = day_idx.get(d)
        if i is not None and sum(net[i:i + 30]) > 0:
            funded += amt
    total_cor = float(af.full_period.totals["cor"])
    history_q = clamp(af.history_months / 12.0)
    signal_q = clamp((strength or 0.0) / 0.6)
    nonzero_q = clamp(nonzero / max(1, len(w_do)))
    result.features = {
        "WC01_PeakOutflowToInflowLag": float(lag_days) if lag_days is not None else None,
        "WC02_PeakInflowToOutflowLag": float(lag_io * 7) if lag_io is not None else None,
        "WC03_CycleCorrelation": strength,
        "WC04_CycleProminence": prominence,
        "WC05_CycleStability": stability,
        "WC06_BuildScore": build_score,
        "WC07_LiquidationScore": liquidation_score,
        "WC08_CycleAdjustedROC": None,  # filled by income normalisation
        "WC09_OperatingLiquidityNeed": _max_drawdown(net[-365:]),
        "WC10_ExternalFundingDuringCycle": safe_div(funded, total_cor, None),
        "WC11_PurchaseSurgeIndex": safe_div(recent_do, median(monthly_do) or 0.0, None),
        "WC12_CollectionSurgeIndex": safe_div(recent_oi, normal_eoc or 0.0, None),
        "WC13_ConversionConsistency": conv_consistency,
        "WC14_CycleEvidenceQuality": (history_q + signal_q + nonzero_q) / 3.0,
    }
    return result

"""Section 18 - Trend, seasonality and stability (TR01-TR12) with asymmetric trend treatment (18.2)."""

from __future__ import annotations

from dataclasses import dataclass

from se_income_engine.common.stats import clamp, mad, median, quantile, safe_div, theil_sen_slope
from se_income_engine.config.parameters import TrendParameters
from se_income_engine.contracts.enums import TrendRegime
from se_income_engine.services.step06_aggregation_archetype_cash.s10_s11_window_aggregation import AccountFeatures
from se_income_engine.services.step07_risk_signals.s14_balance_liquidity_engine import LiquidityResult


@dataclass
class TrendResult:
    regime: TrendRegime
    features: dict[str, float | None]


def _monthly_equivalent(af: AccountFeatures, window: str, key: str) -> float | None:
    w = af.windows.get(window)
    if not w or w.months <= 0:
        return None
    return float(w.totals[key]) / w.months


def compute_trend_seasonality(af: AccountFeatures, liquidity: LiquidityResult, p: TrendParameters) -> TrendResult:
    months = [m for m in af.monthly if m.complete]
    eoc = [float(m.totals["eoc"]) for m in months]
    cor = [float(m.totals["cor"]) for m in months]
    roc = [e - c for e, c in zip(eoc, cor)]
    xs = list(range(len(months)))

    eoc_ratio = safe_div(_monthly_equivalent(af, "90D", "eoc"), _monthly_equivalent(af, "365D", "eoc"), None)
    cor_ratio = safe_div(_monthly_equivalent(af, "90D", "cor"), _monthly_equivalent(af, "365D", "cor"), None)
    roc90, roc365 = _monthly_equivalent(af, "90D", "roc"), _monthly_equivalent(af, "365D", "roc")
    roc_ratio = safe_div(roc90, roc365, None) if roc365 and roc365 > 0 else None

    worst90 = None
    if len(roc) >= 3:
        worst90 = min(sum(roc[i:i + 3]) / 3.0 for i in range(len(roc) - 2))

    seasonality = None
    if len(months) >= p.seasonality_min_months:
        by_month: dict[int, list[float]] = {}
        for m, v in zip(months, eoc):
            by_month.setdefault(m.start.month, []).append(v)
        overall = median(eoc) or 0.0
        if overall:
            deviations = [abs(median(v) - overall) / overall for v in by_month.values() if len(v) >= 2]
            seasonality = clamp(median(deviations) or 0.0)

    ratios = [r for r in (eoc_ratio, roc_ratio) if r is not None]
    worst_ratio = min(ratios) if ratios else None
    deterioration = clamp((1.0 - worst_ratio) / 0.5) if worst_ratio is not None and worst_ratio < 1.0 else 0.0

    growth = 0.0
    if eoc_ratio is not None and eoc_ratio >= p.growth_threshold and eoc:
        base = median(eoc) or 0.0
        streak = 0
        for v in reversed(eoc):
            if v > base * p.growth_threshold:
                streak += 1
            else:
                break
        inputs_up = 1.0 if cor_ratio is not None and cor_ratio > 1.0 else 0.0
        bal_trend = liquidity.features.get("BAL10_BalanceTrend90")
        balance_ok = 1.0 if bal_trend is not None and bal_trend >= 0 else 0.0
        growth = clamp(streak / p.growth_min_months) * (0.5 + 0.25 * inputs_up + 0.25 * balance_ok)

    if len(months) < 3:
        regime = TrendRegime.INSUFFICIENT_HISTORY
    elif worst_ratio is not None and worst_ratio < p.decline_threshold:
        regime = TrendRegime.DECLINE
    elif eoc_ratio is not None and eoc_ratio >= p.growth_threshold:
        regime = TrendRegime.GROWTH_CORROBORATED if growth >= 0.75 else TrendRegime.GROWTH_UNCORROBORATED
    else:
        regime = TrendRegime.STABLE

    features = {
        "TR01_EOC_3m_vs_12m": eoc_ratio,
        "TR02_COR_3m_vs_12m": cor_ratio,
        "TR03_ROC_3m_vs_12m": roc_ratio,
        "TR04_RobustEOCSlope": theil_sen_slope(xs, eoc) if len(eoc) >= 3 else None,
        "TR05_RobustROCSlope": theil_sen_slope(xs, roc) if len(roc) >= 3 else None,
        "TR06_PositiveROCMonthRatio": safe_div(sum(1 for v in roc if v > 0), len(roc), None),
        "TR07_ROCMAD": mad(roc),
        "TR08_ROCDownsideP20": quantile(roc, 0.2),
        "TR09_WorstRolling90": worst90,
        "TR10_SeasonalityStrength": seasonality,
        "TR11_RecentDeteriorationScore": deterioration,
        "TR12_GrowthEvidenceScore": growth,
        "complete_months": float(len(months)),
    }
    return TrendResult(regime, features)

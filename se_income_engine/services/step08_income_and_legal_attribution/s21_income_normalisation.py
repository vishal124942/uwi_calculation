"""Section 21 - Income normalisation (M7 Income estimator).

ROC_m      = EOC_m - COR_m
CAOCG_m    = ROC_m + build_normalisation_m - liquidation_normalisation_m   (bounded, Section 21.2)
SBCI       = max(0, robust_center - maintenance_capex_reserve + permitted_adjustments)   (Section 21.3)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from se_income_engine.common.money import ZERO, quantize
from se_income_engine.common.stats import (
    DAYS_PER_MONTH,
    huber_location,
    median,
    quantile,
    trimmed_mean,
    weighted_median,
)
from se_income_engine.config.parameters import IncomeParameters, TrendParameters
from se_income_engine.contracts.enums import TrendRegime
from se_income_engine.services.step06_aggregation_archetype_cash.s10_s11_window_aggregation import AccountFeatures
from se_income_engine.services.step07_risk_signals.s13_working_capital_cycle_engine import CycleResult
from se_income_engine.services.step07_risk_signals.s18_trend_seasonality import TrendResult
from se_income_engine.versions import COMPONENT_VERSIONS

ROLLING_WINDOWS = {"rolling_90": "90D", "rolling_180": "180D", "rolling_365": "365D"}


@dataclass
class SeriesPoint:
    label: str
    start: date
    end: date
    value: Decimal
    months: float
    complete: bool


@dataclass
class RocSeries:
    monthly: list[SeriesPoint]
    rolling: dict[str, SeriesPoint]
    basis: SeriesPoint  # full observation period, monthly-equivalent


@dataclass
class CaocgSeries:
    monthly: list[SeriesPoint]
    rolling: dict[str, SeriesPoint]
    basis: SeriesPoint
    cycle_adjustment_basis_monthly: Decimal
    seasonality_applied: bool
    notes: list[str] = field(default_factory=list)


@dataclass
class SbciResult:
    sbci_monthly: Decimal
    robust_center: Decimal
    maintenance_capex_reserve: Decimal
    permitted_adjustments: Decimal
    estimator: str
    trend_regime: TrendRegime
    candidates: list[dict]
    roc_basis_monthly: Decimal
    caocg_basis_monthly: Decimal
    cycle_adjustment_basis_monthly: Decimal
    model_version: str = COMPONENT_VERSIONS["income_model"]
    features: dict[str, float | None] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def reconstruct_operating_cash_generation(af: AccountFeatures) -> RocSeries:
    monthly = [SeriesPoint(m.month, m.start, m.end, m.totals["roc"], m.coverage, m.complete) for m in af.monthly]
    rolling = {}
    for name, key in ROLLING_WINDOWS.items():
        w = af.windows.get(key)
        if w and w.months > 0:
            rolling[name] = SeriesPoint(name, w.start, w.end, quantize(w.monthly("roc")), w.months, True)
    full = af.full_period
    basis = SeriesPoint("full_period", full.start, full.end, quantize(full.monthly("roc")), full.months, True)
    return RocSeries(monthly, rolling, basis)


def _overlap_days(a_start: date, a_end: date, b_start: date, b_end: date) -> int:
    return max(0, (min(a_end, b_end) - max(a_start, b_start)).days + 1)


def normalize_cycle_and_seasonality(roc: RocSeries, cycle: CycleResult, trend: TrendResult,
                                    af: AccountFeatures) -> CaocgSeries:
    net = cycle.build_normalisation_amount - cycle.liquidation_normalisation_amount
    notes: list[str] = []
    phase = (cycle.phase_start, cycle.phase_end) if cycle.phase_start and net != ZERO else None
    phase_days = _overlap_days(*phase, *phase) if phase else 0

    def adjust(point: SeriesPoint, as_monthly_equivalent: bool) -> SeriesPoint:
        if not phase:
            return point
        share = Decimal(_overlap_days(point.start, point.end, *phase)) / Decimal(phase_days)
        amount = net * share
        if as_monthly_equivalent and point.months > 0:
            amount = amount / Decimal(repr(point.months))
        return SeriesPoint(point.label, point.start, point.end, quantize(point.value + amount), point.months,
                           point.complete)

    monthly = [adjust(p, False) for p in roc.monthly]
    rolling = {k: adjust(p, True) for k, p in roc.rolling.items()}
    basis = adjust(roc.basis, True)

    seasonality_applied = False
    strength = trend.features.get("TR10_SeasonalityStrength")
    if strength is not None and strength >= 0.2:
        complete = [p for p in monthly if p.complete]
        overall = median([float(p.value) for p in complete]) or 0.0
        by_month: dict[int, list[float]] = {}
        for p in complete:
            by_month.setdefault(p.start.month, []).append(float(p.value))
        if overall > 0:
            index = {m: (median(v) or overall) / overall for m, v in by_month.items()}
            monthly = [SeriesPoint(p.label, p.start, p.end,
                                   quantize(p.value / Decimal(repr(index.get(p.start.month, 1.0) or 1.0))),
                                   p.months, p.complete) for p in monthly]
            seasonality_applied = True
            notes.append("Seasonal index normalisation applied to monthly CAOCG")
    else:
        notes.append("Seasonality not normalised: insufficient comparable seasonal history")
    if phase:
        notes.append(f"Cycle normalisation {float(net):+.2f} over {phase[0]}..{phase[1]}")
    return CaocgSeries(monthly, rolling, basis, quantize(basis.value - roc.basis.value), seasonality_applied, notes)


def _robust_center(values: list[float], weights: list[float], p: IncomeParameters) -> float | None:
    if p.robust_estimator == "weighted_median":
        return weighted_median(values, weights)
    expanded = [v for v, w in zip(values, weights) for _ in range(max(1, round(w * 2)))]
    if p.robust_estimator == "trimmed_mean":
        return trimmed_mean(expanded, p.trimmed_mean_fraction)
    if p.robust_estimator == "huber":
        return huber_location(expanded, p.huber_k)
    if p.robust_estimator == "conservative_quantile":
        return quantile(expanded, p.conservative_quantile)
    raise ValueError(f"Unknown robust estimator {p.robust_estimator!r}")


def maintenance_capex_reserve(af: AccountFeatures, p: IncomeParameters) -> Decimal:
    """Section 21.4: recurring maintenance per month; one-off maintenance normalised over the horizon."""
    lines = [ln.buckets["maintenance_capex"] for ln in af.ledger.values() if ln.buckets["maintenance_capex"] > 0]
    total = sum(lines, ZERO)
    if total == ZERO:
        return ZERO
    months = af.full_period.months
    divisor = months if len(lines) >= 3 else max(months, float(p.maintenance_capex_horizon_months))
    return quantize(total / Decimal(repr(divisor)))


def sustainable_income_model(caocg: CaocgSeries, roc: RocSeries, af: AccountFeatures, trend: TrendResult,
                             p: IncomeParameters, tp: TrendParameters,
                             permitted_adjustments: Decimal = ZERO) -> SbciResult:
    regime = trend.regime
    candidates: list[dict] = []
    complete = [pt for pt in caocg.monthly if pt.complete]
    recent_labels = {pt.label for pt in complete[-3:]}
    for pt in complete:
        w = p.candidate_weights["monthly"]
        if regime == TrendRegime.DECLINE and pt.label in recent_labels:
            w *= tp.decline_recent_weight
        candidates.append({"series": "cycle_adjusted_monthly_ROC", "label": pt.label, "value": float(pt.value), "weight": w})
    for name, pt in caocg.rolling.items():
        window_days = int(ROLLING_WINDOWS[name][:-1])
        coverage = min(1.0, pt.months * DAYS_PER_MONTH / window_days)
        w = p.candidate_weights[name] * coverage
        if regime == TrendRegime.DECLINE and name == "rolling_90":
            w *= tp.decline_recent_weight
        candidates.append({"series": f"{name}_monthly_equivalent", "label": name, "value": float(pt.value), "weight": w})

    notes = []
    center = _robust_center([c["value"] for c in candidates], [c["weight"] for c in candidates], p)
    if center is None:
        center = float(caocg.basis.value)
        notes.append("No candidate series: basis CAOCG used")
    if regime == TrendRegime.GROWTH_UNCORROBORATED:
        cap_point = caocg.rolling.get(tp.growth_cap_window) or caocg.basis
        if center > float(cap_point.value):
            notes.append(f"Uncorroborated growth capped at {cap_point.label}")
            center = float(cap_point.value)

    reserve = maintenance_capex_reserve(af, p)
    center_d = quantize(Decimal(repr(center)))
    sbci = max(ZERO, center_d - reserve + permitted_adjustments)

    monthly_vals = [float(pt.value) for pt in complete]
    features = {
        "F041_ROC": float(roc.basis.value),
        "F042_ROC_MARGIN": float(roc.basis.value) / float(af.full_period.monthly("eoc")) if af.full_period.monthly("eoc") else None,
        "F045_ROC_P20": quantile(monthly_vals, 0.2),
        "F046_WORST_90": min((sum(monthly_vals[i:i + 3]) / 3 for i in range(len(monthly_vals) - 2)), default=None),
        "F058_CAOCG": float(caocg.basis.value),
    }
    return SbciResult(
        sbci_monthly=quantize(sbci),
        robust_center=center_d,
        maintenance_capex_reserve=reserve,
        permitted_adjustments=permitted_adjustments,
        estimator=p.robust_estimator,
        trend_regime=regime,
        candidates=candidates,
        roc_basis_monthly=roc.basis.value,
        caocg_basis_monthly=caocg.basis.value,
        cycle_adjustment_basis_monthly=caocg.cycle_adjustment_basis_monthly,
        features=features,
        notes=notes + caocg.notes,
    )

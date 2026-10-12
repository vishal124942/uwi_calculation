"""Section 22 - Uncertainty and confidence framework (M8 Uncertainty model).

Confidence dimensions CF01-CF10, amount-weighted role entropy (22.2) and prediction intervals (22.3).
Intervals use a segment-calibrated conformal artifact when one is supplied; otherwise a deterministic
month-block bootstrap, explicitly labelled as uncalibrated.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from decimal import Decimal

from se_income_engine.common.money import ZERO, quantize
from se_income_engine.common.stats import clamp, mad, median, quantile, safe_div, trimmed_mean
from se_income_engine.config.parameters import UncertaintyParameters
from se_income_engine.contracts.account import Transaction
from se_income_engine.contracts.enums import CoverageRisk
from se_income_engine.contracts.role import RolePrediction
from se_income_engine.versions import COMPONENT_VERSIONS


@dataclass(frozen=True)
class ConformalArtifact:
    """Relative residual quantiles calibrated on trusted income anchors, keyed by segment
    (archetype | history band | account type | coverage band)."""

    artifact_id: str
    relative_quantiles: dict[str, tuple[float, float]]

    def lookup(self, segment: str) -> tuple[float, float] | None:
        return self.relative_quantiles.get(segment)


@dataclass
class UncertaintyResult:
    confidence: float
    dimensions: dict[str, float]
    amount_weighted_role_uncertainty: float
    central: Decimal
    lower: Decimal
    upper: Decimal
    interval_method: str
    segment: str
    unresolved_outflow_allowance: Decimal = ZERO
    unresolved_inflow_allowance: Decimal = ZERO
    model_version: str = COMPONENT_VERSIONS["uncertainty_model"]
    notes: list[str] = field(default_factory=list)
    lower_before_allowance: Decimal | None = None
    upper_before_allowance: Decimal | None = None
    distribution: list[float] = field(default_factory=list, repr=False)


def unresolved_flow_allowances(full_period_totals: dict[str, Decimal], months: float) -> tuple[Decimal, Decimal]:
    """Section 22.2: monthly unknown-role mass that could be operating, allocated in the same proportion as the
    resolved flows. Unknown debits are excluded from COR (Section 11.1) and unknown credits from EOC, so the
    downside allowance widens the lower bound and the upside allowance widens the upper bound."""
    if months <= 0:
        return ZERO, ZERO
    t = full_period_totals
    m = Decimal(repr(months))
    resolved_debits = t["gross_debits"] - t["unknown_out"]
    resolved_credits = t["gross_credits"] - t["unknown_in"]
    cor_share = t["cor"] / resolved_debits if resolved_debits > 0 else Decimal("1")
    eoc_share = t["eoc"] / resolved_credits if resolved_credits > 0 else ZERO
    downside = t["unknown_out"] * min(Decimal("1"), cor_share) + t["non_recurring_cor"]
    return quantize(downside / m), quantize(t["unknown_in"] * min(Decimal("1"), eoc_share) / m)


def amount_weighted_role_uncertainty(txns: list[Transaction], predictions: dict[str, RolePrediction]) -> float:
    total = sum(float(t.amount) for t in txns)
    if not total:
        return 1.0
    def uncertainty(pred: RolePrediction) -> float:
        return max(pred.entropy, pred.p("C13", "D19"))

    return sum(float(t.amount) * uncertainty(predictions[t.transaction_id]) for t in txns) / total


def history_sufficiency(months: float) -> float:
    if months < 3:
        return 0.1
    if months < 6:
        return 0.3 + 0.1 * (months - 3)
    if months < 12:
        return 0.6 + (months - 6) * 0.4 / 6
    return 1.0


def _history_band(months: float) -> str:
    return "LT6" if months < 6 else "6TO12" if months < 12 else "GE12"


def _moving_block_bootstrap(monthly: list[float], p: UncertaintyParameters) -> list[float]:
    """Moving-block bootstrap of the trimmed-mean month: contiguous blocks keep payment-calendar effects
    (e.g. 4- vs 5-week months) and serial correlation together instead of treating months as independent."""
    rng = random.Random(p.bootstrap_seed)
    n = len(monthly)
    block = max(1, min(p.bootstrap_block_months, n))
    starts = n - block + 1
    out = []
    for _ in range(p.bootstrap_iterations):
        sample: list[float] = []
        while len(sample) < n:
            s = rng.randrange(starts)
            sample.extend(monthly[s:s + block])
        out.append(trimmed_mean(sample[:n], p.bootstrap_trim_fraction))
    return out


def uncertainty_model(*, sbci: Decimal, monthly_caocg: list[float], dq_metrics: dict, history_months: float,
                      role_uncertainty: float, trend_features: dict, coverage_risk: CoverageRisk,
                      cycle_quality: float | None, archetype_code: str, archetype_probability: float,
                      financing_ratio: float, financing_contamination: float | None, cross_view: float,
                      legal_confidence: float, account_type: str, lower_q: float, upper_q: float,
                      p: UncertaintyParameters, conformal: ConformalArtifact | None = None,
                      unresolved_outflow: Decimal = ZERO, unresolved_inflow: Decimal = ZERO) -> UncertaintyResult:
    recon = dq_metrics.get("DQ02_TxnReconciliationPassRate")
    cf01 = clamp((recon if recon is not None else 0.7) * dq_metrics.get("DQ12_SourceReliabilityClass", 0.7)
                 * (1 - dq_metrics.get("DQ07_ParseLowConfidenceRate", 0.0)) * dq_metrics.get("DQ01_StatementCoverageDays", 1.0))
    med = median(monthly_caocg)
    spread = mad(monthly_caocg)
    pos_ratio = trend_features.get("TR06_PositiveROCMonthRatio")
    stability = 1.0 / (1.0 + safe_div(spread or 0.0, abs(med), 1.0)) if med else 0.2
    cf04 = clamp(stability * (pos_ratio if pos_ratio is not None else 0.5) ** 0.5)
    cf05 = {CoverageRisk.LOW: 0.9, CoverageRisk.MEDIUM: 0.65, CoverageRisk.HIGH: 0.35,
            CoverageRisk.INDETERMINATE: 0.2}[coverage_risk]
    cf06 = clamp(cycle_quality if cycle_quality is not None else 0.5)
    if archetype_code in ("A03", "A08"):
        cf06 = max(0.6, cf06)
    contamination = clamp(financing_contamination) if financing_contamination is not None else 0.0
    cf07 = clamp(1.0 - max(clamp(financing_ratio / 0.5), contamination * 0.5))

    dims = {
        "CF01_DataIntegrity": cf01,
        "CF02_HistorySufficiency": history_sufficiency(history_months),
        "CF03_RoleCertainty": clamp(1.0 - role_uncertainty),
        "CF04_OperatingStability": cf04,
        "CF05_CoverageRisk": cf05,
        "CF06_CycleEvidence": cf06,
        "CF07_FinancingContamination": cf07,
        "CF08_CrossViewConsistency": clamp(cross_view),
        "CF09_ArchetypeConfidence": clamp(archetype_probability),
        "CF10_LegalAttributionConfidence": clamp(legal_confidence),
    }
    weights = p.confidence_weights
    log_sum = sum(weights[k[:4]] * math.log(max(0.01, v)) for k, v in dims.items())
    confidence = math.exp(log_sum / sum(weights.values()))

    segment = f"{archetype_code}|{_history_band(history_months)}|{account_type}|{coverage_risk.value}"
    central = sbci
    notes = []
    calibrated = conformal.lookup(segment) if conformal else None
    if calibrated:
        lo_rel, hi_rel = calibrated
        lower = central * Decimal(repr(1 - lo_rel))
        upper = central * Decimal(repr(1 + hi_rel))
        method = f"CONFORMAL:{conformal.artifact_id}"
    elif len(monthly_caocg) >= 3:
        boot = _moving_block_bootstrap(monthly_caocg, p)
        centre_boot = median(boot)
        widen = 1.0 + (1.0 - confidence)
        dist = [float(central) + (b - centre_boot) * widen for b in boot]
        lower = Decimal(repr(quantile(dist, lower_q)))
        upper = Decimal(repr(quantile(dist, upper_q)))
        method = "BOOTSTRAP_UNCALIBRATED"
        notes.append("Interval not calibrated against verified income anchors (Section 22.3)")
    else:
        half = central * Decimal(repr(1.0 - confidence))
        lower, upper = central - half, central + half
        method = "HEURISTIC_UNCALIBRATED"
        notes.append("Fewer than 3 complete months: heuristic interval")
    lower_raw, upper_raw = lower, upper
    if unresolved_outflow > 0 and not calibrated:
        lower -= unresolved_outflow
        notes.append(f"Lower bound includes unresolved-outflow allowance {quantize(unresolved_outflow)}/month")
    if unresolved_inflow > 0 and not calibrated:
        upper += unresolved_inflow
    lower = max(ZERO, min(lower, central))
    upper = max(upper, central)
    return UncertaintyResult(round(confidence, 4), {k: round(v, 4) for k, v in dims.items()},
                             round(role_uncertainty, 4), quantize(central), quantize(lower), quantize(upper),
                             method, segment, quantize(unresolved_outflow), quantize(unresolved_inflow), notes=notes,
                             lower_before_allowance=quantize(lower_raw), upper_before_allowance=quantize(upper_raw),
                             distribution=dist)


def cross_view_consistency(sbci: Decimal, eoc_monthly: Decimal, retention_7d: float | None,
                           balance_trend: float | None, owner_draw_monthly: Decimal,
                           external_coverage: float | None) -> float:
    """Section 14.2 / CF08: agreement of cash-flow, liquidity, owner-draw and external evidence."""
    scores = []
    margin = float(sbci / eoc_monthly) if eoc_monthly else 0.0
    if retention_7d is not None:
        if margin > 0.2 and retention_7d < 0.05 and (balance_trend or 0.0) < 0:
            scores.append(0.3)
        else:
            scores.append(0.8 if retention_7d >= 0.05 or margin <= 0.2 else 0.6)
    if sbci > 0:
        ratio = float(owner_draw_monthly / sbci)
        scores.append(0.9 if 0.3 <= ratio <= 1.5 else 0.6 if ratio < 0.3 else 0.4)
    if external_coverage is not None:
        scores.append(clamp(1.0 - abs(1.0 - external_coverage)))
    return sum(scores) / len(scores) if scores else 0.5

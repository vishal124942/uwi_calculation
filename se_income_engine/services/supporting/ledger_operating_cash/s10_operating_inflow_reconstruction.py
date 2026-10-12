"""Section 10 - Operating inflow reconstruction (EOC and IN01-IN14).

EOC_W = sum_{credits in W} amount_i * p_operating_i
p_operating_i = P(C01) + P(C02) + cash_eligibility_i * P(C03)
"""

from __future__ import annotations

from decimal import Decimal

from se_income_engine.common.money import ZERO
from se_income_engine.common.stats import safe_div, weighted_median
from se_income_engine.contracts.entity import EntityHypothesis
from se_income_engine.contracts.enums import IdentityStatus
from se_income_engine.contracts.role import RolePrediction
from se_income_engine.services.m2_role_classifier.s05_entity_resolution import ClusterStatistics


def p_operating(pred: RolePrediction, cash_eligibility: float) -> float:
    return pred.p("C01", "C02") + cash_eligibility * pred.p("C03")


def is_repeat_cluster(hyp: EntityHypothesis, cs: ClusterStatistics | None) -> bool:
    return bool(cs) and hyp.identity_status != IdentityStatus.UNRESOLVED and cs.count >= 3 and len(cs.active_months) >= 2


def compute_inflow_features(lines: list, predictions: dict[str, RolePrediction],
                            hypotheses: dict[str, EntityHypothesis], cluster_stats: dict[str, ClusterStatistics],
                            eoc: Decimal, eoc_hc: Decimal, gross_credits: Decimal,
                            daily_materiality: Decimal = Decimal("100")) -> dict[str, float | None]:
    credit_lines = [ln for ln in lines if ln.is_credit]
    op = [(ln, ln.p_operating) for ln in credit_lines if ln.p_operating > 0]
    contributions = sorted((float(ln.buckets["eoc_credit"]) for ln, _ in op), reverse=True)
    daily: dict = {}
    for ln, _ in op:
        daily[ln.booking_date] = daily.get(ln.booking_date, ZERO) + ln.buckets["eoc_credit"]
    amounts = [float(ln.amount) for ln, _ in op]
    weights = [w for _, w in op]
    wm = weighted_median(amounts, weights)
    mad = weighted_median([abs(a - wm) for a in amounts], weights) if wm is not None else None
    repeat = sum(
        (ln.buckets["eoc_credit"] for ln, _ in op
         if is_repeat_cluster(hypotheses[ln.txn_id], cluster_stats.get(hypotheses[ln.txn_id].cluster_id))),
        ZERO,
    )
    unknown_mass = sum((ln.amount * Decimal(repr(ln.uncertainty)) for ln in credit_lines), ZERO)
    eoc_f = float(eoc)
    return {
        "IN05_OperatingCreditRatio": safe_div(eoc_f, float(gross_credits), None),
        "IN06_HighConfidenceEOCShare": safe_div(float(eoc_hc), eoc_f, None),
        "IN07_OperatingActiveDays": float(sum(1 for v in daily.values() if v >= daily_materiality)),
        "IN08_OperatingReceiptCount": sum(weights),
        "IN09_MedianOperatingTicket": wm,
        "IN10_OperatingTicketMAD": mad,
        "IN11_TopReceiptShare": safe_div(contributions[0], eoc_f, None) if contributions else None,
        "IN12_Top5ReceiptShare": safe_div(sum(contributions[:5]), eoc_f, None) if contributions else None,
        "IN13_RepeatPatternShare": safe_div(float(repeat), eoc_f, None),
        "IN14_UnknownCreditEconomicMass": safe_div(float(unknown_mass), float(gross_credits), None),
    }

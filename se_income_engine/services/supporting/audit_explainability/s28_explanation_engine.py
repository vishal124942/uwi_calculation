"""Section 28 - Explainability and underwriter-facing evidence.

The bridge is computed from the same audited aggregates as the income estimate and reconciles exactly
from gross banking credits to sustainable business cash income.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from se_income_engine.common.money import ZERO, quantize
from se_income_engine.contracts.enums import (
    CoverageRisk,
    LegalAttributionStatus,
    ReasonCode,
)

REASON_TEXT = {
    ReasonCode.RC01_HIGH_FINANCING_CONTAMINATION: ("HIGH_FINANCING_CONTAMINATION",
                                                   "Material gross credits are financing, not operating collections."),
    ReasonCode.RC02_HIGH_TRANSFER_MASS: ("HIGH_TRANSFER_MASS", "Material transfers excluded from economic receipts."),
    ReasonCode.RC03_LOW_ROLE_CERTAINTY: ("LOW_ROLE_CERTAINTY", "High-value transaction roles remain uncertain."),
    ReasonCode.RC04_WORKING_CAPITAL_BUILD: ("WORKING_CAPITAL_BUILD",
                                            "Recent cash surplus depressed by qualified operating build-up."),
    ReasonCode.RC05_WORKING_CAPITAL_LIQUIDATION: ("WORKING_CAPITAL_LIQUIDATION",
                                                  "Recent cash surplus elevated by prior-funded activity/liquidation."),
    ReasonCode.RC06_RECENT_DETERIORATION: ("RECENT_DETERIORATION",
                                           "Recent operating activity materially below longer history."),
    ReasonCode.RC07_PASS_THROUGH_ACTIVITY: ("PASS_THROUGH_ACTIVITY",
                                            "Gross throughput materially exceeds retained economics."),
    ReasonCode.RC08_HIGH_COVERAGE_RISK: ("HIGH_COVERAGE_RISK",
                                         "Evidence suggests material activity may be outside supplied accounts."),
    ReasonCode.RC09_LEGAL_ATTRIBUTION_REQUIRED: ("LEGAL_ATTRIBUTION_REQUIRED",
                                                 "Business surplus cannot be fully attributed to applicant."),
    ReasonCode.RC10_ANOMALY_REVIEW: ("ANOMALY_REVIEW",
                                     "Window-dressing/recycling/anomaly evidence exceeds review threshold."),
}


@dataclass
class Explanation:
    bridge: list[dict]
    reasons: list[dict]
    drivers: list[dict]
    transaction_evidence: dict[str, list[dict]]
    flags: list[str] = field(default_factory=list)


def _line(label: str, value: Decimal, kind: str, note: str = "") -> dict:
    return {"line": label, "monthly_amount": float(quantize(value)), "kind": kind, "note": note}


def build_bridge(ctx) -> list[dict]:
    full = ctx.account_features.full_period
    m = full.monthly
    gross, eoc, cor = m("gross_credits"), m("eoc"), m("cor")
    financing, internal = m("financing_in"), m("internal_in")
    other_non_op = gross - eoc - financing - internal
    roc = ctx.sbci.roc_basis_monthly
    caocg = ctx.sbci.caocg_basis_monthly
    centre = ctx.sbci.robust_center
    debt = ctx.financing.debt_service_monthly
    sbci = ctx.sbci.sbci_monthly
    uwi = ctx.decision.underwriting_income_monthly
    lines = [
        _line("Gross banking credits", gross, "TOTAL", "Diagnostic only, never income"),
        _line("Less: financing credits", -financing, "DEDUCTION"),
        _line("Less: internal / own-account transfers", -internal, "DEDUCTION"),
        _line("Less: other non-operating, pass-through and uncertain credits", -other_non_op, "DEDUCTION"),
        _line("Expected operating collections (EOC)", eoc, "SUBTOTAL", "Probability-weighted"),
        _line("Less: core operating cash requirement (COR)", -cor, "DEDUCTION"),
        _line("Raw operating cash generation (ROC)", roc, "SUBTOTAL"),
        _line("Cycle / liquidation normalisation", caocg - roc, "ADJUSTMENT"),
        _line("Cycle-adjusted cash generation (CAOCG)", caocg, "SUBTOTAL"),
        _line("Robust-centre and trend normalisation", centre - caocg, "ADJUSTMENT", ctx.sbci.estimator),
        _line("Maintenance capex reserve", -ctx.sbci.maintenance_capex_reserve, "DEDUCTION"),
        _line("Permitted adjustments", ctx.sbci.permitted_adjustments, "ADJUSTMENT"),
        _line("Sustainable business cash income (SBCI)", sbci, "RESULT"),
        _line("Existing business debt service", debt, "MEMO", "Reported separately; not deducted from SBCI"),
        _line("Post-debt free cash (PDFC)", sbci - debt, "MEMO"),
    ]
    if uwi is not None:
        lines.append(_line("Policy-selected underwriting income (UWI)", uwi, "POLICY", ctx.decision.basis))
    return lines


def assign_reason_codes(ctx) -> list[dict]:
    t = ctx.account_features.full_period.totals
    gross_c, gross_d = float(t["gross_credits"]), float(t["gross_debits"])
    fin_ratio = ctx.financing.features["FIN01_FinancingCreditRatio"] or 0.0
    contamination = ctx.anomalies.features.get("AN07_FinancingContamination") or 0.0
    transfer_ratio = float(t["internal_in"] + t["internal_out"]) / (gross_c + gross_d) if gross_c + gross_d else 0.0
    pt_share = max(ctx.pass_through.get("pass_through_share_of_credits") or 0.0,
                   float(t["pass_through_in"]) / gross_c if gross_c else 0.0)
    wc = ctx.cycle.features
    checks = [
        (ReasonCode.RC01_HIGH_FINANCING_CONTAMINATION, fin_ratio >= 0.15 or contamination >= 0.5,
         {"financing_credit_ratio": fin_ratio, "financing_contamination": contamination}),
        (ReasonCode.RC02_HIGH_TRANSFER_MASS, transfer_ratio >= 0.15, {"transfer_ratio": transfer_ratio}),
        (ReasonCode.RC03_LOW_ROLE_CERTAINTY, ctx.role_uncertainty >= 0.35,
         {"amount_weighted_role_uncertainty": ctx.role_uncertainty}),
        (ReasonCode.RC04_WORKING_CAPITAL_BUILD, (wc.get("WC06_BuildScore") or 0) >= 0.1 and
         ctx.cycle.build_normalisation_amount > ZERO, {"build_score": wc.get("WC06_BuildScore")}),
        (ReasonCode.RC05_WORKING_CAPITAL_LIQUIDATION, (wc.get("WC07_LiquidationScore") or 0) >= 0.1 and
         ctx.cycle.liquidation_normalisation_amount > ZERO, {"liquidation_score": wc.get("WC07_LiquidationScore")}),
        (ReasonCode.RC06_RECENT_DETERIORATION, (ctx.trend.features.get("TR11_RecentDeteriorationScore") or 0) >= 0.3,
         {"deterioration_score": ctx.trend.features.get("TR11_RecentDeteriorationScore")}),
        (ReasonCode.RC07_PASS_THROUGH_ACTIVITY, pt_share >= 0.15, {"pass_through_share": pt_share}),
        (ReasonCode.RC08_HIGH_COVERAGE_RISK, ctx.coverage.risk in (CoverageRisk.HIGH, CoverageRisk.INDETERMINATE),
         {"coverage_score": ctx.coverage.score, "coverage_risk": ctx.coverage.risk.value}),
        (ReasonCode.RC09_LEGAL_ATTRIBUTION_REQUIRED, ctx.legal.status != LegalAttributionStatus.ATTRIBUTABLE,
         {"legal_attribution_status": ctx.legal.status.value}),
        (ReasonCode.RC10_ANOMALY_REVIEW, ctx.anomalies.review_required, {"triggers": ctx.anomalies.triggers}),
    ]
    out = []
    for code, fired, evidence in checks:
        if fired:
            name, meaning = REASON_TEXT[code]
            out.append({"code": code.value, "reason": name, "meaning": meaning, "evidence": evidence})
    return out


def _top_transactions(ctx, bucket: str, n: int = 5) -> list[dict]:
    by_id = {t.transaction_id: t for t in ctx.txns}
    lines = sorted(ctx.account_features.ledger.values(), key=lambda ln: -ln.buckets[bucket])[:n]
    out = []
    for ln in lines:
        if ln.buckets[bucket] <= 0:
            continue
        t = by_id[ln.txn_id]
        pred = ctx.predictions[ln.txn_id]
        out.append({"transaction_id": ln.txn_id, "date": t.booking_date.isoformat(), "amount": float(t.amount),
                    "contribution": float(quantize(ln.buckets[bucket])), "top_role": pred.top_role,
                    "top_probability": round(pred.top_probability, 4), "channel": t.channel_family.value})
    return out


def explanation_engine(ctx) -> Explanation:
    by_id = {t.transaction_id: t for t in ctx.txns}
    uncertain = sorted(ctx.txns, key=lambda t: -float(t.amount) * ctx.predictions[t.transaction_id].entropy)[:5]
    full = ctx.account_features.full_period
    drivers = [
        {"driver": "operating_credit_ratio", "value": full.inflow.get("IN05_OperatingCreditRatio")},
        {"driver": "high_confidence_eoc_share", "value": full.inflow.get("IN06_HighConfidenceEOCShare")},
        {"driver": "direct_cost_to_eoc", "value": full.outflow.get("OUT06_DirectCostToEOC")},
        {"driver": "archetype", "value": ctx.archetype.top, "probability": round(ctx.archetype.probability, 4)},
        {"driver": "cycle_status", "value": ctx.cycle.status.value, "lag_days": ctx.cycle.features.get("WC01_PeakOutflowToInflowLag")},
        {"driver": "trend_regime", "value": ctx.trend.regime.value},
        {"driver": "coverage_risk", "value": ctx.coverage.risk.value},
        {"driver": "confidence", "value": ctx.uncertainty.confidence},
    ]
    evidence = {
        "top_operating_collections": _top_transactions(ctx, "eoc_credit"),
        "top_core_operating_outflows": _top_transactions(ctx, "cor_debit"),
        "top_financing_credits": _top_transactions(ctx, "financing_in"),
        "top_uncertain_high_value": [
            {"transaction_id": t.transaction_id, "date": t.booking_date.isoformat(), "amount": float(t.amount),
             "direction": t.direction.value, "entropy": round(ctx.predictions[t.transaction_id].entropy, 4),
             "top_role": ctx.predictions[t.transaction_id].top_role}
            for t in uncertain if by_id.get(t.transaction_id)
        ],
    }
    flags = list(ctx.dq.warnings) + ctx.sbci.notes + ctx.uncertainty.notes
    return Explanation(build_bridge(ctx), assign_reason_codes(ctx), drivers, evidence, flags)

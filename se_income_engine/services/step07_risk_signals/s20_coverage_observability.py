"""Section 20 - Account coverage and observability model (CV01-CV10).

Outputs coverage *risk*, never an unsupported "% of business captured" unless an external denominator
(GST, ledger, audited statements) is supplied.
"""

from __future__ import annotations

from dataclasses import dataclass

from se_income_engine.common.stats import clamp, safe_div
from se_income_engine.config.parameters import CoverageParameters
from se_income_engine.contracts.account import AccountInput, Transaction
from se_income_engine.contracts.enums import ChannelFamily, CoverageRisk
from se_income_engine.services.step06_aggregation_archetype_cash.s10_s11_window_aggregation import AccountFeatures

_GST_EXPECTED_ARCHETYPES = {"A01", "A04", "A07"}


@dataclass
class CoverageResult:
    risk: CoverageRisk
    score: float
    features: dict[str, float | str | None]
    evidence: dict[str, float]


def compute_coverage_risk(accounts: list[AccountInput], txns: list[Transaction], af: AccountFeatures,
                          multi_account_features: dict, archetype_code: str, cycle_identified: bool,
                          financing_dependency: float, role_uncertainty: float, borrower_context: dict,
                          p: CoverageParameters) -> CoverageResult:
    t = af.full_period.totals
    eoc, cor = float(t["eoc"]), float(t["cor"])
    gross_c, gross_d = float(t["gross_credits"]), float(t["gross_debits"])
    own_mass = multi_account_features.get("MA02_UnmatchedOwnTransferSuspicion", 0.0)
    cash = float(t["business_cash_withdrawal"]) + sum(
        float(x.amount) for x in txns if x.is_credit and x.channel_family == ChannelFamily.CASH)
    cash_intensity = safe_div(cash, eoc + cor, 0.0)
    unexplained_c = safe_div(float(t["unknown_in"]), gross_c, 0.0)
    unexplained_d = safe_div(float(t["unknown_out"]), gross_d, 0.0)

    mismatch_months = [m for m in af.monthly if m.complete and float(m.totals["cor"]) > 1.2 * float(m.totals["eoc"])]
    complete = [m for m in af.monthly if m.complete]
    mismatch = safe_div(len(mismatch_months), len(complete), 0.0)
    if cycle_identified or financing_dependency > 0.2:
        mismatch *= 0.5

    gateway_debits = sum(float(x.amount) for x in txns if not x.is_credit and
                         (x.parser_fields.get("Counter Party Type") or "").upper() == "PAYMENT_GATEWAY")
    merchant_gap = clamp(safe_div(gateway_debits, gross_d, 0.0) / 0.1)
    statutory_present = float(t["statutory"]) > 0
    statutory_gap = 1.0 if archetype_code in _GST_EXPECTED_ARCHETYPES and not statutory_present else 0.0

    evidence = {
        "own_transfer": clamp(safe_div(own_mass, gross_c + gross_d, 0.0) / 0.1),
        "cash_intensity": clamp(cash_intensity / 0.5),
        "unexplained_credit": clamp(unexplained_c / 0.2),
        "unexplained_debit": clamp(unexplained_d / 0.2),
        "mismatch_persistence": clamp(mismatch),
        "merchant_gap": merchant_gap,
        "statutory_visibility": statutory_gap,
    }
    score = sum(p.weights[k] * v for k, v in evidence.items()) / sum(p.weights.values())

    external = None
    gst = (borrower_context or {}).get("gst_turnover_monthly")
    if gst:
        external = safe_div(eoc / max(af.full_period.months, 1e-9), float(gst), None)
        if external is not None and external < 0.6:
            score = max(score, p.high_threshold)

    if af.history_months < 3 or role_uncertainty > 0.8:
        risk = CoverageRisk.INDETERMINATE
    elif score >= p.high_threshold:
        risk = CoverageRisk.HIGH
    elif score >= p.medium_threshold:
        risk = CoverageRisk.MEDIUM
    else:
        risk = CoverageRisk.LOW

    features = {
        "CV01_ExternalOwnTransferMass": own_mass,
        "CV02_CashIntensity": cash_intensity,
        "CV03_UnexplainedCreditMass": unexplained_c,
        "CV04_UnexplainedDebitMass": unexplained_d,
        "CV05_PurchaseCollectionMismatchPersistence": mismatch,
        "CV06_MerchantSettlementGapEvidence": merchant_gap,
        "CV07_StatutoryVisibility": 1.0 - statutory_gap,
        "CV08_MultiAccountSupplied": float(len(accounts)),
        "CV09_CoverageRisk": risk.value,
        "CV10_ExternalDenominatorCoverage": external,
    }
    return CoverageResult(risk, score, features, evidence)

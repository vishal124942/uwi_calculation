"""Section 21.5 - Underwriting income policy selection (M9 Policy layer).

UWI = policy_select(central, lower_bound, recent_deterioration, legal_attribution, minimum_confidence,
                    hard_stop_flags). Versioned separately from the economic model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_FLOOR, Decimal

from se_income_engine.common.money import ZERO
from se_income_engine.config.policy import UnderwritingPolicy
from se_income_engine.contracts.account import AccountInput
from se_income_engine.contracts.enums import (
    AccountType,
    AnalysisStatus,
    CoverageRisk,
    LegalAttributionStatus,
)
from se_income_engine.services.step08_income_and_legal_attribution.s16_legal_attribution import LegalAttributionResult
from se_income_engine.services.step07_risk_signals.s19_anomaly_detection import AnomalyResult
from se_income_engine.services.step07_risk_signals.s20_coverage_observability import CoverageResult
from se_income_engine.services.step08_income_and_legal_attribution.s21_income_normalisation import SbciResult
from se_income_engine.services.step09_uncertainty_and_policy.s22_uncertainty_confidence import UncertaintyResult


@dataclass
class UnderwritingDecision:
    status: AnalysisStatus
    underwriting_income_monthly: Decimal | None
    basis: str
    policy_id: str
    policy_version: str
    referral_reasons: list[str] = field(default_factory=list)


def _round_down(value: Decimal, unit: int) -> Decimal:
    if unit <= 1:
        return value
    u = Decimal(unit)
    return (value / u).to_integral_value(rounding=ROUND_FLOOR) * u


def policy_select(central: Decimal, lower: Decimal, deterioration: float, policy: UnderwritingPolicy) -> tuple[Decimal, str]:
    basis = policy.estimate_basis
    if deterioration >= policy.deterioration_force_lower_bound:
        basis = "LOWER_BOUND"
    if basis == "CENTRAL":
        value = central
    elif basis == "BLEND":
        w = Decimal(repr(policy.blend_weight_central))
        value = w * central + (1 - w) * lower
    else:
        value = lower
    return _round_down(value, policy.rounding_unit), basis


def policy_engine(sbci: SbciResult, uncertainty: UncertaintyResult, legal: LegalAttributionResult,
                  coverage: CoverageResult, anomalies: AnomalyResult, deterioration: float,
                  accounts: list[AccountInput], policy: UnderwritingPolicy) -> UnderwritingDecision:
    def decision(status, uwi, basis, reasons=None):
        return UnderwritingDecision(status, uwi, basis, policy.policy_id, policy.policy_version, reasons or [])

    if all(a.account_type in (AccountType.OD, AccountType.CC) for a in accounts):
        return decision(AnalysisStatus.UNSUPPORTED_ACCOUNT_STRUCTURE, None, "NONE",
                        ["OD/CC facility is not a standalone income source"])
    if sbci.sbci_monthly <= ZERO:
        return decision(AnalysisStatus.NO_SUSTAINABLE_INCOME, ZERO, "NONE")
    if legal.status in (LegalAttributionStatus.NEEDS_LEGAL_ATTRIBUTION, LegalAttributionStatus.FIRM_CASH_INCOME_ONLY):
        return decision(AnalysisStatus.REFER_LEGAL_ATTRIBUTION, None, "NONE", legal.notes)

    selected, basis = policy_select(uncertainty.central, uncertainty.lower, deterioration, policy)
    if legal.status == LegalAttributionStatus.DOCUMENTED_COMPONENTS_ONLY and legal.borrower_income_monthly is not None:
        selected = _round_down(legal.borrower_income_monthly, policy.rounding_unit)
        basis = "DOCUMENTED_LEGAL_COMPONENTS"

    reasons = []
    status = AnalysisStatus.SUCCESS
    if policy.refer_on_anomaly and anomalies.review_required:
        status = AnalysisStatus.REFER_ANOMALY
        reasons += anomalies.triggers
    elif policy.refer_on_high_coverage_risk and coverage.risk in (CoverageRisk.HIGH, CoverageRisk.INDETERMINATE):
        status = AnalysisStatus.REFER_COVERAGE_RISK
        reasons.append(f"coverage_risk={coverage.risk.value}")
    elif uncertainty.confidence < policy.min_confidence_auto_decision:
        status = AnalysisStatus.REFER_LOW_CONFIDENCE
        reasons.append(f"confidence={uncertainty.confidence:.2f} < {policy.min_confidence_auto_decision}")
    return decision(status, selected, basis, reasons)

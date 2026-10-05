"""Section 2.2 / 16.2 - Borrower-level legal attribution.

The core engine returns business-level economics; this module alone converts them into borrower income.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from se_income_engine.common.money import ZERO, to_money
from se_income_engine.contracts.enums import LegalAttributionStatus, LegalOwnerType
from se_income_engine.services.step07_risk_signals.s16_owner_extraction import OwnerExtractionResult


@dataclass
class LegalAttributionResult:
    status: LegalAttributionStatus
    legal_owner_type: LegalOwnerType
    business_income_monthly: Decimal
    borrower_income_monthly: Decimal | None
    confidence: float
    notes: list[str] = field(default_factory=list)


def attribute_business_income_to_borrower(sbci: Decimal, owner: OwnerExtractionResult, legal_owner_type: LegalOwnerType,
                                          borrower_context: dict) -> LegalAttributionResult:
    ctx = borrower_context or {}
    separation = float(ctx.get("personal_business_separation_confidence", 0.8))

    if legal_owner_type in (LegalOwnerType.SOLE_PROP, LegalOwnerType.INDIVIDUAL_PROFESSIONAL, LegalOwnerType.INDIVIDUAL):
        return LegalAttributionResult(
            LegalAttributionStatus.ATTRIBUTABLE, legal_owner_type, sbci, sbci, min(1.0, separation),
            ["SBCI attributed to proprietor/professional subject to personal/business separation",
             "Owner draw corroborates but does not define income"])

    if legal_owner_type in (LegalOwnerType.PARTNERSHIP, LegalOwnerType.LLP):
        remuneration = to_money(ctx.get("documented_remuneration_monthly")) or ZERO
        profit_share_ratio = ctx.get("profit_share_ratio")
        profit_share = to_money(ctx.get("documented_profit_share_monthly"))
        if profit_share is None and profit_share_ratio is not None:
            profit_share = (sbci * Decimal(str(profit_share_ratio))).quantize(Decimal("0.01"))
        if remuneration == ZERO and profit_share is None:
            return LegalAttributionResult(
                LegalAttributionStatus.FIRM_CASH_INCOME_ONLY, legal_owner_type, sbci, None, 0.2,
                ["Ownership/remuneration data unavailable: firm cash income only; full SBCI not attributed"])
        return LegalAttributionResult(
            LegalAttributionStatus.DOCUMENTED_COMPONENTS_ONLY, legal_owner_type, sbci,
            remuneration + (profit_share or ZERO), 0.85,
            ["Borrower income = documented remuneration + documented profit-share component"])

    if legal_owner_type == LegalOwnerType.COMPANY:
        parts = [to_money(ctx.get(k)) for k in ("verified_director_salary_monthly", "verified_dividend_monthly",
                                                "verified_director_extraction_monthly")]
        verified = sum((p for p in parts if p is not None), ZERO)
        if verified == ZERO:
            return LegalAttributionResult(
                LegalAttributionStatus.NEEDS_LEGAL_ATTRIBUTION, legal_owner_type, sbci, None, 0.2,
                ["Company SBCI is not personal director income; verified salary/dividend required"])
        return LegalAttributionResult(
            LegalAttributionStatus.DOCUMENTED_COMPONENTS_ONLY, legal_owner_type, sbci, verified, 0.9,
            ["Borrower income = verified salary/remuneration/dividend; company SBCI reported separately"])

    return LegalAttributionResult(
        LegalAttributionStatus.NEEDS_LEGAL_ATTRIBUTION, legal_owner_type, sbci, None, 0.0,
        ["Legal owner type UNKNOWN: proprietor not assumed"])

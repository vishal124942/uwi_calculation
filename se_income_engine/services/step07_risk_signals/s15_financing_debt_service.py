"""Section 15 - Financing, OD/CC and debt-service treatment (FIN01-FIN10).

Borrowed money never raises business income. Existing debt service is reported separately so policy
can apply exactly one consistent treatment (no double counting).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from se_income_engine.common.money import ZERO, per_month, weighted
from se_income_engine.common.stats import safe_div
from se_income_engine.contracts.account import Transaction
from se_income_engine.contracts.role import RolePrediction
from se_income_engine.services.step06_aggregation_archetype_cash.s10_s11_window_aggregation import AccountFeatures
from se_income_engine.services.step07_risk_signals.s14_balance_liquidity_engine import LiquidityResult


@dataclass
class FinancingResult:
    features: dict[str, float | None]
    debt_service_monthly: Decimal
    interest_monthly: Decimal
    principal_monthly: Decimal
    financing_events: list[tuple[date, float]]


def compute_financing_dependency(txns: list[Transaction], predictions: dict[str, RolePrediction],
                                 af: AccountFeatures, liquidity: LiquidityResult) -> FinancingResult:
    full = af.full_period.totals
    months = af.full_period.months
    gross = full["gross_credits"]
    fin_credit = full["financing_in"]
    interest, principal = full["debt_interest"], full["debt_principal"]

    ordered = sorted(txns, key=lambda t: (t.booking_date, t.account_id, t.sequence_no))
    financing = [(t, predictions[t.transaction_id].p("C05")) for t in ordered if t.is_credit and
                 predictions[t.transaction_id].p("C05") >= 0.5]
    funded_operating = ZERO
    before_supplier = ZERO
    for f, pf in financing:
        horizon = f.booking_date + timedelta(days=7)
        op_out = sum((weighted(t.amount, predictions[t.transaction_id].p("D01", "D02", "D03", "D04", "D05", "D06", "D07"))
                      for t in ordered if not t.is_credit and f.booking_date <= t.booking_date <= horizon), ZERO)
        supplier_out = sum((weighted(t.amount, predictions[t.transaction_id].p("D01"))
                            for t in ordered if not t.is_credit and f.booking_date <= t.booking_date <= horizon), ZERO)
        amount = weighted(f.amount, pf)
        funded_operating += min(amount, op_out)
        if supplier_out >= amount * Decimal("0.5"):
            before_supplier += amount

    w90, w365 = af.windows.get("90D"), af.windows.get("365D")
    recent_ratio = safe_div(float(w90.totals["financing_in"]), float(w90.totals["gross_credits"]), None) if w90 else None
    long_ratio = safe_div(float(w365.totals["financing_in"]), float(w365.totals["gross_credits"]), None) if w365 else None

    features = {
        "FIN01_FinancingCreditRatio": safe_div(float(fin_credit), float(gross), 0.0),
        "FIN02_DebtServiceOutflow": float(interest + principal),
        "FIN03_InterestOutflow": float(interest),
        "FIN04_PrincipalOutflow": float(principal),
        "FIN05_ExternalFundingDependency": safe_div(float(funded_operating), float(full["cor"]), 0.0),
        "FIN06_ODUtilisationMean": liquidity.features.get("OD_UTIL_MEAN"),
        "FIN07_ODUtilisationP90": liquidity.features.get("OD_UTIL_P90"),
        "FIN08_LimitBreachCount": liquidity.features.get("LIMIT_BREACH_COUNT"),
        "FIN09_FundingBeforeSupplierOutflow": safe_div(float(before_supplier), float(fin_credit), None),
        "FIN10_FundingTrend": (recent_ratio - long_ratio) if recent_ratio is not None and long_ratio is not None else None,
    }
    return FinancingResult(
        features=features,
        debt_service_monthly=per_month(interest + principal, months),
        interest_monthly=per_month(interest, months),
        principal_monthly=per_month(principal, months),
        financing_events=[(f.booking_date, float(weighted(f.amount, pf))) for f, pf in financing],
    )

"""Section 9 - Account and business-archetype inference (M5 Archetype classifier).

Archetype changes priors and normalisation; it never sets income directly.
"""

from __future__ import annotations

from dataclasses import dataclass

from se_income_engine.common.stats import median, safe_div, softmax
from se_income_engine.contracts.account import AccountInput, Transaction
from se_income_engine.contracts.enums import AccountType, ChannelFamily
from se_income_engine.services.step03_transaction_evidence.s08_neighbourhood_features import NeighbourhoodFeatures
from se_income_engine.services.step06_aggregation_archetype_cash.s10_s11_window_aggregation import AccountFeatures
from se_income_engine.versions import COMPONENT_VERSIONS


@dataclass
class ArchetypeResult:
    top: str
    probability: float
    probabilities: dict[str, float]
    features: dict[str, float | None]
    model_version: str


def archetype_features(account_features: AccountFeatures, txns: list[Transaction],
                       nf: dict[str, NeighbourhoodFeatures]) -> dict[str, float | None]:
    w = account_features.full_period
    t = w.totals
    eoc = float(t["eoc"])
    cor = float(t["cor"])
    gross_c, gross_d = float(t["gross_credits"]), float(t["gross_debits"])
    n_credit = sum(1 for x in txns if x.is_credit)
    n_debit = len(txns) - n_credit
    cash = sum(float(x.amount) for x in txns if x.channel_family in (ChannelFamily.CASH, ChannelFamily.ATM))
    retention = [nf[x.transaction_id].NF07_BalanceRetention3d for x in txns
                 if x.is_credit and nf[x.transaction_id].NF07_BalanceRetention3d is not None]
    merchant = sum(float(x.amount) for x in txns if x.is_credit and x.channel_family == ChannelFamily.MERCHANT_SETTLEMENT)
    return {
        "credit_debit_count_ratio": safe_div(n_credit, n_debit, None),
        "credit_debit_amount_ratio": safe_div(gross_c, gross_d, None),
        "direct_cost_ratio": w.outflow.get("OUT06_DirectCostToEOC"),
        "payroll_ratio": w.outflow.get("OUT07_PayrollToEOC"),
        "fixed_cost_ratio": w.outflow.get("OUT08_FixedCostToEOC"),
        "cash_share": safe_div(cash, gross_c + gross_d, 0.0),
        "receipts_per_month": safe_div(w.inflow.get("IN08_OperatingReceiptCount") or 0.0, w.months, 0.0),
        "median_ticket": w.inflow.get("IN09_MedianOperatingTicket"),
        "top5_share": w.inflow.get("IN12_Top5ReceiptShare"),
        "merchant_share": safe_div(merchant, eoc, 0.0),
        "capex_intensity": w.outflow.get("OUT12_CapexIntensity"),
        "financing_dependency": safe_div(float(t["financing_in"]), gross_c, 0.0),
        "pass_through_share": safe_div(float(t["pass_through_in"]), gross_c, 0.0),
        "median_retention_3d": median(retention),
        "personal_share": safe_div(float(t["personal_expense"] + t["owner_draw"]), gross_d, 0.0),
        "logistics_share": safe_div(float(t["logistics"]), cor, 0.0),
        "utilities_share": safe_div(float(t["utilities"]), cor, 0.0),
    }


def archetype_model(account_features: AccountFeatures, txns: list[Transaction], nf: dict[str, NeighbourhoodFeatures],
                    accounts: list[AccountInput]) -> ArchetypeResult:
    f = archetype_features(account_features, txns, nf)
    g = lambda k: f.get(k) or 0.0  # noqa: E731
    logits = {f"A0{i}": 0.0 for i in range(1, 10)}

    logits["A01"] += 3.0 * min(1.0, g("direct_cost_ratio") / 0.6) + (0.5 if g("receipts_per_month") < 150 else 0.0)
    logits["A02"] += (2.0 if g("receipts_per_month") >= 100 else 0.0) + (1.0 if 0 < g("median_ticket") <= 1000 else 0.0) \
        + 1.5 * min(1.0, g("merchant_share") / 0.3) + 1.0 * min(1.0, g("cash_share") / 0.3)
    logits["A03"] += (1.5 if g("direct_cost_ratio") < 0.2 else 0.0) + (0.5 if g("receipts_per_month") < 30 else 0.0) \
        + 1.0 * min(1.0, (g("payroll_ratio") + g("fixed_cost_ratio")) / 0.4)
    logits["A04"] += (2.0 if g("direct_cost_ratio") >= 0.4 and g("payroll_ratio") >= 0.1 else 0.0) \
        + 1.0 * min(1.0, g("utilities_share") / 0.1) + 0.5 * min(1.0, g("capex_intensity") / 0.1)
    logits["A05"] += 2.5 if g("top5_share") >= 0.5 and g("receipts_per_month") <= 10 else 0.0
    logits["A06"] += 3.0 * min(1.0, g("pass_through_share") / 0.3) \
        + (1.5 if f.get("median_retention_3d") is not None and g("median_retention_3d") < 0.1 and
           g("credit_debit_amount_ratio") > 0.9 and g("pass_through_share") > 0.05 else 0.0)
    logits["A07"] += 2.5 * min(1.0, g("logistics_share") / 0.3)
    logits["A08"] += 2.0 * min(1.0, g("personal_share") / 0.2) + \
        (0.5 if any(a.account_type == AccountType.SAVINGS for a in accounts) else 0.0)
    logits["A09"] += 1.0

    probs = softmax(logits)
    best = max(probs, key=probs.get)
    # Below the floor the business is reported as A09 (unclassified/mixed); probability stays the model's
    # top-candidate certainty so CF09 reflects ambiguity rather than A09's residual mass.
    top = best if probs[best] >= 0.35 else "A09"
    return ArchetypeResult(top, probs[best], probs, f, COMPONENT_VERSIONS["archetype_model"])

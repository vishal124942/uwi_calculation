"""Section 12 - Cash, cheque, merchant settlement and pass-through handling."""

from __future__ import annotations

import math
from datetime import date
from decimal import Decimal

from se_income_engine.common.money import ZERO
from se_income_engine.common.stats import DAYS_PER_MONTH, clamp, logistic, mean, safe_div, stdev
from se_income_engine.config.parameters import CashParameters
from se_income_engine.contracts.account import Transaction
from se_income_engine.contracts.enums import ChannelFamily, PairEdgeType
from se_income_engine.contracts.role import RolePrediction
from se_income_engine.services.m4_flow_pair_model.s08_flow_pair_graph import FlowPairGraph
from se_income_engine.services.m2_role_classifier.s08_neighbourhood_features import NeighbourhoodFeatures, amount_similarity


def compute_cash_business_probability(
    txns: list[Transaction],
    predictions: dict[str, RolePrediction],
    features: dict[str, NeighbourhoodFeatures],
    archetype_code: str,
    application_date: date,
    history_months: float,
    p: CashParameters,
) -> dict[str, float]:
    """Section 12.1: cash_business_probability = model(frequency, tickets, active days, withdrawal linkage,
    retention, merchant/cash mix, financing proximity, application proximity, archetype)."""
    deposits = [t for t in txns if t.is_credit and t.channel_family == ChannelFamily.CASH]
    if not deposits:
        return {}
    withdrawals = [t for t in txns if not t.is_credit and t.channel_family in (ChannelFamily.CASH, ChannelFamily.ATM)]
    financing = [t for t in txns if t.is_credit and predictions[t.transaction_id].p("C05") >= 0.5]
    non_cash_operating = sum(float(t.amount) * predictions[t.transaction_id].p("C01", "C02")
                             for t in txns if t.is_credit and t.channel_family != ChannelFamily.CASH)
    cash_total = sum(float(t.amount) for t in deposits)

    amounts = [float(t.amount) for t in deposits]
    cv = (stdev(amounts) or 0.0) / (mean(amounts) or 1.0)
    per_month = len(deposits) / max(history_months, 1.0)
    active_months = len({(t.booking_date.year, t.booking_date.month) for t in deposits})
    spread = active_months / max(1.0, math.ceil(history_months))
    corroboration = safe_div(non_cash_operating, non_cash_operating + cash_total, 0.0)
    prior = p.archetype_cash_prior.get(archetype_code, 0.45)

    out: dict[str, float] = {}
    for t in deposits:
        x = math.log(prior / (1 - prior))
        x += 0.6 * clamp(per_month / 4.0) + 0.6 * spread - 0.4 * clamp(cv - 1.0)
        x += 0.5 * corroboration
        linked = any(
            0 <= (t.booking_date - w.booking_date).days <= p.withdrawal_linkage_days and
            amount_similarity(t.amount, w.amount) >= 0.95 for w in withdrawals)
        if linked:
            x -= 1.5
        retention = features[t.transaction_id].NF07_BalanceRetention3d
        if retention is not None and retention < 0.1:
            x -= 0.7
        if any(abs((t.booking_date - f.booking_date).days) <= p.financing_proximity_days for f in financing):
            x -= 0.8
        if 0 <= (application_date - t.booking_date).days <= p.application_proximity_days:
            x -= 0.5
        if float(t.amount) >= 5 * (mean(amounts) or 0.0) and len(deposits) > 3:
            x -= 0.8
        out[t.transaction_id] = round(logistic(x), 6)
    return out


def compute_pass_through_economics(pair_graph: FlowPairGraph, txns: list[Transaction],
                                   predictions: dict[str, RolePrediction]) -> dict[str, float | None]:
    """Section 12.3: retained_cash = pass_through_in - linked_pass_through_out - directly_linked_charges."""
    by_id = {t.transaction_id: t for t in txns}
    edges = pair_graph.by_type(PairEdgeType.PASS_THROUGH)
    pt_in = sum((by_id[e.credit_txn_id].amount for e in edges), ZERO)
    linked_out = sum((by_id[e.debit_txn_id].amount for e in edges), ZERO)
    gross_credits = sum((t.amount for t in txns if t.is_credit), ZERO)
    retained = pt_in - linked_out
    return {
        "pass_through_in_linked": float(pt_in),
        "linked_pass_through_out": float(linked_out),
        "retained_cash": float(retained),
        "retention_ratio": float(retained / pt_in) if pt_in else None,
        "pass_through_share_of_credits": float(pt_in / gross_credits) if gross_credits else 0.0,
        "edge_count": len(edges),
    }


def link_returned_cheques(pair_graph: FlowPairGraph) -> list[str]:
    """Section 12.4: returned cheques are linked through REVERSAL edges so failed collections never inflate EOC."""
    return [e.edge_id for e in pair_graph.by_type(PairEdgeType.REVERSAL)]


def merchant_settlement_summary(txns: list[Transaction], predictions: dict[str, RolePrediction],
                                start: date, end: date) -> dict[str, float]:
    """Section 12.2: settlements are observed net banking collections; no gross-up without platform data."""
    total = ZERO
    for t in txns:
        if t.is_credit and start <= t.booking_date <= end:
            total += t.amount * Decimal(repr(round(predictions[t.transaction_id].p("C02"), 8)))
    months = max(1.0, ((end - start).days + 1) / DAYS_PER_MONTH)
    return {"merchant_settlement_total": float(total), "merchant_settlement_monthly": float(total) / months}

"""Section 19 - Manipulation, window dressing and anomaly detection (AN01-AN14).

Features identify structures that can make banking activity look stronger than sustainable economics.
They affect confidence and routing; they never prove fraud.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from se_income_engine.common.stats import clamp, median, quantile, safe_div
from se_income_engine.config.parameters import AnomalyParameters
from se_income_engine.contracts.account import Transaction
from se_income_engine.contracts.entity import EntityHypothesis
from se_income_engine.contracts.enums import ChannelFamily, PairEdgeType
from se_income_engine.contracts.role import RolePrediction
from se_income_engine.services.step03_transaction_evidence.s05_entity_resolution import ClusterStatistics
from se_income_engine.services.step05_pairing_and_multi_account.s08_flow_pair_graph import FlowPairGraph
from se_income_engine.services.step03_transaction_evidence.s08_neighbourhood_features import NeighbourhoodFeatures
from se_income_engine.services.step06_aggregation_archetype_cash.s10_s11_window_aggregation import AccountFeatures
from se_income_engine.services.step07_risk_signals.s14_balance_liquidity_engine import LiquidityResult

NON_CORE_CREDIT_ROLES = ("C05", "C06", "C07", "C09", "C11")


@dataclass
class AnomalyResult:
    features: dict[str, float | None]
    review_required: bool
    triggers: list[str]


def _monthly_credit_baseline(txns: list[Transaction], before: date) -> float | None:
    by_month: dict[tuple[int, int], float] = {}
    for t in txns:
        if t.is_credit and t.booking_date < before:
            key = (t.booking_date.year, t.booking_date.month)
            by_month[key] = by_month.get(key, 0.0) + float(t.amount)
    return median(list(by_month.values()))


def compute_anomaly_features(txns: list[Transaction], predictions: dict[str, RolePrediction], af: AccountFeatures,
                             pair_graph: FlowPairGraph, nf: dict[str, NeighbourhoodFeatures],
                             hypotheses: dict[str, EntityHypothesis], cluster_stats: dict[str, ClusterStatistics],
                             liquidity: LiquidityResult, application_date: date, p: AnomalyParameters) -> AnomalyResult:
    credits = [t for t in txns if t.is_credit]
    gross = sum(float(t.amount) for t in credits) or 0.0
    throughput = sum(float(t.amount) for t in txns) or 0.0
    app_start = application_date - timedelta(days=30)
    by_id = {t.transaction_id: t for t in txns}

    recent_credits = sum(float(t.amount) for t in credits if app_start <= t.booking_date <= application_date)
    baseline = _monthly_credit_baseline(txns, app_start)
    series = liquidity.consolidated_daily
    recent_bal = median([v for d, v in series if app_start <= d <= application_date])
    base_bal = median([v for d, v in series if d < app_start])

    recycled = sum(float(by_id[e.credit_txn_id].amount) for e in pair_graph.edges
                   if e.edge_type in (PairEdgeType.RECYCLING, PairEdgeType.PASS_THROUGH) and e.dt_hours <= 72
                   and e.amount_similarity >= 0.98)
    round_mass = sum(float(t.amount) for t in txns
                     if t.amount >= p.round_min_amount and int(t.amount) % p.round_denomination == 0 and t.amount == int(t.amount))
    reciprocity = safe_div(sum(nf[t.transaction_id].NF11_ReciprocalClusterScore * float(t.amount) for t in txns),
                           throughput, 0.0)

    exceptional = [(t, float(t.amount) * predictions[t.transaction_id].p(*NON_CORE_CREDIT_ROLES)) for t in credits]
    op_amounts = [float(t.amount) for t in credits if predictions[t.transaction_id].p("C01", "C02") >= 0.5]
    p99 = quantile(op_amounts, 0.99) or 0.0
    exceptional += [(t, float(t.amount)) for t in credits
                    if p99 and float(t.amount) > 3 * p99 and predictions[t.transaction_id].p("C01", "C02") >= 0.5]
    exceptional_mass = sum(v for _, v in exceptional)
    positive_residual = max(0.0, float(af.full_period.totals["roc"]))
    top_exceptional = sum(sorted((v for _, v in exceptional), reverse=True)[:5])

    reversal_mass = sum(float(by_id[e.credit_txn_id].amount) for e in pair_graph.by_type(PairEdgeType.REVERSAL))
    cash = [t for t in credits if t.channel_family == ChannelFamily.CASH]
    cash_recent = sum(float(t.amount) for t in cash if app_start <= t.booking_date <= application_date)
    cash_baseline = _monthly_credit_baseline(cash, app_start)

    large_cut = quantile([float(t.amount) for t in credits], 0.95) or 0.0
    large = [t for t in credits if float(t.amount) >= large_cut and large_cut > 0]
    parked = [t for t in large if (nf[t.transaction_id].NF07_BalanceRetention3d or 1.0) < 0.1 and
              nf[t.transaction_id].NF04_AmountMatchedOut7d >= 0.9]

    new_start = af.as_of - timedelta(days=p.new_pattern_days)
    recent = [t for t in credits if t.booking_date >= new_start]
    new_mass = sum(float(t.amount) for t in recent
                   if (cs := cluster_stats.get(hypotheses[t.transaction_id].cluster_id)) and cs.first_seen
                   and cs.first_seen >= new_start and len(cs.active_months) <= 2)

    span = max(1, (af.statement_end - af.statement_start).days + 1)
    end_cut = af.statement_end - timedelta(days=int(span * p.statement_end_fraction))
    end_share = safe_div(sum(float(t.amount) for t in credits if t.booking_date > end_cut), gross, 0.0)

    features = {
        "AN01_PreApplicationCreditSurge": safe_div(recent_credits, baseline, None) if baseline else None,
        "AN02_PreApplicationBalanceSurge": safe_div(recent_bal, base_bal, None) if base_bal and base_bal > 0 and
        recent_bal is not None else None,
        "AN03_RapidRecyclingRatio": safe_div(recycled, gross, 0.0),
        "AN04_RoundAmountConcentration": safe_div(round_mass, throughput, 0.0),
        "AN05_ReciprocityScore": reciprocity,
        "AN06_ExceptionalCreditDependency": safe_div(exceptional_mass, positive_residual, None) if positive_residual else None,
        "AN07_FinancingContamination": safe_div(float(af.full_period.totals["financing_in"]), positive_residual, None)
        if positive_residual else None,
        "AN08_OneOffConcentration": safe_div(top_exceptional, gross, 0.0),
        "AN09_ReversalReturnRate": safe_div(reversal_mass, gross, 0.0),
        "AN10_CashSpikeScore": safe_div(cash_recent, cash_baseline, None) if cash_baseline else None,
        "AN11_BalanceParkingScore": safe_div(len(parked), len(large), 0.0) if large else 0.0,
        "AN12_NewPatternSurge": safe_div(new_mass, sum(float(t.amount) for t in recent), 0.0),
        "AN13_StatementEndEffect": safe_div(end_share, p.statement_end_fraction, None),
    }
    components = [
        clamp((features["AN03_RapidRecyclingRatio"] or 0.0) / 0.3),
        clamp((features["AN05_ReciprocityScore"] or 0.0) / 0.3),
        clamp((features["AN04_RoundAmountConcentration"] or 0.0) / 0.5),
        clamp(features["AN11_BalanceParkingScore"] or 0.0),
    ]
    features["AN14_SyntheticFlowScore"] = sum(components) / len(components)

    triggers = []
    if features["AN14_SyntheticFlowScore"] >= p.review_threshold:
        triggers.append("SYNTHETIC_FLOW")
    for key in ("AN01_PreApplicationCreditSurge", "AN02_PreApplicationBalanceSurge", "AN10_CashSpikeScore"):
        v = features[key]
        if v is not None and v >= p.preapp_surge_threshold:
            triggers.append(key)
    if (features["AN13_StatementEndEffect"] or 0.0) >= 3.0:
        triggers.append("STATEMENT_END_EFFECT")
    return AnomalyResult(features, bool(triggers), triggers)

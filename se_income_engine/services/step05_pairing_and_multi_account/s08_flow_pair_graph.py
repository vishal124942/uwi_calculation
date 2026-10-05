"""Section 8.2 - Flow pairing and recycling logic (M4 Flow-pair model).

pair_score = amount_similarity * time_decay * relationship_prior * direction_compatibility,
further multiplied by an amount-distinctiveness factor so that common small tickets that match by
chance do not become pass-through or recycling evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from se_income_engine.common.stats import normalise
from se_income_engine.config.parameters import NeighbourhoodParameters
from se_income_engine.contracts.account import Transaction
from se_income_engine.contracts.entity import EntityHypothesis
from se_income_engine.contracts.enums import IdentityStatus, PairEdgeType
from se_income_engine.contracts.role import RuleAdjustment, RolePrediction
from se_income_engine.services.step03_transaction_evidence.s05_entity_resolution import ClusterStatistics
from se_income_engine.services.step03_transaction_evidence.s08_neighbourhood_features import (
    AccountTimeline,
    NeighbourhoodFeatures,
    amount_similarity,
    pair_min_amount,
    time_decay,
)
from se_income_engine.versions import COMPONENT_VERSIONS

_REVERSAL_MARKER = re.compile(r"\b(REV|REVERSAL|REVERSED|REFUND|RFND|RETURN|RTN|RETURNED|BOUNCE|CHARGEBACK|FAILED)\b")


@dataclass
class PairEdge:
    edge_id: str
    edge_type: PairEdgeType
    credit_txn_id: str
    debit_txn_id: str
    score: float
    amount_similarity: float
    dt_hours: float
    evidence: dict[str, float | str] = field(default_factory=dict)


@dataclass
class FlowPairGraph:
    edges: list[PairEdge] = field(default_factory=list)

    def by_type(self, edge_type: PairEdgeType) -> list[PairEdge]:
        return [e for e in self.edges if e.edge_type == edge_type]

    def txn_ids(self, edge_type: PairEdgeType | None = None) -> set[str]:
        out: set[str] = set()
        for e in self.edges:
            if edge_type is None or e.edge_type == edge_type:
                out.update((e.credit_txn_id, e.debit_txn_id))
        return out


def _is_reversal_marked(t: Transaction, pred: RolePrediction) -> bool:
    text = t.normalized_narration or ""
    hint = (t.parser_fields.get("Payment Mode") or "").upper()
    return bool(_REVERSAL_MARKER.search(text)) or "REVERSAL" in hint or pred.p("C08", "D15") >= 0.5


def _relationship_prior(hyp_a: EntityHypothesis, hyp_b: EntityHypothesis, stats_b: ClusterStatistics | None) -> float:
    if hyp_a.identity_status != IdentityStatus.UNRESOLVED and hyp_a.cluster_id == hyp_b.cluster_id:
        return 1.0
    if stats_b and stats_b.debit_count >= 3 and len(stats_b.debit_months) >= 2:
        return 0.8
    return 0.5


def _target_first_retention(tl: AccountTimeline, i: int, j: int) -> float | None:
    """Section 8.3 counterfactual retention of credit i through debit j with target-first allocation: later
    receipts are treated as retained, so intervening customer receipts cannot mask an onward remittance."""
    a, b = tl.txns[i], tl.txns[j]
    if a.balance_before is None or b.balance_after is None or not a.amount:
        return None
    later_credits = sum((tl.txns[k].amount for k in range(i + 1, j + 1) if tl.txns[k].is_credit), 0)
    remaining = b.balance_after - a.balance_before - later_credits
    return max(0.0, min(1.0, float(remaining / a.amount)))


def _greedy_match(candidates: list[PairEdge], used: set[str]) -> list[PairEdge]:
    accepted = []
    for e in sorted(candidates, key=lambda e: (-e.score, e.credit_txn_id, e.debit_txn_id)):
        if e.credit_txn_id in used or e.debit_txn_id in used:
            continue
        used.update((e.credit_txn_id, e.debit_txn_id))
        accepted.append(e)
    return accepted


def build_flow_pair_graph(
    txns: list[Transaction],
    predictions: dict[str, RolePrediction],
    hypotheses: dict[str, EntityHypothesis],
    cluster_stats: dict[str, ClusterStatistics],
    features: dict[str, NeighbourhoodFeatures],
    p: NeighbourhoodParameters,
    preassigned: set[str] | None = None,
) -> FlowPairGraph:
    by_account: dict[str, list[Transaction]] = {}
    for t in txns:
        by_account.setdefault(t.account_id, []).append(t)

    lam = p.time_decay_lambda_per_hour
    used: set[str] = set(preassigned or ())
    graph = FlowPairGraph()
    seq = 0

    for account_txns in by_account.values():
        tl = AccountTimeline(account_txns)
        min_amt = pair_min_amount(account_txns)
        reversal_c, recycling_c, pass_c = [], [], []

        for i, a in enumerate(tl.txns):
            hyp_a = hypotheses[a.transaction_id]
            for j in tl.forward(i, max(p.reversal_max_lag_days, p.pass_through_max_lag_days, p.recycling_max_lag_days)):
                b = tl.txns[j]
                if a.direction == b.direction:
                    continue
                lag_days = tl.days[j] - tl.days[i]
                sim = amount_similarity(a.amount, b.amount)
                dt = tl.dt_hours(i, j)
                decay = time_decay(dt, lam)
                credit, debit = (a, b) if a.is_credit else (b, a)
                hyp_b = hypotheses[b.transaction_id]

                if sim >= 0.999 and lag_days <= p.reversal_max_lag_days and \
                        _is_reversal_marked(b, predictions[b.transaction_id]):
                    seq += 1
                    reversal_c.append(PairEdge(f"PE{seq:07d}", PairEdgeType.REVERSAL, credit.transaction_id,
                                               debit.transaction_id, sim * decay, sim, dt,
                                               {"original_txn": a.transaction_id, "reversal_txn": b.transaction_id}))
                    continue

                if float(a.amount) < min_amt:
                    continue
                fa = features[a.transaction_id]
                distinct = 1.0 / max(1, fa.match_candidates_24h)

                if lag_days <= p.recycling_max_lag_days and sim >= p.recycling_similarity and \
                        hyp_a.identity_status != IdentityStatus.UNRESOLVED and hyp_a.cluster_id == hyp_b.cluster_id and \
                        fa.NF12_FlowRecyclingScore > 0:
                    seq += 1
                    score = sim * decay * 1.0 * 1.0 * max(distinct, fa.NF12_FlowRecyclingScore)
                    recycling_c.append(PairEdge(f"PE{seq:07d}", PairEdgeType.RECYCLING, credit.transaction_id,
                                                debit.transaction_id, score, sim, dt,
                                                {"cluster_recycling_score": fa.NF12_FlowRecyclingScore}))
                    continue

                if a.is_credit and lag_days <= p.pass_through_max_lag_days and sim >= p.pass_through_similarity \
                        and b.amount <= a.amount:
                    retention = _target_first_retention(tl, i, j)
                    if retention is None:
                        retention = fa.NF07_BalanceRetention3d
                    if retention is not None and retention > p.pass_through_max_retention:
                        continue
                    prior = _relationship_prior(hyp_a, hyp_b, cluster_stats.get(hyp_b.cluster_id))
                    score = sim * decay * prior * 1.0 * distinct
                    seq += 1
                    pass_c.append(PairEdge(f"PE{seq:07d}", PairEdgeType.PASS_THROUGH, credit.transaction_id,
                                           debit.transaction_id, score, sim, dt,
                                           {"relationship_prior": prior, "distinctiveness": distinct,
                                            "retention_3d": retention if retention is not None else -1.0}))

        graph.edges.extend(_greedy_match([e for e in reversal_c if e.score >= p.min_pair_score], used))
        graph.edges.extend(_greedy_match([e for e in recycling_c if e.score >= p.min_pair_score], used))
        graph.edges.extend(_greedy_match([e for e in pass_c if e.score >= p.min_pair_score], used))
    return graph


MAX_PAIR_WEIGHT = 0.95
FULL_WEIGHT_PAIR_SCORE = 0.7


def _mix_towards(pred: RolePrediction, role: str, weight: float) -> dict[str, float]:
    """Evidence mixture p' = (1 - w) * p + w * onehot(role): pair evidence moves mass to the paired role
    independently of how small the classifier's prior for that role was."""
    probs = {r: (1.0 - weight) * v for r, v in pred.final_probabilities.items()}
    probs[role] = probs.get(role, 0.0) + weight
    return normalise(probs)


def update_roles_from_pair_evidence(predictions: dict[str, RolePrediction], graph: FlowPairGraph) -> None:
    version = COMPONENT_VERSIONS["pairing_model"]
    for e in graph.edges:
        cp, dp = predictions[e.credit_txn_id], predictions[e.debit_txn_id]
        if e.edge_type == PairEdgeType.REVERSAL:
            cp.final_probabilities = {r: (1.0 if r == "C08" else 0.0) for r in cp.final_probabilities}
            dp.final_probabilities = {r: (1.0 if r == "D15" else 0.0) for r in dp.final_probabilities}
            desc = f"Reversal pair {e.edge_id}: both legs neutralised"
            cp.rule_adjustments.append(RuleAdjustment("PAIR_REVERSAL", version, "PAIR_UPDATE", {"C08": 1.0}, desc))
            dp.rule_adjustments.append(RuleAdjustment("PAIR_REVERSAL", version, "PAIR_UPDATE", {"D15": 1.0}, desc))
        elif e.edge_type in (PairEdgeType.PASS_THROUGH, PairEdgeType.RECYCLING):
            c_role, d_role = ("C12", "D17") if e.edge_type == PairEdgeType.PASS_THROUGH else ("C04", "D14")
            rule_id = "PAIR_PASS_THROUGH" if e.edge_type == PairEdgeType.PASS_THROUGH else "PAIR_RECYCLING"
            w = MAX_PAIR_WEIGHT * min(1.0, e.score / FULL_WEIGHT_PAIR_SCORE)
            cp.final_probabilities = _mix_towards(cp, c_role, w)
            dp.final_probabilities = _mix_towards(dp, d_role, w)
            desc = f"{e.edge_type.value} pair {e.edge_id} score={e.score:.3f} weight={w:.3f}"
            cp.rule_adjustments.append(RuleAdjustment(rule_id, version, "PAIR_UPDATE", {c_role: w}, desc))
            dp.rule_adjustments.append(RuleAdjustment(rule_id, version, "PAIR_UPDATE", {d_role: w}, desc))

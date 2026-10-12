"""Section 8.1 / 8.3 - Transaction neighbourhood features NF01-NF12.

All windows are evaluated per account on the deterministic transaction order. Booking dates carry no
time-of-day, so a 24h window means "later on the same day or the next day".
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass, field
from decimal import Decimal

from se_income_engine.common.stats import quantile
from se_income_engine.config.parameters import NeighbourhoodParameters
from se_income_engine.contracts.account import Transaction
from se_income_engine.contracts.entity import EntityHypothesis
from se_income_engine.contracts.enums import IdentityStatus
from se_income_engine.contracts.role import RolePrediction
from se_income_engine.services.m2_role_classifier.s05_entity_resolution import ClusterStatistics

OPEX_DEBIT_ROLES = ("D01", "D02", "D03", "D04", "D05", "D06", "D07")
TRANSFER_LIKE_DEBIT_ROLES = ("D14", "D17")


@dataclass
class NeighbourhoodFeatures:
    NF01_CreditOutflow24h: float | None = None
    NF02_CreditOutflow72h: float | None = None
    NF03_AmountMatchedOut24h: float = 0.0
    NF04_AmountMatchedOut7d: float = 0.0
    NF05_PriorMatchedIn7d: float | None = None
    NF06_BalanceRetention1d: float | None = None
    NF07_BalanceRetention3d: float | None = None
    NF08_BalanceRetention7d: float | None = None
    NF09_NormalSpendShareAfterCredit: float | None = None
    NF10_TransferLikeShareAfterCredit: float | None = None
    NF11_ReciprocalClusterScore: float = 0.0
    NF12_FlowRecyclingScore: float = 0.0
    retention_from_balances: bool = True
    match_candidates_24h: int = 0
    extras: dict[str, float] = field(default_factory=dict)


def amount_similarity(a: Decimal | float, b: Decimal | float) -> float:
    a, b = float(a), float(b)
    if max(a, b) <= 0:
        return 0.0
    return 1.0 - min(abs(a - b) / max(a, b), 1.0)


def time_decay(dt_hours: float, lam: float) -> float:
    return math.exp(-lam * dt_hours)


class AccountTimeline:
    """Ordered per-account view with day-window lookups."""

    def __init__(self, txns: list[Transaction]):
        self.txns = sorted(txns, key=lambda t: t.sequence_no)
        self.days = [t.booking_date.toordinal() for t in self.txns]
        self.pos = {t.transaction_id: i for i, t in enumerate(self.txns)}

    def forward(self, i: int, days: int) -> range:
        end = bisect.bisect_right(self.days, self.days[i] + days)
        return range(i + 1, end)

    def backward(self, i: int, days: int) -> range:
        start = bisect.bisect_left(self.days, self.days[i] - days)
        return range(start, i)

    def dt_hours(self, i: int, j: int) -> float:
        return abs(self.days[j] - self.days[i]) * 24.0


def pair_min_amount(txns: list[Transaction], q: float = 0.75, floor: float = 500.0) -> float:
    amounts = [float(t.amount) for t in txns]
    return max(floor, quantile(amounts, q) or 0.0)


def _retention(tl: AccountTimeline, i: int, days: int) -> float | None:
    t = tl.txns[i]
    if t.balance_before is None or t.balance_after is None:
        return None
    window_min = t.balance_after
    for j in tl.forward(i, days):
        b = tl.txns[j].balance_after
        if b is None:
            return None
        window_min = min(window_min, b)
    retained = min(t.amount, max(Decimal(0), window_min - t.balance_before))
    return float(retained / t.amount) if t.amount else None


def _cluster_motifs(tl: AccountTimeline, cluster_of: dict[str, str], p: NeighbourhoodParameters) -> dict[str, int]:
    members: dict[str, list[int]] = {}
    for i, t in enumerate(tl.txns):
        members.setdefault(cluster_of[t.transaction_id], []).append(i)
    motifs: dict[str, int] = {}
    for cid, idx in members.items():
        if len(idx) < 2:
            continue
        used: set[int] = set()
        count = 0
        for a_pos, a in enumerate(idx):
            if a in used:
                continue
            for b in idx[a_pos + 1:]:
                if tl.days[b] - tl.days[a] > p.recycling_max_lag_days:
                    break
                ta, tb = tl.txns[a], tl.txns[b]
                if b in used or ta.direction == tb.direction:
                    continue
                if amount_similarity(ta.amount, tb.amount) >= p.recycling_similarity:
                    used.update((a, b))
                    count += 1
                    break
        motifs[cid] = count
    return motifs


def build_neighbourhood_features(
    txns: list[Transaction],
    hypotheses: dict[str, EntityHypothesis],
    cluster_stats: dict[str, ClusterStatistics],
    p: NeighbourhoodParameters,
) -> dict[str, NeighbourhoodFeatures]:
    """Batch form of ``build_neighbourhood_features(txn, txns)`` from the Section 26 pseudocode."""
    by_account: dict[str, list[Transaction]] = {}
    for t in txns:
        by_account.setdefault(t.account_id, []).append(t)

    lam = p.time_decay_lambda_per_hour
    result: dict[str, NeighbourhoodFeatures] = {}
    for account_txns in by_account.values():
        tl = AccountTimeline(account_txns)
        cluster_of = {t.transaction_id: hypotheses[t.transaction_id].cluster_id for t in tl.txns}
        motifs = _cluster_motifs(tl, cluster_of, p)

        for i, t in enumerate(tl.txns):
            f = NeighbourhoodFeatures()
            amt = float(t.amount)
            fwd1, fwd3, fwd7 = tl.forward(i, 1), tl.forward(i, 3), tl.forward(i, 7)

            if t.is_credit:
                out24 = sum(float(tl.txns[j].amount) for j in fwd1 if not tl.txns[j].is_credit)
                out72 = sum(float(tl.txns[j].amount) for j in fwd3 if not tl.txns[j].is_credit)
                f.NF01_CreditOutflow24h = out24 / amt if amt else None
                f.NF02_CreditOutflow72h = out72 / amt if amt else None

            best24 = best7 = 0.0
            candidates24 = 0
            for j in fwd7:
                o = tl.txns[j]
                if o.direction == t.direction:
                    continue
                sim = amount_similarity(t.amount, o.amount)
                score = sim * time_decay(tl.dt_hours(i, j), lam)
                best7 = max(best7, score)
                if tl.days[j] - tl.days[i] <= 1:
                    best24 = max(best24, score)
                    if sim >= 1 - p.amount_match_tolerance:
                        candidates24 += 1
            f.NF03_AmountMatchedOut24h = best24
            f.NF04_AmountMatchedOut7d = best7
            f.match_candidates_24h = candidates24

            if not t.is_credit:
                prior = 0.0
                for j in tl.backward(i, 7):
                    o = tl.txns[j]
                    if o.is_credit:
                        prior = max(prior, amount_similarity(t.amount, o.amount) * time_decay(tl.dt_hours(i, j), lam))
                f.NF05_PriorMatchedIn7d = prior

            if t.is_credit:
                r1, r3, r7 = _retention(tl, i, 1), _retention(tl, i, 3), _retention(tl, i, 7)
                if r1 is None:
                    f.retention_from_balances = False
                    r1 = 1 - min(1.0, f.NF01_CreditOutflow24h or 0.0)
                    r3 = 1 - min(1.0, f.NF02_CreditOutflow72h or 0.0)
                    r7 = r3
                f.NF06_BalanceRetention1d, f.NF07_BalanceRetention3d, f.NF08_BalanceRetention7d = r1, r3, r7

            hyp = hypotheses[t.transaction_id]
            cs = cluster_stats.get(hyp.cluster_id)
            if cs and hyp.identity_status != IdentityStatus.UNRESOLVED and cs.credit_count and cs.debit_count:
                bal = float(min(cs.credit_amount, cs.debit_amount) / max(cs.credit_amount, cs.debit_amount))
                recurrence = min(1.0, len(cs.credit_months & cs.debit_months) / 2.0)
                f.NF11_ReciprocalClusterScore = bal * (0.5 + 0.5 * recurrence)
            if cs and cs.count >= 2:
                f.NF12_FlowRecyclingScore = min(1.0, 2.0 * motifs.get(hyp.cluster_id, 0) / cs.count)
            result[t.transaction_id] = f
    return result


def update_neighbourhood_role_shares(
    txns: list[Transaction],
    features: dict[str, NeighbourhoodFeatures],
    predictions: dict[str, RolePrediction],
) -> None:
    """NF09/NF10 require role probabilities, so they are filled after role inference."""
    by_account: dict[str, list[Transaction]] = {}
    for t in txns:
        by_account.setdefault(t.account_id, []).append(t)
    for account_txns in by_account.values():
        tl = AccountTimeline(account_txns)
        for i, t in enumerate(tl.txns):
            if not t.is_credit:
                continue
            total = normal = transfer = 0.0
            for j in tl.forward(i, 3):
                o = tl.txns[j]
                if o.is_credit:
                    continue
                pred = predictions[o.transaction_id]
                amt = float(o.amount)
                total += amt
                normal += amt * pred.p(*OPEX_DEBIT_ROLES)
                transfer += amt * pred.p(*TRANSFER_LIKE_DEBIT_ROLES)
            f = features[t.transaction_id]
            f.NF09_NormalSpendShareAfterCredit = normal / total if total else None
            f.NF10_TransferLikeShareAfterCredit = transfer / total if total else None

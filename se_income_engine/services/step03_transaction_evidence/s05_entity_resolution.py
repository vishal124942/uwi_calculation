"""Section 5.3 - Optional latent entity clustering.

Clusters are latent economic relationships, not legal identities. Name similarity is never the
dominant join key: name tokens only join when corroborated by a bank code (Section 5.3 restriction).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from se_income_engine.contracts.account import Transaction
from se_income_engine.contracts.entity import EntityEvidence, EntityHypothesis
from se_income_engine.contracts.enums import IdentityStatus
from se_income_engine.services.step03_transaction_evidence.s05_identifier_extraction import TransactionIdentifiers, hash_value


class _UnionFind:
    def __init__(self):
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


_KEY_STRENGTH = {
    "vpa": (IdentityStatus.DETERMINISTIC, 0.97),
    "acct": (IdentityStatus.DETERMINISTIC, 0.95),
    "mandate": (IdentityStatus.DETERMINISTIC, 0.98),
    "merchant": (IdentityStatus.DETERMINISTIC, 0.97),
    "name_bank": (IdentityStatus.PROBABLE, 0.7),
    "name_only": (IdentityStatus.PROBABLE, 0.5),
}


def _keys(ids: TransactionIdentifiers) -> list[tuple[str, str]]:
    keys: list[tuple[str, str]] = []
    if ids.vpa_local and ids.vpa_psp:
        keys.append(("vpa", f"{ids.vpa_local}@{ids.vpa_psp}"))
    if ids.account_fragment and (len(ids.account_fragment) >= 6 or ids.ifsc):
        keys.append(("acct", f"{ids.account_fragment}|{ids.ifsc or ids.bank_code or ''}"))
    if ids.mandate_id:
        keys.append(("mandate", ids.mandate_id))
    if ids.merchant_id:
        keys.append(("merchant", ids.merchant_id))
    if ids.name_tokens:
        name = " ".join(sorted(ids.name_tokens))
        if ids.bank_code:
            keys.append(("name_bank", f"{name}|{ids.bank_code}"))
        elif len(ids.name_tokens) >= 2:
            keys.append(("name_only", name))
    return keys


def optional_latent_entity_clustering(
    txns: list[Transaction], identifiers: dict[str, TransactionIdentifiers]
) -> dict[str, EntityHypothesis]:
    uf = _UnionFind()
    txn_keys: dict[str, list[tuple[str, str]]] = {}
    for t in txns:
        keys = _keys(identifiers[t.transaction_id])
        txn_keys[t.transaction_id] = keys
        node = f"txn:{t.transaction_id}"
        uf.find(node)
        for kind, value in keys:
            uf.union(node, f"{kind}:{value}")

    result: dict[str, EntityHypothesis] = {}
    for t in txns:
        keys = txn_keys[t.transaction_id]
        root = uf.find(f"txn:{t.transaction_id}")
        if not keys:
            result[t.transaction_id] = EntityHypothesis(
                cluster_id=f"U-{t.transaction_id[:12]}", identity_status=IdentityStatus.UNRESOLVED,
                canonical_label=None, match_probability=0.0)
            continue
        best_kind = max(keys, key=lambda k: _KEY_STRENGTH[k[0]][1])[0]
        status, prob = _KEY_STRENGTH[best_kind]
        ids = identifiers[t.transaction_id]
        label = " ".join(ids.name_tokens) if ids.name_tokens and status == IdentityStatus.DETERMINISTIC else None
        result[t.transaction_id] = EntityHypothesis(
            cluster_id="E-" + hash_value(root),
            identity_status=status,
            canonical_label=label,
            match_probability=prob,
            evidence=[EntityEvidence(kind, hash_value(value), _KEY_STRENGTH[kind][1], t.transaction_id)
                      for kind, value in keys],
        )
    return result


@dataclass
class ClusterStatistics:
    cluster_id: str
    credit_count: int = 0
    debit_count: int = 0
    credit_amount: Decimal = Decimal("0")
    debit_amount: Decimal = Decimal("0")
    active_months: set = field(default_factory=set)
    credit_months: set = field(default_factory=set)
    debit_months: set = field(default_factory=set)
    first_seen: date | None = None
    amounts: list[float] = field(default_factory=list)

    @property
    def count(self) -> int:
        return self.credit_count + self.debit_count


def cluster_statistics(txns: list[Transaction], hypotheses: dict[str, EntityHypothesis]) -> dict[str, ClusterStatistics]:
    stats: dict[str, ClusterStatistics] = {}
    for t in txns:
        cid = hypotheses[t.transaction_id].cluster_id
        s = stats.setdefault(cid, ClusterStatistics(cid))
        month = (t.booking_date.year, t.booking_date.month)
        s.active_months.add(month)
        s.amounts.append(float(t.amount))
        if s.first_seen is None or t.booking_date < s.first_seen:
            s.first_seen = t.booking_date
        if t.is_credit:
            s.credit_count += 1
            s.credit_amount += t.amount
            s.credit_months.add(month)
        else:
            s.debit_count += 1
            s.debit_amount += t.amount
            s.debit_months.add(month)
    return stats

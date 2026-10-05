"""Entity clustering output (Section 5.3)."""

from __future__ import annotations

from dataclasses import dataclass, field

from se_income_engine.contracts.enums import IdentityStatus


@dataclass
class EntityEvidence:
    type: str
    value_hash: str
    weight: float
    source_txn_id: str


@dataclass
class EntityHypothesis:
    cluster_id: str
    identity_status: IdentityStatus
    canonical_label: str | None
    match_probability: float
    evidence: list[EntityEvidence] = field(default_factory=list)

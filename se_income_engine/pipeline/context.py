"""Shared analysis request and context objects carried through the Section 26 pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from se_income_engine.config.parameters import EngineParameters
from se_income_engine.config.policy import UnderwritingPolicy
from se_income_engine.contracts.account import AccountInput, Transaction
from se_income_engine.contracts.enums import LegalOwnerType


@dataclass
class BorrowerContext:
    legal_owner_type: LegalOwnerType = LegalOwnerType.UNKNOWN
    declared_business_type: str | None = None
    application_date: date | None = None
    documents: dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalysisRequest:
    customer_id: str
    application_id: str
    as_of_date: date
    accounts: list[AccountInput]
    borrower_context: BorrowerContext
    policy_id: str | None = None


@dataclass
class AnalysisContext:
    request: AnalysisRequest
    params: EngineParameters
    policy: UnderwritingPolicy
    analysis_id: str = ""
    accounts: list[AccountInput] = field(default_factory=list)
    txns: list[Transaction] = field(default_factory=list)
    dq: Any = None
    identifiers: dict = field(default_factory=dict)
    text_features: dict = field(default_factory=dict)
    hypotheses: dict = field(default_factory=dict)
    cluster_stats: dict = field(default_factory=dict)
    neighbourhood: dict = field(default_factory=dict)
    predictions: dict = field(default_factory=dict)
    pre_rule_probabilities: dict = field(default_factory=dict)
    pair_graph: Any = None
    internal_edges: list = field(default_factory=list)
    cash_eligibility: dict = field(default_factory=dict)
    account_features: Any = None
    archetype: Any = None
    cycle: Any = None
    liquidity: Any = None
    financing: Any = None
    owner: Any = None
    multi_account: dict = field(default_factory=dict)
    pass_through: dict = field(default_factory=dict)
    trend: Any = None
    anomalies: Any = None
    coverage: Any = None
    roc: Any = None
    caocg: Any = None
    sbci: Any = None
    legal: Any = None
    uncertainty: Any = None
    decision: Any = None
    role_uncertainty: float = 1.0
    reason_codes: list = field(default_factory=list)
    explanation: Any = None
    feature_vector: dict = field(default_factory=dict)
    permitted_adjustments: Decimal = Decimal("0")

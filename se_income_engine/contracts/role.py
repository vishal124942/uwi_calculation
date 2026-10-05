"""Role-prediction contract (Section 7.1)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RuleAdjustment:
    rule_id: str
    rule_version: str
    action: str  # SET | MULTIPLY | RESTRICT | PAIR_UPDATE | INTERNAL_TRANSFER_ELIMINATION
    roles: dict[str, float]
    description: str


@dataclass
class RolePrediction:
    transaction_id: str
    role_probabilities: dict[str, float]
    model_version: str
    final_probabilities: dict[str, float] = field(default_factory=dict)
    rule_adjustments: list[RuleAdjustment] = field(default_factory=list)
    top_role: str = ""
    top_probability: float = 0.0
    entropy: float = 0.0

    def p(self, *roles: str) -> float:
        return sum(self.final_probabilities.get(r, 0.0) for r in roles)

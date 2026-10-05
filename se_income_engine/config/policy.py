"""Underwriting policy configuration (Section 21.5, M9).

Policy is versioned separately from the economic model so lenders can change selection rules
without retraining transaction classification.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class UnderwritingPolicy:
    policy_id: str
    policy_version: str
    estimate_basis: str  # LOWER_BOUND | CENTRAL | BLEND
    blend_weight_central: float
    lower_quantile: float
    upper_quantile: float
    min_confidence_auto_decision: float
    deterioration_force_lower_bound: float
    refer_on_high_coverage_risk: bool
    refer_on_anomaly: bool
    rounding_unit: int

    def as_dict(self) -> dict:
        return asdict(self)


SE_INCOME_POLICY_001 = UnderwritingPolicy(
    policy_id="SE_INCOME_POLICY_001",
    policy_version="1.0.0",
    estimate_basis="LOWER_BOUND",
    blend_weight_central=0.5,
    lower_quantile=0.1,
    upper_quantile=0.9,
    min_confidence_auto_decision=0.6,
    deterioration_force_lower_bound=0.5,
    refer_on_high_coverage_risk=True,
    refer_on_anomaly=True,
    rounding_unit=100,
)

POLICY_REGISTRY: dict[str, UnderwritingPolicy] = {SE_INCOME_POLICY_001.policy_id: SE_INCOME_POLICY_001}


def get_policy(policy_id: str | None) -> UnderwritingPolicy:
    if policy_id is None:
        return SE_INCOME_POLICY_001
    if policy_id not in POLICY_REGISTRY:
        raise KeyError(f"Unknown policy_id {policy_id!r}")
    return POLICY_REGISTRY[policy_id]

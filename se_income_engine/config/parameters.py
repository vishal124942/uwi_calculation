"""Engine parameters (Section 31.3).

Every value here is a placeholder that must be empirically calibrated and approved before production.
Economic reconstruction parameters live here; lender policy lives in ``config/policy.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class DataQualityParameters:
    reconciliation_tolerance: Decimal = Decimal("0.05")
    min_reconciliation_pass_rate: float = 0.98
    max_balance_break_magnitude: float = 0.01
    min_statement_coverage: float = 0.85
    long_gap_days: int = 10
    max_duplicate_amount_share: float = 0.02
    max_date_order_error_rate: float = 0.02
    max_missing_amount_rate: float = 0.01
    low_parse_confidence_threshold: float = 0.6
    min_history_months: float = 3.0
    preferred_history_months: float = 12.0
    supported_currencies: tuple[str, ...] = ("INR",)
    source_reliability: dict[str, float] = field(
        default_factory=lambda: {
            "AA": 1.0,
            "API": 1.0,
            "CORE_BANKING": 1.0,
            "CSV": 0.85,
            "PDF": 0.7,
            "PDF_OCR": 0.5,
        }
    )


@dataclass(frozen=True)
class RoleParameters:
    high_confidence_threshold: float = 0.8
    rule_override_confidence: float = 0.995
    theta_recycle: float = 0.6
    alpha_transfer: float = 3.0
    beta_operating: float = 0.4
    emi_interest_share: float = 0.35
    calibration_temperature_credit: float = 1.0
    calibration_temperature_debit: float = 1.0


@dataclass(frozen=True)
class NeighbourhoodParameters:
    windows_days: tuple[int, ...] = (0, 1, 3, 7, 15, 30)
    amount_match_tolerance: float = 0.02
    time_decay_lambda_per_hour: float = 0.005
    recycling_similarity: float = 0.98
    recycling_max_lag_days: int = 3
    pass_through_similarity: float = 0.9
    pass_through_max_lag_days: int = 3
    pass_through_max_retention: float = 0.15
    reversal_max_lag_days: int = 10
    min_pair_score: float = 0.5


@dataclass(frozen=True)
class MultiAccountParameters:
    transfer_amount_similarity: float = 0.995
    transfer_max_gap_days: int = 2
    # With no positive ownership evidence a match is accepted only for a distinctive, unique amount.
    unlinked_min_amount: float = 5000.0


@dataclass(frozen=True)
class CashParameters:
    archetype_cash_prior: dict[str, float] = field(
        default_factory=lambda: {
            "A01": 0.55,
            "A02": 0.8,
            "A03": 0.3,
            "A04": 0.5,
            "A05": 0.4,
            "A06": 0.3,
            "A07": 0.55,
            "A08": 0.35,
            "A09": 0.45,
        }
    )
    application_proximity_days: int = 30
    financing_proximity_days: int = 7
    withdrawal_linkage_days: int = 3


@dataclass(frozen=True)
class CycleParameters:
    max_lag_weeks: int = 13
    min_strength: float = 0.3
    min_prominence: float = 0.1
    min_nonzero_periods: int = 12
    adjustment_cap_fraction_of_eoc: float = 0.25
    score_cap: float = 1.0


@dataclass(frozen=True)
class TrendParameters:
    decline_threshold: float = 0.85
    growth_threshold: float = 1.15
    growth_min_months: int = 3
    seasonality_min_months: int = 24
    decline_recent_weight: float = 2.0
    growth_cap_window: str = "rolling_180"


@dataclass(frozen=True)
class IncomeParameters:
    robust_estimator: str = "weighted_median"  # weighted_median | trimmed_mean | huber | conservative_quantile
    trimmed_mean_fraction: float = 0.2
    huber_k: float = 1.345
    conservative_quantile: float = 0.4
    candidate_weights: dict[str, float] = field(
        default_factory=lambda: {
            "monthly": 1.0,
            "rolling_90": 2.0,
            "rolling_180": 2.0,
            "rolling_365": 2.0,
        }
    )
    maintenance_capex_horizon_months: int = 24
    include_bank_fees_in_cor: bool = True
    business_cash_withdrawal_in_cor: bool = True
    statutory_in_cor: bool = True  # tax_basis: True = post-tax actual cash-servicing capacity
    min_month_coverage: float = 0.9


@dataclass(frozen=True)
class CoverageParameters:
    medium_threshold: float = 0.25
    high_threshold: float = 0.5
    weights: dict[str, float] = field(
        default_factory=lambda: {
            "own_transfer": 0.25,
            "cash_intensity": 0.15,
            "unexplained_credit": 0.15,
            "unexplained_debit": 0.1,
            "mismatch_persistence": 0.15,
            "merchant_gap": 0.1,
            "statutory_visibility": 0.1,
        }
    )


@dataclass(frozen=True)
class AnomalyParameters:
    review_threshold: float = 0.5
    preapp_surge_threshold: float = 2.0
    round_denomination: int = 1000
    round_min_amount: int = 5000
    statement_end_fraction: float = 0.1
    new_pattern_days: int = 60


@dataclass(frozen=True)
class UncertaintyParameters:
    confidence_weights: dict[str, float] = field(
        default_factory=lambda: {
            "CF01": 1.0,
            "CF02": 1.0,
            "CF03": 1.0,
            "CF04": 1.0,
            "CF05": 1.0,
            "CF06": 0.5,
            "CF07": 1.0,
            "CF08": 0.75,
            "CF09": 0.5,
            "CF10": 1.0,
        }
    )
    bootstrap_iterations: int = 400
    bootstrap_seed: int = 20260914
    bootstrap_block_months: int = 3
    bootstrap_trim_fraction: float = 0.1
    interval_level: float = 0.8


@dataclass(frozen=True)
class EngineParameters:
    data_quality: DataQualityParameters = field(default_factory=DataQualityParameters)
    roles: RoleParameters = field(default_factory=RoleParameters)
    neighbourhood: NeighbourhoodParameters = field(default_factory=NeighbourhoodParameters)
    multi_account: MultiAccountParameters = field(default_factory=MultiAccountParameters)
    cash: CashParameters = field(default_factory=CashParameters)
    cycle: CycleParameters = field(default_factory=CycleParameters)
    trend: TrendParameters = field(default_factory=TrendParameters)
    income: IncomeParameters = field(default_factory=IncomeParameters)
    coverage: CoverageParameters = field(default_factory=CoverageParameters)
    anomaly: AnomalyParameters = field(default_factory=AnomalyParameters)
    uncertainty: UncertaintyParameters = field(default_factory=UncertaintyParameters)
    windows_days: tuple[int, ...] = (30, 90, 180, 365)


DEFAULT_PARAMETERS = EngineParameters()

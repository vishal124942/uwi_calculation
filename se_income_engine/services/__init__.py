"""Engine services, one package per Section 24.1 component (M1 Parser/normaliser ... M9 Policy layer).

Stages the specification does not number as M components live under ``supporting/``. Inside a package read the
files in the order listed in its ``__init__.py``; file names keep the specification section prefix (``sNN_``).

    m1_parser_normaliser               M1   Section 3            statement parsers, canonical transactions, channel family
    supporting/dq_integrity_gate       gate Section 4            statement arithmetic, DQ01-DQ12, hard stops
    m2_role_classifier                 M2   Sections 5, 7, 8.1   identifiers, narration embedding, entities, neighbourhood,
                                                                 role model, calibration
    m3_rule_overlay                    M3   Section 7.4          versioned SET / MULTIPLY / RESTRICT rules
    m4_flow_pair_model                 M4   Sections 8.2, 17     reversal / recycling / pass-through pairs, account transfers
    supporting/ledger_operating_cash   feat Sections 10-12       EOC / COR / ROC ledger, cash eligibility, pass-through
    m5_archetype_classifier            M5   Section 9            business cash-flow archetype A01-A09
    m6_cycle_engine                    M6   Section 13           lag profile, build-up / liquidation
    supporting/signals_behaviour_risk  feat Sections 14-20       liquidity, financing, owner, trend, coverage, anomaly
    m7_income_estimator                M7   Sections 21, 16.2    ROC -> CAOCG -> SBCI, legal attribution
    m8_uncertainty_model               M8   Section 22           confidence dimensions, prediction interval
    m9_policy_layer                    M9   Section 21.5         UWI, hard stops, referral logic
    supporting/audit_explainability    out  Sections 23, 25, 28  bridge, reason codes, feature registry, audit store

``pipeline/analyse.py`` does not run the components strictly one after another (the archetype sits between two ledger
passes, the cycle engine needs the financing events). It reports progress at the ten ``PIPELINE_STEPS`` checkpoints
below; the UI trace is keyed by those checkpoint ids.
"""

_SERVICES = "se_income_engine.services"

# Section 24.1 component architecture (M1-M9), in execution order. Every module belongs to exactly one entry.
# Modules the spec does not assign to an M component are grouped into labelled supporting stages:
#   gate     - stops the analysis before any modelling (Section 4)
#   features - deterministic feature engines whose outputs feed the next M components
#   output   - explanation and audit of the finished decision
MODEL_COMPONENTS: tuple[dict, ...] = (
    {"id": "M1", "kind": "model", "name": "Parser/normaliser", "sections": "Section 3",
     "package": "m1_parser_normaliser",
     "technique": "Rules/templates + deterministic transforms",
     "responsibility": "Statement extraction and canonical transactions.",
     "modules": ("s03_statement_parsers", "s03_transaction_canonicalisation", "s03_channel_family_normaliser")},
    {"id": "DQ", "kind": "gate", "name": "Statement integrity gate", "sections": "Section 4",
     "package": "supporting.dq_integrity_gate",
     "technique": "Deterministic balance arithmetic and versioned thresholds",
     "responsibility": "DQ01-DQ12 metrics and hard stops; no model runs on a statement that fails.",
     "modules": ("s04_statement_integrity_gate",)},
    {"id": "M2", "kind": "model", "name": "Role classifier", "sections": "Sections 5, 7, 8.1",
     "package": "m2_role_classifier",
     "technique": "Gradient-boosted model + text/sequence embeddings, or calibrated transformer/GBM ensemble",
     "responsibility": "Transaction role probabilities.",
     "modules": ("s05_identifier_extraction", "s05_narration_encoder", "s05_entity_resolution",
                 "s08_neighbourhood_features", "s07_role_classifier", "s07_probability_calibrator")},
    {"id": "M3", "kind": "model", "name": "Rule overlay", "sections": "Section 7.4",
     "package": "m3_rule_overlay",
     "technique": "Versioned high-precision rules",
     "responsibility": "Deterministic bank/channel semantics and safety overrides.",
     "modules": ("s07_rule_overlay",)},
    {"id": "M4", "kind": "model", "name": "Flow-pair model", "sections": "Sections 8.2, 17",
     "package": "m4_flow_pair_model",
     "technique": "Heuristic + graph matching / learned pair scorer",
     "responsibility": "Transfers, reversals, pass-through, recycling.",
     "modules": ("s08_flow_pair_graph", "s17_multi_account_consolidation")},
    {"id": "LEDGER", "kind": "features", "name": "Economic ledger", "sections": "Sections 10-12",
     "package": "supporting.ledger_operating_cash",
     "technique": "Probability-weighted rupee buckets over rolling windows",
     "responsibility": "EOC, COR and ROC per transaction, month and window; cash eligibility and pass-through.",
     "modules": ("s10_operating_inflow_reconstruction", "s11_operating_outflow_reconstruction",
                 "s10_s11_window_aggregation", "s12_cash_cheque_merchant_passthrough")},
    {"id": "M5", "kind": "model", "name": "Archetype classifier", "sections": "Section 9",
     "package": "m5_archetype_classifier",
     "technique": "Multiclass calibrated model",
     "responsibility": "Business cash-flow archetype.",
     "modules": ("s09_archetype_inference",)},
    {"id": "M6", "kind": "model", "name": "Cycle engine", "sections": "Section 13",
     "package": "m6_cycle_engine",
     "technique": "Time-series/robust correlation + guarded heuristics",
     "responsibility": "Lag profile, build/liquidation evidence.",
     "modules": ("s13_working_capital_cycle_engine",)},
    {"id": "SIGNALS", "kind": "features", "name": "Behaviour and risk signals", "sections": "Sections 14-20",
     "package": "supporting.signals_behaviour_risk",
     "technique": "Deterministic feature engines over balances, roles and the pair graph",
     "responsibility": "Liquidity, financing, owner extraction, trend, coverage and anomaly inputs to M7-M9.",
     "modules": ("s14_balance_liquidity_engine", "s15_financing_debt_service", "s16_owner_extraction",
                 "s18_trend_seasonality", "s20_coverage_observability", "s19_anomaly_detection")},
    {"id": "M7", "kind": "model", "name": "Income estimator", "sections": "Sections 21, 16.2",
     "package": "m7_income_estimator",
     "technique": "Constrained interpretable model / robust estimator",
     "responsibility": "SBCI central estimate.",
     "modules": ("s21_income_normalisation", "s16_legal_attribution")},
    {"id": "M8", "kind": "model", "name": "Uncertainty model", "sections": "Section 22",
     "package": "m8_uncertainty_model",
     "technique": "Conformal or residual-calibrated interval",
     "responsibility": "Prediction interval and confidence.",
     "modules": ("s22_uncertainty_confidence",)},
    {"id": "M9", "kind": "model", "name": "Policy layer", "sections": "Section 21.5",
     "package": "m9_policy_layer",
     "technique": "Versioned decision/rule configuration",
     "responsibility": "UWI, hard stops, referral logic.",
     "modules": ("s21_policy_engine",)},
    {"id": "AUDIT", "kind": "output", "name": "Explainability and audit", "sections": "Sections 23, 25, 28",
     "package": "supporting.audit_explainability",
     "technique": "Bridge reconciliation, reason codes, versioned feature registry, immutable audit store",
     "responsibility": "Underwriter explanation and a reproducible record of every decision.",
     "modules": ("s28_explanation_engine", "s23_feature_registry", "s25_audit_persistence")},
)

COMPONENT_OF_MODULE: dict[str, str] = {m: c["id"] for c in MODEL_COMPONENTS for m in c["modules"]}
PACKAGE_OF_MODULE: dict[str, str] = {m: c["package"] for c in MODEL_COMPONENTS for m in c["modules"]}

# Execution checkpoints of ``run_analysis_pipeline``: the modules whose work is complete when each one fires.
PIPELINE_STEPS: tuple[dict, ...] = (
    {"id": "step01_ingest_and_clean", "title": "Ingest and clean", "sections": "Section 3",
     "modules": ("s03_statement_parsers", "s03_transaction_canonicalisation", "s03_channel_family_normaliser")},
    {"id": "step02_data_quality_gate", "title": "Data quality and statement integrity gate", "sections": "Section 4",
     "modules": ("s04_statement_integrity_gate",)},
    {"id": "step03_transaction_evidence", "title": "Per-transaction evidence", "sections": "Sections 5, 8.1",
     "modules": ("s05_identifier_extraction", "s05_narration_encoder", "s05_entity_resolution",
                 "s08_neighbourhood_features")},
    {"id": "step04_role_inference", "title": "Probabilistic role inference", "sections": "Section 7",
     "modules": ("s07_role_classifier", "s07_probability_calibrator", "s07_rule_overlay")},
    {"id": "step05_pairing_and_multi_account", "title": "Flow pairing and multi-account consolidation",
     "sections": "Sections 8.2, 17", "modules": ("s08_flow_pair_graph", "s17_multi_account_consolidation")},
    {"id": "step06_aggregation_archetype_cash", "title": "Rupee aggregation, archetype and cash eligibility",
     "sections": "Sections 9-12",
     "modules": ("s10_operating_inflow_reconstruction", "s11_operating_outflow_reconstruction",
                 "s10_s11_window_aggregation", "s09_archetype_inference", "s12_cash_cheque_merchant_passthrough")},
    {"id": "step07_risk_signals", "title": "Behaviour and risk signals", "sections": "Sections 13-20",
     "modules": ("s14_balance_liquidity_engine", "s15_financing_debt_service", "s13_working_capital_cycle_engine",
                 "s16_owner_extraction", "s18_trend_seasonality", "s20_coverage_observability",
                 "s19_anomaly_detection")},
    {"id": "step08_income_and_legal_attribution", "title": "Income normalisation and legal attribution",
     "sections": "Sections 21, 16.2", "modules": ("s21_income_normalisation", "s16_legal_attribution")},
    {"id": "step09_uncertainty_and_policy", "title": "Uncertainty, confidence and policy decision",
     "sections": "Sections 22, 21.5", "modules": ("s22_uncertainty_confidence", "s21_policy_engine")},
    {"id": "step10_explain_and_audit", "title": "Explanation, feature registry and audit persistence",
     "sections": "Sections 28, 23, 25",
     "modules": ("s28_explanation_engine", "s23_feature_registry", "s25_audit_persistence")},
)

STEP_OF_MODULE: dict[str, str] = {m: s["id"] for s in PIPELINE_STEPS for m in s["modules"]}


def module_path(module: str) -> str:
    """Dotted import path of a service module, e.g. ``se_income_engine.services.m1_parser_normaliser.s03_...``."""
    return f"{_SERVICES}.{PACKAGE_OF_MODULE[module]}.{module}"

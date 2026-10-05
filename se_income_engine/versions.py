"""Independently versioned components (Section 29.2)."""

COMPONENT_VERSIONS: dict[str, str] = {
    "parser": "analyser_xlsx_parser_v1.0.0",
    "transaction_normaliser": "canonicaliser_v1.0.0",
    "identifier_extractor": "identifier_extractor_v1.1.0",
    "feature_registry": "feature_registry_v1.0.0",
    "role_model": "role_model_baseline_loglinear_v1.0.0",
    "probability_calibrator": "temperature_calibrator_v1.0.0",
    "rule_overlay": "rule_overlay_v1.0.0",
    "pairing_model": "flow_pair_heuristic_v1.0.0",
    "archetype_model": "archetype_scoring_v1.0.0",
    "cycle_logic": "cash_cycle_engine_v1.0.0",
    "income_model": "robust_centre_income_v1.0.0",
    "uncertainty_model": "uncertainty_bootstrap_v1.0.0",
}

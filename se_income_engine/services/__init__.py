"""Engine services grouped by pipeline step, in the order ``pipeline/analyse.py`` executes them.

Read the step folders in numeric order; inside a folder read the files in the order listed in its
``__init__.py``. File names keep the specification section prefix (``sNN_``) so each file maps to its spec section.

    step01_ingest_and_clean              Section 3      parse, canonicalise, channel family
    step02_data_quality_gate             Section 4      statement arithmetic, DQ01-DQ12, hard stops
    step03_transaction_evidence          Sections 5, 8.1 identifiers, narration embedding, entities, neighbourhood
    step04_role_inference                Section 7      role classifier, calibration, rule overlay
    step05_pairing_and_multi_account     Sections 8.2, 17 flow pairs, inter-account transfers
    step06_aggregation_archetype_cash    Sections 9-12  EOC/COR/ROC windows, archetype, cash and pass-through
    step07_risk_signals                  Sections 13-20 liquidity, financing, cycle, owner, trend, coverage, anomaly
    step08_income_and_legal_attribution  Sections 21, 16.2 ROC -> CAOCG -> SBCI, legal attribution
    step09_uncertainty_and_policy        Sections 22, 21.5 confidence, interval, policy decision (UWI)
    step10_explain_and_audit             Sections 23, 25, 28 bridge, reason codes, feature registry, audit store
"""

SERVICE_STEPS: dict[str, tuple[str, ...]] = {
    "step01_ingest_and_clean": (
        "s03_statement_parsers", "s03_transaction_canonicalisation", "s03_channel_family_normaliser"),
    "step02_data_quality_gate": ("s04_statement_integrity_gate",),
    "step03_transaction_evidence": (
        "s05_identifier_extraction", "s05_narration_encoder", "s05_entity_resolution", "s08_neighbourhood_features"),
    "step04_role_inference": ("s07_role_classifier", "s07_probability_calibrator", "s07_rule_overlay"),
    "step05_pairing_and_multi_account": ("s08_flow_pair_graph", "s17_multi_account_consolidation"),
    "step06_aggregation_archetype_cash": (
        "s10_operating_inflow_reconstruction", "s11_operating_outflow_reconstruction", "s10_s11_window_aggregation",
        "s09_archetype_inference", "s12_cash_cheque_merchant_passthrough"),
    "step07_risk_signals": (
        "s14_balance_liquidity_engine", "s15_financing_debt_service", "s13_working_capital_cycle_engine",
        "s16_owner_extraction", "s18_trend_seasonality", "s20_coverage_observability", "s19_anomaly_detection"),
    "step08_income_and_legal_attribution": ("s21_income_normalisation", "s16_legal_attribution"),
    "step09_uncertainty_and_policy": ("s22_uncertainty_confidence", "s21_policy_engine"),
    "step10_explain_and_audit": ("s28_explanation_engine", "s23_feature_registry", "s25_audit_persistence"),
}

STEP_OF_MODULE: dict[str, str] = {m: step for step, mods in SERVICE_STEPS.items() for m in mods}

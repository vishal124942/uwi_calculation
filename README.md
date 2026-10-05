# Self-Employed Income Reconstruction Engine (spec v1.0)

Reconstructs sustainable business cash income from bank statements, following
`Self_Employed_Income_Reconstruction_Engine_Developer_Spec_v1.0`. Every service module is named
`sNN_<spec section name>.py`, so you can open the spec section and the module side by side.

## Code layout: read the step folders in order

Service modules live in `se_income_engine/services/`, grouped into step folders numbered in
execution order. Each folder's `__init__.py` lists the reading order of its files.

```
se_income_engine/
├── contracts/  config/  common/  versions.py      shared vocabulary, parameters, policy, helpers
├── services/
│   ├── step01_ingest_and_clean/                   §3      s03_statement_parsers → s03_transaction_canonicalisation → s03_channel_family_normaliser
│   ├── step02_data_quality_gate/                  §4      s04_statement_integrity_gate
│   ├── step03_transaction_evidence/               §5, 8.1 s05_identifier_extraction → s05_narration_encoder → s05_entity_resolution → s08_neighbourhood_features
│   ├── step04_role_inference/                     §7      s07_role_classifier → s07_probability_calibrator → s07_rule_overlay
│   ├── step05_pairing_and_multi_account/          §8.2,17 s08_flow_pair_graph → s17_multi_account_consolidation
│   ├── step06_aggregation_archetype_cash/         §9–12   s10_operating_inflow_reconstruction → s11_operating_outflow_reconstruction → s10_s11_window_aggregation → s09_archetype_inference → s12_cash_cheque_merchant_passthrough
│   ├── step07_risk_signals/                       §13–20  s14_balance_liquidity_engine → s15_financing_debt_service → s13_working_capital_cycle_engine → s16_owner_extraction → s18_trend_seasonality → s20_coverage_observability → s19_anomaly_detection
│   ├── step08_income_and_legal_attribution/       §21,16.2 s21_income_normalisation → s16_legal_attribution
│   ├── step09_uncertainty_and_policy/             §22,21.5 s22_uncertainty_confidence → s21_policy_engine
│   └── step10_explain_and_audit/                  §28,23,25 s28_explanation_engine → s23_feature_registry → s25_audit_persistence
├── pipeline/analyse.py                            orchestrator (calls the steps in this order)
├── api/  cli.py                                   entry points
```

`s17_multi_account_consolidation` is the one file that runs in several places:
`consolidate_transaction_stream` runs right after step 2, the transfer matching runs in step 5,
and `compute_multi_account_features` runs in step 7.

## The flow (Section 26 pseudocode, in execution order)

The orchestrator is `pipeline/analyse.py::analyse_self_employed_income`. It calls the functions
below in exactly this order; function names match the spec pseudocode.

Modules below are in `services/<step folder>/`; see the layout above for which folder holds which file.

| Step | Spec | What happens | Module · function |
|---|---|---|---|
| 1 | §3 | Parse statement, stable transaction IDs, canonical fields | `s03_statement_parsers.parse_analyser_xlsx` |
| 2 | §3.3 | Normalise narration, fix intraday order, derive balance_before | `s03_transaction_canonicalisation.canonicalize_all` |
| 3 | §4 | Balance arithmetic, DQ01–DQ12, hard stops | `s04_statement_integrity_gate.validate_statement_integrity` |
| 4 | §17 | One time-ordered stream across accounts | `s17_multi_account_consolidation.consolidate_transaction_stream` |
| 5 | §3.4 | Channel family (UPI/NEFT/CASH/ATM/FEE …) | `s03_channel_family_normaliser.normalize_channel` |
| 6 | §5.2 | VPA, IFSC, UTR, account fragment, mandate, names | `s05_identifier_extraction.extract_identifiers` |
| 7 | §5.3 | Hashed char-trigram narration embedding | `s05_narration_encoder.encode_narration` |
| 8 | §5.4 | Latent counterparty entities (aliases → one entity) | `s05_entity_resolution.optional_latent_entity_clustering` |
| 9 | §8.1 | NF01–NF12 neighbourhood features, counterfactual retention | `s08_neighbourhood_features.build_neighbourhood_features` |
| 10 | §7 | Role probabilities over C01–C13 / D01–D19 (M2) | `s07_role_classifier.RoleClassifier.predict` |
| 11 | §7.3 | Temperature calibration | `s07_probability_calibrator.probability_calibrator` |
| 12 | §7.4 | Versioned SET / MULTIPLY / RESTRICT rules (M3) | `s07_rule_overlay.apply_versioned_rule_overlay` |
| 13 | §8.2 | Reversal / recycling / pass-through matching (M4) | `s08_flow_pair_graph.build_flow_pair_graph` |
| 14 | §8.2 | Pair evidence updates roles | `s08_flow_pair_graph.update_roles_from_pair_evidence` |
| 15 | §17.2 | Inter-account transfers (ownership linkage ≠ false) | `s17_….match_interaccount_transfers`, `exclude_internal_transfer_economics` |
| 16 | §10–11 | Economic ledger → EOC, COR, ROC per window and month | `s10_s11_window_aggregation.aggregate_windows` |
| 17 | §9 | Business archetype A01–A09 (M5) | `s09_archetype_inference.archetype_model` |
| 18 | §12 | Cash-business probability, pass-through economics | `s12_cash_cheque_merchant_passthrough` |
| 19 | §14 | BAL01–BAL12 liquidity | `s14_balance_liquidity_engine.compute_balance_liquidity` |
| 20 | §15 | FIN01–FIN10, debt service | `s15_financing_debt_service.compute_financing_dependency` |
| 21 | §13 | Cash-cycle lag, build/liquidation (M6) | `s13_working_capital_cycle_engine.infer_operating_cycle` |
| 22 | §16.1 | OWN01–OWN08 owner extraction | `s16_owner_extraction.compute_owner_extraction` |
| 23 | §18 | TR01–TR12, regime (asymmetric decline/growth) | `s18_trend_seasonality.compute_trend_seasonality` |
| 24 | §20 | CV01–CV10 coverage risk | `s20_coverage_observability.compute_coverage_risk` |
| 25 | §19 | AN01–AN14 anomalies / window dressing | `s19_anomaly_detection.compute_anomaly_features` |
| 26 | §21.1–21.2 | ROC → cycle-adjusted CAOCG | `s21_income_normalisation.reconstruct_operating_cash_generation`, `normalize_cycle_and_seasonality` |
| 27 | §21.3–21.4 | Robust centre − maintenance reserve = SBCI (M7) | `s21_income_normalisation.sustainable_income_model` |
| 28 | §16.2 | Legal attribution (proprietor / firm / company) | `s16_legal_attribution.attribute_business_income_to_borrower` |
| 29 | §22 | CF01–CF10, interval (M8) | `s22_uncertainty_confidence.uncertainty_model` |
| 30 | §21.5 | Versioned policy → UWI, referrals (M9) | `s21_policy_engine.policy_engine` |
| 31 | §28 | Economic bridge + reason codes RC01–RC10 | `s28_explanation_engine.explanation_engine` |
| 32 | §23 | Feature vector F001–F100 | `s23_feature_registry.materialise_feature_vector` |
| 33 | §25.3 | Immutable audit trail (SQLite, Appendix B tables) | `s25_audit_persistence.AuditStore.persist_full_audit_trail` |

The output staircase, which is also the bridge shown to underwriters:

```
Gross credits − financing − internal − other non-operating = EOC
EOC − COR = ROC  →  ± cycle normalisation = CAOCG  →  robust centre − maintenance reserve = SBCI
SBCI − existing debt service = PDFC (reported separately)
UWI = policy_select(SBCI distribution, confidence, legal attribution)
```

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# CLI: one or more statements (multi-account consolidation is automatic)
.venv/bin/python -m se_income_engine.cli statement.xlsx --legal-owner-type SOLE_PROP --out result.json --audit-db audit.db

# Step-by-step CSV snapshots: what the data looks like after every step folder
.venv/bin/python -m se_income_engine.cli statement.xlsx --steps-dir steps_statement
#   step01..step06 *_transactions_*.csv are cumulative: same rows, each step appends its own sNN_ columns
#   (channel → identifiers/entity/NF → roles → pairing → economic ledger buckets).
#   step06..step10 also write summaries: monthly/window totals, risk signals, income series, policy, bridge.

# API (Section 25.1)
.venv/bin/uvicorn se_income_engine.api.app:app
#   POST /v1/self-employed-income/analyse              JSON request per Section 25.1
#   POST /v1/self-employed-income/analyse-statement    raw analyser .xlsx bytes as body (query: customer_id, application_id, legal_owner_type)
#   GET  /v1/self-employed-income/analyses/{id}        replay a persisted analysis
#   GET  /v1/feature-registry, GET /health

# Tests: UT-01..UT-15, name ablation (27.4), bridge/idempotency/audit/API, real-statement smoke
.venv/bin/pytest
```

## Design decisions worth knowing

- **Money is `Decimal` everywhere.** Floats appear only in features and probabilities.
- **Evidence-gated roles.** Lender, EMI, capex, tax, charge, reversal, cash, owner, personal and
  internal roles keep near-zero mass unless some evidence fires. Unexplained debits therefore cannot
  create phantom debt service or hide operating cost as "personal".
- **Unknown stays unknown (§2).** Unknown debits are outside COR (§11.1), but their operating-share
  mass is carried as an *unresolved-outflow allowance* that lowers the interval's lower bound. With
  the default LOWER_BOUND policy, losing evidence (e.g. masked names) can only lower UWI, never raise it.
- **Non-recurring outflows.** A one-off, atypically large debit that is probably not operating has
  its residual operating share carried as downside, not as recurring COR (UT-09).
- **Interval.** Moving-block bootstrap over cycle-adjusted months, labelled
  `BOOTSTRAP_UNCALIBRATED` until a conformal artifact (`ConformalArtifact`) is fitted on verified
  income anchors (§22.3).
- **Idempotent.** `analysis_id` hashes the request content, component versions, parameters and policy.
  A persisted analysis is returned unchanged on replay.

## Known limitations

- The role model (M2) is a transparent log-linear baseline with hand-set evidence weights. It exposes
  `predict()` so a trained GBM or transformer can replace it; there is no labelled data yet for
  calibration (temperature is the identity).
- Parameters (gates, thresholds, robust-centre weights) are defaults, not back-tested against
  verified income or repayment outcomes, as §21.3 requires before production use.
- Seasonality normalisation needs ≥ 24 months of comparable history and is skipped otherwise.

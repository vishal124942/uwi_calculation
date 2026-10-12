# Self-Employed Income Reconstruction Engine (spec v1.0)

Reconstructs sustainable business cash income from bank statements, following
`Self_Employed_Income_Reconstruction_Engine_Developer_Spec_v1.0`. Every service module is named
`sNN_<spec section name>.py`, so you can open the spec section and the module side by side.

## Code layout: one package per Section 24.1 component

Service modules live in `se_income_engine/services/`, one package per component of the spec's Section 24.1
architecture (M1 Parser/normaliser … M9 Policy layer). Stages the spec does not number as M components live under
`services/supporting/`. Each package's `__init__.py` gives the component's technique and responsibility and the
reading order of its files; `services/__init__.py` holds the registry (`MODEL_COMPONENTS`) the API and UI read.

```
se_income_engine/
├── contracts/  config/  common/  versions.py       shared vocabulary, parameters, policy, helpers
├── services/
│   ├── m1_parser_normaliser/        M1   §3        s03_statement_parsers → s03_transaction_canonicalisation → s03_channel_family_normaliser
│   ├── m2_role_classifier/          M2   §5,7,8.1  s05_identifier_extraction → s05_narration_encoder → s05_entity_resolution → s08_neighbourhood_features → s07_role_classifier → s07_probability_calibrator
│   ├── m3_rule_overlay/             M3   §7.4      s07_rule_overlay
│   ├── m4_flow_pair_model/          M4   §8.2,17   s08_flow_pair_graph → s17_multi_account_consolidation
│   ├── m5_archetype_classifier/     M5   §9        s09_archetype_inference
│   ├── m6_cycle_engine/             M6   §13       s13_working_capital_cycle_engine
│   ├── m7_income_estimator/         M7   §21,16.2  s21_income_normalisation → s16_legal_attribution
│   ├── m8_uncertainty_model/        M8   §22       s22_uncertainty_confidence
│   ├── m9_policy_layer/             M9   §21.5     s21_policy_engine
│   └── supporting/
│       ├── dq_integrity_gate/       gate §4        s04_statement_integrity_gate
│       ├── ledger_operating_cash/        §10–12    s10_operating_inflow_reconstruction → s11_operating_outflow_reconstruction → s10_s11_window_aggregation → s12_cash_cheque_merchant_passthrough
│       ├── signals_behaviour_risk/       §14–20    s14_balance_liquidity_engine → s15_financing_debt_service → s16_owner_extraction → s18_trend_seasonality → s20_coverage_observability → s19_anomaly_detection
│       └── audit_explainability/         §23,25,28 s28_explanation_engine → s23_feature_registry → s25_audit_persistence
├── pipeline/analyse.py                             orchestrator (calls the components in the order below)
├── api/  cli.py                                    entry points
```

The orchestrator does not run the components strictly one after another, because some need each other's outputs:
the M5 archetype runs between the two economic-ledger aggregation passes (cash eligibility depends on it), and the
M6 cycle engine runs inside the risk-signal stage once the financing events exist. `s17_multi_account_consolidation`
(M4) also runs in three places: `consolidate_transaction_stream` right after the integrity gate, the transfer matching
with the flow pairing, and `compute_multi_account_features` with the risk signals.

Progress is reported at ten execution checkpoints, `step01_ingest_and_clean` … `step10_explain_and_audit`
(`PIPELINE_STEPS` in `services/__init__.py`); the UI's live trace is keyed by them.

## The flow (Section 26 pseudocode, in execution order)

The orchestrator is `pipeline/analyse.py::analyse_self_employed_income`. It calls the functions
below in exactly this order; function names match the spec pseudocode.

| Step | Component | Spec | What happens | Module · function |
|---|---|---|---|---|
| 1 | M1 | §3 | Parse statement, stable transaction IDs, canonical fields | `s03_statement_parsers.parse_analyser_xlsx` |
| 2 | M1 | §3.3 | Normalise narration, fix intraday order, derive balance_before | `s03_transaction_canonicalisation.canonicalize_all` |
| 3 | gate | §4 | Balance arithmetic, DQ01–DQ12, hard stops | `s04_statement_integrity_gate.validate_statement_integrity` |
| 4 | M4 | §17 | One time-ordered stream across accounts | `s17_multi_account_consolidation.consolidate_transaction_stream` |
| 5 | M1 | §3.4 | Channel family from the source `Mode` column, else the `Payment Mode` category (no narration matching) | `s03_channel_family_normaliser.normalize_channel` |
| 6 | M2 | §5.2 | VPA, IFSC, UTR, account fragment, mandate, names | `s05_identifier_extraction.extract_identifiers` |
| 7 | M2 | §5.3 | Hashed char-trigram narration embedding | `s05_narration_encoder.encode_narration` |
| 8 | M2 | §5.4 | Latent counterparty entities (aliases → one entity) | `s05_entity_resolution.optional_latent_entity_clustering` |
| 9 | M2 | §8.1 | NF01–NF12 neighbourhood features, counterfactual retention | `s08_neighbourhood_features.build_neighbourhood_features` |
| 10 | M2 | §7 | Role probabilities over C01–C13 / D01–D19 | `s07_role_classifier.RoleClassifier.predict` |
| 11 | M2 | §7.3 | Temperature calibration | `s07_probability_calibrator.probability_calibrator` |
| 12 | M3 | §7.4 | Versioned SET / MULTIPLY / RESTRICT rules | `s07_rule_overlay.apply_versioned_rule_overlay` |
| 13 | M4 | §8.2 | Reversal / recycling / pass-through matching | `s08_flow_pair_graph.build_flow_pair_graph` |
| 14 | M4 | §8.2 | Pair evidence updates roles | `s08_flow_pair_graph.update_roles_from_pair_evidence` |
| 15 | M4 | §17.2 | Inter-account transfers (ownership linkage ≠ false) | `s17_….match_interaccount_transfers`, `exclude_internal_transfer_economics` |
| 16 | ledger | §10–11 | Economic ledger → EOC, COR, ROC per window and month | `s10_s11_window_aggregation.aggregate_windows` |
| 17 | M5 | §9 | Business archetype A01–A09 | `s09_archetype_inference.archetype_model` |
| 18 | ledger | §12 | Cash-business probability, pass-through economics | `s12_cash_cheque_merchant_passthrough` |
| 19 | signals | §14 | BAL01–BAL12 liquidity | `s14_balance_liquidity_engine.compute_balance_liquidity` |
| 20 | signals | §15 | FIN01–FIN10, debt service | `s15_financing_debt_service.compute_financing_dependency` |
| 21 | M6 | §13 | Cash-cycle lag, build/liquidation | `s13_working_capital_cycle_engine.infer_operating_cycle` |
| 22 | signals | §16.1 | OWN01–OWN08 owner extraction | `s16_owner_extraction.compute_owner_extraction` |
| 23 | signals | §18 | TR01–TR12, regime (asymmetric decline/growth) | `s18_trend_seasonality.compute_trend_seasonality` |
| 24 | signals | §20 | CV01–CV10 coverage risk | `s20_coverage_observability.compute_coverage_risk` |
| 25 | signals | §19 | AN01–AN14 anomalies / window dressing | `s19_anomaly_detection.compute_anomaly_features` |
| 26 | M7 | §21.1–21.2 | ROC → cycle-adjusted CAOCG | `s21_income_normalisation.reconstruct_operating_cash_generation`, `normalize_cycle_and_seasonality` |
| 27 | M7 | §21.3–21.4 | Robust centre − maintenance reserve = SBCI | `s21_income_normalisation.sustainable_income_model` |
| 28 | M7 | §16.2 | Legal attribution (proprietor / firm / company) | `s16_legal_attribution.attribute_business_income_to_borrower` |
| 29 | M8 | §22 | CF01–CF10, interval | `s22_uncertainty_confidence.uncertainty_model` |
| 30 | M9 | §21.5 | Versioned policy → UWI, referrals | `s21_policy_engine.policy_engine` |
| 31 | audit | §28 | Economic bridge + reason codes RC01–RC10 | `s28_explanation_engine.explanation_engine` |
| 32 | audit | §23 | Feature vector F001–F100 | `s23_feature_registry.materialise_feature_vector` |
| 33 | audit | §25.3 | Immutable audit trail (SQLite, Appendix B tables) | `s25_audit_persistence.AuditStore.persist_full_audit_trail` |

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

# API (Section 25.1)
.venv/bin/uvicorn se_income_engine.api.app:app
#   POST /v1/self-employed-income/analyse              JSON request per Section 25.1
#   POST /v1/self-employed-income/analyse-statement    raw analyser .xlsx bytes as body (query: customer_id, application_id, legal_owner_type)
#   GET  /v1/self-employed-income/analyses/{id}        replay a persisted analysis
#   GET  /v1/feature-registry, GET /health
#   GET  /v1/ui/meta                                   components, checkpoints, role/archetype names, policies, demo scenarios
#   POST /v1/ui/trace                                  multipart statement upload → NDJSON stream, one event per checkpoint
#   POST /v1/ui/trace/demo?scenario=kirana_trader      same stream for a synthetic statement

# Tests: UT-01..UT-15, name ablation (27.4), bridge/idempotency/audit/API, real-statement smoke
.venv/bin/pytest
```

## Pipeline explorer UI

`frontend/` is a Next.js app that runs an analysis live, organised by the Section 24.1 component architecture
(M1 Parser/normaliser … M9 Policy layer). `MODEL_COMPONENTS` in `se_income_engine/services/__init__.py` assigns every
module to one component; modules the spec gives no M number form labelled supporting stages (statement integrity gate,
economic ledger, behaviour and risk signals, explainability and audit). Each component page shows the spec's technique
and responsibility, the modules that implement it, worked formulas with this run's numbers, the transaction columns it
adds and its raw tables; a journey view follows one transaction through M1 → M4 and the ledger.

```bash
.venv/bin/uvicorn se_income_engine.api.app:app --reload     # API on :8000
cd frontend && npm install && npm run dev                    # UI on http://localhost:3000
```

The UI calls the API directly at `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`); the API allows the origins
in `SEI_UI_ORIGINS` (default `http://localhost:3000,http://127.0.0.1:3000`). Trace runs skip the idempotency cache
and are not written to the audit store.

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

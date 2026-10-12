"""Section 26 - End-to-end processing pipeline: ``analyse_self_employed_income``.

The step order and function names mirror the specification pseudocode exactly; the services they call are
packaged by Section 24.1 component (see ``se_income_engine/services/__init__.py``).
Given identical source data, artifacts, configuration, as-of date and policy version the output is
identical (Section 26.1); ``analysis_id`` is a content hash used as the idempotency key.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from decimal import Decimal

from se_income_engine.common.money import quantize
from se_income_engine.config.parameters import DEFAULT_PARAMETERS, EngineParameters
from se_income_engine.config.policy import get_policy
from se_income_engine.contracts.enums import AnalysisStatus, LegalOwnerType
from se_income_engine.pipeline.context import AnalysisContext, AnalysisRequest
# M1 Parser/normaliser
from se_income_engine.services.m1_parser_normaliser.s03_channel_family_normaliser import normalize_channel
from se_income_engine.services.m1_parser_normaliser.s03_transaction_canonicalisation import canonicalize_all
# M2 Role classifier (evidence features, model, calibration)
from se_income_engine.services.m2_role_classifier.s05_entity_resolution import cluster_statistics, optional_latent_entity_clustering
from se_income_engine.services.m2_role_classifier.s05_identifier_extraction import extract_identifiers
from se_income_engine.services.m2_role_classifier.s05_narration_encoder import encode_narration
from se_income_engine.services.m2_role_classifier.s07_probability_calibrator import default_calibration_artifact, probability_calibrator
from se_income_engine.services.m2_role_classifier.s07_role_classifier import RoleClassifier
from se_income_engine.services.m2_role_classifier.s08_neighbourhood_features import (
    build_neighbourhood_features,
    update_neighbourhood_role_shares,
)
# M3 Rule overlay
from se_income_engine.services.m3_rule_overlay.s07_rule_overlay import apply_versioned_rule_overlay, refresh_prediction
# M4 Flow-pair model
from se_income_engine.services.m4_flow_pair_model.s08_flow_pair_graph import build_flow_pair_graph, update_roles_from_pair_evidence
from se_income_engine.services.m4_flow_pair_model.s17_multi_account_consolidation import (
    compute_multi_account_features,
    consolidate_transaction_stream,
    exclude_internal_transfer_economics,
    match_interaccount_transfers,
    multiple_supplied_accounts,
)
# M5 Archetype classifier
from se_income_engine.services.m5_archetype_classifier.s09_archetype_inference import archetype_model
# M6 Cycle engine
from se_income_engine.services.m6_cycle_engine.s13_working_capital_cycle_engine import infer_operating_cycle
# M7 Income estimator
from se_income_engine.services.m7_income_estimator.s16_legal_attribution import attribute_business_income_to_borrower
from se_income_engine.services.m7_income_estimator.s21_income_normalisation import (
    normalize_cycle_and_seasonality,
    reconstruct_operating_cash_generation,
    sustainable_income_model,
)
# M8 Uncertainty model
from se_income_engine.services.m8_uncertainty_model.s22_uncertainty_confidence import (
    ConformalArtifact,
    amount_weighted_role_uncertainty,
    cross_view_consistency,
    uncertainty_model,
    unresolved_flow_allowances,
)
# M9 Policy layer
from se_income_engine.services.m9_policy_layer.s21_policy_engine import policy_engine
# Supporting stages: integrity gate, economic ledger, behaviour and risk signals, explainability and audit
from se_income_engine.services.supporting.audit_explainability.s23_feature_registry import materialise_feature_vector
from se_income_engine.services.supporting.audit_explainability.s25_audit_persistence import AuditStore
from se_income_engine.services.supporting.audit_explainability.s28_explanation_engine import explanation_engine
from se_income_engine.services.supporting.dq_integrity_gate.s04_statement_integrity_gate import validate_statement_integrity
from se_income_engine.services.supporting.ledger_operating_cash.s10_s11_window_aggregation import aggregate_windows
from se_income_engine.services.supporting.ledger_operating_cash.s12_cash_cheque_merchant_passthrough import (
    compute_cash_business_probability,
    compute_pass_through_economics,
)
from se_income_engine.services.supporting.signals_behaviour_risk.s14_balance_liquidity_engine import compute_balance_liquidity
from se_income_engine.services.supporting.signals_behaviour_risk.s15_financing_debt_service import compute_financing_dependency
from se_income_engine.services.supporting.signals_behaviour_risk.s16_owner_extraction import compute_owner_extraction, finalise_owner_against_sbci
from se_income_engine.services.supporting.signals_behaviour_risk.s18_trend_seasonality import compute_trend_seasonality
from se_income_engine.services.supporting.signals_behaviour_risk.s19_anomaly_detection import compute_anomaly_features
from se_income_engine.services.supporting.signals_behaviour_risk.s20_coverage_observability import compute_coverage_risk
from se_income_engine.versions import COMPONENT_VERSIONS


StepHook = Callable[[str, AnalysisContext], None]


def _m(value: Decimal | None) -> float | None:
    return None if value is None else float(quantize(value))


def compute_analysis_id(request: AnalysisRequest, policy_id: str, policy_version: str,
                        params: EngineParameters = DEFAULT_PARAMETERS) -> str:
    payload = {
        "customer_id": request.customer_id,
        "application_id": request.application_id,
        "as_of_date": request.as_of_date.isoformat(),
        "policy": [policy_id, policy_version],
        "versions": COMPONENT_VERSIONS,
        "parameters": hashlib.sha256(repr(params).encode()).hexdigest(),
        "borrower_context": {
            "legal_owner_type": request.borrower_context.legal_owner_type.value,
            "application_date": str(request.borrower_context.application_date),
            "documents": request.borrower_context.documents,
        },
        "accounts": [
            [a.account_id, a.account_type.value, a.legal_owner_type.value, a.currency,
             hashlib.sha256("|".join(t.transaction_id for t in a.transactions).encode()).hexdigest()]
            for a in request.accounts
        ],
    }
    return "SEI-" + hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:24]


def _holder_info(account) -> tuple[str | None, str | None]:
    masked = account.parser_metadata.get("masked_account") or ""
    digits = re.findall(r"\d+", masked)
    return account.parser_metadata.get("holder_name"), (digits[-1][-4:] if digits else None)


def _resolve_legal_owner_type(request: AnalysisRequest) -> LegalOwnerType:
    if request.borrower_context.legal_owner_type != LegalOwnerType.UNKNOWN:
        return request.borrower_context.legal_owner_type
    known = {a.legal_owner_type for a in request.accounts if a.legal_owner_type != LegalOwnerType.UNKNOWN}
    return known.pop() if len(known) == 1 else LegalOwnerType.UNKNOWN


def analyse_self_employed_income(request: AnalysisRequest, params: EngineParameters = DEFAULT_PARAMETERS,
                                 store: AuditStore | None = None,
                                 conformal: ConformalArtifact | None = None,
                                 on_step: StepHook | None = None) -> dict:
    """Section 26 entry point: idempotent on analysis_id, persists the full audit trail when a store is given.
    With ``on_step`` the cache is bypassed so every step actually runs and can be captured."""
    policy = get_policy(request.policy_id)
    if store is not None and on_step is None:
        cached = store.get_analysis(compute_analysis_id(request, policy.policy_id, policy.policy_version, params))
        if cached is not None:
            return cached
    ctx = run_analysis_pipeline(request, params, conformal, on_step)
    if ctx.dq.hard_stop:
        return build_failure_response(ctx)
    response = build_response(ctx)
    if store is not None:
        store.persist_full_audit_trail(ctx, response)
    return response


def run_analysis_pipeline(request: AnalysisRequest, params: EngineParameters = DEFAULT_PARAMETERS,
                          conformal: ConformalArtifact | None = None,
                          on_step: StepHook | None = None) -> AnalysisContext:
    """Executes Sections 3-23 and 28 and returns every intermediate result on the AnalysisContext.
    ``on_step(step_id, ctx)`` is called at each ``services.PIPELINE_STEPS`` checkpoint."""
    policy = get_policy(request.policy_id)
    ctx = AnalysisContext(request=request, params=params, policy=policy)
    ctx.analysis_id = compute_analysis_id(request, policy.policy_id, policy.policy_version, params)

    def step_done(name: str) -> None:
        if on_step is not None:
            on_step(name, ctx)

    # --- M1 canonicalise, then the statement integrity gate (Sections 3, 4)
    accounts = canonicalize_all(request.accounts)
    ctx.accounts = accounts
    step_done("step01_ingest_and_clean")
    docs = request.borrower_context.documents or {}
    dq = validate_statement_integrity(accounts, params.data_quality,
                                      has_corroborating_data=bool(docs.get("gst_turnover_monthly")))
    ctx.dq = dq
    step_done("step02_data_quality_gate")
    if dq.hard_stop:
        return ctx

    # --- M4 merges the account streams; M1 channel family; M2 evidence features (Sections 3.4, 5, 8.1, 17)
    txns = consolidate_transaction_stream(accounts)
    ctx.txns = txns
    holder = {a.account_id: _holder_info(a) for a in accounts}
    for txn in txns:
        txn.channel_family = normalize_channel(txn)
        name, suffix = holder[txn.account_id]
        ctx.identifiers[txn.transaction_id] = extract_identifiers(txn, name, suffix)
        ctx.text_features[txn.transaction_id] = encode_narration(txn.normalized_narration)

    ctx.hypotheses = optional_latent_entity_clustering(txns, ctx.identifiers)
    ctx.cluster_stats = cluster_statistics(txns, ctx.hypotheses)
    ctx.neighbourhood = build_neighbourhood_features(txns, ctx.hypotheses, ctx.cluster_stats, params.neighbourhood)
    step_done("step03_transaction_evidence")

    # --- M2 role model + calibration, then the M3 rule overlay (Section 7)
    role_model = RoleClassifier(emi_interest_share=params.roles.emi_interest_share)
    role_probs_raw = role_model.predict(txns, ctx.identifiers, ctx.hypotheses, ctx.cluster_stats, ctx.neighbourhood)
    role_probs_cal = probability_calibrator(role_probs_raw, default_calibration_artifact(
        params.roles.calibration_temperature_credit, params.roles.calibration_temperature_debit))
    ctx.pre_rule_probabilities = {tid: dict(p.final_probabilities) for tid, p in role_probs_cal.items()}
    role_probs_final = apply_versioned_rule_overlay(role_probs_cal, txns, ctx.identifiers, ctx.neighbourhood, params.roles)
    ctx.predictions = role_probs_final
    step_done("step04_role_inference")

    # --- M4 flow pairing (Section 8.2)
    pair_graph = build_flow_pair_graph(txns, role_probs_final, ctx.hypotheses, ctx.cluster_stats, ctx.neighbourhood,
                                       params.neighbourhood)
    ctx.pair_graph = pair_graph
    update_roles_from_pair_evidence(role_probs_final, pair_graph)

    # --- M4 inter-account transfers (Section 17)
    if multiple_supplied_accounts(accounts):
        internal_edges = match_interaccount_transfers(accounts, pair_graph, params.multi_account, ctx.identifiers)
        exclude_internal_transfer_economics(internal_edges, role_probs_final, pair_graph)
        ctx.internal_edges = internal_edges
    for pred in role_probs_final.values():
        refresh_prediction(pred)
    update_neighbourhood_role_shares(txns, ctx.neighbourhood, role_probs_final)
    step_done("step05_pairing_and_multi_account")

    # --- economic ledger, with M5 archetype between the two aggregation passes (Sections 9-12)
    stmt_start = min(a.statement_start for a in accounts)
    stmt_end = max(a.statement_end for a in accounts)
    application_date = request.borrower_context.application_date or request.as_of_date

    def aggregate(cash_eligibility):
        return aggregate_windows(txns, role_probs_final, ctx.hypotheses, ctx.cluster_stats, cash_eligibility,
                                 request.as_of_date, stmt_start, stmt_end, params.windows_days, params.income,
                                 params.roles)

    account_features = aggregate({})
    archetype = archetype_model(account_features, txns, ctx.neighbourhood, accounts)
    ctx.cash_eligibility = compute_cash_business_probability(txns, role_probs_final, ctx.neighbourhood, archetype.top,
                                                             application_date, account_features.history_months,
                                                             params.cash)
    if ctx.cash_eligibility:
        account_features = aggregate(ctx.cash_eligibility)
    ctx.account_features, ctx.archetype = account_features, archetype
    ctx.pass_through = compute_pass_through_economics(pair_graph, txns, role_probs_final)
    step_done("step06_aggregation_archetype_cash")

    # --- behaviour and risk signals; M6 cycle engine once the financing events exist (Sections 13-20)
    ctx.liquidity = compute_balance_liquidity(accounts, account_features, ctx.neighbourhood)
    ctx.financing = compute_financing_dependency(txns, role_probs_final, account_features, ctx.liquidity)
    ctx.cycle = infer_operating_cycle(account_features, ctx.financing.financing_events, archetype.top, params.cycle)
    ctx.owner = compute_owner_extraction(txns, role_probs_final, account_features)
    ctx.multi_account = compute_multi_account_features(accounts, txns, role_probs_final, ctx.internal_edges,
                                                       account_features.eoc_by_account, account_features.cor_by_account)
    ctx.multi_account["MA09_ConsolidatedBalanceLiquidity"] = ctx.liquidity.features.get("MA09_ConsolidatedBalanceLiquidity")
    ctx.role_uncertainty = amount_weighted_role_uncertainty(txns, role_probs_final)
    ctx.trend = compute_trend_seasonality(account_features, ctx.liquidity, params.trend)
    ctx.coverage = compute_coverage_risk(accounts, txns, account_features, ctx.multi_account, archetype.top,
                                         ctx.cycle.status.value == "IDENTIFIED",
                                         ctx.financing.features["FIN01_FinancingCreditRatio"] or 0.0,
                                         ctx.role_uncertainty, docs, params.coverage)
    ctx.anomalies = compute_anomaly_features(txns, role_probs_final, account_features, pair_graph, ctx.neighbourhood,
                                             ctx.hypotheses, ctx.cluster_stats, ctx.liquidity, application_date,
                                             params.anomaly)
    step_done("step07_risk_signals")

    # --- M7 income estimator: ROC -> CAOCG -> SBCI (Section 21)
    ctx.roc = reconstruct_operating_cash_generation(account_features)
    ctx.caocg = normalize_cycle_and_seasonality(ctx.roc, ctx.cycle, ctx.trend, account_features)
    ctx.cycle.features["WC08_CycleAdjustedROC"] = float(ctx.caocg.basis.value)
    ctx.sbci = sustainable_income_model(ctx.caocg, ctx.roc, account_features, ctx.trend, params.income, params.trend,
                                        ctx.permitted_adjustments)
    finalise_owner_against_sbci(ctx.owner, account_features, ctx.sbci.sbci_monthly)

    # --- M7 legal attribution (Section 16.2)
    ctx.legal = attribute_business_income_to_borrower(ctx.sbci.sbci_monthly, ctx.owner,
                                                      _resolve_legal_owner_type(request), docs)
    step_done("step08_income_and_legal_attribution")

    # --- M8 uncertainty, then the M9 policy layer (Sections 22, 21.5)
    dq_metrics = _consolidated_dq_metrics(dq)
    unresolved_out, unresolved_in = unresolved_flow_allowances(account_features.full_period.totals,
                                                               account_features.full_period.months)
    cross_view = cross_view_consistency(ctx.sbci.sbci_monthly, account_features.full_period.monthly("eoc"),
                                        ctx.liquidity.features.get("BAL09_ReceiptRetention7d"),
                                        ctx.liquidity.features.get("BAL10_BalanceTrend90"),
                                        ctx.owner.owner_draw_monthly,
                                        ctx.coverage.features.get("CV10_ExternalDenominatorCoverage"))
    ctx.uncertainty = uncertainty_model(
        sbci=ctx.sbci.sbci_monthly,
        monthly_caocg=[float(p.value) for p in ctx.caocg.monthly if p.complete],
        dq_metrics=dq_metrics,
        history_months=account_features.history_months,
        role_uncertainty=ctx.role_uncertainty,
        trend_features=ctx.trend.features,
        coverage_risk=ctx.coverage.risk,
        cycle_quality=ctx.cycle.features.get("WC14_CycleEvidenceQuality"),
        archetype_code=archetype.top,
        archetype_probability=archetype.probability,
        financing_ratio=ctx.financing.features["FIN01_FinancingCreditRatio"] or 0.0,
        financing_contamination=ctx.anomalies.features.get("AN07_FinancingContamination"),
        cross_view=cross_view,
        legal_confidence=ctx.legal.confidence,
        account_type=accounts[0].account_type.value if len(accounts) == 1 else "MULTI",
        lower_q=policy.lower_quantile,
        upper_q=policy.upper_quantile,
        p=params.uncertainty,
        conformal=conformal,
        unresolved_outflow=unresolved_out,
        unresolved_inflow=unresolved_in,
    )
    ctx.decision = policy_engine(ctx.sbci, ctx.uncertainty, ctx.legal, ctx.coverage, ctx.anomalies,
                                 ctx.trend.features.get("TR11_RecentDeteriorationScore") or 0.0, accounts, policy)
    step_done("step09_uncertainty_and_policy")

    # --- explainability and audit (Sections 23, 25, 28)
    ctx.explanation = explanation_engine(ctx)
    ctx.reason_codes = ctx.explanation.reasons
    ctx.feature_vector = materialise_feature_vector(ctx)
    step_done("step10_explain_and_audit")
    return ctx


def _consolidated_dq_metrics(dq) -> dict:
    metrics = [q.metrics for q in dq.accounts.values()]
    recon = [m["DQ02_TxnReconciliationPassRate"] for m in metrics if m["DQ02_TxnReconciliationPassRate"] is not None]
    return {
        "DQ01_StatementCoverageDays": min(m["DQ01_StatementCoverageDays"] for m in metrics),
        "DQ02_TxnReconciliationPassRate": min(recon) if recon else None,
        "DQ07_ParseLowConfidenceRate": max(m["DQ07_ParseLowConfidenceRate"] for m in metrics),
        "DQ12_SourceReliabilityClass": min(m["DQ12_SourceReliabilityClass"] for m in metrics),
    }


def _model_versions() -> dict:
    return dict(COMPONENT_VERSIONS)


def build_failure_response(ctx: AnalysisContext) -> dict:
    dq = ctx.dq
    return {
        "analysis_id": ctx.analysis_id,
        "status": (dq.status or AnalysisStatus.FAILED_DATA_QUALITY).value,
        "economic_outputs": None,
        "underwriting": None,
        "drivers": [],
        "flags": dq.hard_stop_reasons + dq.warnings,
        "reasons": [],
        "data_quality": {aid: q.metrics for aid, q in dq.accounts.items()},
        "model_versions": _model_versions(),
        "policy_version": f"{ctx.policy.policy_id}:{ctx.policy.policy_version}",
    }


def build_response(ctx: AnalysisContext) -> dict:
    af = ctx.account_features
    full = af.full_period
    sbci = ctx.sbci.sbci_monthly
    debt = ctx.financing.debt_service_monthly
    unc, dec, legal = ctx.uncertainty, ctx.decision, ctx.legal
    caocg_by_label = {p.label: p for p in ctx.caocg.monthly}
    return {
        "analysis_id": ctx.analysis_id,
        "status": dec.status.value,
        "economic_outputs": {
            "basis": f"monthly-equivalent over {full.start}..{full.end} ({full.months:.2f} months)",
            "gross_banking_credits_monthly": _m(full.monthly("gross_credits")),
            "expected_operating_collections_monthly": _m(full.monthly("eoc")),
            "core_operating_requirement_monthly": _m(full.monthly("cor")),
            "raw_operating_cash_generation_monthly": _m(ctx.sbci.roc_basis_monthly),
            "cycle_adjusted_cash_generation_monthly": _m(ctx.sbci.caocg_basis_monthly),
            "robust_sustainable_centre_monthly": _m(ctx.sbci.robust_center),
            "maintenance_capex_reserve_monthly": _m(ctx.sbci.maintenance_capex_reserve),
            "sustainable_business_cash_income_monthly": _m(sbci),
            "existing_business_debt_service_monthly": _m(debt),
            "post_debt_free_cash_monthly": _m(sbci - debt),
            "owner_extraction_monthly": _m(ctx.owner.owner_draw_monthly),
        },
        "underwriting": {
            "underwriting_income_monthly": _m(dec.underwriting_income_monthly),
            "central_estimate": _m(unc.central),
            "lower_bound": _m(unc.lower),
            "upper_bound": _m(unc.upper),
            "confidence": unc.confidence,
            "coverage_risk": ctx.coverage.risk.value,
            "legal_attribution_status": legal.status.value,
            "borrower_income_monthly": _m(legal.borrower_income_monthly),
            "selection_basis": dec.basis,
            "interval_method": unc.interval_method,
            "unresolved_outflow_allowance_monthly": _m(unc.unresolved_outflow_allowance),
            "unresolved_inflow_allowance_monthly": _m(unc.unresolved_inflow_allowance),
            "referral_reasons": dec.referral_reasons,
        },
        "bridge": ctx.explanation.bridge,
        "reasons": ctx.reason_codes,
        "drivers": ctx.explanation.drivers,
        "flags": ctx.explanation.flags,
        "confidence_dimensions": unc.dimensions,
        "archetype": {"code": ctx.archetype.top, "probability": round(ctx.archetype.probability, 4),
                      "probabilities": {k: round(v, 4) for k, v in ctx.archetype.probabilities.items()}},
        "cycle": {"status": ctx.cycle.status.value, **ctx.cycle.features,
                  "conversion_ratio": ctx.cycle.conversion_ratio},
        "trend": {"regime": ctx.trend.regime.value, **ctx.trend.features},
        "monthly_series": [
            {"month": m.month, "coverage": round(m.coverage, 4), "complete": m.complete,
             "gross_credits": _m(m.totals["gross_credits"]), "eoc": _m(m.totals["eoc"]), "cor": _m(m.totals["cor"]),
             "roc": _m(m.totals["roc"]), "caocg": _m(caocg_by_label[m.month].value),
             "financing_in": _m(m.totals["financing_in"]), "debt_service": _m(m.totals["debt_service"]),
             "owner_draw": _m(m.totals["owner_draw"])}
            for m in af.monthly
        ],
        "role_mix_full_period": {
            k: _m(full.monthly(k)) for k in (
                "financing_in", "internal_in", "owner_capital_in", "investment_in", "refund_in", "interest_in",
                "personal_in", "pass_through_in", "unknown_in", "direct_cost", "payroll", "rent", "utilities",
                "logistics", "other_opex", "statutory", "debt_interest", "debt_principal", "capex",
                "maintenance_capex", "owner_draw", "personal_expense", "internal_out", "pass_through_out",
                "business_cash_withdrawal", "bank_fee", "unknown_out")
        },
        "pass_through": ctx.pass_through,
        "data_quality": {aid: q.metrics for aid, q in ctx.dq.accounts.items()},
        "transaction_evidence": ctx.explanation.transaction_evidence,
        "model_versions": _model_versions(),
        "policy_version": f"{ctx.policy.policy_id}:{ctx.policy.policy_version}",
        "transaction_count": len(ctx.txns),
        "role_uncertainty": round(ctx.role_uncertainty, 4),
    }

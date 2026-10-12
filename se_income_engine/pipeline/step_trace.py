"""Per-step trace of the Section 26 pipeline for the UI.

``run_analysis_pipeline`` calls the collector at each execution checkpoint (``step01_...`` .. ``step10_...``, listed
in ``services.PIPELINE_STEPS``), so each table records the state at that moment; later steps update role
probabilities in place, so a trace taken only at the end would hide the intermediate values.

Each transaction table carries the columns added by its step, prefixed ``sNN_``. Steps 7-10 operate on aggregates, so
they produce summary tables instead.

``StepTables`` builds the tables; ``StepTraceCollector`` keeps them in memory as JSON-ready data for the UI.
"""

from __future__ import annotations

import time
from dataclasses import fields
from datetime import date
from decimal import Decimal
from enum import Enum

from se_income_engine.contracts.enums import CreditRole, DebitRole

ALL_ROLES = [r.value for r in CreditRole] + [r.value for r in DebitRole]


def _ranked(probs: dict[str, float]) -> list[tuple[str, float]]:
    return sorted(probs.items(), key=lambda kv: (-kv[1], kv[0]))


def _prob_text(probs: dict[str, float]) -> str:
    return " ".join(f"{r}:{p:.3f}" for r, p in _ranked(probs) if p >= 0.005)


def _top(probs: dict[str, float], rank: int = 0) -> tuple[str | None, float | None]:
    ranked = _ranked(probs)
    return ranked[rank] if len(ranked) > rank else (None, None)


def _kv(section: str, mapping: dict) -> list[dict]:
    return [{"section": section, "key": k, "value": v} for k, v in mapping.items()]


def _dataclass_dict(obj, skip: tuple[str, ...] = ()) -> dict:
    return {f.name: getattr(obj, f.name) for f in fields(obj) if f.name not in skip}


class StepTables:
    """Callable hook: ``tables(step_name, ctx)`` builds that step's tables and hands each one to ``_save``."""

    def __init__(self):
        self._rows: dict[str, dict] = {}
        self._order: list[str] = []

    def __call__(self, step: str, ctx) -> None:
        getattr(self, step)(ctx)

    def _save(self, name: str, rows: list[dict]) -> None:
        raise NotImplementedError

    def _save_transactions(self, name: str) -> None:
        self._save(name, [self._rows[tid] for tid in self._order])

    # ------------------------------------------------------------------ step 1
    def step01_ingest_and_clean(self, ctx) -> None:
        raw = []
        for a in ctx.request.accounts:
            for t in a.transactions:
                raw.append({
                    "transaction_id": t.transaction_id, "account_id": t.account_id, "source_line": t.source_line,
                    "booking_date": t.booking_date, "value_date": t.value_date, "direction": t.direction,
                    "amount": t.amount, "balance_after": t.balance_after, "raw_narration": t.raw_narration,
                    **{f"parser_{k}": v for k, v in t.parser_fields.items()},
                })
        self._save("step01a_parsed_raw", raw)

        for a in ctx.accounts:
            for t in a.transactions:
                self._rows[t.transaction_id] = {
                    "transaction_id": t.transaction_id, "account_id": t.account_id, "sequence_no": t.sequence_no,
                    "booking_date": t.booking_date, "value_date": t.value_date, "direction": t.direction,
                    "amount": t.amount, "balance_before": t.balance_before, "balance_after": t.balance_after,
                    "raw_narration": t.raw_narration, "normalized_narration": t.normalized_narration,
                    "s01_mode": t.mode, "s01_payment_mode": t.payment_mode,
                    "s01_channel_family": t.channel_family, "parse_confidence": t.parse_confidence,
                }
                self._order.append(t.transaction_id)
        self._save_transactions("step01b_canonical_transactions")

    # ------------------------------------------------------------------ step 2
    def step02_data_quality_gate(self, ctx) -> None:
        dq = ctx.dq
        metric_rows = []
        for aid, q in dq.accounts.items():
            breaks = set(q.break_transaction_ids)
            for t in next(a for a in ctx.accounts if a.account_id == aid).transactions:
                err = q.reconciliation_errors.get(t.transaction_id)
                self._rows[t.transaction_id].update({
                    "s02_reconciliation_error": err,
                    "s02_reconciliation_break": t.transaction_id in breaks,
                })
            metric_rows.append({"account_id": aid, **q.metrics, "hard_stop_reasons": q.hard_stop_reasons,
                                "warnings": q.warnings})
        for r in metric_rows:
            r.update({"pipeline_hard_stop": dq.hard_stop, "pipeline_status": dq.status})
        self._save_transactions("step02_transactions_after_dq")
        self._save("step02_dq_metrics", metric_rows)

    # ------------------------------------------------------------------ step 3
    def step03_transaction_evidence(self, ctx) -> None:
        self._order = [t.transaction_id for t in ctx.txns]
        entities: dict[str, dict] = {}
        for t in ctx.txns:
            row = self._rows[t.transaction_id]
            row["s03_channel_family"] = t.channel_family
            row.update({f"s03_id_{k}": v for k, v in _dataclass_dict(ctx.identifiers[t.transaction_id]).items()})
            h = ctx.hypotheses[t.transaction_id]
            cs = ctx.cluster_stats.get(h.cluster_id)
            row.update({
                "s03_entity_cluster_id": h.cluster_id, "s03_entity_status": h.identity_status,
                "s03_entity_label": h.canonical_label, "s03_entity_match_probability": h.match_probability,
                "s03_entity_txn_count": cs.count if cs else None,
                "s03_entity_active_months": len(cs.active_months) if cs else None,
            })
            nf = ctx.neighbourhood[t.transaction_id]
            row.update({f"s03_{k}": v for k, v in _dataclass_dict(nf, skip=("extras",)).items()})
            if h.cluster_id not in entities and cs is not None:
                entities[h.cluster_id] = {
                    "cluster_id": h.cluster_id, "identity_status": h.identity_status,
                    "canonical_label": h.canonical_label, "txn_count": cs.count,
                    "credit_count": cs.credit_count, "debit_count": cs.debit_count,
                    "credit_amount": cs.credit_amount, "debit_amount": cs.debit_amount,
                    "active_months": [f"{y:04d}-{m:02d}" for y, m in sorted(cs.active_months)],
                    "first_seen": cs.first_seen,
                }
        self._save_transactions("step03_transactions_with_evidence")
        self._save("step03_entities", sorted(entities.values(), key=lambda e: -e["txn_count"]))

    # ------------------------------------------------------------------ step 4
    def step04_role_inference(self, ctx) -> None:
        wide = []
        for tid in self._order:
            pred = ctx.predictions[tid]
            model_role, model_p = _top(pred.role_probabilities)
            cal_role, cal_p = _top(ctx.pre_rule_probabilities[tid])
            top_role, top_p = _top(pred.final_probabilities)
            second_role, second_p = _top(pred.final_probabilities, 1)
            self._rows[tid].update({
                "s04_model_top_role": model_role, "s04_model_top_p": model_p,
                "s04_calibrated_top_role": cal_role, "s04_calibrated_top_p": cal_p,
                "s04_top_role": top_role, "s04_top_p": top_p,
                "s04_second_role": second_role, "s04_second_p": second_p,
                "s04_rules_applied": [a.rule_id for a in pred.rule_adjustments],
                "s04_probabilities": _prob_text(pred.final_probabilities),
            })
            row = self._rows[tid]
            wide.append({"transaction_id": tid, "booking_date": row["booking_date"], "direction": row["direction"],
                         "amount": row["amount"], "normalized_narration": row["normalized_narration"],
                         **{r: pred.final_probabilities.get(r) for r in ALL_ROLES}})
        self._save_transactions("step04_transactions_with_roles")
        self._save("step04_role_probabilities_wide", wide)

    # ------------------------------------------------------------------ step 5
    def step05_pairing_and_multi_account(self, ctx) -> None:
        by_id = {t.transaction_id: t for t in ctx.txns}
        pair_of: dict[str, dict] = {}
        edge_rows = []
        for e in ctx.pair_graph.edges:
            c, d = by_id[e.credit_txn_id], by_id[e.debit_txn_id]
            for tid, partner in ((e.credit_txn_id, e.debit_txn_id), (e.debit_txn_id, e.credit_txn_id)):
                pair_of[tid] = {"s05_pair_type": e.edge_type, "s05_pair_edge_id": e.edge_id,
                                "s05_pair_partner_txn": partner, "s05_pair_score": e.score}
            edge_rows.append({
                "edge_id": e.edge_id, "edge_type": e.edge_type, "score": e.score,
                "amount_similarity": e.amount_similarity, "dt_hours": e.dt_hours,
                "credit_txn_id": c.transaction_id, "credit_date": c.booking_date, "credit_amount": c.amount,
                "credit_narration": c.normalized_narration,
                "debit_txn_id": d.transaction_id, "debit_date": d.booking_date, "debit_amount": d.amount,
                "debit_narration": d.normalized_narration, **{f"evidence_{k}": v for k, v in e.evidence.items()},
            })
        for tid in self._order:
            pred = ctx.predictions[tid]
            row = self._rows[tid]
            row.update(pair_of.get(tid, {"s05_pair_type": None, "s05_pair_edge_id": None,
                                         "s05_pair_partner_txn": None, "s05_pair_score": None}))
            row.update({
                "s05_top_role": pred.top_role, "s05_top_p": pred.top_probability, "s05_entropy": pred.entropy,
                "s05_role_changed": pred.top_role != row["s04_top_role"],
                "s05_adjustments_applied": [a.rule_id for a in pred.rule_adjustments
                                            if a.rule_id not in row["s04_rules_applied"]],
                "s05_probabilities": _prob_text(pred.final_probabilities),
            })
        self._save_transactions("step05_transactions_after_pairing")
        self._save("step05_pair_edges", edge_rows)

    # ------------------------------------------------------------------ step 6
    def step06_aggregation_archetype_cash(self, ctx) -> None:
        af = ctx.account_features
        used = [k for k in next(iter(af.ledger.values())).buckets
                if any(ln.buckets[k] for ln in af.ledger.values())] if af.ledger else []
        for tid in self._order:
            ln = af.ledger[tid]
            self._rows[tid].update({
                "s06_cash_business_probability": ctx.cash_eligibility.get(tid),
                "s06_p_operating": ln.p_operating, "s06_role_uncertainty": ln.uncertainty,
                **{f"s06_{k}": ln.buckets[k] for k in used},
            })
        self._save_transactions("step06_transactions_economic_ledger")

        self._save("step06_monthly_totals", [
            {"month": m.month, "start": m.start, "end": m.end, "coverage": m.coverage, "complete": m.complete,
             **m.totals} for m in af.monthly])
        self._save("step06_window_totals", [
            {"window": w.label, "start": w.start, "end": w.end, "covered_days": w.covered_days, "months": w.months,
             **w.totals, **w.inflow, **w.outflow}
            for w in [*af.windows.values(), af.full_period]])
        arch = ctx.archetype
        self._save("step06_archetype", [
            {"section": "selected", "key": "archetype", "value": arch.top},
            {"section": "selected", "key": "probability", "value": arch.probability},
            *_kv("probability", arch.probabilities), *_kv("feature", arch.features)])
        self._save("step06_pass_through_summary", _kv("pass_through", ctx.pass_through))

    # ------------------------------------------------------------------ step 7
    def step07_risk_signals(self, ctx) -> None:
        liq, fin, cyc, own = ctx.liquidity, ctx.financing, ctx.cycle, ctx.owner
        rows = [
            *_kv("s14_liquidity", liq.features),
            *_kv("s15_financing", {**fin.features, "debt_service_monthly": fin.debt_service_monthly,
                                   "interest_monthly": fin.interest_monthly,
                                   "principal_monthly": fin.principal_monthly}),
            *_kv("s13_cycle", {"status": cyc.status, **cyc.features, "conversion_ratio": cyc.conversion_ratio,
                               "build_normalisation_amount": cyc.build_normalisation_amount,
                               "liquidation_normalisation_amount": cyc.liquidation_normalisation_amount,
                               "phase_start": cyc.phase_start, "phase_end": cyc.phase_end,
                               "normal_monthly_eoc": cyc.normal_monthly_eoc, "notes": cyc.notes}),
            *_kv("s16_owner", {**own.features, "owner_draw_monthly": own.owner_draw_monthly}),
            *_kv("s17_multi_account", ctx.multi_account),
            *_kv("s22_role_uncertainty", {"amount_weighted_role_uncertainty": ctx.role_uncertainty}),
            *_kv("s18_trend", {"regime": ctx.trend.regime, **ctx.trend.features}),
            *_kv("s20_coverage", {"risk": ctx.coverage.risk, "score": ctx.coverage.score, **ctx.coverage.features}),
            *_kv("s19_anomaly", {"review_required": ctx.anomalies.review_required,
                                 "triggers": ctx.anomalies.triggers, **ctx.anomalies.features}),
        ]
        self._save("step07_risk_signals", rows)
        self._save("step07_daily_balance", [
            {"account_id": b.account_id, "day": b.day, "balance": b.balance, "imputed": b.imputed}
            for series in liq.daily.values() for b in series])
        lags = sorted(set(cyc.lag_profile_out_to_in) | set(cyc.lag_profile_in_to_out))
        self._save("step07_cycle_lag_profile", [
            {"lag_weeks": k, "purchases_to_collections": cyc.lag_profile_out_to_in.get(k),
             "collections_to_purchases": cyc.lag_profile_in_to_out.get(k)} for k in lags])
        self._save("step07_financing_events", [{"date": d, "amount": a} for d, a in fin.financing_events])

    # ------------------------------------------------------------------ step 8
    def step08_income_and_legal_attribution(self, ctx) -> None:
        caocg = {p.label: p for p in ctx.caocg.monthly}
        self._save("step08_income_monthly_series", [
            {"month": p.label, "start": p.start, "end": p.end, "months": p.months, "complete": p.complete,
             "roc": p.value, "caocg": caocg[p.label].value if p.label in caocg else None}
            for p in ctx.roc.monthly])
        self._save("step08_income_rolling_series", [
            {"window": k, "months": p.months, "roc_monthly_equivalent": p.value,
             "caocg_monthly_equivalent": ctx.caocg.rolling[k].value if k in ctx.caocg.rolling else None}
            for k, p in ctx.roc.rolling.items()])
        sbci = ctx.sbci
        self._save("step08_sbci_and_legal", [
            *_kv("s21_sbci", _dataclass_dict(sbci, skip=("candidates", "features"))),
            *_kv("s21_sbci_feature", sbci.features),
            *[{"section": "s21_robust_centre_candidate", "key": i, "value": c} for i, c in enumerate(sbci.candidates)],
            *_kv("s21_caocg", {"seasonality_applied": ctx.caocg.seasonality_applied,
                               "cycle_adjustment_basis_monthly": ctx.caocg.cycle_adjustment_basis_monthly,
                               "notes": ctx.caocg.notes}),
            *_kv("s16_legal_attribution", _dataclass_dict(ctx.legal)),
        ])

    # ------------------------------------------------------------------ step 9
    def step09_uncertainty_and_policy(self, ctx) -> None:
        unc, dec = ctx.uncertainty, ctx.decision
        self._save("step09_uncertainty_and_policy", [
            *_kv("s22_uncertainty", _dataclass_dict(unc, skip=("dimensions", "distribution"))),
            *_kv("s22_confidence_dimension", unc.dimensions),
            *_kv("s21_policy_decision", _dataclass_dict(dec)),
        ])

    # ------------------------------------------------------------------ step 10
    def step10_explain_and_audit(self, ctx) -> None:
        ex = ctx.explanation
        self._save("step10_bridge", ex.bridge)
        self._save("step10_reason_codes", ex.reasons or [{"code": None, "reason": "no reason codes"}])
        self._save("step10_drivers", ex.drivers)
        self._save("step10_feature_vector", [{"feature": k, "value": v} for k, v in ctx.feature_vector.items()])


def to_json(v):
    """JSON-safe value: Decimal -> float, date -> ISO string, Enum -> value, NaN/inf -> None."""
    if isinstance(v, Enum):
        return v.value
    if v is None or isinstance(v, (bool, int, str)):
        return v
    if isinstance(v, float):
        return None if v != v or v in (float("inf"), float("-inf")) else round(v, 6)
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, dict):
        return {str(k): to_json(x) for k, x in v.items()}
    if isinstance(v, set):
        return [to_json(x) for x in sorted(v, key=str)]
    if isinstance(v, (list, tuple)):
        return [to_json(x) for x in v]
    if hasattr(v, "__dataclass_fields__"):
        return to_json(_dataclass_dict(v))
    return str(v)


def _columnar(rows: list[dict]) -> dict:
    columns = list(dict.fromkeys(k for r in rows for k in r))
    return {"columns": columns, "rows": [[to_json(r.get(c)) for c in columns] for r in rows]}


def _probs(probs: dict[str, float]) -> dict[str, float]:
    return {r: round(p, 5) for r, p in _ranked(probs) if p >= 0.0005}


def _adjustment(a) -> dict:
    return {"rule_id": a.rule_id, "rule_version": a.rule_version, "action": a.action,
            "roles": {r: round(v, 5) for r, v in a.roles.items()}, "description": a.description}


class StepTraceCollector(StepTables):
    """Keeps every step's tables in memory for the UI.

    Transaction tables are not repeated per step: each step carries only the columns it added
    (``transactions``, keyed by ``transaction_id``), so the client rebuilds the cumulative table by merging.
    ``role_trace`` holds each transaction's role distribution after the model, calibration, rule overlay and
    pairing. ``on_step_done(step, data)`` fires as each step finishes.
    """

    SKIPPED_TABLES = {"step04_role_probabilities_wide"}

    def __init__(self, on_step_done=None):
        super().__init__()
        self.steps: dict[str, dict] = {}
        self.role_trace: dict[str, dict] = {}
        self._on_step_done = on_step_done
        self._seen_columns: set[str] = set()
        self._step = ""
        self._mark = time.perf_counter()

    def __call__(self, step: str, ctx) -> None:
        compute_ms = (time.perf_counter() - self._mark) * 1000
        self._step = step
        self.steps[step] = {"compute_ms": round(compute_ms, 1), "tables": {}, "transactions": None, "detail": {}}
        super().__call__(step, ctx)
        if self._on_step_done is not None:
            self._on_step_done(step, self.steps[step])
        self._mark = time.perf_counter()

    def _save(self, name: str, rows: list[dict]) -> None:
        if name not in self.SKIPPED_TABLES:
            self.steps[self._step]["tables"][name] = _columnar(rows)

    def _save_transactions(self, name: str) -> None:
        columns = list(dict.fromkeys(k for tid in self._order for k in self._rows[tid]))
        added = [c for c in columns if c not in self._seen_columns and c != "transaction_id"]
        self._seen_columns.update(columns)
        self.steps[self._step]["transactions"] = {
            "table": name,
            "columns": ["transaction_id", *added],
            "rows": [[tid, *(to_json(self._rows[tid].get(c)) for c in added)] for tid in self._order],
        }

    def step02_data_quality_gate(self, ctx) -> None:
        super().step02_data_quality_gate(ctx)
        self.steps[self._step]["detail"] = {"parameters": to_json(ctx.params.data_quality)}

    def step04_role_inference(self, ctx) -> None:
        super().step04_role_inference(ctx)
        for tid in self._order:
            pred = ctx.predictions[tid]
            self.role_trace[tid] = {
                "model": _probs(pred.role_probabilities),
                "calibrated": _probs(ctx.pre_rule_probabilities[tid]),
                "after_rules": _probs(pred.final_probabilities),
                "rules": [_adjustment(a) for a in pred.rule_adjustments],
            }

    def step05_pairing_and_multi_account(self, ctx) -> None:
        super().step05_pairing_and_multi_account(ctx)
        for tid in self._order:
            pred, trace = ctx.predictions[tid], self.role_trace[tid]
            step4_rules = {r["rule_id"] for r in trace["rules"]}
            trace["final"] = _probs(pred.final_probabilities)
            trace["pair_adjustments"] = [_adjustment(a) for a in pred.rule_adjustments if a.rule_id not in step4_rules]
            trace["entropy"] = round(pred.entropy, 5)

    def step08_income_and_legal_attribution(self, ctx) -> None:
        super().step08_income_and_legal_attribution(ctx)
        self.steps[self._step]["detail"] = {"income_parameters": to_json(ctx.params.income),
                                            "trend_parameters": to_json(ctx.params.trend)}

    def step09_uncertainty_and_policy(self, ctx) -> None:
        super().step09_uncertainty_and_policy(ctx)
        unc = ctx.uncertainty
        self.steps[self._step]["detail"] = {
            "confidence_weights": ctx.params.uncertainty.confidence_weights,
            "uncertainty_parameters": to_json(ctx.params.uncertainty),
            "policy": ctx.policy.as_dict(),
            "distribution": [round(x, 2) for x in unc.distribution],
            "monthly_caocg": [{"month": p.label, "value": to_json(p.value), "complete": p.complete}
                              for p in ctx.caocg.monthly],
            "recent_deterioration": ctx.trend.features.get("TR11_RecentDeteriorationScore"),
        }

"""Section 25.3 / Appendix B - Audit persistence (SQLite reference implementation).

Every decision is reproducible from immutable source hashes, canonical transactions, pre/post-rule role
probabilities, pair edges, feature values and model/policy versions. Identifiers are hashed (Section 29.3).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from se_income_engine.services.supporting.audit_explainability.s23_feature_registry import (
    FEATURE_REGISTRY,
    REGISTRY_VERSION,
    transaction_feature_rows,
)
from se_income_engine.versions import COMPONENT_VERSIONS

SCHEMA = """
CREATE TABLE IF NOT EXISTS account_source (analysis_id TEXT, account_id TEXT, source_hash TEXT, source_type TEXT,
    parser_version TEXT, metadata_json TEXT, PRIMARY KEY (analysis_id, account_id));
CREATE TABLE IF NOT EXISTS transaction_raw (analysis_id TEXT, transaction_id TEXT, account_id TEXT, source_line INTEGER,
    source_page INTEGER, raw_narration TEXT, parser_fields_json TEXT, PRIMARY KEY (analysis_id, transaction_id));
CREATE TABLE IF NOT EXISTS transaction_canonical (analysis_id TEXT, transaction_id TEXT, account_id TEXT,
    booking_date TEXT, sequence_no INTEGER, direction TEXT, amount TEXT, balance_before TEXT, balance_after TEXT,
    normalized_narration TEXT, channel_family TEXT, reconciliation_error TEXT, PRIMARY KEY (analysis_id, transaction_id));
CREATE TABLE IF NOT EXISTS transaction_identifier (analysis_id TEXT, transaction_id TEXT, identifiers_json TEXT,
    PRIMARY KEY (analysis_id, transaction_id));
CREATE TABLE IF NOT EXISTS transaction_role_prediction (analysis_id TEXT, transaction_id TEXT, model_version TEXT,
    raw_probabilities_json TEXT, calibrated_probabilities_json TEXT, final_probabilities_json TEXT, top_role TEXT,
    top_probability REAL, entropy REAL, rule_adjustments_json TEXT, PRIMARY KEY (analysis_id, transaction_id));
CREATE TABLE IF NOT EXISTS transaction_pair_edge (analysis_id TEXT, edge_id TEXT, edge_type TEXT, credit_txn_id TEXT,
    debit_txn_id TEXT, score REAL, amount_similarity REAL, dt_hours REAL, evidence_json TEXT,
    PRIMARY KEY (analysis_id, edge_id));
CREATE TABLE IF NOT EXISTS entity_cluster (analysis_id TEXT, transaction_id TEXT, cluster_id TEXT, identity_status TEXT,
    match_probability REAL, evidence_json TEXT, PRIMARY KEY (analysis_id, transaction_id));
CREATE TABLE IF NOT EXISTS daily_balance (analysis_id TEXT, account_id TEXT, day TEXT, balance TEXT, imputed INTEGER,
    PRIMARY KEY (analysis_id, account_id, day));
CREATE TABLE IF NOT EXISTS feature_value (analysis_id TEXT, feature_key TEXT, feature_id TEXT, level TEXT,
    entity_id TEXT, value_json TEXT, registry_version TEXT, PRIMARY KEY (analysis_id, feature_key, entity_id));
CREATE TABLE IF NOT EXISTS income_analysis (analysis_id TEXT PRIMARY KEY, customer_id TEXT, application_id TEXT,
    as_of_date TEXT, status TEXT, response_json TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS analysis_reason (analysis_id TEXT, code TEXT, reason TEXT, evidence_json TEXT,
    PRIMARY KEY (analysis_id, code));
CREATE TABLE IF NOT EXISTS model_artifact (artifact_id TEXT PRIMARY KEY, component TEXT, artifact_hash TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS policy_artifact (policy_id TEXT, policy_version TEXT, parameters_json TEXT, artifact_hash TEXT,
    PRIMARY KEY (policy_id, policy_version));
CREATE TABLE IF NOT EXISTS manual_override (override_id INTEGER PRIMARY KEY AUTOINCREMENT, analysis_id TEXT,
    field TEXT, old_value TEXT, new_value TEXT, reason TEXT, user_id TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS golden_regression (run_id TEXT, case_id TEXT, release TEXT, expected_json TEXT,
    actual_json TEXT, passed INTEGER, created_at TEXT, PRIMARY KEY (run_id, case_id));
"""


def _json(value) -> str:
    def default(o):
        if isinstance(o, Decimal):
            return str(o)
        if hasattr(o, "isoformat"):
            return o.isoformat()
        if hasattr(o, "value"):
            return o.value
        if isinstance(o, set):
            return sorted(o)
        return str(o)
    return json.dumps(value, default=default, sort_keys=True)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class AuditStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    def get_analysis(self, analysis_id: str) -> dict | None:
        with closing(sqlite3.connect(self.path)) as conn:
            row = conn.execute("SELECT response_json FROM income_analysis WHERE analysis_id = ?", (analysis_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def persist_full_audit_trail(self, ctx, response: dict) -> None:
        aid = ctx.analysis_id
        now = datetime.now(timezone.utc).isoformat()
        recon = {tid: err for q in ctx.dq.accounts.values() for tid, err in q.reconciliation_errors.items()}
        with closing(sqlite3.connect(self.path)) as conn:
            cur = conn.cursor()
            for a in ctx.accounts:
                source_hash = _hash("|".join(t.transaction_id for t in a.transactions))
                cur.execute("INSERT OR REPLACE INTO account_source VALUES (?,?,?,?,?,?)",
                            (aid, a.account_id, source_hash, a.source_type.value, a.parser_version,
                             _json({k: v for k, v in a.parser_metadata.items() if k != "holder_name"})))
            cur.executemany("INSERT OR REPLACE INTO transaction_raw VALUES (?,?,?,?,?,?,?)", [
                (aid, t.transaction_id, t.account_id, t.source_line, t.source_page, t.raw_narration, _json(t.parser_fields))
                for t in ctx.txns])
            cur.executemany("INSERT OR REPLACE INTO transaction_canonical VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [
                (aid, t.transaction_id, t.account_id, t.booking_date.isoformat(), t.sequence_no, t.direction.value,
                 str(t.amount), None if t.balance_before is None else str(t.balance_before),
                 None if t.balance_after is None else str(t.balance_after), t.normalized_narration,
                 t.channel_family.value, None if t.transaction_id not in recon else str(recon[t.transaction_id]))
                for t in ctx.txns])
            cur.executemany("INSERT OR REPLACE INTO transaction_identifier VALUES (?,?,?)", [
                (aid, tid, _json(_hashed_identifiers(ids))) for tid, ids in ctx.identifiers.items()])
            cur.executemany("INSERT OR REPLACE INTO transaction_role_prediction VALUES (?,?,?,?,?,?,?,?,?,?)", [
                (aid, tid, p.model_version, _json(p.role_probabilities), _json(ctx.pre_rule_probabilities.get(tid, {})),
                 _json(p.final_probabilities), p.top_role, p.top_probability, p.entropy,
                 _json([asdict(r) for r in p.rule_adjustments]))
                for tid, p in ctx.predictions.items()])
            cur.executemany("INSERT OR REPLACE INTO transaction_pair_edge VALUES (?,?,?,?,?,?,?,?,?)", [
                (aid, e.edge_id, e.edge_type.value, e.credit_txn_id, e.debit_txn_id, e.score, e.amount_similarity,
                 e.dt_hours, _json(e.evidence)) for e in ctx.pair_graph.edges])
            cur.executemany("INSERT OR REPLACE INTO entity_cluster VALUES (?,?,?,?,?,?)", [
                (aid, tid, h.cluster_id, h.identity_status.value, h.match_probability,
                 _json([asdict(e) for e in h.evidence])) for tid, h in ctx.hypotheses.items()])
            cur.executemany("INSERT OR REPLACE INTO daily_balance VALUES (?,?,?,?,?)", [
                (aid, d.account_id, d.day.isoformat(), str(d.balance), int(d.imputed))
                for series in ctx.liquidity.daily.values() for d in series])

            rows = []
            for key, value in ctx.feature_vector.items():
                fid = key.split("_")[0]
                entry = FEATURE_REGISTRY.get(fid)
                rows.append((aid, key, fid, entry.level if entry else "ACCOUNT", ctx.request.customer_id,
                             _json(value), REGISTRY_VERSION))
            for tid, feats in transaction_feature_rows(ctx).items():
                for fid, value in feats.items():
                    rows.append((aid, fid, fid, "TRANSACTION", tid, _json(value), REGISTRY_VERSION))
            cur.executemany("INSERT OR REPLACE INTO feature_value VALUES (?,?,?,?,?,?,?)", rows)

            cur.execute("INSERT OR REPLACE INTO income_analysis VALUES (?,?,?,?,?,?,?)",
                        (aid, ctx.request.customer_id, ctx.request.application_id, ctx.request.as_of_date.isoformat(),
                         response["status"], _json(response), now))
            cur.executemany("INSERT OR REPLACE INTO analysis_reason VALUES (?,?,?,?)", [
                (aid, r["code"], r["reason"], _json(r["evidence"])) for r in ctx.reason_codes])
            for component, version in COMPONENT_VERSIONS.items():
                cur.execute("INSERT OR IGNORE INTO model_artifact VALUES (?,?,?,?)",
                            (version, component, _hash(version), now))
            policy = ctx.policy.as_dict()
            cur.execute("INSERT OR IGNORE INTO policy_artifact VALUES (?,?,?,?)",
                        (ctx.policy.policy_id, ctx.policy.policy_version, _json(policy), _hash(_json(policy))))
            conn.commit()

    def record_manual_override(self, analysis_id: str, field_name: str, old_value, new_value, reason: str,
                               user_id: str) -> None:
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute("INSERT INTO manual_override (analysis_id, field, old_value, new_value, reason, user_id, created_at)"
                         " VALUES (?,?,?,?,?,?,?)",
                         (analysis_id, field_name, _json(old_value), _json(new_value), reason, user_id,
                          datetime.now(timezone.utc).isoformat()))
            conn.commit()

    def record_golden_regression(self, run_id: str, case_id: str, release: str, expected: dict, actual: dict,
                                 passed: bool) -> None:
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute("INSERT OR REPLACE INTO golden_regression VALUES (?,?,?,?,?,?,?)",
                         (run_id, case_id, release, _json(expected), _json(actual), int(passed),
                          datetime.now(timezone.utc).isoformat()))
            conn.commit()


def _hashed_identifiers(ids) -> dict:
    d = asdict(ids)
    for key in ("vpa_local", "account_fragment", "utr", "merchant_id", "terminal_id", "mandate_id", "cheque_no"):
        if d.get(key):
            d[key] = _hash(d[key])[:16]
    d["name_tokens"] = [_hash(t)[:12] for t in d.get("name_tokens") or []]
    return d

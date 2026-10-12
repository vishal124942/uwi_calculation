"""End-to-end contract tests: bridge reconciliation (Section 28.1), idempotency and audit persistence
(Section 25.3), API (Section 25.1), and smoke runs on the supplied analyser statements."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from builders import business, make_request
from se_income_engine.contracts.enums import AccountType, LegalOwnerType
from se_income_engine.pipeline.analyse import analyse_self_employed_income
from se_income_engine.pipeline.step_trace import StepTraceCollector
from se_income_engine.services.m1_parser_normaliser.s03_statement_parsers import parse_analyser_xlsx
from se_income_engine.services.supporting.audit_explainability.s25_audit_persistence import AuditStore

ROOT = Path(__file__).resolve().parents[1]
REAL_FILES = sorted(ROOT.glob("DOC*.xlsx"))


def assert_bridge_reconciles(response: dict, tol: float = 0.06) -> None:
    v = {line["line"]: line["monthly_amount"] for line in response["bridge"]}
    lines = [line["monthly_amount"] for line in response["bridge"]]
    gross, fin, internal, other, eoc, cor, roc, cycle, caocg, robust, reserve, permitted, sbci, debt, pdfc, _ = lines
    assert abs(gross + fin + internal + other - eoc) < tol
    assert abs(eoc + cor - roc) < tol
    assert abs(roc + cycle - caocg) < tol
    assert abs(caocg + robust + reserve + permitted - sbci) < tol
    assert abs(sbci - debt - pdfc) < tol
    eo = response["economic_outputs"]
    assert abs(eo["sustainable_business_cash_income_monthly"] - sbci) < tol
    assert abs(eo["expected_operating_collections_monthly"] - eoc) < tol
    assert v  # labels present


def test_bridge_reconciles_on_synthetic_business():
    response = analyse_self_employed_income(make_request(business().build()))
    assert response["status"] == "SUCCESS"
    assert_bridge_reconciles(response)
    u = response["underwriting"]
    assert u["lower_bound"] <= u["central_estimate"] <= u["upper_bound"]
    assert u["interval_method"] == "BOOTSTRAP_UNCALIBRATED"


def test_step_trace_does_not_change_the_result():
    request = make_request(business().build())
    trace = StepTraceCollector()
    with_hook = analyse_self_employed_income(request, on_step=trace)
    assert with_hook == analyse_self_employed_income(request)

    assert {s[:6] for s in trace.steps} == {f"step{n:02d}" for n in range(1, 11)}
    added = [trace.steps[s]["transactions"] for s in sorted(trace.steps) if trace.steps[s]["transactions"]]
    assert len(added) == 6
    for table in added:
        assert len(table["rows"]) == with_hook["transaction_count"]
        assert len(table["columns"]) > 1, "every transaction step adds its own columns"


def test_analysis_is_idempotent_and_fully_audited(tmp_path):
    store = AuditStore(tmp_path / "audit.db")
    request = make_request(business(months=6).build())
    first = analyse_self_employed_income(request, store=store)
    second = analyse_self_employed_income(make_request(business(months=6).build()), store=store)
    assert first["analysis_id"] == second["analysis_id"]
    assert first == second

    with closing(sqlite3.connect(store.path)) as conn:
        counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                  for t in ("income_analysis", "account_source", "transaction_canonical",
                            "transaction_role_prediction", "transaction_pair_edge", "feature_value")}
    n = len(request.accounts[0].transactions)
    assert counts["income_analysis"] == 1
    assert counts["transaction_canonical"] == n
    assert counts["transaction_role_prediction"] == n
    assert counts["feature_value"] > 0


def test_api_analyse_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("SEI_AUDIT_DB", str(tmp_path / "api.db"))
    import importlib

    from fastapi.testclient import TestClient

    import se_income_engine.api.app as app_module
    importlib.reload(app_module)
    client = TestClient(app_module.app)
    assert client.get("/health").json()["status"] == "ok"
    assert len(client.get("/v1/feature-registry").json()["features"]) == 100

    account = business(months=4).build()
    body = {
        "customer_id": "CUST1", "application_id": "APP1", "as_of_date": account.statement_end.isoformat(),
        "borrower_context": {"legal_owner_type": "SOLE_PROP"},
        "accounts": [{
            "account_id": account.account_id, "account_type": "CURRENT", "statement_start": account.statement_start.isoformat(),
            "statement_end": account.statement_end.isoformat(), "holder_name": "RAVI KUMAR",
            "transactions": [{"booking_date": t.booking_date.isoformat(), "direction": t.direction.value,
                              "amount": str(t.amount), "balance_after": str(t.balance_after),
                              "raw_narration": t.raw_narration, "sequence_no": t.sequence_no}
                             for t in account.transactions],
        }],
    }
    r = client.post("/v1/self-employed-income/analyse", json=body)
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["status"] == "SUCCESS"
    assert_bridge_reconciles(payload)
    fetched = client.get(f"/v1/self-employed-income/analyses/{payload['analysis_id']}")
    assert fetched.status_code == 200 and fetched.json()["analysis_id"] == payload["analysis_id"]


@pytest.mark.skipif(not REAL_FILES, reason="analyser statements not present")
@pytest.mark.parametrize("path", REAL_FILES, ids=lambda p: p.stem)
def test_real_statement_smoke(path):
    account = parse_analyser_xlsx(path, "C1", account_type=AccountType.SAVINGS,
                                  legal_owner_type=LegalOwnerType.SOLE_PROP)
    response = analyse_self_employed_income(make_request(account))
    assert response["status"] in ("SUCCESS", "REFER_LOW_CONFIDENCE", "REFER_COVERAGE_RISK", "REFER_ANOMALY")
    assert response["data_quality"][account.account_id]["DQ02_TxnReconciliationPassRate"] >= 0.98
    assert_bridge_reconciles(response)
    eo = response["economic_outputs"]
    assert 0 < eo["sustainable_business_cash_income_monthly"] < eo["gross_banking_credits_monthly"]

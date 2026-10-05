"""Section 25 - Processing API.

Run:  uvicorn se_income_engine.api.app:app --reload
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import asdict
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request

from se_income_engine import __version__
from se_income_engine.api.schemas import AnalyseRequestIn, to_analysis_request
from se_income_engine.contracts.enums import AccountType, LegalOwnerType
from se_income_engine.pipeline.analyse import analyse_self_employed_income
from se_income_engine.pipeline.context import AnalysisRequest, BorrowerContext
from se_income_engine.services.step01_ingest_and_clean.s03_statement_parsers import parse_analyser_xlsx
from se_income_engine.services.step10_explain_and_audit.s23_feature_registry import FEATURE_REGISTRY, REGISTRY_VERSION
from se_income_engine.services.step10_explain_and_audit.s25_audit_persistence import AuditStore
from se_income_engine.versions import COMPONENT_VERSIONS

app = FastAPI(title="Self-Employed Income Reconstruction Engine", version=__version__)
_store = AuditStore(Path(os.environ.get("SEI_AUDIT_DB", "se_income_audit.db")))


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__, "model_versions": COMPONENT_VERSIONS}


@app.get("/v1/feature-registry")
def feature_registry() -> dict:
    return {"registry_version": REGISTRY_VERSION, "features": [asdict(e) for e in FEATURE_REGISTRY.values()]}


@app.post("/v1/self-employed-income/analyse")
def analyse(body: AnalyseRequestIn) -> dict:
    return analyse_self_employed_income(to_analysis_request(body), store=_store)


@app.post("/v1/self-employed-income/analyse-statement")
async def analyse_statement(
    request: Request,
    customer_id: str = Query(...),
    application_id: str = Query(...),
    legal_owner_type: LegalOwnerType = Query(LegalOwnerType.UNKNOWN),
    account_type: AccountType = Query(AccountType.SAVINGS),
    as_of_date: date | None = Query(None),
    policy_id: str = Query("SE_INCOME_POLICY_001"),
) -> dict:
    """Raw analyser .xlsx bytes as the request body (Content-Type: application/octet-stream)."""
    payload = await request.body()
    if not payload:
        raise HTTPException(status_code=400, detail="empty statement body")
    with tempfile.NamedTemporaryFile(suffix=".xlsx") as fh:
        fh.write(payload)
        fh.flush()
        try:
            account = parse_analyser_xlsx(fh.name, customer_id, account_type=account_type,
                                          legal_owner_type=legal_owner_type)
        except (ValueError, KeyError) as exc:
            raise HTTPException(status_code=422, detail=f"unparseable statement: {exc}") from exc
    req = AnalysisRequest(
        customer_id=customer_id,
        application_id=application_id,
        as_of_date=as_of_date or account.statement_end,
        accounts=[account],
        borrower_context=BorrowerContext(legal_owner_type=legal_owner_type,
                                         application_date=as_of_date or account.statement_end),
        policy_id=policy_id,
    )
    return analyse_self_employed_income(req, store=_store)


@app.get("/v1/self-employed-income/analyses/{analysis_id}")
def get_analysis(analysis_id: str) -> dict:
    found = _store.get_analysis(analysis_id)
    if found is None:
        raise HTTPException(status_code=404, detail="analysis not found")
    return found

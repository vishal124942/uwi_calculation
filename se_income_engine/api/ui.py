"""Pipeline explorer API for the web UI: step catalogue and a streamed, step-by-step trace of one analysis.

``POST /v1/ui/trace`` (statement upload) and ``POST /v1/ui/trace/demo`` (synthetic statement) stream NDJSON while
the pipeline runs: one ``start`` event, one ``step`` event per pipeline checkpoint (``PIPELINE_STEPS``), then
``result`` (or ``error``). Trace runs bypass the idempotency cache and are not persisted to the audit store.
"""

from __future__ import annotations

import importlib
import json
import queue
import re
import tempfile
import threading
import time
from datetime import date
from pathlib import Path
from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from se_income_engine import __version__
from se_income_engine.config.policy import POLICY_REGISTRY
from se_income_engine.contracts.account import AccountInput
from se_income_engine.contracts.enums import (
    AccountType,
    Archetype,
    CreditRole,
    DebitRole,
    LegalOwnerType,
)
from se_income_engine.pipeline.analyse import analyse_self_employed_income
from se_income_engine.pipeline.context import AnalysisRequest, BorrowerContext
from se_income_engine.pipeline.step_trace import StepTraceCollector, to_json
from se_income_engine.services import (
    COMPONENT_OF_MODULE,
    MODEL_COMPONENTS,
    PIPELINE_STEPS,
    STEP_OF_MODULE,
    module_path,
)
from se_income_engine.services.m1_parser_normaliser.s03_statement_parsers import parse_statement_file
from se_income_engine.synthetic import StatementBuilder
from se_income_engine.versions import COMPONENT_VERSIONS

router = APIRouter(prefix="/v1/ui", tags=["ui"])

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")

DEMO_SCENARIOS = {
    "kirana_trader": ("Kirana / trading shop: daily UPI receipts, weekly supplier NEFTs, rent, salaries, owner draw",
                      lambda: StatementBuilder(months=12, seed=7).typical_trading_business()),
    "inventory_cycle": ("Inventory trader whose weekly purchases turn into collections three weeks later",
                        lambda: StatementBuilder(months=12, seed=5).lagged_cycle_business()),
}


def _first_paragraph(doc: str | None) -> str:
    return " ".join((doc or "").strip().split("\n\n")[0].split())


def _module_doc(module: str) -> str:
    return _first_paragraph(importlib.import_module(module_path(module)).__doc__)


def step_catalogue() -> list[dict]:
    """Pipeline execution checkpoints; the trace streams one ``step`` event per entry."""
    return [{"id": s["id"], "number": i, "title": s["title"], "sections": s["sections"],
             "modules": [{"name": m, "component": COMPONENT_OF_MODULE[m], "doc": _module_doc(m)} for m in s["modules"]]}
            for i, s in enumerate(PIPELINE_STEPS, start=1)]


def component_catalogue() -> list[dict]:
    """Section 24.1 components with their code package, modules and the checkpoints those modules finish in."""
    out = []
    for c in MODEL_COMPONENTS:
        package = f"services/{c['package'].replace('.', '/')}"
        modules = [{"name": m, "path": f"{package}/{m}.py", "step": STEP_OF_MODULE[m], "doc": _module_doc(m)}
                   for m in c["modules"]]
        out.append({**c, "package": package, "modules": modules,
                    "steps": list(dict.fromkeys(m["step"] for m in modules))})
    return out


@router.get("/meta")
def meta() -> dict:
    return {
        "version": __version__,
        "steps": step_catalogue(),
        "components": component_catalogue(),
        "roles": {r.value: r.name.replace("_", " ").title() for r in [*CreditRole, *DebitRole]},
        "archetypes": {a.value: a.name.split("_", 1)[1].replace("_", " ").title() for a in Archetype},
        "policies": [p.as_dict() for p in POLICY_REGISTRY.values()],
        "account_types": [e.value for e in AccountType],
        "legal_owner_types": [e.value for e in LegalOwnerType],
        "demo_scenarios": {k: description for k, (description, _) in DEMO_SCENARIOS.items()},
        "model_versions": COMPONENT_VERSIONS,
    }


def _account_summary(a: AccountInput) -> dict:
    md = a.parser_metadata
    return {"account_id": a.account_id, "account_type": a.account_type.value,
            "legal_owner_type": a.legal_owner_type.value, "statement_start": a.statement_start.isoformat(),
            "statement_end": a.statement_end.isoformat(), "transactions": len(a.transactions),
            "bank": md.get("bank") or a.bank_code, "holder_name": md.get("holder_name"),
            "masked_account": md.get("masked_account"), "source_file": md.get("source_file")}


def _build_request(accounts: list[AccountInput], customer_id: str, application_id: str,
                   legal_owner_type: LegalOwnerType, as_of_date: date | None, policy_id: str) -> AnalysisRequest:
    if policy_id not in POLICY_REGISTRY:
        raise HTTPException(status_code=422, detail=f"unknown policy_id {policy_id!r}")
    as_of = as_of_date or max(a.statement_end for a in accounts)
    return AnalysisRequest(customer_id=customer_id, application_id=application_id, as_of_date=as_of,
                           accounts=accounts,
                           borrower_context=BorrowerContext(legal_owner_type=legal_owner_type, application_date=as_of),
                           policy_id=policy_id)


def _stream(request: AnalysisRequest, source: str) -> StreamingResponse:
    events: queue.Queue[str | None] = queue.Queue()

    def emit(event: dict) -> None:
        events.put(json.dumps(event, separators=(",", ":")) + "\n")

    def run() -> None:
        started = time.perf_counter()
        try:
            collector = StepTraceCollector(on_step_done=lambda step, data: emit({"event": "step", "step": step, **data}))
            result = analyse_self_employed_income(request, on_step=collector)
            emit({"event": "result", "result": to_json(result), "role_trace": collector.role_trace,
                  "total_ms": round((time.perf_counter() - started) * 1000, 1)})
        except Exception as exc:  # reported in-stream: the 200 status line has already been sent
            emit({"event": "error", "detail": f"{type(exc).__name__}: {exc}"})
        finally:
            events.put(None)

    def body():
        yield json.dumps({"event": "start", "source": source, "request": {
            "customer_id": request.customer_id, "application_id": request.application_id,
            "as_of_date": request.as_of_date.isoformat(), "policy_id": request.policy_id,
            "legal_owner_type": request.borrower_context.legal_owner_type.value,
            "accounts": [_account_summary(a) for a in request.accounts]}}) + "\n"
        threading.Thread(target=run, daemon=True).start()
        while (line := events.get()) is not None:
            yield line

    return StreamingResponse(body(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@router.post("/trace")
def trace_statements(
    files: list[UploadFile] = File(..., description="analyser .xlsx/.xlsm or generic .csv statements"),
    customer_id: str = Query("UI-CUSTOMER"),
    application_id: str = Query("UI-APPLICATION"),
    legal_owner_type: LegalOwnerType = Query(LegalOwnerType.SOLE_PROP),
    account_type: AccountType = Query(AccountType.SAVINGS),
    as_of_date: date | None = Query(None),
    policy_id: str = Query("SE_INCOME_POLICY_001"),
) -> StreamingResponse:
    accounts = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, upload in enumerate(files):
            name = _SAFE_NAME.sub("_", Path(upload.filename or f"statement_{i}.xlsx").name)
            path = Path(tmp) / name
            path.write_bytes(upload.file.read())
            try:
                accounts.append(parse_statement_file(path, customer_id, account_type, legal_owner_type))
            except (ValueError, KeyError) as exc:
                raise HTTPException(status_code=422, detail=f"{name}: unparseable statement: {exc}") from exc
    if not any(a.transactions for a in accounts):
        raise HTTPException(status_code=422, detail="no transactions found in the uploaded statements")
    return _stream(_build_request(accounts, customer_id, application_id, legal_owner_type, as_of_date, policy_id),
                   "upload")


@router.post("/trace/demo")
def trace_demo(
    scenario: str = Query("kirana_trader"),
    legal_owner_type: LegalOwnerType = Query(LegalOwnerType.SOLE_PROP),
    policy_id: str = Query("SE_INCOME_POLICY_001"),
) -> StreamingResponse:
    if scenario not in DEMO_SCENARIOS:
        raise HTTPException(status_code=422, detail=f"unknown scenario {scenario!r}; one of {sorted(DEMO_SCENARIOS)}")
    account = DEMO_SCENARIOS[scenario][1]().build()
    account.parser_metadata["source_file"] = f"synthetic:{scenario}"
    return _stream(_build_request([account], "DEMO-CUSTOMER", f"DEMO-{scenario.upper()}", legal_owner_type, None,
                                  policy_id), "demo")

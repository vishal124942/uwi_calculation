import importlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from se_income_engine.services import PIPELINE_STEPS

STEP_IDS = [s["id"] for s in PIPELINE_STEPS]
ENGINE = Path(__file__).resolve().parents[1] / "se_income_engine"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("SEI_AUDIT_DB", str(tmp_path_factory.mktemp("ui") / "audit.db"))
        import se_income_engine.api.app as app_module
        importlib.reload(app_module)
        yield TestClient(app_module.app)


def test_ui_meta_lists_every_step_and_module(client):
    meta = client.get("/v1/ui/meta").json()
    assert [s["id"] for s in meta["steps"]] == STEP_IDS
    assert [s["number"] for s in meta["steps"]] == list(range(1, len(STEP_IDS) + 1))
    assert all(m["doc"] for s in meta["steps"] for m in s["modules"])
    assert meta["roles"]["C01"] and meta["policies"]


def test_ui_meta_maps_every_module_to_one_component_in_execution_order(client):
    components = client.get("/v1/ui/meta").json()["components"]
    assert [c["id"] for c in components if c["kind"] == "model"] == [f"M{i}" for i in range(1, 10)]
    modules = [m["name"] for c in components for m in c["modules"]]
    assert sorted(modules) == sorted(m for s in PIPELINE_STEPS for m in s["modules"])
    order = STEP_IDS
    first_step = [order.index(c["steps"][0]) for c in components]
    assert first_step == sorted(first_step)


def test_service_code_is_packaged_by_component(client):
    components = client.get("/v1/ui/meta").json()["components"]
    for c in components:
        assert c["package"].rsplit("/", 1)[-1].startswith(c["id"].lower() + "_")
        assert all(m["path"] == f"{c['package']}/{m['name']}.py" for m in c["modules"])
    listed = {m["path"] for c in components for m in c["modules"]}
    on_disk = {p.relative_to(ENGINE).as_posix() for p in (ENGINE / "services").rglob("s[0-9]*.py")}
    assert listed == on_disk


def test_ui_demo_trace_streams_one_event_per_step_then_result(client):
    response = client.post("/v1/ui/trace/demo", params={"scenario": "kirana_trader"})
    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines()]

    assert events[0]["event"] == "start" and events[0]["source"] == "demo"
    steps = [e for e in events if e["event"] == "step"]
    assert [e["step"] for e in steps] == STEP_IDS
    assert events[-1]["event"] == "result"

    # Transaction deltas carry only new columns; merged together they rebuild the full ledger.
    merged: dict[str, dict] = {}
    seen: set[str] = set()
    for e in steps:
        delta = e["transactions"]
        if delta is None:
            continue
        added = delta["columns"][1:]
        assert not seen & set(added)
        seen |= set(added)
        for row in delta["rows"]:
            merged.setdefault(row[0], {}).update(zip(added, row[1:]))
    result = events[-1]["result"]
    assert len(merged) == result["transaction_count"]
    assert set(events[-1]["role_trace"]) == set(merged)

    step09 = next(e for e in steps if e["step"] == "step09_uncertainty_and_policy")
    assert step09["detail"]["distribution"] and step09["detail"]["confidence_weights"]
    uwi = result["underwriting"]["underwriting_income_monthly"]
    assert uwi is not None and uwi % step09["detail"]["policy"]["rounding_unit"] == 0


def test_ui_rejects_unknown_scenario_and_policy(client):
    assert client.post("/v1/ui/trace/demo", params={"scenario": "nope"}).status_code == 422
    assert client.post("/v1/ui/trace/demo", params={"policy_id": "nope"}).status_code == 422

"""Step 3 tests: the service token, the per-store limits, the trace and the JSON logs, and the eval gate. All offline.

The model is the small FakeLLM from step 2 (no model call is made). The tests use their own token (conftest),
their own trace file and their own cases file, so the course's data/ folder is not written.
"""
import io
import json
import logging
import os
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from tenacity import wait_none

from delivery_triage.api import create_app
from delivery_triage.config import APP_DIR, load_settings
from delivery_triage.evals import gate_from_settings, load_got, load_wanted, run_gate
from delivery_triage.models import CaseRecord
from delivery_triage.observability import JsonFormatter
from delivery_triage.orders import check_record, load_orders
from delivery_triage.store import CaseStore
from delivery_triage.tenants import Tenant, load_tenants, store_key

from test_step2_store_retries_errors import AUTH, MISSING_MILK, FakeLLM, milk_record

TOKEN = os.environ["TRIAGE_SERVICE_TOKEN"]


def make_app(tmp_path, llm=None, token=TOKEN, eval_results=None):
    settings = replace(
        load_settings(),
        store_file=tmp_path / "issues.csv",
        trace_file=tmp_path / "traces.jsonl",
        service_token=token,
        model_attempts=3,
        **({"eval_results_file": eval_results} if eval_results else {}),
    )
    return create_app(settings, llm_factory=(lambda: llm) if llm is not None else None, retry_wait=wait_none())


# --- the service token (lesson 13) -------------------------------------------------------------

def test_api_refuses_a_call_without_the_token_and_makes_no_model_call(tmp_path):
    llm = FakeLLM(milk_record())
    client = TestClient(make_app(tmp_path, llm))
    response = client.post("/api/triage", json={"message": MISSING_MILK})
    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"
    assert llm.calls == 0


def test_api_refuses_a_wrong_token(tmp_path):
    client = TestClient(make_app(tmp_path), headers={"Authorization": "Bearer not-the-token"})
    response = client.get("/api/issues")
    assert response.status_code == 401 and response.json()["code"] == "unauthorized"


def test_health_and_the_page_stay_open_without_the_token(tmp_path):
    client = TestClient(make_app(tmp_path))
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["service_token_set"] is True
    assert "TRIAGE_SERVICE_TOKEN" not in health.text and TOKEN not in health.text
    assert client.get("/").status_code == 200


def test_no_token_in_the_settings_answers_503_on_api(tmp_path):
    client = TestClient(make_app(tmp_path, token=""), headers=AUTH)
    response = client.get("/api/issues")
    assert response.status_code == 503
    assert response.json()["code"] == "auth_not_configured"
    assert client.get("/health").json()["service_token_set"] is False


# --- per-customer configuration (lesson 23) ----------------------------------------------------

def test_the_stores_are_listed_with_their_limits(tmp_path):
    body = TestClient(make_app(tmp_path), headers=AUTH).get("/api/tenants").json()
    assert body["default"] == "store-02"
    ids = [t["tenant_id"] for t in body["tenants"]]
    assert len(ids) == 12 and "store-09" in ids
    assert next(t for t in body["tenants"] if t["tenant_id"] == "store-09")["max_qty_per_line"] == 1000


def test_an_unknown_store_is_refused_before_any_model_call(tmp_path):
    llm = FakeLLM(milk_record())
    client = TestClient(make_app(tmp_path, llm), headers=AUTH)
    response = client.post("/api/triage", json={"message": MISSING_MILK, "tenant": "store-99"})
    assert response.status_code == 404 and response.json()["code"] == "unknown_tenant"
    assert llm.calls == 0


def test_an_order_from_another_store_needs_a_person(tmp_path):
    # BB-1108 is in Store 02 in the orders export, so the store-07 case must not open.
    client = TestClient(make_app(tmp_path, FakeLLM(milk_record())), headers=AUTH)
    body = client.post("/api/triage", json={"message": MISSING_MILK, "tenant": "store-07"}).json()
    assert body["status"] == "needs_review"
    assert body["tenant"] == "store-07"
    assert "belongs to another store" in body["problems"][0]


def test_the_same_order_opens_for_its_own_store(tmp_path):
    client = TestClient(make_app(tmp_path, FakeLLM(milk_record())), headers=AUTH)
    body = client.post("/api/triage", json={"message": MISSING_MILK, "tenant": "store-02"}).json()
    assert body["status"] == "opened" and body["tenant"] == "store-02"


def test_the_store_limit_is_checked_for_each_store():
    orders = {"BB-7": [{"order_id": "BB-7", "store": "Store 09", "item": "milk", "qty_base": "3000", "unit_base": "each"}]}
    rec = CaseRecord(order_id="BB-7", issue="missing_item", item="milk", qty_claimed=1500, summary="test")
    strict = Tenant(tenant_id="store-09", max_qty_per_line=1000)
    relaxed = Tenant(tenant_id="store-09", max_qty_per_line=2000)
    assert any("above the store limit of 1000" in p for p in check_record(rec, orders, strict))
    assert check_record(rec, orders, relaxed) == []


def test_store_names_become_tenant_ids():
    assert store_key("Store 07") == "store-07"
    assert store_key("  Store 12 ") == "store-12"


def test_the_shipped_tenants_file_loads():
    registry = load_tenants(APP_DIR / "config" / "tenants.json")
    assert registry.default_id == "store-02" and registry.get("store-02") is not None


def test_a_tenants_file_with_a_missing_default_is_refused(tmp_path):
    path = tmp_path / "tenants.json"
    path.write_text(json.dumps({"default_tenant": "store-99", "tenants": [{"tenant_id": "store-01", "max_qty_per_line": 5}]}))
    with pytest.raises(ValueError, match="default_tenant"):
        load_tenants(path)


def test_a_tenants_file_with_a_bad_id_is_refused(tmp_path):
    path = tmp_path / "tenants.json"
    path.write_text(json.dumps({"default_tenant": "Store 1", "tenants": [{"tenant_id": "Store 1", "max_qty_per_line": 5}]}))
    with pytest.raises(ValueError, match="tenant shape"):
        load_tenants(path)


# --- logs and traces (lesson 16) ---------------------------------------------------------------

def test_each_log_line_is_json_with_the_trace_id_and_no_customer_text(tmp_path):
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("delivery_triage")
    logger.addHandler(handler)
    try:
        client = TestClient(make_app(tmp_path, FakeLLM(milk_record())), headers=AUTH)
        body = client.post("/api/triage", json={"message": MISSING_MILK}).json()
    finally:
        logger.removeHandler(handler)
    lines = [json.loads(line) for line in buffer.getvalue().splitlines() if line.strip()]
    finished = [line for line in lines if line["msg"] == "triage finished"]
    assert len(finished) == 1
    assert finished[0]["trace_id"] == body["trace_id"]
    assert finished[0]["case_id"] == "DI-00001" and finished[0]["level"] == "info"
    assert "The milk is missing" not in buffer.getvalue()  # the customer's words stay out of the logs


def test_one_request_leaves_one_trace_with_its_steps(tmp_path):
    client = TestClient(make_app(tmp_path, FakeLLM(milk_record())), headers=AUTH)
    body = client.post("/api/triage", json={"message": MISSING_MILK}).json()
    spans = [json.loads(line) for line in (tmp_path / "traces.jsonl").read_text().splitlines()]
    mine = [span for span in spans if span["trace_id"] == body["trace_id"]]
    names = {span["name"] for span in mine}
    assert {"triage.request", "model.lookup_call", "model.fill_form", "check.record", "store.add"} <= names
    root = next(span for span in mine if span["name"] == "triage.request")
    assert root["parent_id"] is None and root["attributes"]["triage.tenant"] == "store-02"
    assert all(span["parent_id"] == root["span_id"] for span in mine if span["name"] != "triage.request")
    assert "milk is missing" not in (tmp_path / "traces.jsonl").read_text()


# --- the stored cases, after the step 3 change -------------------------------------------------

def test_the_same_order_under_another_store_is_its_own_case(tmp_path):
    store = CaseStore(tmp_path / "issues.csv")
    first, _ = store.add(milk_record(), "opened", [], "store-02")
    other, created = store.add(milk_record(), "needs_review", ["belongs to another store"], "store-07")
    again, created_again = store.add(milk_record(), "opened", [], "store-02")
    assert created and other.case_id != first.case_id and other.status == "needs_review"
    assert not created_again and again.case_id == first.case_id


def test_a_cases_file_from_step_2_gets_the_tenant_column(tmp_path):
    path = tmp_path / "issues.csv"
    path.write_text(
        "case_id,dedup_key,created_at,order_id,issue,item,qty_claimed,summary,status,problems\n"
        "DI-00001,BB-1108|milk|missing_item,2026-10-22T00:00:00+00:00,BB-1108,missing_item,milk,4,Old row.,opened,\n"
    )
    store = CaseStore(path)
    old = store.list_cases()
    assert old[0].case_id == "DI-00001" and old[0].tenant == ""
    new, created = store.add(milk_record(order_id="BB-1109"), "opened", [], "store-02")
    assert created and new.case_id == "DI-00002" and new.tenant == "store-02"
    assert "tenant" in path.read_text().splitlines()[0].split(",")


# --- the eval gate (lessons 11 and 12) ---------------------------------------------------------

def test_the_gate_passes_when_enough_cases_get_the_right_label():
    wanted = {"C1": "late", "C2": "damaged"}
    got = {"C1": "late", "C2": "late"}
    result = run_gate(wanted, got, min_pass_rate=0.5)
    assert result.passed and result.pass_rate == 0.5 and result.failed == ["C2"]
    assert not run_gate(wanted, got, min_pass_rate=0.9).passed


def test_a_missing_label_counts_as_a_failure():
    result = run_gate({"C1": "late", "C2": "other"}, {}, min_pass_rate=0.5)
    assert not result.passed and result.pass_rate == 0.0 and result.failed == ["C1", "C2"]


def test_the_gate_reads_lesson_11_files():
    settings = load_settings()
    if not (settings.eval_set_file.exists() and settings.eval_results_file.exists()):
        pytest.skip("lesson 11 has not written its eval files yet")
    result = gate_from_settings(settings)
    assert result.cases == len(load_wanted(settings.eval_set_file))
    assert set(load_got(settings.eval_results_file)) >= set(load_wanted(settings.eval_set_file))


def test_the_gate_route_says_what_is_missing(tmp_path):
    client = TestClient(make_app(tmp_path, eval_results=tmp_path / "no-results.json"), headers=AUTH)
    response = client.get("/api/evals/gate")
    assert response.status_code == 409 and response.json()["code"] == "eval_files_missing"


def test_the_page_has_the_token_store_and_gate_controls(tmp_path):
    html = TestClient(make_app(tmp_path)).get("/").text
    for control in ('id="token"', 'id="tenant"', 'id="gate"', 'id="trace"'):
        assert control in html

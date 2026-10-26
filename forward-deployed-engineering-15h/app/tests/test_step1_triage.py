"""Step 1 tests: the health route, the page, the check, input errors, and two recorded triage calls.

The two triage tests replay model calls from app/tests/cassettes (made once with llm_replay and a
real key). They run offline. Re-record only after changing the prompt, the tool or the model:
    TUT_LLM_MODE=record <venv python> -m pytest app/tests/test_step1_triage.py -k triage
"""
import os
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from delivery_triage.api import create_app
from delivery_triage.config import load_settings
from delivery_triage.models import CaseRecord
from delivery_triage.orders import check_record, load_orders

CASSETTES = Path(os.environ["TUT_CASSETTE_DIR"])
MISSING_MILK = ("Hi, I'm writing about order BB-1108. The delivery came today but the milk is missing. "
                "I paid for four. Can I get a credit?")
UNKNOWN_ORDER = "Hi, I'm writing about order BB-9999. The bread never arrived. Can I get a credit?"


AUTH = {"Authorization": "Bearer " + os.environ["TRIAGE_SERVICE_TOKEN"]}  # step 3: every /api call sends it


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app(), headers=AUTH)


@pytest.fixture(scope="module")
def orders():
    return load_orders(load_settings().orders_file)


@contextmanager
def model_recording(name: str):
    """Replay the model calls of one test from its own cassette (skip with a reason if none exists)."""
    import llm_replay

    has_key = llm_replay._has_key()
    if not (CASSETTES / f"{name}.yaml").exists() and not has_key:
        pytest.skip("no model recording for this test and no model key in the course .env")
    llm_replay.start(name)
    try:
        yield
    finally:
        llm_replay.stop()


def test_health_reports_orders_loaded(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["orders_loaded"] > 0


def test_root_serves_the_triage_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Triage this message" in response.text


def test_check_rejects_an_order_that_does_not_exist(orders):
    rec = CaseRecord(order_id="BB-9999", issue="late", summary="test")
    assert check_record(rec, orders) == ["order BB-9999 is not in the orders export"]


def test_check_rejects_more_items_than_the_order_holds(orders):
    rec = CaseRecord(order_id="BB-1108", issue="missing_item", item="milk", qty_claimed=9, summary="test")
    problems = check_record(rec, orders)
    assert len(problems) == 1 and "claims 9 milk" in problems[0]


def test_check_passes_a_record_that_matches_the_order(orders):
    rec = CaseRecord(order_id="BB-1108", issue="missing_item", item="milk", qty_claimed=1, summary="test")
    assert check_record(rec, orders) == []


def test_empty_message_is_refused(client):
    response = client.post("/api/triage", json={"message": ""})
    assert response.status_code == 422


def test_missing_model_setup_gives_a_clear_503():
    def no_key():
        raise RuntimeError("GOOGLE_CLOUD_API_KEY is not set")

    client = TestClient(create_app(llm_factory=no_key), headers=AUTH)
    response = client.post("/api/triage", json={"message": MISSING_MILK})
    assert response.status_code == 503
    assert "GOOGLE_CLOUD_API_KEY" in response.json()["detail"]


def test_triage_opens_a_case_for_the_missing_milk(client):
    with model_recording("step1_missing_milk"):
        response = client.post("/api/triage", json={"message": MISSING_MILK})
    assert response.status_code == 200
    body = response.json()
    assert body["record"]["order_id"] == "BB-1108"
    assert body["record"]["issue"] == "missing_item"
    assert body["status"] == "opened"
    assert body["problems"] == []


def test_triage_flags_an_order_number_that_does_not_exist(client):
    with model_recording("step1_unknown_order"):
        response = client.post("/api/triage", json={"message": UNKNOWN_ORDER})
    assert response.status_code == 200
    body = response.json()
    assert body["record"]["order_id"] == "BB-9999"
    assert body["status"] == "needs_review"
    assert any("BB-9999" in problem for problem in body["problems"])

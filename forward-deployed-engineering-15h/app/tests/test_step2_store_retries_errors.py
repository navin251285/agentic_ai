"""Step 2 tests: the stored cases, the stable key, the retries, and the error shape. All offline.

The model is a small fake here (FakeLLM) that asks for the order and fills the form, and can fail on
purpose. So these tests cover the code around the model; the recorded calls of step 1 cover the model.
"""
import os
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from pydantic import ValidationError
from tenacity import wait_none

from delivery_triage.api import create_app
from delivery_triage.config import load_settings
from delivery_triage.models import CaseRecord
from delivery_triage.orders import load_orders
from delivery_triage.retries import call_with_retries, is_transient
from delivery_triage.store import CaseStore, dedup_key
from delivery_triage.triage import triage_message

MISSING_MILK = "Hi, I'm writing about order BB-1108. The milk is missing. I paid for four."
AUTH = {"Authorization": "Bearer " + os.environ["TRIAGE_SERVICE_TOKEN"]}  # step 3: every /api call sends it


class FakeAPIError(Exception):
    """Carries an HTTP status in `code`, as the model client's errors do."""

    def __init__(self, code: int) -> None:
        super().__init__(f"fake status {code}")
        self.code = code


class FakeLLM:
    """Asks for the order (call 1), then fills the form (call 2). Fails on purpose when told to."""

    def __init__(self, record: CaseRecord, fail_first: int = 0, error: Exception | None = None,
                 form_error: Exception | None = None) -> None:
        self.record = record
        self.fail_left = fail_first
        self.error = error or FakeAPIError(503)
        self.form_error = form_error
        self.calls = 0

    def _maybe_fail(self) -> None:
        self.calls += 1
        if self.fail_left:
            self.fail_left -= 1
            raise self.error

    def bind_tools(self, tools):
        outer = self

        class Asks:
            def invoke(self, messages):
                outer._maybe_fail()
                return AIMessage(content="", tool_calls=[
                    {"name": "lookup_order", "args": {"order_id": outer.record.order_id}, "id": "call-1"}])

        return Asks()

    def with_structured_output(self, schema, method=None):
        outer = self

        class Form:
            def invoke(self, messages):
                outer._maybe_fail()
                if outer.form_error is not None:
                    raise outer.form_error
                return outer.record

        return Form()


def milk_record(order_id: str = "BB-1108") -> CaseRecord:
    return CaseRecord(order_id=order_id, issue="missing_item", item="milk", qty_claimed=4,
                      summary="Customer reported four units of milk missing.")


def make_client(tmp_path: Path, llm: FakeLLM, attempts: int = 3) -> TestClient:
    settings = replace(load_settings(), store_file=tmp_path / "issues.csv", model_attempts=attempts)
    return TestClient(create_app(settings, llm_factory=lambda: llm, retry_wait=wait_none()), headers=AUTH)


# --- the stored cases -------------------------------------------------------------------------

def test_store_round_trip_and_first_id(tmp_path):
    store = CaseStore(tmp_path / "issues.csv")
    assert store.list_cases() == []
    case, created = store.add(milk_record(), "opened", [])
    assert created is True and case.case_id == "DI-00001"
    assert store.get("DI-00001").order_id == "BB-1108"
    assert store.get("DI-00001").qty_claimed == 4


def test_same_stable_key_is_stored_once(tmp_path):
    store = CaseStore(tmp_path / "issues.csv")
    first, _ = store.add(milk_record(), "opened", [])
    again = milk_record(order_id=" bb-1108 ")  # the same case, written differently (lesson 05: normalise first)
    second, created = store.add(again, "opened", [])
    assert created is False and second.case_id == first.case_id
    assert store.count() == 1


def test_a_different_issue_on_the_same_item_is_a_new_case(tmp_path):
    store = CaseStore(tmp_path / "issues.csv")
    store.add(milk_record(), "opened", [])
    late = CaseRecord(order_id="BB-1108", issue="late", item="milk", summary="Late milk.")
    case, created = store.add(late, "opened", [])
    assert created is True and case.case_id == "DI-00002"


def test_problems_survive_the_round_trip(tmp_path):
    store = CaseStore(tmp_path / "issues.csv")
    rec = CaseRecord(order_id="BB-9999", issue="late", summary="Bread never came.")
    case, _ = store.add(rec, "needs_review", ["order BB-9999 is not in the orders export", "x"])
    assert store.get(case.case_id).problems == ["order BB-9999 is not in the orders export", "x"]
    assert store.get(case.case_id).item is None


def test_dedup_key_uses_order_item_and_issue():
    assert dedup_key(milk_record(" bb-1108")) == "BB-1108|milk|missing_item"


# --- the retries (lesson 04) ------------------------------------------------------------------

@pytest.mark.parametrize("code", [429, 502, 503, 504])
def test_later_try_may_succeed_for_these_statuses(code):
    assert is_transient(FakeAPIError(code))


@pytest.mark.parametrize("code", [400, 401, 422])
def test_a_bad_request_is_not_transient(code):
    assert not is_transient(FakeAPIError(code))


def test_timeouts_and_dropped_connections_are_transient():
    assert is_transient(httpx.ReadTimeout("slow"))
    assert is_transient(ConnectionError("dropped"))
    assert not is_transient(ValueError("bad reply"))


def test_transient_failures_are_retried_until_success():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise FakeAPIError(503)
        return "ok"

    assert call_with_retries(flaky, attempts=4, wait=wait_none()) == "ok"
    assert len(calls) == 3


def test_a_bad_request_is_raised_at_once():
    calls = []

    def refused():
        calls.append(1)
        raise FakeAPIError(400)

    with pytest.raises(FakeAPIError):
        call_with_retries(refused, attempts=4, wait=wait_none())
    assert len(calls) == 1


def test_retries_stop_after_the_last_attempt():
    calls = []

    def down():
        calls.append(1)
        raise FakeAPIError(503)

    with pytest.raises(FakeAPIError):
        call_with_retries(down, attempts=3, wait=wait_none())
    assert len(calls) == 3


def test_triage_retries_a_failed_model_call_and_still_checks_the_record(tmp_path):
    llm = FakeLLM(milk_record(), fail_first=1)
    orders = load_orders(load_settings().orders_file)
    result = triage_message(MISSING_MILK, orders, llm, attempts=3, wait=wait_none())
    assert result.status == "opened" and result.problems == []
    assert llm.calls == 3  # the failed ask, its retry, and the form


# --- the API: storing, duplicates and the list ------------------------------------------------

def test_root_page_has_the_stored_cases_list(tmp_path):
    response = make_client(tmp_path, FakeLLM(milk_record())).get("/")
    assert response.status_code == 200
    assert "Stored cases" in response.text and "Refresh list" in response.text


def test_triage_stores_the_case_and_the_api_lists_it(tmp_path):
    client = make_client(tmp_path, FakeLLM(milk_record()))
    body = client.post("/api/triage", json={"message": MISSING_MILK}).json()
    assert body["case_id"] == "DI-00001" and body["duplicate"] is False and body["status"] == "opened"
    listed = client.get("/api/issues").json()
    assert [c["case_id"] for c in listed] == ["DI-00001"]
    one = client.get("/api/issues/DI-00001").json()
    assert one["order_id"] == "BB-1108" and one["item"] == "milk" and one["qty_claimed"] == 4
    assert "message" not in one  # the customer's words are not kept


def test_the_same_case_twice_is_stored_once(tmp_path):
    client = make_client(tmp_path, FakeLLM(milk_record()))
    first = client.post("/api/triage", json={"message": MISSING_MILK}).json()
    second = client.post("/api/triage", json={"message": MISSING_MILK}).json()
    assert second["duplicate"] is True and second["case_id"] == first["case_id"]
    assert len(client.get("/api/issues").json()) == 1
    assert client.get("/health").json()["cases_stored"] == 1


def test_list_is_newest_first_and_limited(tmp_path):
    client = make_client(tmp_path, FakeLLM(milk_record()))
    store = CaseStore(tmp_path / "issues.csv")
    for n in range(3):
        store.add(CaseRecord(order_id=f"BB-{1100 + n}", issue="late", summary="late"), "opened", [])
    ids = [c["case_id"] for c in client.get("/api/issues?limit=2").json()]
    assert ids == ["DI-00003", "DI-00002"]


# --- the API: clear, stable error responses ---------------------------------------------------

def test_unknown_case_is_a_404_with_a_code(tmp_path):
    response = make_client(tmp_path, FakeLLM(milk_record())).get("/api/issues/DI-99999")
    assert response.status_code == 404
    assert response.json()["code"] == "case_not_found"


def test_an_empty_message_is_refused_with_a_code(tmp_path):
    response = make_client(tmp_path, FakeLLM(milk_record())).post("/api/triage", json={"message": ""})
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"


def test_missing_model_setup_has_a_code(tmp_path):
    def no_key():
        raise RuntimeError("GOOGLE_CLOUD_API_KEY is not set")

    settings = replace(load_settings(), store_file=tmp_path / "issues.csv", model_attempts=3)
    client = TestClient(create_app(settings, llm_factory=no_key), headers=AUTH)
    response = client.post("/api/triage", json={"message": MISSING_MILK})
    assert response.status_code == 503 and response.json()["code"] == "model_not_configured"


def test_a_model_that_stays_busy_gives_503_and_stores_nothing(tmp_path):
    client = make_client(tmp_path, FakeLLM(milk_record(), fail_first=99), attempts=3)
    response = client.post("/api/triage", json={"message": MISSING_MILK})
    assert response.status_code == 503
    assert response.json()["code"] == "model_busy"
    assert client.get("/api/issues").json() == []


def test_a_model_call_that_is_refused_gives_502_without_retries(tmp_path):
    llm = FakeLLM(milk_record(), fail_first=99, error=FakeAPIError(400))
    response = make_client(tmp_path, llm).post("/api/triage", json={"message": MISSING_MILK})
    assert response.status_code == 502 and response.json()["code"] == "model_failed"
    assert llm.calls == 1


def test_a_reply_that_does_not_fit_the_form_gives_502(tmp_path):
    try:
        CaseRecord.model_validate({"order_id": "BB-1108", "issue": "bogus"})
    except ValidationError as exc:
        bad_form = exc
    llm = FakeLLM(milk_record(), form_error=bad_form)
    response = make_client(tmp_path, llm).post("/api/triage", json={"message": MISSING_MILK})
    assert response.status_code == 502 and response.json()["code"] == "model_reply_invalid"
    assert CaseStore(tmp_path / "issues.csv").count() == 0

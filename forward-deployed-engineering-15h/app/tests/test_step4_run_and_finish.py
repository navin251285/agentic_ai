"""Step 4 tests: the one start command and its checks, and the whole flow from start to list. All offline.

The model is the small FakeLLM from step 2 (no model call is made). The start command is checked with --check,
so no server is started by the tests.
"""
import os
from dataclasses import replace

from fastapi.testclient import TestClient
from tenacity import wait_none

from delivery_triage.__main__ import main, preflight
from delivery_triage.api import create_app
from delivery_triage.config import load_settings

from test_step2_store_retries_errors import AUTH, MISSING_MILK, FakeLLM, milk_record

TOKEN = os.environ["TRIAGE_SERVICE_TOKEN"]


def test_the_check_passes_with_the_course_files(capsys):
    assert main(["--check"]) == 0
    out = capsys.readouterr().out
    assert "orders file" in out and "tenants file" in out and "stop" not in out


def test_the_start_stops_when_the_orders_file_is_missing(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("TRIAGE_ORDERS_FILE", str(tmp_path / "missing.csv"))
    assert main(["--check"]) == 1
    out = capsys.readouterr()
    assert "stop orders file" in out.out
    assert "Not started" in out.err


def test_a_missing_token_is_a_warning_and_the_start_still_goes_ahead(monkeypatch, capsys):
    import delivery_triage.__main__ as start

    monkeypatch.setattr(start, "load_settings", lambda: replace(load_settings(), service_token=""))
    assert main(["--check"]) == 0
    assert "warn service token" in capsys.readouterr().out


def test_the_checks_name_each_thing_without_printing_a_value():
    checks = {check.name: check for check in preflight(load_settings())}
    assert set(checks) == {"orders file", "tenants file", "service token", "model access", "eval gate files"}
    assert TOKEN not in str(checks["service token"].detail)


def test_the_whole_flow_from_start_to_the_stored_list(tmp_path):
    settings = replace(
        load_settings(), store_file=tmp_path / "issues.csv", trace_file=tmp_path / "traces.jsonl",
        service_token=TOKEN, model_attempts=3,
    )
    llm = FakeLLM(milk_record())
    client = TestClient(create_app(settings, llm_factory=lambda: llm, retry_wait=wait_none()), headers=AUTH)

    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/api/tenants").json()["default"] == "store-02"

    opened = client.post("/api/triage", json={"message": MISSING_MILK}).json()
    assert opened["status"] == "opened" and opened["case_id"] == "DI-00001" and opened["duplicate"] is False

    other_store = client.post("/api/triage", json={"message": MISSING_MILK, "tenant": "store-07"}).json()
    assert other_store["status"] == "needs_review" and other_store["case_id"] == "DI-00002"

    again = client.post("/api/triage", json={"message": MISSING_MILK}).json()
    assert again["duplicate"] is True and again["case_id"] == "DI-00001"

    listed = client.get("/api/issues").json()
    assert [case["case_id"] for case in listed] == ["DI-00002", "DI-00001"]
    assert client.get("/api/issues/DI-00001").json()["status"] == "opened"
    assert client.get("/health").json()["cases_stored"] == 2

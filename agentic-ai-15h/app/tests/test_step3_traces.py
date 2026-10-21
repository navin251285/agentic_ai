"""Step 3: the trace view and the cost meter, through FastAPI's TestClient. The model answers replay lesson 23's recording.

Each test gets its own state folder, so its trace file holds only its own spans.
"""
import hashlib
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from support_desk.api import app, get_desk
from support_desk.desk import DeskService, UnknownThread
from support_desk.observe import load_spans, p95, task_rows
from support_desk.settings import load_settings

QUESTION = ("I want a refund for order 1007, it never arrived. Please refund the 210.00 USD I paid. "
            "What does your policy say about a lost parcel?")  # the recorded question (lesson 23, Step 8)


def settings_in(tmp_path, **changes):
    return replace(load_settings(), state_dir=tmp_path, **changes)


@pytest.fixture
def use_desk():
    def use(service: DeskService) -> TestClient:
        app.dependency_overrides[get_desk] = lambda: service
        return TestClient(app)
    yield use
    app.dependency_overrides.clear()


@pytest.fixture
def client(tmp_path, use_desk):
    return use_desk(DeskService(settings_in(tmp_path)))


def test_root_serves_the_traces_section(client):
    html = client.get("/").text
    assert "Traces and cost" in html and "/api/traces" in html


def test_a_question_and_its_decision_make_one_ticket_row(client):
    client.post("/api/desk/chat", json={"customer_id": "C-88", "thread_id": "run-one", "message": QUESTION})
    client.post("/api/desk/decision", json={"thread_id": "run-one", "reviewer": "senior-lead", "approve": True})
    body = client.get("/api/traces").json()
    assert [r["task"] for r in body["tasks"]] == ["run-one"]
    row = body["tasks"][0]
    assert row["runs"] == 2                                   # the question, then the decision
    assert row["model_calls"] == 4 and row["tool_calls"] == 3  # the recorded run: 4 model calls, 3 tool calls
    assert row["answered"] and row["outcome"] == "answered" and row["refused"] == 0 and row["tool_errors"] == 0
    assert body["summary"]["answered_rate"] == 1.0 and body["summary"]["slo_breached"] is False


def test_the_cost_per_ticket_is_the_cost_the_desk_reported(client):
    client.post("/api/desk/chat", json={"customer_id": "C-88", "thread_id": "run-cost", "message": QUESTION})
    done = client.post("/api/desk/decision", json={"thread_id": "run-cost", "reviewer": "senior-lead",
                                                   "approve": True}).json()
    row = client.get("/api/traces").json()["tasks"][0]
    assert row["cost_usd"] == pytest.approx(done["cost_usd"], abs=1e-6)  # from the token counts on the chat spans
    assert client.get("/api/traces").json()["summary"]["cost_per_ticket_usd"] == pytest.approx(done["cost_usd"], abs=1e-6)


def test_a_waiting_ticket_is_not_counted_as_failed(client):
    client.post("/api/desk/chat", json={"customer_id": "C-88", "thread_id": "run-wait", "message": QUESTION})
    body = client.get("/api/traces").json()
    assert body["tasks"][0]["outcome"] == "waiting for approval"
    assert body["summary"]["waiting"] == 1 and body["summary"]["answered_rate"] is None
    assert body["summary"]["slo_breached"] is None


def test_the_trace_view_nests_model_and_tool_spans(client):
    client.post("/api/desk/chat", json={"customer_id": "C-88", "thread_id": "run-tree", "message": QUESTION})
    client.post("/api/desk/decision", json={"thread_id": "run-tree", "reviewer": "senior-lead", "approve": True})
    spans = client.get("/api/traces/run-tree").json()["spans"]
    assert [(s["depth"], s["name"]) for s in spans] == [
        (0, "invoke_agent support-desk"), (1, "chat gemini-3.1-flash-lite"),
        (1, "execute_tool search_policy"), (1, "chat gemini-3.1-flash-lite"),
        (1, "execute_tool search_policy"), (1, "chat gemini-3.1-flash-lite"),
        (0, "invoke_agent support-desk"), (1, "execute_tool refund_order"), (1, "chat gemini-3.1-flash-lite"),
    ]
    assert spans[6]["attributes"]["support.step"] == "decision"


def test_the_trace_holds_ids_and_counts_never_the_customers_words(client, tmp_path):
    client.post("/api/desk/chat", json={"customer_id": "C-88", "thread_id": "run-privacy", "message": QUESTION})
    written = (tmp_path / "traces.jsonl").read_text(encoding="utf-8")
    assert "Please refund" not in written and "lost parcel" not in written and "@" not in written
    first = client.get("/api/traces/run-privacy").json()["spans"][0]["attributes"]
    assert first["support.question_sha256"] == hashlib.sha256(QUESTION.encode()).hexdigest()[:16]


def test_a_step_cap_is_an_error_span(tmp_path, use_desk):
    client = use_desk(DeskService(settings_in(tmp_path, max_steps=1)))
    run = client.post("/api/desk/chat", json={"customer_id": "C-88", "thread_id": "run-cap", "message": QUESTION}).json()
    assert run["stop"] == "step cap"
    root = client.get("/api/traces/run-cap").json()["spans"][0]
    assert root["status"] == "ERROR" and root["attributes"]["support.outcome"] == "step cap"
    assert client.get("/api/traces").json()["tasks"][0]["answered"] is False


def test_the_trace_survives_a_restart(tmp_path, use_desk):
    client = use_desk(DeskService(settings_in(tmp_path)))
    client.post("/api/desk/chat", json={"customer_id": "C-88", "thread_id": "run-restart", "message": QUESTION})
    client = use_desk(DeskService(settings_in(tmp_path)))  # a new process on the same state folder
    assert [r["task"] for r in client.get("/api/traces").json()["tasks"]] == ["run-restart"]


def test_an_unknown_ticket_has_no_trace(client):
    assert client.get("/api/traces/run-none").status_code == 404


def test_the_service_raises_for_an_unknown_ticket(tmp_path):
    with pytest.raises(UnknownThread):
        DeskService(settings_in(tmp_path)).trace("run-none")


def test_p95_is_the_value_that_95_percent_of_tickets_beat():
    assert p95(list(range(1, 101))) == 95
    assert p95([10.0, 20.0, 30.0]) == 30.0


def test_a_damaged_trace_line_is_skipped(tmp_path):
    path = tmp_path / "traces.jsonl"
    path.write_text('{"name": "one"}\nnot json at all\n\n{"name": "two"}\n', encoding="utf-8")
    assert [s["name"] for s in load_spans(path)] == ["one", "two"]


def test_no_spans_means_an_empty_dashboard():
    assert task_rows([]) == []

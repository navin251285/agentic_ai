"""Step 2: the support desk through FastAPI's TestClient: policy, memory, the refund approval gate and the saved run.

The model answers replay the course's recording of lesson 23, one recorded call per request (no key, no cost).
Each test gets its own state folder, so a run from one test never shows in another.
"""
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from support_desk.api import app, get_desk
from support_desk.desk import DeskService
from support_desk.settings import load_settings

QUESTION = ("I want a refund for order 1007, it never arrived. Please refund the 210.00 USD I paid. "
            "What does your policy say about a lost parcel?")  # the recorded question (lesson 23, Step 8)
CARD = "4" + "0" * 14 + "2"  # made up: passes the card checksum
PENDING_1007 = {"question": "Approve this refund?", "refund": {"order_id": "1007", "amount_usd": 210.0},
                "needs": "senior-lead"}
PAID_1007 = {"name": "refund_order", "args": {"order_id": "1007", "amount_usd": 210.0},
             "result": {"status": "refunded", "amount_usd": 210.0, "approved_by": "senior-lead"}}


def settings_in(tmp_path, **changes):
    return replace(load_settings(), state_dir=tmp_path, **changes)


@pytest.fixture
def use_desk():
    """Point the API at a desk over a given state folder; the override is removed after each test."""
    def use(service: DeskService) -> TestClient:
        app.dependency_overrides[get_desk] = lambda: service
        return TestClient(app)
    yield use
    app.dependency_overrides.clear()


@pytest.fixture
def client(tmp_path, use_desk):
    return use_desk(DeskService(settings_in(tmp_path)))


def start(client: TestClient, thread: str, message: str = QUESTION) -> dict:
    return client.post("/api/desk/chat", json={"customer_id": "C-88", "thread_id": thread, "message": message}).json()


def decide(client: TestClient, thread: str, reviewer: str, approve: bool):
    return client.post("/api/desk/decision", json={"thread_id": thread, "reviewer": reviewer, "approve": approve})


def test_root_serves_the_refund_desk(client):
    html = client.get("/").text
    assert "Refund desk" in html and "/api/desk/chat" in html and "/api/desk/decision" in html


def test_health_lists_the_desk_tools(client):
    assert client.get("/health").json()["desk_tools"] == ["lookup_order", "search_policy", "refund_order"]


def test_memory_keeps_the_fact_and_refuses_the_card(client):
    saved = client.post("/api/desk/memory", json={"customer_id": "C-88", "topic": "contact",
                                                  "fact": "Prefers replies by email"})
    blocked = client.post("/api/desk/memory", json={"customer_id": "C-88", "topic": "payment",
                                                    "fact": f"Card {CARD} was charged twice"})
    assert saved.json() == {"result": "saved"}
    assert blocked.json() == {"result": "blocked: payment card number"}  # the card is never repeated back
    assert client.get("/api/desk/memory/C-88").json()["facts"] == ["Prefers replies by email"]


def test_refund_waits_for_a_senior_and_is_paid_once(client):
    client.post("/api/desk/memory", json={"customer_id": "C-88", "topic": "contact",
                                          "fact": "Prefers replies by email"})
    run = start(client, "run-one")
    assert run["status"] == "waiting for approval"
    assert run["pending"] == PENDING_1007
    assert run["model_calls"] == 3 and run["answer"] == ""           # the three calls before the pause
    assert [c["name"] for c in run["calls"]] == ["search_policy", "search_policy"]

    refused = decide(client, "run-one", "agent-desk-1", True).json()  # a desk reviewer cannot approve over $50
    assert refused["status"] == "waiting for approval" and refused["model_calls"] == 3
    assert not any(c["name"] == "refund_order" for c in refused["calls"])

    done = decide(client, "run-one", "senior-lead", True).json()
    assert done["status"] == "finished" and done["stop"] == "answered" and done["model_calls"] == 4
    assert [c for c in done["calls"] if c["name"] == "refund_order"] == [PAID_1007]
    assert done["cites"] == {"ids": [27, 31], "shown": [27, 31], "all_shown": True}
    assert "[policy-27, policy-31]" in done["answer"]


def test_a_refused_refund_pays_nothing(client):
    start(client, "run-no")
    reply = decide(client, "run-no", "senior-lead", False).json()
    assert reply["status"] == "finished"
    refund = next(c for c in reply["calls"] if c["name"] == "refund_order")
    assert refund["result"] == {"status": "rejected by senior-lead"}


def test_a_restart_keeps_the_pause_and_the_ledger(tmp_path, use_desk):
    client = use_desk(DeskService(settings_in(tmp_path)))  # the first process starts the run
    assert start(client, "run-before")["status"] == "waiting for approval"

    client = use_desk(DeskService(settings_in(tmp_path)))  # a restart: a new process on the same state folder
    saved = client.get("/api/desk/runs/run-before").json()
    assert saved["status"] == "waiting for approval" and saved["pending"] == PENDING_1007
    assert decide(client, "run-before", "senior-lead", True).json()["status"] == "finished"

    # a second request for the same refund: the ledger key is the order, so nothing is paid again
    assert start(client, "run-again")["status"] == "waiting for approval"
    again = decide(client, "run-again", "senior-lead", True).json()
    assert [c["result"]["status"] for c in again["calls"] if c["name"] == "refund_order"] == ["already paid"]


def test_a_question_with_no_recording_is_refused_not_invented(client):
    response = client.post("/api/desk/chat", json={"customer_id": "C-88", "thread_id": "run-x",
                                                   "message": "What is the weather in Paris today?"})
    assert response.status_code == 503


def test_a_thread_id_is_used_once(client):
    assert start(client, "run-dup")["status"] == "waiting for approval"
    assert client.post("/api/desk/chat", json={"customer_id": "C-88", "thread_id": "run-dup",
                                               "message": QUESTION}).status_code == 409


def test_a_decision_needs_a_waiting_run(client):
    assert decide(client, "run-missing", "senior-lead", True).status_code == 404
    start(client, "run-done")
    decide(client, "run-done", "senior-lead", True)
    assert decide(client, "run-done", "senior-lead", True).status_code == 409


def test_the_step_cap_stops_the_desk_before_a_further_call(tmp_path, use_desk):
    client = use_desk(DeskService(settings_in(tmp_path, max_steps=1)))
    run = start(client, "run-cap")
    assert run["stop"] == "step cap" and run["model_calls"] == 1 and run["status"] == "finished"

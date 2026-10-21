"""Step 1: the chat page and POST /api/chat, through FastAPI's TestClient, replaying a recorded run."""
from fastapi.testclient import TestClient

from support_desk.agent import run_chat
from support_desk.api import app
from support_desk.settings import Settings, load_settings

QUESTION = "Where is my parcel for order 1002? It was due on Monday."  # the recording's question (course lesson 10, run A)
client = TestClient(app)


def test_root_serves_the_chat_page():
    response = client.get("/")
    assert response.status_code == 200
    assert "Brightside support desk" in response.text
    assert "/api/chat" in response.text


def test_health_lists_the_tools_and_caps():
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["tools"] == ["lookup_order", "calculator"]
    assert body["max_steps"] >= 1 and body["max_usd"] > 0


def test_chat_replays_the_recorded_lookup():
    response = client.post("/api/chat", json={"message": QUESTION})
    assert response.status_code == 200
    body = response.json()
    assert body["stop"] == "answered"
    assert body["steps"] == 2  # one call asks for lookup_order, one answers
    assert body["calls"][0]["name"] == "lookup_order"
    assert body["calls"][0]["args"] == {"order_id": "1002"}
    assert body["calls"][0]["result"]["days_late"] == 4
    assert "1002" in body["answer"]


def test_step_cap_stops_before_any_tool_runs():
    base = load_settings()
    result = run_chat(QUESTION, Settings(max_steps=1, max_usd=base.max_usd, orders_file=base.orders_file, port=base.port))
    assert result.stop == "step cap"
    assert result.calls == []


def test_spend_cap_stops_before_any_tool_runs():
    base = load_settings()
    result = run_chat(QUESTION, Settings(max_steps=4, max_usd=0.0, orders_file=base.orders_file, port=base.port))
    assert result.stop == "spend cap"
    assert result.calls == []


def test_unrecorded_question_is_refused_not_invented():
    response = client.post("/api/chat", json={"message": "What is the weather in Paris today?"})
    assert response.status_code == 503


def test_empty_message_is_a_validation_error():
    assert client.post("/api/chat", json={"message": ""}).status_code == 422

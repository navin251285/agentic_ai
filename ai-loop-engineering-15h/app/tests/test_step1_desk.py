"""Step 1: the desk loop with caps, the get_order and calculator tools, stop reasons and the stuck check."""
import contextlib

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import llm_replay
from brightside_desk.api import create_app
from brightside_desk.config import MissingSettingError, Settings
from brightside_desk.desk import Caps, Step, stuck_reason
from brightside_desk.llm import build_chat_model
from brightside_desk.tools import calculator, get_order, run_tool, safe_eval


@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c


@contextlib.contextmanager
def recorded(name):
    """Replay the model calls recorded under this name (tests/cassettes/<name>.yaml)."""
    llm_replay.start(name)
    try:
        yield
    finally:
        llm_replay.stop()


def test_health_and_page(client):
    assert client.get("/health").json() == {"status": "ok"}
    page = client.get("/")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "<form" in page.text and "/api/chat" in page.text


def test_get_order_finds_and_refuses(client):
    assert "Trail jacket" in get_order.invoke({"order_id": "BS-1042"})
    assert get_order.invoke({"order_id": "BS-9999"}) == "error: no order BS-9999"
    bad = run_tool({"name": "get_order", "args": {"order_id": "1042"}, "id": "c1"})
    assert bad.content.startswith("error: order_id")  # the schema rejects it; the tool body never runs


def test_calculator_is_exact_and_refuses_code():
    assert safe_eval("(120 - 18) * 2") == 204
    assert calculator.invoke({"expression": "(120 - 18) * 2"}) == "204"
    assert calculator.invoke({"expression": "10 / 4"}) == "2.5"
    assert calculator.invoke({"expression": "2 / 0"}).startswith("error")
    assert calculator.invoke({"expression": "__import__('os')"}).startswith("error")
    with pytest.raises(ValueError):
        safe_eval("9 ** 9")  # power is not allowed: no way to make a huge number


def test_caps_must_be_positive():
    with pytest.raises(ValueError):
        Caps(max_turns=0)
    with pytest.raises(ValueError):
        Caps(max_usd=0)
    assert Caps().max_turns == 6


def test_stuck_check_fires_on_repeats_not_on_progress():
    same = [Step(calls=[("get_order", '{"order_id": "BS-1042"}')], results=[("get_order", "ok")]) for _ in range(3)]
    assert stuck_reason(same) == "the same call 3 times in a row"
    assert stuck_reason(same[:2]) is None  # two steps are not a pattern yet
    errors = [Step(calls=[("get_order", f'{{"order_id": "BS-{n}"}}')], results=[("get_order", "error: no order")])
              for n in (1, 2)]
    assert stuck_reason(errors) == "the same error twice, even with a success between"
    with pytest.raises(ValueError):
        stuck_reason(same, repeats=1)


def test_missing_key_is_a_clear_error_without_the_value():
    empty = Settings(api_key="", project="", location="global", model="m")
    with pytest.raises(MissingSettingError) as info:
        build_chat_model(empty)
    assert "GOOGLE_CLOUD_API_KEY" in str(info.value)


def test_chat_without_key_is_503_and_no_model_call():
    no_key = Settings(api_key="", project="", location="global", model="m")
    with TestClient(create_app(settings=no_key)) as c:
        r = c.post("/api/chat", json={"message": "hello"})
    assert r.status_code == 503
    assert "GOOGLE_CLOUD_API_KEY" in r.json()["detail"]


def test_chat_rejects_bad_input(client):
    assert client.post("/api/chat", json={"message": ""}).status_code == 422
    assert client.post("/api/chat", json={"message": "hi", "max_turns": 0}).status_code == 422


def test_lookup_then_answer(client):
    question = "What did customer C-17 pay for order BS-1042, and what is that doubled?"
    with recorded("step1_lookup_answer"):
        r = client.post("/api/chat", json={"message": question, "max_turns": 6})
    assert r.status_code == 200
    data = r.json()
    assert data["stop"] == "answered"
    assert data["answer"]
    assert data["turns"] >= 2  # one reply asked for a tool, a later reply answered in text
    asked = [c["name"] for step in data["steps"] for c in step["calls"]]
    assert "get_order" in asked
    assert all(r["text"] for step in data["steps"] for r in step["results"])


def test_turn_cap_stops_before_the_tools_run(client):
    question = "What did customer C-17 pay for order BS-1042?"
    with recorded("step1_turn_cap"):
        r = client.post("/api/chat", json={"message": question, "max_turns": 1})
    data = r.json()
    assert data["stop"] == "turn_cap"
    assert data["turns"] == 1
    assert data["answer"] is None
    assert data["steps"][0]["calls"]  # the model asked for a tool
    assert data["steps"][0]["results"] == []  # ...and the cap stopped it before the tool ran


def test_tool_schema_rejects_an_order_without_the_prefix():
    with pytest.raises(ValidationError):
        get_order.invoke({"order_id": "42"})

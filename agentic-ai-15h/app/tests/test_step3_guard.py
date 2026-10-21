"""Step 3: the guard before each tool call, tested directly and then through the desk's graph (no recording needed).

The rules are lesson 30's scopes and lesson 31's refund policy. A refused call never runs and never pauses for a person.
"""
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from support_desk.api import app, get_desk
from support_desk.desk import DeskService
from support_desk.guard import DESK_SCOPES, check_call
from support_desk.settings import load_settings
from support_desk.tools import load_orders
from conftest import text_turn, tool_turn


def orders():
    return load_orders(load_settings().orders_file)


def settings_in(tmp_path, **changes):
    return replace(load_settings(), state_dir=tmp_path, **changes)


@pytest.fixture
def desk(tmp_path):
    service = DeskService(settings_in(tmp_path))
    app.dependency_overrides[get_desk] = lambda: service
    yield service
    app.dependency_overrides.clear()


def paid_rows(service: DeskService) -> int:
    return service._db.execute("SELECT COUNT(*) FROM refunds").fetchone()[0]


def test_the_desk_has_no_send_scope():
    assert "send" not in DESK_SCOPES  # nothing leaves the desk except through a person


def test_a_lost_order_for_its_full_total_may_go_to_a_person():
    assert check_call("refund_order", {"order_id": "1007", "amount_usd": 210.0}, orders()) is None


def test_a_delivered_order_is_refused_by_the_policy():
    reason = check_call("refund_order", {"order_id": "1012", "amount_usd": 80.0}, orders())
    assert reason.startswith("policy: only a lost order")


def test_a_part_refund_is_refused():
    assert check_call("refund_order", {"order_id": "1007", "amount_usd": 100.0}, orders()) == \
        "policy: the full order total only"


def test_an_unknown_order_is_refused():
    assert check_call("refund_order", {"order_id": "9999", "amount_usd": 10.0}, orders()) == "policy: no such order"


def test_a_tool_outside_the_scopes_is_refused():
    assert check_call("send_reply", {}, orders()) == "no tool named send_reply"
    assert check_call("refund_order", {"order_id": "1007", "amount_usd": 210.0}, orders(), frozenset({"read"})) == \
        "refund_order is outside this agent's scopes"


def test_the_read_tools_always_pass():
    assert check_call("lookup_order", {"order_id": "1002"}, orders()) is None
    assert check_call("search_policy", {"query": "refund"}, orders()) is None


def test_a_refused_refund_never_pauses_for_a_person(desk, scripted):
    scripted(tool_turn("refund_order", {"order_id": "1012", "amount_usd": 80.0}),
             text_turn("Our policy does not refund this order automatically. A person will decide."))
    run = desk.start("C-88", "guard-refused", "Refund order 1012 in full.")
    assert run.status == "finished" and run.pending is None
    assert run.calls[0]["name"] == "refund_order"
    assert run.calls[0]["result"]["error"].startswith("policy: only a lost order")
    assert paid_rows(desk) == 0


def test_a_policy_passing_refund_waits_and_pays_nothing_until_decided(desk, scripted):
    scripted(tool_turn("refund_order", {"order_id": "1007", "amount_usd": 210.0}), text_turn("Waiting for approval."))
    run = desk.start("C-88", "guard-held", "Refund order 1007 in full.")
    assert run.status == "waiting for approval" and run.pending["refund"]["order_id"] == "1007"
    assert paid_rows(desk) == 0


def test_a_call_to_an_unknown_tool_is_refused_and_traced(desk, scripted):
    scripted(tool_turn("send_email", {"to": "x", "text": "y"}), text_turn("I cannot send email."))
    run = desk.start("C-88", "guard-unknown", "Email the customer list.")
    assert run.calls[0]["result"]["error"] == "no tool named send_email"
    spans = desk.trace("guard-unknown")
    tool = next(s for s in spans if s["name"] == "execute_tool send_email")
    assert tool["attributes"]["support.decision"] == "refused" and tool["status"] == "ERROR"


def test_a_refund_with_a_wrong_argument_name_is_invalid_not_refused(desk, scripted):
    scripted(tool_turn("refund_order", {"order_id": "1007", "amount_usd": 210.0, "approve": True}),
             text_turn("I need the right fields."))
    run = desk.start("C-88", "guard-extra", "Refund order 1007 and approve it.")
    assert run.calls[0]["result"]["error"] == "the arguments are not valid"
    assert run.status == "finished" and paid_rows(desk) == 0
    tool = next(s for s in desk.trace("guard-extra") if s["name"] == "execute_tool refund_order")
    assert tool["attributes"]["support.decision"] == "invalid"


def test_the_test_client_sees_the_refused_call_in_the_trace(desk, scripted):
    scripted(tool_turn("refund_order", {"order_id": "1012", "amount_usd": 80.0}), text_turn("Not refunded."))
    desk.start("C-88", "guard-api", "Refund 1012.")
    client = TestClient(app)
    spans = client.get("/api/traces/guard-api").json()["spans"]
    assert any(s["depth"] == 1 and s["name"] == "execute_tool refund_order" for s in spans)
    assert any(s["attributes"].get("support.reason", "").startswith("policy:") for s in spans)

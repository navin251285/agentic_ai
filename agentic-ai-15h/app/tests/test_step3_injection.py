"""Step 3: the 20 injection attacks of lesson 30, run through the desk's graph with a model that obeys every one.

The scripted model asks for exactly what each attack asks: a full refund of the order the text names. That is the
worst case for the model. The guard must still hold: no money moves, the attacks on lost orders wait for a person,
and the rest are refused by the policy. Nothing is recorded or called; the test is offline and deterministic.
"""
import json
import re
from collections import Counter
from dataclasses import replace

import pytest

from conftest import text_turn, tool_turn
from support_desk.desk import DeskService
from support_desk.observe import WAITING
from support_desk.settings import load_settings
from support_desk.tools import load_orders

GOLDEN = json.loads(load_settings().orders_file.read_text(encoding="utf-8"))  # the course's data: orders and attacks
ORDERS = load_orders(load_settings().orders_file)
ATTACKS = GOLDEN["injection"]


def attack_call(case: dict) -> tuple[str, float]:
    """The refund the attack asks for: the full total of the order its text names (lesson 30's attack_call)."""
    order_id = re.search(r"\b(10(0[1-9]|1[0-2]))\b", case["request"]).group(1)
    return order_id, ORDERS[order_id]["total"]


@pytest.fixture
def desk(tmp_path):
    return DeskService(replace(load_settings(), state_dir=tmp_path))


def test_the_attack_set_has_twenty_cases():
    assert len(ATTACKS) == 20


def test_no_injected_refund_is_paid_and_each_is_held_or_refused(desk, scripted):
    outcomes = Counter()
    for n, case in enumerate(ATTACKS):
        order_id, total = attack_call(case)
        scripted(tool_turn("refund_order", {"order_id": order_id, "amount_usd": total}, call_id=f"c{n}"),
                 text_turn("I cannot approve that from a message."))
        run = desk.start("C-88", f"attack-{case['id']}", case["request"])
        if run.status == WAITING:
            assert ORDERS[order_id]["status"] == "lost", f"{case['id']}: only a lost order may wait for a person"
            outcomes["held for a person"] += 1
        else:
            assert run.calls[0]["result"]["error"].startswith("policy:"), case["id"]
            outcomes["refused by policy"] += 1
    paid = desk._db.execute("SELECT COUNT(*) FROM refunds").fetchone()[0]
    assert paid == 0, "an injected refund was paid"
    assert outcomes == Counter({"held for a person": 4, "refused by policy": 16})  # the lost orders: 1003, 1007, 1011


def test_the_summary_counts_every_refusal_in_the_trace(desk, scripted):
    for n, case in enumerate(ATTACKS):
        order_id, total = attack_call(case)
        scripted(tool_turn("refund_order", {"order_id": order_id, "amount_usd": total}, call_id=f"c{n}"),
                 text_turn("No."))
        desk.start("C-88", f"count-{case['id']}", case["request"])
    rows = desk.tasks()["tasks"]
    assert sum(r["refused"] for r in rows) == 16
    assert desk.tasks()["summary"]["tickets"] == 20


def test_the_trace_never_holds_an_attack_text(desk, scripted):
    for n, case in enumerate(ATTACKS[:5]):
        order_id, total = attack_call(case)
        scripted(tool_turn("refund_order", {"order_id": order_id, "amount_usd": total}, call_id=f"c{n}"), text_turn("No."))
        desk.start("C-88", f"text-{case['id']}", case["request"])
    written = desk.trace_file.read_text(encoding="utf-8")
    assert written.strip(), "the desk wrote no spans"
    for case in ATTACKS[:5]:
        assert case["request"] not in written
    assert "@" not in written

"""Step 2: the policy search, the guarded memory and the refund ledger, tested directly. No model call here."""
import sqlite3

from support_desk.ledger import RefundLedger
from support_desk.memory import CustomerMemory, luhn_ok, never_store
from support_desk.policy import PolicyIndex, cited_ids
from support_desk.settings import load_settings
from support_desk.tools import load_orders

CARD = "4" + "0" * 14 + "2"  # made up: the digits pass the card checksum, so the guard must refuse it


def test_policy_search_shows_numbered_passages_with_cite_ids():
    index = PolicyIndex.from_file(load_settings().policy_file)
    result = index.search("refund")
    assert sorted(cited_ids(result)) == [27, 31]  # the two passages lesson 23's answer cites
    assert all(p["cite"].startswith("policy-") for p in result["passages"])


def test_policy_search_refuses_an_empty_query():
    index = PolicyIndex.from_file(load_settings().policy_file)
    assert "error" in index.search("?!")


def test_luhn_checks_the_card_digits():
    assert luhn_ok("79927398713")          # the standard example number
    assert not luhn_ok("79927398714")


def test_guard_refuses_a_card_and_a_password_but_not_an_ordinary_fact():
    assert never_store(f"Card {CARD} was charged twice") == "payment card number"
    assert never_store("my password is kept by the bank") == "password or PIN"
    assert never_store("Prefers replies by email") is None


def test_memory_refuses_a_card_before_it_is_saved():
    memory = CustomerMemory(sqlite3.connect(":memory:"))
    assert memory.remember("C-88", "payment", f"Card {CARD} was charged twice", "test") == "blocked: payment card number"
    assert memory.facts_for("C-88") == []


def test_a_new_fact_on_the_same_topic_replaces_the_old_one():
    memory = CustomerMemory(sqlite3.connect(":memory:"))
    memory.remember("C-88", "contact", "Prefers phone calls", "test")
    memory.remember("C-88", "contact", "Prefers replies by email", "test")
    assert memory.facts_for("C-88") == ["Prefers replies by email"]


def test_erasure_removes_every_row_of_one_customer():
    memory = CustomerMemory(sqlite3.connect(":memory:"))
    memory.remember("C-88", "contact", "Prefers replies by email", "test")
    memory.remember("C-99", "contact", "Prefers phone calls", "test")
    assert memory.forget_customer("C-88") == 1
    assert memory.facts_for("C-88") == [] and memory.facts_for("C-99") == ["Prefers phone calls"]


def test_ledger_pays_an_order_once(tmp_path):
    orders = load_orders(load_settings().orders_file)
    ledger = RefundLedger(sqlite3.connect(tmp_path / "ledger.sqlite"), orders)
    first = ledger.pay("1007", 210.0, "senior-lead")
    second = ledger.pay("1007", 210.0, "senior-lead")
    assert first == {"status": "refunded", "amount_usd": 210.0, "approved_by": "senior-lead"}
    assert second == {"status": "already paid", "amount_usd": 210.0}


def test_ledger_survives_a_restart(tmp_path):
    orders = load_orders(load_settings().orders_file)
    path = tmp_path / "ledger.sqlite"
    RefundLedger(sqlite3.connect(path), orders).pay("1007", 210.0, "senior-lead")
    again = RefundLedger(sqlite3.connect(path), orders)  # a new connection: what a restart looks like
    assert again.pay("1007", 210.0, "senior-lead")["status"] == "already paid"


def test_ledger_refuses_an_unknown_order_and_more_than_the_total(tmp_path):
    orders = load_orders(load_settings().orders_file)
    ledger = RefundLedger(sqlite3.connect(tmp_path / "ledger.sqlite"), orders)
    assert "error" in ledger.pay("9999", 10.0, "senior-lead")
    assert "error" in ledger.pay("1007", 999.0, "senior-lead")

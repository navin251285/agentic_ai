"""Step 2: retries with backoff, one idempotency key per refund, the checker, and the maker's proposal.

The model call replays the recording made by lesson 13 (tests/cassettes/step2_refund_proposal.yaml): one call,
the model asks for issue_refund on BS-1042 for 120 USD. The payment service is the local stand-in with a ledger.
"""
import contextlib

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from tenacity import wait_none

import llm_replay
from brightside_desk.api import create_app
from brightside_desk.desk import Caps, run_desk
from brightside_desk.refunds import (PaymentService, check_refund, pay_with_retry, refund_key,
                                     review_and_pay)
from brightside_desk.tools import propose_refund

REQUEST = "Customer C-17 says the trail jacket from order BS-1042 arrived torn after one wash. Order BS-1042 paid 120 USD."


@pytest.fixture
def ledger(tmp_path):
    return tmp_path / "ledger.db"


@pytest.fixture
def client(ledger):
    with TestClient(create_app(ledger_path=ledger)) as c:
        yield c


@contextlib.contextmanager
def recorded(name):
    """Replay the model calls recorded under this name (tests/cassettes/<name>.yaml)."""
    llm_replay.start(name)
    try:
        yield
    finally:
        llm_replay.stop()


def test_page_has_the_refund_controls(client):
    page = client.get("/")
    assert page.status_code == 200
    assert "payment_faults" in page.text


def test_retries_only_transient_errors_and_keep_one_key(ledger):
    svc = PaymentService(ledger, script=["503", "503", "lost_reply"])
    text, tries = pay_with_retry(svc, "BS-1042", 120.0, refund_key("BS-1042", 120.0), wait=wait_none())
    assert tries == 4  # 503, 503, written with the reply lost, then the same key finds the first result
    assert text == "already refunded 120.0 on BS-1042"
    assert svc.refunds_written("BS-1042") == 1
    assert svc.refunded_total("BS-1042") == 120.0
    svc.close()


class Refused(ValueError):
    pass


class AlwaysRefuses:
    calls = 0

    def refund(self, order_id, amount_usd, key):
        self.calls += 1
        raise Refused("over the amount paid")


def test_a_refusal_is_not_retried():
    service = AlwaysRefuses()
    with pytest.raises(Refused):
        pay_with_retry(service, "BS-1042", 500.0, refund_key("BS-1042", 500.0), wait=wait_none())
    assert service.calls == 1  # only TransientPaymentError is retried


def test_retries_stop_after_four_tries_and_write_nothing(ledger):
    svc = PaymentService(ledger, script=["503"] * 4)
    outcome = review_and_pay("BS-1042", 120.0, svc, wait=wait_none())
    assert outcome.approved and outcome.result is None
    assert outcome.tries == 4
    assert "did not confirm after 4 tries" in outcome.reason
    assert svc.refunds_written("BS-1042") == 0
    svc.close()


@pytest.mark.parametrize("order_id, amount, refunded, approved", [
    ("BS-1042", 120.0, 0.0, True),
    ("BS-1042", 60.0, 70.0, False),   # 50 still refundable
    ("BS-1042", 150.0, 0.0, False),   # more than was paid
    ("BS-9999", 10.0, 0.0, False),    # no such order
    ("BS-1042", 0.0, 0.0, False),     # nothing to refund
])
def test_checker_keeps_refunds_within_what_was_paid(order_id, amount, refunded, approved):
    assert check_refund(order_id, amount, refunded).approved is approved


def test_idempotency_key_comes_from_the_case():
    assert refund_key("BS-1042", 120) == refund_key("BS-1042", 120.0)  # same on every try and restart
    assert refund_key("BS-1042", 120) != refund_key("BS-1042", 60)


def test_bad_refund_arguments_come_back_as_text_and_the_loop_goes_on():
    class Scripted:
        def __init__(self, replies):
            self.replies = list(replies)

        def invoke(self, messages):
            return self.replies.pop(0)

    bad = AIMessage(content="", tool_calls=[{"name": "issue_refund", "args": {"order_id": "42", "amount_usd": 5},
                                             "id": "c1", "type": "tool_call"}])
    done = AIMessage(content="I need a valid order id, such as BS-1042.")
    result = run_desk("refund order 42", Caps(max_turns=4), Scripted([bad, done]))
    assert result.stop == "answered"
    assert result.proposals == []
    assert result.steps[0].results[0][0] == "issue_refund"
    assert "order_id" in result.steps[0].results[0][1]


def test_maker_proposal_is_a_proposal_not_a_payment():
    message, proposal = propose_refund({"name": "issue_refund", "args": {"order_id": "BS-1042", "amount_usd": 120},
                                        "id": "c2"})
    assert proposal == {"order_id": "BS-1042", "amount_usd": 120.0}
    assert "checker decides" in message.content


def test_recorded_proposal_is_checked_and_paid_once(client, ledger):
    with recorded("step2_refund_proposal"):
        r = client.post("/api/chat", json={"message": REQUEST, "max_turns": 6})
    assert r.status_code == 200
    data = r.json()
    assert data["stop"] == "refund_proposed"
    assert data["answer"] is None
    assert data["proposals"] == [{"order_id": "BS-1042", "amount_usd": 120.0}]
    [refund] = data["refunds"]
    assert refund["approved"] is True
    assert refund["result"] == "refunded 120.0 on BS-1042"
    assert refund["tries"] == 1
    svc = PaymentService(ledger)
    assert svc.refunds_written("BS-1042") == 1
    svc.close()


def test_lost_reply_is_retried_and_a_second_ask_is_refused(client, ledger):
    with recorded("step2_refund_proposal"):
        first = client.post("/api/chat", json={"message": REQUEST, "max_turns": 6,
                                               "payment_faults": ["lost_reply"]}).json()
    [refund] = first["refunds"]
    assert refund["tries"] == 2  # written, reply lost; the retry finds the key and returns the first result
    assert refund["result"] == "already refunded 120.0 on BS-1042"

    with recorded("step2_refund_proposal"):
        second = client.post("/api/chat", json={"message": REQUEST, "max_turns": 6}).json()
    [again] = second["refunds"]
    assert again["approved"] is False  # the checker: nothing is still refundable on BS-1042
    assert again["tries"] == 0
    svc = PaymentService(ledger)
    assert svc.refunds_written("BS-1042") == 1
    svc.close()


def test_chat_rejects_unknown_payment_faults(client):
    r = client.post("/api/chat", json={"message": "hi", "payment_faults": ["timeout"]})
    assert r.status_code == 422

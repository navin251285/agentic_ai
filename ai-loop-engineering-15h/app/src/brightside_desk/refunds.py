"""Refunds after a proposal: a checker decides, then the payment service pays once, with retries (lessons 13 and 14).

The model only proposes (the maker). `check_refund` is the checker: plain Python that sees the order record and the
proposal, never the model's reasoning. An approved refund is paid by `pay_with_retry`: transient errors are retried
with exponential backoff and jitter, and every try sends the same idempotency key, built from the case, so the
ledger's unique key column turns a repeat into "already refunded" instead of a second payment.

The payment service is a stand-in: a SQLite ledger. Its `script` makes a 503 or a lost reply on the next calls, so
the retry path can be shown and tested offline. The real provider is not called anywhere in this app.
"""
from __future__ import annotations

import logging
import sqlite3
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from tenacity import (Retrying, RetryCallState, retry_if_exception_type, stop_after_attempt,
                      wait_exponential_jitter)
from tenacity.wait import wait_base

from .tools import ORDERS

log = logging.getLogger(__name__)

MAX_TRIES = 4  # lesson 13: one first try and three retries for a transient error


class TransientPaymentError(Exception):
    """A 503 or a lost reply: the same call may work if it is tried again."""


@dataclass(frozen=True)
class Verdict:
    approved: bool
    reason: str


@dataclass(frozen=True)
class RefundOutcome:
    order_id: str
    amount_usd: float
    approved: bool
    reason: str
    result: str | None  # what the payment service said, or None when it never confirmed
    tries: int          # payment calls made; 0 when the checker refused

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PaymentService:
    """The refund API stand-in. The unique `key` column is what makes a repeated refund a no-op."""

    def __init__(self, path: str | Path = ":memory:", script: Sequence[str] = ()) -> None:
        self.script = list(script)  # per call: "503", "lost_reply", or anything else for a normal refund
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        with self.db:
            self.db.execute("create table if not exists refunds (id integer primary key, key text unique, "
                            "order_id text not null, amount_usd real not null)")

    def close(self) -> None:
        self.db.close()

    def refund(self, order_id: str, amount_usd: float, key: str) -> str:
        step = self.script.pop(0) if self.script else "ok"
        if step == "503":
            raise TransientPaymentError("503 unavailable: nothing was written")
        with self.db:  # committed before the reply can be lost; a repeated key writes nothing
            cur = self.db.execute("insert or ignore into refunds (key, order_id, amount_usd) values (?, ?, ?)",
                                  (key, order_id, amount_usd))
        if cur.rowcount == 0:  # the key is already in the ledger: return the first result
            stored = self.db.execute("select amount_usd from refunds where key = ?", (key,)).fetchone()
            return f"already refunded {stored[0]} on {order_id}"
        if step == "lost_reply":
            raise TransientPaymentError("read timeout: the write happened, the reply did not arrive")
        return f"refunded {amount_usd} on {order_id}"

    def refunded_total(self, order_id: str) -> float:
        row = self.db.execute("select coalesce(sum(amount_usd), 0) from refunds where order_id = ?",
                              (order_id,)).fetchone()
        return float(row[0])

    def refunds_written(self, order_id: str) -> int:
        row = self.db.execute("select count(*) from refunds where order_id = ?", (order_id,)).fetchone()
        return int(row[0])


def refund_key(order_id: str, amount_usd: float) -> str:
    """The idempotency key comes from the case, never from a random number: a restart builds the same key."""
    return f"refund:{order_id}:{amount_usd:.2f}"


def check_refund(order_id: str, amount_usd: float, refunded_so_far: float = 0.0) -> Verdict:
    """The checker: the order must exist, and the refunds must stay within what was paid."""
    order = ORDERS.get(order_id)
    if order is None:
        return Verdict(False, f"no order {order_id}")
    if amount_usd <= 0:
        return Verdict(False, "the amount must be more than 0")
    paid = float(order["paid_usd"])
    left = round(paid - refunded_so_far, 2)
    if round(amount_usd, 2) > left:
        return Verdict(False, f"{amount_usd} is more than the {left} still refundable on {order_id} (paid {paid})")
    return Verdict(True, f"within the {left} still refundable on {order_id}")


def _announce(state: RetryCallState) -> None:
    """Called by tenacity before each wait: the try that failed and how long the wait is."""
    log.warning("payment try %d failed (%s); waiting %.2f s", state.attempt_number,
                state.outcome.exception(), state.next_action.sleep)


def pay_with_retry(svc: PaymentService, order_id: str, amount_usd: float, key: str,
                   wait: wait_base | None = None) -> tuple[str, int]:
    """Retry only transient errors, with the same key on every try. Returns the result and the number of tries."""
    retrying = Retrying(retry=retry_if_exception_type(TransientPaymentError),
                        stop=stop_after_attempt(MAX_TRIES),
                        wait=wait if wait is not None else wait_exponential_jitter(initial=0.2, max=2, jitter=0.2),
                        before_sleep=_announce, reraise=True)
    text = retrying(svc.refund, order_id, amount_usd, key)
    return text, int(retrying.statistics["attempt_number"])


def review_and_pay(order_id: str, amount_usd: float, svc: PaymentService,
                   wait: wait_base | None = None) -> RefundOutcome:
    """One proposal, end to end: the checker first, then the paid write with its retries."""
    verdict = check_refund(order_id, amount_usd, svc.refunded_total(order_id))
    if not verdict.approved:
        log.info("checker refused a refund on %s: %s", order_id, verdict.reason)
        return RefundOutcome(order_id, amount_usd, False, verdict.reason, None, 0)
    try:
        text, tries = pay_with_retry(svc, order_id, amount_usd, refund_key(order_id, amount_usd), wait)
    except TransientPaymentError as exc:
        reason = (f"the payment service did not confirm after {MAX_TRIES} tries ({exc}). The key is saved, "
                  "so a later retry with the same key cannot pay twice.")
        return RefundOutcome(order_id, amount_usd, True, reason, None, MAX_TRIES)
    return RefundOutcome(order_id, amount_usd, True, verdict.reason, text, tries)


def decide_refunds(proposals: Sequence[dict[str, Any]], ledger_path: str | Path,
                   faults: Sequence[str] = (), wait: wait_base | None = None) -> list[dict[str, Any]]:
    """Run the checker and the payment for each proposal, in order, on one ledger."""
    svc = PaymentService(ledger_path, script=faults)
    try:
        return [review_and_pay(p["order_id"], float(p["amount_usd"]), svc, wait).to_dict() for p in proposals]
    finally:
        svc.close()

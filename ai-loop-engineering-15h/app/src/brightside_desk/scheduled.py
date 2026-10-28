"""Scheduled runs: a heartbeat adds the inbox's tickets, a worker claims one with a lease, and the desk runs it in its
own worktree under the run's grant list. A refund over the limit waits at the approval gate (lessons 20 to 24).

The flow for one claimed ticket:
    worktree and branch from main -> desk loop (grant list, caps) -> checker -> case file committed on the branch
    -> small refunds: merge, pay, done | larger refunds: park at the gate, the lease covers the review window
    -> a reviewer answers: approve (lease still held, amount echoed) merges and pays once; reject keeps the branch
    -> an answer after the window is refused, and the task goes back to the queue.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from .desk import Caps, RunResult, run_desk
from .permissions import SCHEDULED_RUN, granted_tools, permit
from .refunds import PaymentService, RefundOutcome, check_refund, review_and_pay
from .taskqueue import (DONE, FAILED, PAID, REJECTED, WAITING, Claim, claim, finish, get_task, heartbeat,
                        open_queue, park, requeue, set_status, transaction)
from .workspace import DeskRepo

log = logging.getLogger(__name__)

# The inbox: tickets the heartbeat finds. The one ticket is the lesson 13 request, so its recording replays.
INBOX: dict[str, str] = {
    "TK-2201": "Customer C-17 says the trail jacket from order BS-1042 arrived torn after one wash. "
               "Order BS-1042 paid 120 USD.",
}
SCHEDULED_CAPS = Caps(max_turns=4, max_usd=0.05)  # unattended: a turn cap and a dollar cap (lesson 05)
WORKER = "worker-1"                                # one worker per process; its claims carry this owner
MAX_CLAIMS_PER_TICK = 20                           # a bound on one tick, so a bad queue cannot loop forever


class ApprovalError(Exception):
    """Base for a refused decision. The API maps each subclass to a status code."""


class UnknownTask(ApprovalError):
    pass


class NotWaiting(ApprovalError):
    pass


class AmountMismatch(ApprovalError):
    pass


class ScheduledDesk:
    def __init__(self, *, state_dir: Path, ledger_path: Path, clock: Callable[[], float],
                 make_model: Callable[[list[str]], Any], limit_usd: float, lease_s: float, window_s: float,
                 inbox: Mapping[str, str] = INBOX) -> None:
        self.db_path = state_dir / "queue.db"
        self.worktrees = state_dir / "worktrees"
        self.repo = DeskRepo(state_dir / "desk-repo")
        self.ledger_path = ledger_path
        self.clock = clock
        self.make_model = make_model
        self.limit_usd = limit_usd
        self.lease_s = lease_s
        self.window_s = window_s
        self.inbox = dict(inbox)
        self._lock = threading.Lock()  # one tick or decision at a time in this process

    # ---- the heartbeat and the worker -------------------------------------------------------------------------
    def tick(self) -> dict[str, Any]:
        """The scheduled tick: add the inbox's tickets once, then run every claimable task."""
        with self._lock:
            model = self.make_model(granted_tools(SCHEDULED_RUN))  # a missing key fails here, before any claim
            db = open_queue(self.db_path)
            try:
                added = heartbeat(db, self.inbox.keys())
                runs = []
                for _ in range(MAX_CLAIMS_PER_TICK):
                    got = claim(db, WORKER, self.clock(), self.lease_s)
                    if got is None:
                        break
                    runs.append(self._run(db, got, model))
            finally:
                db.close()
        return {"added": added, "runs": runs}

    def _run(self, db: sqlite3.Connection, got: Claim, model: Any) -> dict[str, Any]:
        branch = f"run/{got.ticket}-a{got.attempt}"
        folder = self.worktrees / f"{got.ticket}-a{got.attempt}"
        self.repo.add_run(branch, folder)  # one worktree and one branch per run (lesson 21)
        summary = {"ticket": got.ticket, "attempt": got.attempt, "branch": branch}
        try:
            result = run_desk(self.inbox[got.ticket], SCHEDULED_CAPS, model,
                              allowed=lambda name: permit(SCHEDULED_RUN, name))
        except Exception:
            log.exception("scheduled run %s failed", got.ticket)
            finish(db, got, self.clock(), FAILED, "the model call failed; the server log has the details")
            self.repo.remove_run(folder, branch, keep_branch=False)
            return {**summary, "status": FAILED}
        return self._decide_run(db, got, result, folder, branch, summary)

    def _decide_run(self, db: sqlite3.Connection, got: Claim, result: RunResult, folder: Path, branch: str,
                    summary: dict[str, Any]) -> dict[str, Any]:
        now = self.clock()
        if not result.proposals:  # nothing to decide: the branch has no commit, so it is dropped
            finish(db, got, now, DONE, f"no refund proposed (stop: {result.stop})")
            self.repo.remove_run(folder, branch, keep_branch=False)
            return {**summary, "status": DONE, "stop": result.stop}

        verdicts = self._check(result.proposals)
        refused = next((v for v in verdicts if not v.approved), None)
        if refused is not None:  # a red run: nothing goes to review
            finish(db, got, now, DONE, f"checker refused: {refused.reason}")
            self.repo.remove_run(folder, branch, keep_branch=False)
            return {**summary, "status": DONE, "checker": refused.reason}

        record = {"ticket": got.ticket, "run": SCHEDULED_RUN, "stop": result.stop,
                  "proposals": result.proposals, "checker": [v.reason for v in verdicts]}
        self.repo.commit_case(folder, got.ticket, record)  # green: the run's work is one commit on its branch

        if max(p["amount_usd"] for p in result.proposals) <= self.limit_usd:  # small refunds skip the gate (lesson 22)
            self.repo.remove_run(folder, branch, keep_branch=True)
            self.repo.merge(branch)
            paid = self._pay(result.proposals)
            status = PAID if all(o["result"] is not None for o in paid) else DONE
            finish(db, got, self.clock(), status, _reason(paid))
            return {**summary, "status": status, "paid": paid}

        if not park(db, got, now, self.window_s, json.dumps(result.proposals), branch):
            self.repo.remove_run(folder, branch, keep_branch=True)  # cannot happen in one process; kept visible
            return {**summary, "status": "lease lost"}
        self.repo.remove_run(folder, branch, keep_branch=True)  # the record stays on the branch for the reviewer
        return {**summary, "status": WAITING, "window_ends": now + self.window_s}

    # ---- the checker and the paid write -----------------------------------------------------------------------
    def _check(self, proposals: list[dict[str, Any]]) -> list[Any]:
        """The checker on every proposal, in order, counting earlier proposals of this run against the paid amount."""
        svc = PaymentService(self.ledger_path)
        try:
            planned: dict[str, float] = {}
            verdicts = []
            for p in proposals:
                order = p["order_id"]
                so_far = svc.refunded_total(order) + planned.get(order, 0.0)
                verdict = check_refund(order, float(p["amount_usd"]), so_far)
                if verdict.approved:
                    planned[order] = planned.get(order, 0.0) + float(p["amount_usd"])
                verdicts.append(verdict)
            return verdicts
        finally:
            svc.close()

    def _pay(self, proposals: list[dict[str, Any]]) -> list[dict[str, Any]]:
        svc = PaymentService(self.ledger_path)
        try:
            outcomes: list[RefundOutcome] = [review_and_pay(p["order_id"], float(p["amount_usd"]), svc)
                                             for p in proposals]
        finally:
            svc.close()
        return [o.to_dict() for o in outcomes]

    # ---- the approval gate ------------------------------------------------------------------------------------
    def approvals(self) -> list[dict[str, Any]]:
        """Runs waiting for a person: what they propose, the window, and the diff the reviewer reads."""
        db = open_queue(self.db_path)
        try:
            rows = db.execute("select * from tasks where status = ? order by ticket", (WAITING,)).fetchall()
        finally:
            db.close()
        out = []
        for row in rows:
            proposals = json.loads(row["proposals"])
            out.append({"ticket": row["ticket"], "attempt": row["attempt"], "proposals": proposals,
                        "total_usd": _total(proposals), "window_ends": row["lease_until"],
                        "diff": self.repo.review_text(row["branch"], row["ticket"])})
        return out

    def tasks(self) -> list[dict[str, Any]]:
        db = open_queue(self.db_path)
        try:
            return [dict(r) for r in db.execute("select ticket, status, owner, attempt, reason from tasks "
                                                "order by ticket").fetchall()]
        finally:
            db.close()

    def decide(self, ticket: str, decision: str, amount_usd: float | None) -> dict[str, Any]:
        """A reviewer's answer. Approve must echo the total shown; the lease is checked in the same transaction
        as the merge, so an answer after the window is refused and the task goes back to the queue."""
        with self._lock:
            db = open_queue(self.db_path)
            try:
                with transaction(db):
                    row = get_task(db, ticket)
                    if row is None:
                        raise UnknownTask(ticket)
                    if row["status"] != WAITING:
                        raise NotWaiting(f"{ticket} is {row['status']}, not waiting for a decision")
                    now = self.clock()
                    if row["lease_until"] < now:
                        requeue(db, ticket, "review window closed: the task went back to the queue")
                        return {"ticket": ticket, "outcome": "refused",
                                "reason": "review window closed: the task went back to the queue"}
                    proposals = json.loads(row["proposals"])
                    total = _total(proposals)
                    if decision == "reject":
                        set_status(db, ticket, REJECTED, "rejected by the reviewer; the branch is kept")
                        return {"ticket": ticket, "outcome": REJECTED, "reason": "rejected by the reviewer"}
                    if amount_usd is None or round(amount_usd, 2) != total:
                        raise AmountMismatch(f"approve by echoing the amount shown: {total} USD")
                    self.repo.merge(row["branch"])  # inside the transaction: the lease was checked just above
                    paid = self._pay(proposals)
                    status = PAID if all(o["result"] is not None for o in paid) else DONE
                    set_status(db, ticket, status, _reason(paid))
                    return {"ticket": ticket, "outcome": status, "reason": _reason(paid), "paid": paid}
            finally:
                db.close()


class Ticker:
    """Calls desk.tick() every `seconds` on a daemon thread. Off when seconds is 0: call POST /api/tick instead."""

    def __init__(self, desk: ScheduledDesk, seconds: float) -> None:
        self.desk = desk
        self.seconds = seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self.seconds <= 0:
            return
        self._thread = threading.Thread(target=self._loop, name="desk-ticker", daemon=True)
        self._thread.start()
        log.info("scheduled ticks every %.0f s", self.seconds)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        while not self._stop.wait(self.seconds):
            try:
                self.desk.tick()
            except Exception:
                log.exception("scheduled tick failed")


def _total(proposals: list[dict[str, Any]]) -> float:
    return round(sum(float(p["amount_usd"]) for p in proposals), 2)


def _reason(paid: list[dict[str, Any]]) -> str:
    return "; ".join(o["result"] or o["reason"] for o in paid) or "nothing paid"

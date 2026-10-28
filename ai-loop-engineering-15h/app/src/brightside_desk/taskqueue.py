"""The task queue for scheduled runs: one row per ticket, a lease per claim, and fenced writes (lessons 20 and 22).

A heartbeat adds a ticket once (its key is the ticket id). A worker claims a task in one write transaction, which
sets an owner, an attempt number and an expiry. A parked run (waiting for a reviewer) keeps its lease for the review
window. Every later write checks the owner, the attempt and the lease in the same transaction, so a worker whose
lease has lapsed cannot write after another worker took the task over.

The database is a SQLite file. Each call opens its own connection, so a restarted process reads the same state.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

OPEN, LEASED, WAITING, PAID, DONE, REJECTED, FAILED = (
    "open", "leased", "waiting", "paid", "done", "rejected", "failed")
TERMINAL = (PAID, DONE, REJECTED, FAILED)

SCHEMA = """
create table if not exists tasks (
    ticket text primary key,
    status text not null default 'open',
    owner text,
    attempt integer not null default 0,
    lease_until real not null default 0,
    branch text,
    proposals text,
    reason text
)
"""


@dataclass(frozen=True)
class Claim:
    ticket: str
    owner: str
    attempt: int


def open_queue(path: Path) -> sqlite3.Connection:
    """Open the queue file. Autocommit: each write sets its own transaction with `transaction`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), isolation_level=None, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute(SCHEMA)
    return db


@contextmanager
def transaction(db: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """A write transaction. `begin immediate` takes the write lock before any read, so two workers cannot read
    the same open task. An exception rolls the whole transaction back."""
    db.execute("begin immediate")
    try:
        yield db
    except BaseException:
        db.execute("rollback")
        raise
    db.execute("commit")


def heartbeat(db: sqlite3.Connection, tickets: Iterable[str]) -> int:
    """The scheduled tick: add each ticket that is not a task yet. Returns how many were added."""
    with transaction(db):
        return sum(db.execute("insert or ignore into tasks (ticket) values (?)", (t,)).rowcount for t in tickets)


def claim(db: sqlite3.Connection, owner: str, now: float, lease_s: float) -> Claim | None:
    """Take the first open task, or one whose lease has lapsed. The attempt number goes up by one."""
    with transaction(db):
        row = db.execute(
            "select ticket from tasks where status = ? or (status in (?, ?) and lease_until < ?) "
            "order by ticket limit 1", (OPEN, LEASED, WAITING, now)).fetchone()
        if row is None:
            return None
        db.execute("update tasks set status = ?, owner = ?, lease_until = ?, attempt = attempt + 1 where ticket = ?",
                   (LEASED, owner, now + lease_s, row["ticket"]))
        attempt = db.execute("select attempt from tasks where ticket = ?", (row["ticket"],)).fetchone()["attempt"]
    return Claim(row["ticket"], owner, attempt)


def holds(db: sqlite3.Connection, claim: Claim, now: float, status: str) -> bool:
    """True while this claim still owns the task in that status: same owner, same attempt, lease not lapsed."""
    return db.execute("select 1 from tasks where ticket = ? and owner = ? and attempt = ? and status = ? "
                      "and lease_until >= ?", (claim.ticket, claim.owner, claim.attempt, status, now)).fetchone() is not None


def park(db: sqlite3.Connection, claim: Claim, now: float, window_s: float, proposals: str, branch: str) -> bool:
    """Park a leased run at the approval gate. The lease now covers the review window. False if the lease was lost."""
    with transaction(db):
        if not holds(db, claim, now, LEASED):
            return False
        db.execute("update tasks set status = ?, lease_until = ?, proposals = ?, branch = ? where ticket = ?",
                   (WAITING, now + window_s, proposals, branch, claim.ticket))
    return True


def finish(db: sqlite3.Connection, claim: Claim, now: float, status: str, reason: str) -> bool:
    """Close a leased task with a final status. False (and no change) if the lease was lost."""
    with transaction(db):
        if not holds(db, claim, now, LEASED):
            return False
        db.execute("update tasks set status = ?, reason = ? where ticket = ?", (status, reason, claim.ticket))
    return True


def get_task(db: sqlite3.Connection, ticket: str) -> sqlite3.Row | None:
    return db.execute("select * from tasks where ticket = ?", (ticket,)).fetchone()


def set_status(db: sqlite3.Connection, ticket: str, status: str, reason: str) -> None:
    """Set a status inside a transaction the caller holds (approval decisions)."""
    db.execute("update tasks set status = ?, reason = ? where ticket = ?", (status, reason, ticket))


def requeue(db: sqlite3.Connection, ticket: str, reason: str) -> None:
    """The lease lapsed before a decision: the task goes back to the queue, and the next claim is a new attempt."""
    db.execute("update tasks set status = ?, owner = null, reason = ? where ticket = ?", (OPEN, reason, ticket))

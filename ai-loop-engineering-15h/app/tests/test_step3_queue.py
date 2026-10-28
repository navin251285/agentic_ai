"""Step 3: the task queue (lesson 20), the grant list (lesson 23) and the grant check in the desk loop.

These tests make no model call. The queue is plain SQLite and the clock is a number the test passes in.
"""
from langchain_core.messages import AIMessage

from brightside_desk.desk import Caps, run_desk
from brightside_desk.permissions import CHAT_RUN, SCHEDULED_RUN, granted_tools, permit
from brightside_desk.taskqueue import (LEASED, OPEN, WAITING, claim, finish, get_task, heartbeat, open_queue,
                                       park)


def test_heartbeat_adds_each_ticket_once(tmp_path):
    db = open_queue(tmp_path / "queue.db")
    assert heartbeat(db, ["TK-1", "TK-2"]) == 2
    assert heartbeat(db, ["TK-1", "TK-2"]) == 0  # the same tick again adds nothing
    assert db.execute("select count(*) from tasks").fetchone()[0] == 2
    db.close()


def test_a_claim_gives_one_owner_and_an_attempt(tmp_path):
    db = open_queue(tmp_path / "queue.db")
    heartbeat(db, ["TK-1", "TK-2"])
    a = claim(db, "worker-a", now=0, lease_s=90)
    b = claim(db, "worker-b", now=0, lease_s=90)
    assert (a.ticket, a.owner, a.attempt) == ("TK-1", "worker-a", 1)
    assert (b.ticket, b.owner, b.attempt) == ("TK-2", "worker-b", 1)
    assert claim(db, "worker-c", now=0, lease_s=90) is None  # nothing open is left for a third worker
    db.close()


def test_a_lapsed_lease_is_taken_over_and_the_zombie_is_refused(tmp_path):
    db = open_queue(tmp_path / "queue.db")
    heartbeat(db, ["TK-1"])
    zombie = claim(db, "worker-a", now=0, lease_s=90)  # worker A stops renewing
    new = claim(db, "worker-b", now=100, lease_s=90)   # its lease ended at t=90
    assert new is not None and new.attempt == 2
    assert finish(db, zombie, now=102, status="done", reason="late write") is False  # refused: not its lease
    assert finish(db, new, now=103, status="done", reason="the new owner's write") is True
    assert get_task(db, "TK-1")["reason"] == "the new owner's write"
    db.close()


def test_a_parked_run_keeps_its_lease_for_the_review_window(tmp_path):
    db = open_queue(tmp_path / "queue.db")
    heartbeat(db, ["TK-1"])
    got = claim(db, "worker-a", now=0, lease_s=90)
    assert park(db, got, now=10, window_s=3600, proposals="[]", branch="run/TK-1-a1") is True
    row = get_task(db, "TK-1")
    assert row["status"] == WAITING and row["lease_until"] == 3610
    assert claim(db, "worker-b", now=3000, lease_s=90) is None  # still inside the window: nobody takes it
    assert claim(db, "worker-b", now=3700, lease_s=90).attempt == 2  # after the window: back in the queue
    db.close()


def test_a_second_worker_cannot_claim_a_leased_task(tmp_path):
    db = open_queue(tmp_path / "queue.db")
    heartbeat(db, ["TK-1"])
    claim(db, "worker-a", now=0, lease_s=90)
    assert get_task(db, "TK-1")["status"] == LEASED
    assert get_task(db, "TK-1")["status"] != OPEN
    db.close()


def test_grants_allow_the_listed_tools_and_fail_closed():
    assert permit(SCHEDULED_RUN, "get_order") == (True, "granted")
    assert permit(SCHEDULED_RUN, "issue_refund")[0] is True  # it may propose a refund; the gate pays
    assert permit(SCHEDULED_RUN, "send_email")[0] is False   # not in the list: no such tool for this run
    assert permit("nobody", "get_order")[0] is False         # an unknown run gets nothing
    assert granted_tools(SCHEDULED_RUN) == ["calculator", "get_order", "issue_refund"]
    assert permit(CHAT_RUN, "issue_refund")[0] is True       # the chat keeps the step 2 tools


class Scripted:
    """Replies scripted in advance: a plumbing double for the loop, not a model. Used where no recording is needed."""

    def __init__(self, replies):
        self.replies = list(replies)

    def invoke(self, messages):
        return self.replies.pop(0)


def test_a_denied_tool_never_runs_and_the_model_reads_why():
    asks = AIMessage(content="", tool_calls=[{"name": "calculator", "args": {"expression": "2 + 2"},
                                              "id": "c1", "type": "tool_call"}])
    done = AIMessage(content="I cannot calculate that here.")
    denied_all = lambda name: (False, f"{name} is not granted to this run")  # noqa: E731
    result = run_desk("what is 2 + 2?", Caps(max_turns=4), Scripted([asks, done]), allowed=denied_all)
    assert result.stop == "answered"
    assert result.steps[0].results == [("calculator", "denied: calculator is not granted to this run")]

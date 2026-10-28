"""Step 3: a scheduled run from the heartbeat to the approval gate, with a git worktree per run (lessons 20 to 24).

Each test that starts a run replays the one model call of lesson 13 (tests/cassettes/step2_refund_proposal.yaml):
the model asks for issue_refund on BS-1042 for 120 USD. The refund is over the 50 USD limit, so it waits at the
gate. Each such test makes exactly one replayed call. The tests need git; without it they are skipped.
"""
import contextlib
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

import llm_replay
from brightside_desk.api import create_app
from brightside_desk.refunds import PaymentService

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed on this machine")
pytestmark = needs_git


class FakeClock:
    """A clock the test moves by hand: the lease and the review window are checked against it."""

    def __init__(self, now: float = 0.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


@contextlib.contextmanager
def recorded(name):
    llm_replay.start(name)
    try:
        yield
    finally:
        llm_replay.stop()


@pytest.fixture
def clock():
    return FakeClock(0.0)


@pytest.fixture
def paths(tmp_path):
    return {"ledger": tmp_path / "ledger.db", "state": tmp_path / "state"}


@pytest.fixture
def client(paths, clock):
    with TestClient(create_app(ledger_path=paths["ledger"], state_dir=paths["state"], clock=clock)) as c:
        yield c


def _main_has(paths, ticket):
    """True when the case file is on main (merged) rather than only on the run's branch."""
    return (paths["state"] / "desk-repo" / "cases" / f"{ticket}.json").exists()


def _branches(paths):
    out = subprocess.run(["git", "branch", "--format=%(refname:short)"], cwd=paths["state"] / "desk-repo",
                         capture_output=True, text=True, check=True).stdout
    return out.split()


def _tick_once(client):
    with recorded("step2_refund_proposal"):
        r = client.post("/api/tick")
    assert r.status_code == 200, r.text
    return r.json()


def test_page_has_the_approval_queue(client):
    page = client.get("/")
    assert page.status_code == 200
    assert "approvals" in page.text


def test_permissions_endpoint_lists_the_grants(client):
    grants = client.get("/api/permissions").json()
    assert grants["scheduled-desk"] == ["calculator", "get_order", "issue_refund"]


def test_tick_parks_the_large_refund_at_the_gate(client, paths):
    data = _tick_once(client)
    assert data["added"] == 1
    [run] = data["runs"]
    assert run["status"] == "waiting"
    assert run["branch"] == "run/TK-2201-a1"
    assert run["window_ends"] == 3600.0
    assert PaymentService(paths["ledger"]).refunds_written("BS-1042") == 0  # nothing paid yet
    assert not _main_has(paths, "TK-2201")  # the record is on the run's branch, not on main
    assert "run/TK-2201-a1" in _branches(paths)
    assert not (paths["state"] / "worktrees" / "TK-2201-a1").exists()  # the worktree folder is gone


def test_the_reviewer_sees_the_arguments_and_the_record(client):
    _tick_once(client)
    [pending] = client.get("/api/approvals").json()["approvals"]
    assert pending["ticket"] == "TK-2201"
    assert pending["total_usd"] == 120.0
    assert pending["proposals"] == [{"order_id": "BS-1042", "amount_usd": 120.0}]
    assert "cases/TK-2201.json" in pending["diff"]
    assert '"order_id": "BS-1042"' in pending["diff"]


def test_a_second_tick_adds_and_runs_nothing(client):
    _tick_once(client)
    again = client.post("/api/tick").json()  # no recording is open: any model call here would fail
    assert again == {"added": 0, "runs": []}


def test_approval_with_the_echoed_amount_merges_and_pays_once(client, paths):
    _tick_once(client)
    r = client.post("/api/approvals/TK-2201", json={"decision": "approve", "amount_usd": 120.0})
    assert r.status_code == 200, r.text
    assert r.json()["outcome"] == "paid"
    assert PaymentService(paths["ledger"]).refunds_written("BS-1042") == 1
    assert _main_has(paths, "TK-2201")  # the reviewed record reached main
    task = next(t for t in client.get("/api/tasks").json()["tasks"] if t["ticket"] == "TK-2201")
    assert task["status"] == "paid"
    again = client.post("/api/approvals/TK-2201", json={"decision": "approve", "amount_usd": 120.0})
    assert again.status_code == 409  # no longer waiting: a second approval cannot pay again


def test_a_different_amount_is_refused_and_nothing_moves(client, paths):
    _tick_once(client)
    r = client.post("/api/approvals/TK-2201", json={"decision": "approve", "amount_usd": 100.0})
    assert r.status_code == 409
    assert "120.0" in r.json()["detail"]
    assert PaymentService(paths["ledger"]).refunds_written("BS-1042") == 0
    assert [a["ticket"] for a in client.get("/api/approvals").json()["approvals"]] == ["TK-2201"]


def test_reject_keeps_the_branch_and_pays_nothing(client, paths):
    _tick_once(client)
    r = client.post("/api/approvals/TK-2201", json={"decision": "reject"})
    assert r.status_code == 200 and r.json()["outcome"] == "rejected"
    assert PaymentService(paths["ledger"]).refunds_written("BS-1042") == 0
    assert not _main_has(paths, "TK-2201")
    assert "run/TK-2201-a1" in _branches(paths)  # the record stays for the review


def test_an_answer_after_the_window_is_refused_and_the_task_is_requeued(client, paths, clock):
    _tick_once(client)
    clock.now = 3601.0  # the review window was one hour from t = 0
    r = client.post("/api/approvals/TK-2201", json={"decision": "approve", "amount_usd": 120.0})
    assert r.status_code == 409
    assert "back to the queue" in r.json()["detail"]
    assert PaymentService(paths["ledger"]).refunds_written("BS-1042") == 0
    assert not _main_has(paths, "TK-2201")
    task = next(t for t in client.get("/api/tasks").json()["tasks"] if t["ticket"] == "TK-2201")
    assert task["status"] == "open" and task["attempt"] == 1


def test_an_unknown_ticket_is_404(client):
    r = client.post("/api/approvals/TK-9999", json={"decision": "approve", "amount_usd": 1.0})
    assert r.status_code == 404

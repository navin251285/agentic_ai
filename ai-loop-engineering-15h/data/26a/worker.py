"""Refund worker for lesson 26a: claim a run's lease, then run its graph on the run's thread."""
import argparse, json, sqlite3, threading, time, uuid
from pathlib import Path
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver

LEASE_TTL_S, HEARTBEAT_S = 3.0, 1.0  # a lease expires this long after its last heartbeat

class Refund(TypedDict):
    run: str
    order_id: str
    amount_usd: float
    status: str

def connect(path):  # autocommit: each statement is its own transaction, unless we begin one
    db = sqlite3.connect(path, timeout=10, isolation_level=None, check_same_thread=False)
    db.execute("create table if not exists refunds (key text unique, order_id text, amount_usd real)")
    db.execute("create table if not exists leases (run text primary key, owner text, attempt integer, expires_at real)")
    return db
# Why begin immediate: it takes SQLite's write lock first, so two workers cannot both read a free
# lease and both claim it. The second worker waits, then sees the first worker's row.
def claim(db, run, owner):  # take the lease if it is free, expired or ours; return the attempt number or None
    db.execute("begin immediate")  # one writer at a time: the check and the write are one step
    row = db.execute("select owner, attempt, expires_at from leases where run = ?", (run,)).fetchone()
    now = time.time()
    if row and row[0] != owner and row[2] > now:
        db.execute("commit")
        return None
    attempt = row[1] + 1 if row else 1
    db.execute("insert or replace into leases values (?, ?, ?, ?)", (run, owner, attempt, now + LEASE_TTL_S))
    db.execute("commit")
    return attempt

def heartbeat(path, run, owner, stop):  # renews the lease while this worker lives; a killed worker stops
    db = connect(path)
    while not stop.wait(HEARTBEAT_S):
        db.execute("update leases set expires_at = ? where run = ? and owner = ?", (time.time() + LEASE_TTL_S, run, owner))

def build(folder, keyed=True, hang_s=0.0):
    ledger = folder / "ledger.db"
    def check(s):
        print("  check ran: policy re-check, no write", flush=True)
        return {"status": "checked"}
    def refund(s):
        key = f"{s['run']}:refund:{s['order_id']}" if keyed else str(uuid.uuid4())  # no key: every try is new
        db = connect(ledger)
        new = db.execute("insert or ignore into refunds values (?, ?, ?)", (key, s["order_id"], s["amount_usd"])).rowcount
        db.close()
        print("  refund ran:", "new row written" if new else "key already in the ledger, nothing written", flush=True)
        if hang_s:  # the drill: the row is committed, but the node has not returned, so no checkpoint for it
            print("WROTE the refund is in the ledger; the node has not returned", flush=True)
            time.sleep(hang_s)
        return {"status": "refunded"}
    g = StateGraph(Refund)
    g.add_node("check", check)
    g.add_node("refund", refund)
    g.add_node("done", lambda s: {"status": "done"})
    g.add_edge(START, "check"); g.add_edge("check", "refund"); g.add_edge("refund", "done"); g.add_edge("done", END)
    return g.compile(checkpointer=SqliteSaver(sqlite3.connect(folder / "checkpoints.db", check_same_thread=False)))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder"); ap.add_argument("owner"); ap.add_argument("run")
    ap.add_argument("--hang", type=float, default=0.0); ap.add_argument("--nokey", action="store_true")
    a = ap.parse_args()
    folder = Path(a.folder)
    attempt = claim(connect(folder / "ledger.db"), a.run, a.owner)
    if attempt is None:
        print(f"{a.owner}: the lease is held by another worker; exit"); return
    stop = threading.Event()
    threading.Thread(target=heartbeat, args=(folder / "ledger.db", a.run, a.owner, stop), daemon=True).start()
    print(f"{a.owner}: lease taken, attempt {attempt}", flush=True)
    proposal = json.loads((folder / "proposal.json").read_text())
    g = build(folder, keyed=not a.nokey, hang_s=a.hang)
    cfg = {"configurable": {"thread_id": a.run}, "recursion_limit": 10}
    start = {"run": a.run, "order_id": proposal["order_id"], "amount_usd": proposal["amount_usd"], "status": "new"}
    out = g.invoke(None if g.get_state(cfg).values else start, cfg, durability="sync")  # resume if a checkpoint exists
    stop.set()
    print(f"{a.owner}: finished with status {out['status']}", flush=True)

if __name__ == "__main__":
    main()

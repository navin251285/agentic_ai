"""Fleet worker for lesson 26b: a kill switch, a lease with expiry and a fenced write."""
import argparse, sqlite3, threading, time
from pathlib import Path

LEASE_TTL_S, HEARTBEAT_S = 2.0, 0.5  # lab settings: the lease lasts 4 heartbeats
PAUSE_S, MAX_ITERS = 0.2, 12         # one iteration = one provider call (or its 429) plus one check

class RateLimited(Exception):  # stands in for an HTTP 429 from the provider; the drill injects it
    pass

def connect(path):
    db = sqlite3.connect(path, timeout=10, isolation_level=None, check_same_thread=False)
    db.execute("pragma journal_mode = wal")  # several processes read and write the same file
    return db

def setup(db):
    db.executescript("""
        create table if not exists control (name text primary key, value integer);
        insert or ignore into control values ('stop_all', 0);
        create table if not exists runs (run text primary key, mode text, proposal_usd real, paid_usd real,
            status text default 'open', owner text, attempt integer default 0, expires_at real default 0,
            cancel integer default 0, iters integer default 0);
        create table if not exists ledger (key text primary key, run text, amount_usd real);""")

def stopped(db, run):  # the kill switch: the reason to stop, or None. Fail closed: an unreadable flag stops
    try:
        if db.execute("select value from control where name = 'stop_all'").fetchone()[0]:
            return "stopped"
        return "cancelled" if db.execute("select cancel from runs where run = ?", (run,)).fetchone()[0] else None
    except sqlite3.Error:
        return "stopped"

def claim(db, owner):  # take a free run, or one whose lease expired; the check and the take are one step
    db.execute("begin immediate")
    now = time.time()
    if db.execute("select value from control where name = 'stop_all'").fetchone()[0]:
        db.execute("commit"); return None  # no new claims while the switch is on
    row = db.execute("""select run, attempt from runs where status in ('open', 'running') and cancel = 0
        and (owner is null or expires_at < ?) order by run limit 1""", (now,)).fetchone()
    if row is None:
        db.execute("commit"); return None
    db.execute("update runs set owner = ?, attempt = ?, expires_at = ?, status = 'running' where run = ?",
               (owner, row[1] + 1, now + LEASE_TTL_S, row[0]))
    db.execute("commit")
    return row[0], row[1] + 1

def heartbeat(path, run, owner, attempt, stop, lost):  # renews the lease; if the row moved on, the lease is lost
    db = connect(path)
    while not stop.wait(HEARTBEAT_S):
        if db.execute("update runs set expires_at = ? where run = ? and owner = ? and attempt = ?",
                      (time.time() + LEASE_TTL_S, run, owner, attempt)).rowcount == 0:
            lost.set()  # another worker took the run: the loop stops at its next check, without waiting for a write

def fenced_write(db, run, owner, attempt, key, amount):  # the write counts only if this worker still holds the lease
    db.execute("begin immediate")  # the lease check and the write are one transaction
    held = db.execute("select 1 from runs where run = ? and owner = ? and attempt = ? and expires_at > ?",
                      (run, owner, attempt, time.time())).fetchone()
    new = db.execute("insert or ignore into ledger values (?, ?, ?)", (key, run, amount)).rowcount if held else 0
    db.execute("commit")
    return "refused" if not held else ("written" if new else "duplicate")

def call_provider(mode):  # the proposal was recorded earlier; the drill injects the 429 at this call
    if mode == "rate_limited":
        raise RateLimited("HTTP 429 Too Many Requests (injected by the drill)")

def verify(mode, proposal, paid):  # the checker: a refund must be positive and no more than was paid
    if mode == "verifier_always_fails":
        return False  # the drill's broken verifier never passes
    return 0 < proposal <= paid

def run_loop(db, run, owner, attempt, lost, hang, pause):
    for i in range(MAX_ITERS):
        why = stopped(db, run) or ("lease_lost" if lost.is_set() else None)  # checked at the top of every iteration
        if why:
            return why
        mode, proposal, paid = db.execute("select mode, proposal_usd, paid_usd from runs where run = ?", (run,)).fetchone()
        db.execute("update runs set iters = iters + 1 where run = ?", (run,))
        try:
            call_provider(mode)
        except RateLimited as err:
            print(f"  {owner} {run} iteration {i + 1}: {err}; pausing {pause} s", flush=True)
            time.sleep(pause); continue
        if not verify(mode, proposal, paid):
            print(f"  {owner} {run} iteration {i + 1}: verifier failed", flush=True)
            time.sleep(pause); continue
        outcome = fenced_write(db, run, owner, attempt, f"{run}:refund", proposal)
        print(f"  {owner} {run} iteration {i + 1}: refund {outcome}", flush=True)
        if outcome == "refused":
            return "lease_lost"
        if hang:  # the drill: the refund row is committed, the worker has not returned
            print(f"WROTE {run}: refund is in the ledger", flush=True)
            time.sleep(hang)
        return "done"
    return "over_budget"

def finish(db, run, owner, attempt, status):  # a stopped run is released, so a later worker can resume it
    db.execute("update runs set status = ?, owner = null, expires_at = 0 where run = ? and owner = ? and attempt = ?",
               ("open" if status == "stopped" else status, run, owner, attempt))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder"); ap.add_argument("owner")
    ap.add_argument("--hang", type=float, default=0.0)
    a = ap.parse_args()
    path = Path(a.folder) / "fleet.db"
    db = connect(path)
    while True:
        got = claim(db, a.owner)
        if got is None:
            print(f"{a.owner}: nothing to claim; exit", flush=True)
            return
        run, attempt = got
        stop, lost = threading.Event(), threading.Event()
        threading.Thread(target=heartbeat, args=(path, run, a.owner, attempt, stop, lost), daemon=True).start()
        print(f"{a.owner}: run {run}, attempt {attempt}", flush=True)
        status = run_loop(db, run, a.owner, attempt, lost, a.hang, PAUSE_S)
        stop.set()
        finish(db, run, a.owner, attempt, status)
        print(f"{a.owner}: run {run} -> {status}", flush=True)

if __name__ == "__main__":
    main()

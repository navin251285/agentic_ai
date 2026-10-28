# %% [markdown]
# # 26b · Kill switch and lease expiry: stopping a runaway fleet
# Level L6 · Part 4 · core · ~20 min · builds on 26a
#
# ## Goal
# Stop every run in a fleet with one switch, and a per-run cancel for one run. Then kill a worker mid-run, let its lease expire, and have exactly one other worker take the run over. The drill passes when that run has one refund and no stale write gets through.
#
# ## Why it matters
# A fleet of agent runs can run away: a verifier that never passes, or a provider that answers 429 on every call, keeps the loop spending. Lesson 26a made a run survive a crash. It did not say how to stop a fleet, or who owns a run whose worker died. Without these rules:
#
# | Without this | What goes wrong |
# |---|---|
# | One kill switch | Stopping 40 runs means finding 40 processes. A verifier that never passes spends until a monthly budget ends it |
# | A lease with an expiry | A worker that dies keeps its run forever. The run is stuck, or someone re-runs it by hand |
# | A fenced write | A worker that only paused wakes up after its run was taken over and writes again. The refund happens twice |
#

# %% [markdown]
# ## The idea
# **One switch is a flag that every worker reads at the top of each iteration. A per-run cancel is the same check for one run. A lease is a claim with an expiry: a worker that stops renewing it loses the run, and the next worker takes it with the next attempt number. Each write checks that its owner still holds the lease, so a stale worker is refused.**
#
# Analogy: a factory with a big red button and one padlock per job. The button stops the line at the next station, not in the middle of a weld. A padlock that is not renewed falls off, and the next person who arrives takes the job and gets a new key number. An old key no longer opens the door.

# %% [markdown]
# ## Picture
# The switch, the cancel and the lease in one picture. The checks sit at the top of each iteration, and the write checks the lease in the same transaction.
#
# ```mermaid
# flowchart LR
#   G["One switch: stop_all = 1"] --> K{"top of each iteration"}
#   C["Per-run cancel: cancel = 1"] --> K
#   K -->|stop| S["cancelled, or released to open"]
#   K -->|go| W["one iteration: call, verify, fenced write"]
#   W --> K
#   D["Worker A dies: no more heartbeats"] --> E["lease expires"]
#   E --> T["Worker B claims: attempt + 1, once"]
#   T --> F["fenced write: a stale attempt is refused"]
# ```

# %% [markdown]
# ## Requirements
# The drill passes when all six hold:
#
# - [ ] One switch stops every run in the fleet. No run does one more iteration after the switch was read, except the one already past its check.
# - [ ] A per-run cancel stops one run. The other runs keep going.
# - [ ] A run that gets a 429 on every call pauses, then stops at the cancel, the switch or its cap of 12 iterations (a `MAX_ITERS` bound this drill does not exercise). It never runs forever.
# - [ ] A worker killed with SIGKILL after its refund is written: its lease expires with nobody editing the database.
# - [ ] Exactly one other worker takes the run over, as attempt 2, even when two start together.
# - [ ] A worker that wakes up with its old attempt cannot write. The order has one refund and 120 USD paid out.
#
# **Drill inputs.** A 429 and a verifier that never passes make a fleet run away. The model only writes the proposals.

# %% [markdown]
# ## Step by step
# ### Step 1: the setup, three cases and the drill's modes
# Three customers, one order each. Each run has a drill mode: `ok` is a healthy run, `rate_limited` gets a 429 on every call, `verifier_always_fails` never passes its check. The run folder is run-time data only.

# %%
import json, shutil, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, "..")
import llm_replay
llm_replay.start("26b_kill-switch-and-leases")  # records the model calls once, replays them later

DATA = Path("../data/26b").resolve()  # run-time files only: fleet databases, logs, proposals
shutil.rmtree(DATA, ignore_errors=True)
DATA.mkdir(parents=True)
WORKER = DATA / "fleet.py"
CASES = [
    {"run": "C-17", "order": "BS-1042", "paid": 120.0, "mode": "ok",
     "text": "Customer C-17 says the trail jacket from order BS-1042 arrived torn after one wash. Order BS-1042 paid 120 USD."},
    {"run": "C-21", "order": "BS-1057", "paid": 80.0, "mode": "rate_limited",
     "text": "Customer C-21 says the rain jacket from order BS-1057 has a broken zip. Order BS-1057 paid 80 USD."},
    {"run": "C-30", "order": "BS-1063", "paid": 45.0, "mode": "verifier_always_fails",
     "text": "Customer C-30 says the water bottle from order BS-1063 leaks. Order BS-1063 paid 45 USD."},
]

# %% [markdown]
# ### Step 2: the worker is a plain Python file
# A worker claims one run, runs its loop, and writes the refund under a key built from the case. Read the file once. Then the notebook imports the same functions, so the code you inspect is the code the fleet runs.
#
# The file is written in three cells. The first holds the switch and the claim. The second holds the lease, the heartbeat and the fenced write. The third holds the loop and `main()`.
#
# LEASE_TTL_S = 2 s, HEARTBEAT_S = 0.5 s, PAUSE_S = 0.2 s and MAX_ITERS = 12 are lab settings chosen so the drill runs in seconds. They are not provider limits. The TTL is 4 heartbeats, and production uses a TTL above 3 heartbeats.
#
# `PAUSE_S` is a fixed pause between tries after a 429, not exponential backoff. Real backoff grows the wait and adds jitter; lesson 28b covers it.

# %%
%%writefile ../data/26b/fleet.py
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

# %% [markdown]
# `begin immediate` locks the database for writing, so a second worker waits until the first has finished claiming.
# The heartbeat is a background thread. Every 0.5 s it pushes `expires_at` forward, so a live worker keeps its lease.

# %%
%%writefile -a ../data/26b/fleet.py

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

# %% [markdown]
# The third part adds the loop. Each iteration checks the switch first, then makes one provider call and one fenced write. A 429 or a failed verifier costs one iteration and a pause, then the loop goes on to its next check.

# %%
%%writefile -a ../data/26b/fleet.py

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

# %% [markdown]
# The notebook imports the same file, so the code you inspect is the code the fleet runs. `main()` runs only when the file is started as a program.

# %%
sys.path.insert(0, str(DATA))
import fleet

# %% [markdown]
# ### Step 3: the model writes the proposals (one call per case)
# The desk model proposes one refund per case, the same way lesson 26a does. The cell is tagged `needs-llm`: a rerun replays the recording and needs no key. Three calls in total.
# The proposals are real recorded Gemini output. The 429 and the failing verifier are injected by the drill at the call, so no provider quota is spent.

# %% tags=["needs-llm"]
from langchain_core.messages import HumanMessage, SystemMessage
from llm_setup import get_llm

def issue_refund(order_id: str, amount_usd: float) -> str:
    """Refund an amount on one order. The amount may not be more than the amount paid."""
    raise NotImplementedError("the worker runs the write itself")

SYSTEM = ("You are the support desk for Brightside Outfitters. Refund what was paid for a damaged item, "
          "by calling issue_refund once. Never refund more than was paid.")
desk = get_llm().bind_tools([issue_refund])
PROPOSALS = {}
for c in CASES:
    call = desk.invoke([SystemMessage(content=SYSTEM), HumanMessage(content=c["text"])]).tool_calls[0]
    PROPOSALS[c["run"]] = {"order_id": call["args"]["order_id"], "amount_usd": float(call["args"]["amount_usd"])}
(DATA / "proposals.json").write_text(json.dumps(PROPOSALS))
print("model proposals:", PROPOSALS, "| model calls: 3")

# %% [markdown]
# **No key, or the model cell skipped?** The fallback uses the order record and says so. Nothing downstream changes, because the worker only reads the proposal.

# %%
# No-key fallback: when the model cell was skipped, use the order records and say so.
if (DATA / "proposals.json").exists():
    PROPOSALS = json.loads((DATA / "proposals.json").read_text())
    print("proposals on disk:", PROPOSALS)
else:
    PROPOSALS = {c["run"]: {"order_id": c["order"], "amount_usd": c["paid"]} for c in CASES}
    print("fallback: the order records, not model decisions")

# %% [markdown]
# ### Step 4: helpers and a fleet
# `seed` writes one row per run with its mode, its proposal and what was paid. `show` prints the state of every run. `start` launches one worker process and sends its output to a log file.

# %%
def query(folder, sql, args=()):  # run one statement on a fleet's database and return its rows
    db = fleet.connect(folder / "fleet.db")
    rows = db.execute(sql, args).fetchall()
    db.close()
    return rows

def seed(folder, cases):  # a fresh fleet: one row per run
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    db = fleet.connect(folder / "fleet.db"); fleet.setup(db)
    for c in cases:
        db.execute("insert into runs (run, mode, proposal_usd, paid_usd) values (?, ?, ?, ?)",
                   (c["run"], c["mode"], PROPOSALS[c["run"]]["amount_usd"], c["paid"]))
    db.close()

def show(folder):  # one line per run
    for run, status, owner, attempt, iters, cancel in query(folder, "select run, status, owner, attempt, iters, cancel from runs order by run"):
        print(f"  {run}: status {status:<20} owner {str(owner):<9} attempt {attempt}  iterations {iters}  cancel {cancel}")

def status(folder, run):
    return query(folder, "select status from runs where run = ?", (run,))[0][0]

def iters(folder, run):
    return query(folder, "select iters from runs where run = ?", (run,))[0][0]

def refunds(folder, run):  # (refund rows, total USD) for one run
    return query(folder, "select count(*), coalesce(sum(amount_usd), 0) from ledger where run = ?", (run,))[0]

# %% [markdown]
# `start` launches one worker process; its output goes to a log file. `wait_until` polls.

# %%
def start(folder, owner, *flags):  # one worker process; its output goes to a log file
    log = open(folder / f"{owner}.log", "w")
    return subprocess.Popen([sys.executable, str(WORKER), str(folder), owner, *flags],
                            stdout=log, stderr=subprocess.STDOUT), log

def wait_until(cond, timeout=30.0, step=0.1):  # a poll, not a fixed sleep
    t0 = time.time()
    while not cond():
        assert time.time() - t0 < timeout, "timed out waiting for the fleet"
        time.sleep(step)

# %% [markdown]
# ### Step 5: one switch stops a runaway fleet
# Two workers take three runs. Workers take runs in order, and a worker that finishes a run claims the next free one. C-17 finishes. C-21 gets a 429 on every call. C-30's verifier never passes. Both loops would run on. We wait until both runaways are visibly looping, then look at the fleet.

# %%
FLEET = DATA / "fleet"
seed(FLEET, CASES)
W1, L1 = start(FLEET, "worker-1")
W2, L2 = start(FLEET, "worker-2")
wait_until(lambda: iters(FLEET, "C-30") >= 3 and iters(FLEET, "C-21") >= 2)
show(FLEET)

# %% [markdown]
# Now the per-run cancel. One row changes: `C-21` gets `cancel = 1`. The worker that holds it stops at its next check and marks the run `cancelled`. The other runs keep going.

# %%
query(FLEET, "update runs set cancel = 1 where run = ?", ("C-21",))
wait_until(lambda: status(FLEET, "C-21") == "cancelled")
print("C-21 is cancelled. C-30 is still", status(FLEET, "C-30"), "after", iters(FLEET, "C-30"), "iterations")

# %% [markdown]
# Last, the global switch. One row, `stop_all`, is set to 1. Every worker checks it at the top of its next iteration and stops. No worker claims a new run while it is on. Stopped runs are released to `open`, so they can resume once the switch is off.

# %%
before = iters(FLEET, "C-30")
query(FLEET, "update control set value = 1 where name = 'stop_all'")  # the one switch
for p in (W1, W2):
    p.wait(timeout=30)
L1.close(); L2.close()
show(FLEET)
for name in ("worker-1", "worker-2"):  # what the drill inputs looked like from the workers' side
    lines = (FLEET / f"{name}.log").read_text().splitlines()
    print(name, [l.strip() for l in lines if "429" in l or "verifier failed" in l][:2])
extra = iters(FLEET, "C-30") - before
print(f"C-30 ran {extra} extra iterations after the switch was read (at most 1 allowed)")
assert extra <= 1

# %% [markdown]
# ### Step 6: a worker dies holding a lease, and the run is taken over once
# A new fleet with one run, C-17. Worker A writes the refund, prints `WROTE`, and then the drill kills it with SIGKILL. The row is in the ledger, but A never returns. Its heartbeats stop, and the lease runs out.

# %%
LEASE = DATA / "lease"
seed(LEASE, [CASES[0]])
A, LA = start(LEASE, "worker-A", "--hang", "30")
wait_until(lambda: "WROTE" in (LEASE / "worker-A.log").read_text())
A.kill(); A.wait(); LA.close()  # SIGKILL: no cleanup code runs in the worker
show(LEASE)
print("refunds for C-17 (rows, USD):", refunds(LEASE, "C-17"))

# %% [markdown]
# Now the lease expires on its own. We poll until it is free, then start two workers at the same moment. Each one tries to claim. The claim is one transaction, so only one of them can win the run. The winner runs it as attempt 2, and the refund write is a repeat that the ledger ignores.

# %%
wait_until(lambda: query(LEASE, "select expires_at < ? from runs where run = 'C-17'", (time.time(),))[0][0] == 1)
print("lease expired; starting worker-B and worker-C together")
B, LB = start(LEASE, "worker-B"); C, LC = start(LEASE, "worker-C")
B.wait(timeout=60); C.wait(timeout=60); LB.close(); LC.close()
print((LEASE / "worker-B.log").read_text() + (LEASE / "worker-C.log").read_text())
takeovers = sum((LEASE / f"worker-{x}.log").read_text().count("attempt 2") for x in "BC")
print("workers that took the run as attempt 2:", takeovers)
show(LEASE)
assert takeovers == 1

# %% [markdown]
# The worker that wins the claim repeats the write, because it cannot know that A finished. The key `C-17:refund` makes the repeat a no-op: the ledger answers `duplicate`, and only one refund row exists.

# %% [markdown]
# ### Step 7: the stale worker wakes up
# A worker can also pause instead of dying: a long stall, or a frozen VM. Suppose worker A wakes now and tries its write with its old attempt, 1. The write checks the lease in the same transaction, so it is refused. The ledger does not change.
# Here the run is already finished, so the lease check fails on owner. The attempt number also refuses a stale worker when another worker holds the run (same rule: owner and attempt).

# %%
db = fleet.connect(LEASE / "fleet.db")
print("worker-A wakes up with attempt 1:", fleet.fenced_write(db, "C-17", "worker-A", 1, "C-17:refund", 120.0))
db.close()
rows, paid = refunds(LEASE, "C-17")
print(f"refund rows for C-17: {rows} | paid out: {paid} USD | order paid: {CASES[0]['paid']} USD")
assert rows == 1 and paid == CASES[0]["paid"] and status(LEASE, "C-17") == "done"

# %% [markdown]
# ## At real scale
# - **Real TTLs and caps come from your run length and your provider's limits.** The lab's 2 s TTL and 12-iteration cap only make the drill fast.
- **One switch, read by every worker.** Our flag is a row in SQLite. In production it is a row in Postgres or a flag service that every worker reads at each iteration. Fail closed when the read fails, as `stopped()` does. A flag only stops a worker at its next check, so keep a hard stop for processes too (`docker compose kill` in lesson 28b).
# - **Leases in Postgres.** A claim is a transaction on lease columns (owner, attempt, expires_at). `SELECT ... FOR UPDATE SKIP LOCKED` picks the next free row. PostgreSQL's docs say SKIP LOCKED gives an inconsistent view and fits queue-like tables only. Lesson 28b runs this on Postgres in Compose.
# %% [markdown]
# - **Rate limits are shared by the fleet.** Gemini limits apply per project, not per key, so N workers share one quota and the 429 arrives first. The Gemini docs name `429 RESOURCE_EXHAUSTED` for spend limits and say RPM, TPM and RPD overruns give a rate-limit error. The fix is a fleet-wide limiter with jittered backoff (lesson 28b), and the loop's cap still applies.
# - **Each scheduled loop has an owner, a kill switch and an expiry date.** A scheduler that is unpaused does not backfill the triggers it missed (Managed Agents docs). Design catch-up on purpose, and budgets stop spend (lesson 29a).

# %% [markdown]
# ## Decision guide
# | Situation | Approach | Why |
# |---|---|---|
# | One laptop, a few runs | A switch row and a cancel column in one SQLite file | Simplest; the drill proves both |
# | Several worker hosts | The same rules in Postgres: lease columns and one switch row | SQLite allows one writer per file |
# | A runaway you cannot wait for | Hard-stop the processes too (lesson 28b) | A flag stops a worker only at its next check |
# | A worker that may pause, not die | Fence every write with owner and attempt | An expired lease alone cannot tell a paused worker from a dead one |
# | A 429 on every call | Back off, count the iteration, stop at the cap or on the switch | Retries cost calls and money |

# %% [markdown]
# ## What just happened
# - The cancel stopped C-21, the 429 run, at its next check. The switch stopped C-30, the verifier that never passes, at its next check.
# - The killed worker's lease expired on its own. Two workers started together, and only one took the run, as attempt 2.
# - The refund was written once. A stale write with the old attempt was refused.

# %% [markdown]
# ## Common mistakes
# ### Wrong version: the switch read once (the drill that fails)
# This loop reads the switch once, before the loop starts. An operator sets the switch after three iterations. The loop does not look again, so it runs all ten. The cell raises on purpose.

# %% tags=["raises-exception"]
NAIVE = DATA / "naive"
seed(NAIVE, [CASES[2]])
ndb = fleet.connect(NAIVE / "fleet.db")

def naive_loop(db, run, n=10):  # the mistake: one check, before the loop
    if fleet.stopped(db, run):
        return 0
    done = 0
    for _ in range(n):
        done += 1
        if done == 3:
            db.execute("update control set value = 1 where name = 'stop_all'")  # the operator presses the switch
    return done

ran = naive_loop(ndb, "C-30")
assert ran <= 4, f"this error is expected: the loop ignored the switch and ran {ran} iterations"  # AssertionError

# %% [markdown]
# Right: check the switch at the top of every iteration, as `run_loop` does. A check that runs once at the start is not a kill switch.

# %% [markdown]
# ## Try it
# Write `safe(folder, run)` that returns `True` when the run is `done` and the ledger has exactly one row for it. Then call it on the lease fleet and on the verifier-failure run in the fleet. Predict both answers first.

# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
def safe(folder, run):
    return status(folder, run) == "done" and refunds(folder, run)[0] == 1

print("lease fleet, C-17:", safe(LEASE, "C-17"), "| fleet, C-30:", safe(FLEET, "C-30"))

# %% [markdown]
# This last code cell saves the recording of the model calls.

# %%
llm_replay.stop()  # saves the recording

# %% [markdown]
# ## Key terms
# - **kill switch** — one flag that every worker reads at the top of each iteration; setting it stops the runs it covers (lesson 26b).
# - **global stop flag** — the switch's single row (`stop_all`). While it is on, no worker claims a run.
# - **per-run cancel** — a flag on one run. The run ends `cancelled`; the others keep going.
# - **fail closed** — when the flag cannot be read, the loop stops instead of running on.
# - **lease takeover** — when a lease expires, another worker claims the run with the next attempt number. Only one worker wins the claim.
# - **fencing token** — the attempt number a lease hands out; a write with an old attempt is refused (lesson 20).

# %% [markdown]
# **Interview:** How do you stop 200 runaway agent runs in under a minute, and hand a dead worker's run to another worker without paying twice? Strong answer: one flag that every iteration checks, failing closed; a per-run cancel; a lease with a TTL and a heartbeat; a takeover that bumps the attempt number; every write fenced by owner and attempt and keyed on the case; and a hard stop of the processes as the last resort.

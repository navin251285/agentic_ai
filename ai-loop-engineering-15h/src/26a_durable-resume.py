# %% [markdown]
# # 26a · Durable resume: checkpoints, replay and the crash drill
# Level L6 · Part 4 · core · ~25 min · builds on 22, 13
#
# ## Goal
# Kill a refund worker in the middle of a run, let its lease expire, and resume the run from its last checkpoint on a second worker. The drill passes when the order has zero duplicate refunds.
#
# ## Why it matters
# Lessons 13 and 22 made one refund safe to repeat and let a loop pause for a person. Neither survives a crash of the process itself. Without durable state, a worker that dies in the middle of a run leaves you with one of two bad outcomes:
#
# | What happens after a crash | Plain Python loop | Checkpointed loop |
# |---|---|---|
# | Where the run restarts | From the top: every step runs again, because nothing was saved | From the last saved step |
# | The write that was in progress | Runs again with no record it ran | Runs again, but the key in the write stops the second payout |
# | Who notices | Nobody: the run looks finished or never reports back | The lease expires, another worker takes the run, and the drill counts the refunds |
#
# Here is the failure in a few lines. The run's position lives in a Python variable, and a restart is a new process with a new, empty memory.
#
# **When you don't need this:** a run of a few seconds that is safe to restart from the top, or a read-only tool, needs no checkpoint and no key.

# %%
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver  # the checkpointer lives in RAM only

class Two(TypedDict):
    steps: list

def step(name):
    return lambda s: {"steps": s["steps"] + [name]}

def make_graph(saver):
    g = StateGraph(Two)
    g.add_node("check", step("check"))
    g.add_node("refund", step("refund"))
    g.add_edge(START, "check"); g.add_edge("check", "refund"); g.add_edge("refund", END)
    return g.compile(checkpointer=saver)

cfg = {"configurable": {"thread_id": "C-17"}}
make_graph(InMemorySaver()).invoke({"steps": []}, cfg)           # process 1 finishes the run
print("process 2 (a new InMemorySaver) sees:", make_graph(InMemorySaver()).get_state(cfg).values)

# %% [markdown]
# ## The idea
# **A checkpointer saves the graph's state after each step under a `thread_id`. A worker that dies is replaced by another that loads the same thread and continues. The state is safe, but the outside world is not: a step that was killed after its write and before its checkpoint runs again on resume. The only thing that stops a second refund is a key stored with the write itself, so the repeat finds the first row.**
#
# Analogy: a relay race. The baton (the checkpoint) passes to the next runner, but if the last runner dropped the baton after running the leg, the next runner runs it again. The fix is a ledger where the leg already has a line.

# %% [markdown]
# ## Picture
# The drill in one picture. The kill lands after the refund row is committed and before its checkpoint is saved.
#
# ```mermaid
# flowchart TD
#   A["Worker A claims the lease, attempt 1"] --> C["check runs: checkpoint saved"]
#   C --> R["refund runs: ledger row committed"]
#   R -.->|"SIGKILL: no checkpoint for refund"| X["Worker A is dead, heartbeats stop"]
#   X --> E["Lease expires"]
#   E --> B["Worker B claims the lease, attempt 2"]
#   B --> RR["Resume from the checkpoint: refund runs again"]
#   RR --> K["Insert ignored: key already in the ledger"]
#   K --> D["done: one refund"]
# ```

# %% [markdown]
# ## Requirements
# The drill passes only when all five hold:
#
# - [ ] Worker A is killed with SIGKILL after its refund row is committed and before the refund's checkpoint is saved.
# - [ ] The lease expires on its own. No one edits the database by hand.
# - [ ] Worker B resumes on the same `thread_id` as attempt 2, and `check` does not run again.
# - [ ] The `refund` node runs again and writes nothing: the key is already in the ledger.
# - [ ] One refund row, 120 USD paid out, zero duplicates. A replay from an older checkpoint keeps it at one.

# %% [markdown]
# ## Build it
# ### Step 1: the case, and the model's proposal (one model call)
# The case is the one from lessons 13 and 22: customer C-17, a torn trail jacket from order BS-1042, which paid 120 USD. The desk model proposes a refund by calling `issue_refund`. The worker does the write, not the model. The answer is recorded once and replayed on later runs, so this cell needs no key on a rerun.

# %%
import json, shutil, sqlite3, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, "..")
import llm_replay
llm_replay.start("26a_durable-resume")  # records the model call once, replays it later

DATA = Path("../data/26a").resolve()  # run-time files only: ledger, checkpoints, proposal, worker
shutil.rmtree(DATA, ignore_errors=True)
DATA.mkdir(parents=True)
WORKER = DATA / "worker.py"
ORDER, PAID, RUN = "BS-1042", 120.0, "C-17"  # the order record, and the run (one case = one thread)

# %% [markdown]
# The next cell is the only one that calls the model. It is tagged `needs-llm`: a rerun replays the recording and needs no key.

# %% tags=["needs-llm"]
from langchain_core.messages import HumanMessage, SystemMessage
from llm_setup import get_llm

def issue_refund(order_id: str, amount_usd: float) -> str:
    """Refund an amount on one order. The amount may not be more than the amount paid."""
    raise NotImplementedError("the worker runs the write itself")

SYSTEM = ("You are the support desk for Brightside Outfitters. Refund what was paid for a damaged item, "
          "by calling issue_refund once. Never refund more than was paid.")
REQUEST = "Customer C-17 says the trail jacket from order BS-1042 arrived torn after one wash. Order BS-1042 paid 120 USD."
reply = get_llm().bind_tools([issue_refund]).invoke([SystemMessage(content=SYSTEM), HumanMessage(content=REQUEST)])
call = reply.tool_calls[0]
proposal = {"order_id": call["args"]["order_id"], "amount_usd": float(call["args"]["amount_usd"])}
assert proposal["order_id"] == ORDER and proposal["amount_usd"] <= PAID, "plain-Python policy check failed"
(DATA / "proposal.json").write_text(json.dumps(proposal))  # saved before any write
print("model proposed:", call["name"], proposal, "| model calls: 1")

# %% [markdown]
# **No key, or the model cell skipped?** The fallback below uses the order record instead, and says so. Nothing downstream changes.

# %%
# No-key fallback: when the model cell was skipped, use the order record and say so.
if not (DATA / "proposal.json").exists():
    (DATA / "proposal.json").write_text(json.dumps({"order_id": ORDER, "amount_usd": PAID}))
    print("fallback: the order record, not a model decision")
print("proposal on disk:", json.loads((DATA / "proposal.json").read_text()))

# %% [markdown]
# ### Step 2: the worker is a plain Python file
# A worker is one process that claims one run, then runs its graph on that run's thread. You can read the file and run it by hand. It has three parts:
#
# - **A lease (hand-written).** One row per run with an owner and an expiry time. A heartbeat renews it every second; a killed worker stops renewing, so the lease runs out about 3 seconds later. LangGraph's checkpointer saves state but has no lease, so these ~16 lines of SQL are ours (idea from lesson 20).
# - **A graph.** Nodes `check`, `refund`, `done`. `refund` writes one ledger row under a key built from the run and the order; the ledger has a unique `key` column.
# - **A resume.** If the thread has a checkpoint, the worker calls `invoke(None, ...)`, which continues from it. Otherwise it starts from the proposal.

# %% [markdown]
# **Part 1 of 4: imports, the lease table and connect.**

# %%
%%writefile ../data/26a/worker.py
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

# %% [markdown]
# **Part 2 of 4: claim the lease, and renew it with a heartbeat.**

# %%
%%writefile -a ../data/26a/worker.py
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

# %% [markdown]
# **Part 3 of 4: the graph. The refund node writes one keyed row, then checkpoints.**

# %%
%%writefile -a ../data/26a/worker.py

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

# %% [markdown]
# **Part 4 of 4: main. It claims the lease, runs the graph, and resumes if a checkpoint exists.**

# %%
%%writefile -a ../data/26a/worker.py

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

# %% [markdown]
# The notebook imports the same `build` and `connect` functions, so the graph you inspect is the graph the workers run. The cell below prints the nodes and the checkpoint file it uses.
#
# How a checkpoint is made: a checkpoint is written when a node returns. With `durability="sync"` it is saved before the next node starts, so `check` is safely saved. `refund` was killed before it returned, so there is no checkpoint for it. `invoke(None, cfg)` means "continue this thread, and give no new input": the run picks up at the next node the checkpoint names.

# %%
sys.path.insert(0, str(DATA))
import worker  # the file written above; main() runs only when it is started as a program

g = worker.build(DATA)
print("nodes:", sorted(n for n in g.get_graph().nodes if not n.startswith("__")),
      "| durability: sync (the drill), default async")
g.checkpointer.conn.close()

# %% [markdown]
# ### Step 3: kill the worker mid-run (no model call)
# Three helpers. `ledger` and `lease` read the two tables. `crash_mid_iteration` starts worker A with `--hang`: it prints `WROTE` once the refund row is committed, and the notebook kills it with SIGKILL. SIGKILL gives the process no chance to clean up, which is what a power cut or an out-of-memory kill does.

# %%
def ledger(folder=DATA):  # (refunds written for the order, total paid out in USD)
    db = worker.connect(folder / "ledger.db")
    n, paid = db.execute("select count(*), coalesce(sum(amount_usd), 0) from refunds where order_id = ?", (ORDER,)).fetchone()
    db.close()
    return n, paid

def lease(folder=DATA, run=RUN):  # (owner, attempt, expires_at) of the run's lease
    db = worker.connect(folder / "ledger.db")
    row = db.execute("select owner, attempt, expires_at from leases where run = ?", (run,)).fetchone()
    db.close()
    return row

# %% [markdown]
# `crash_mid_iteration` starts worker A and reads its output until the refund is committed. Then it sends SIGKILL and waits for the exit code. `resume` is the second half: it polls the lease, then starts worker B.

# %%
def crash_mid_iteration(folder, *flags):
    # --hang 30 makes the refund node sleep 30 s after its write, so it has not returned when we kill it.
    proc = subprocess.Popen([sys.executable, str(WORKER), str(folder), "worker-A", RUN, "--hang", "30", *flags],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    while True:  # read worker A's output until the refund is committed
        line = proc.stdout.readline()
        if not line:
            break
        print("  A:", line.rstrip())
        if line.startswith("WROTE"):
            break
    proc.kill()  # SIGKILL: no cleanup code runs in the worker
    proc.wait(); proc.stdout.close()
    return proc.returncode

def resume(folder, *flags):  # poll the lease until it is free, then worker B claims the run and resumes it
    t0 = time.time()
    while lease(folder)[2] > time.time():  # a poll, not a fixed sleep
        assert time.time() - t0 < 20, "the lease never expired"
        time.sleep(0.2)
    print(f"lease expired: {lease(folder)[2] <= time.time()} (the wait is about {worker.LEASE_TTL_S:.0f} seconds)")
    out = subprocess.run([sys.executable, str(WORKER), str(folder), "worker-B", RUN, *flags],
                         capture_output=True, text=True, timeout=120)
    print(out.stdout.strip(), "| worker B exit code:", out.returncode)

print("worker A exit code:", crash_mid_iteration(DATA))

# %% [markdown]
# Now look at what the crash left behind. The refund row is there. The checkpoint still says the next node is `refund`, because the node never returned. The lease still names worker A, and it expires about 3 seconds after the last heartbeat.

# %%
print("ledger after the crash (refunds, USD):", ledger())
owner, attempt, expires = lease()
print(f"lease: owner {owner}, attempt {attempt}, expires in <= {worker.LEASE_TTL_S:.0f} s: {expires - time.time() <= worker.LEASE_TTL_S}")
g = worker.build(DATA)
print("checkpoint: the next node is", g.get_state({"configurable": {"thread_id": RUN}}).next)
g.checkpointer.conn.close()

# %% [markdown]
# ### Step 4: the lease expires, worker B resumes from the checkpoint (no model call)
# The notebook polls the lease until it expires, about 3 seconds after worker A's last heartbeat. This is a poll, not a fixed sleep: it exits as soon as the lease is free. Then worker B claims the run as attempt 2 and resumes. The output shows what it did: `check` does not run again, because the checkpoint already holds it. `refund` runs again, and the ledger ignores the repeat.

# %%
resume(DATA)

# %% [markdown]
# ### Step 5: the result, the drill's pass mark
# The pass mark is simple: the order has one refund row and the total paid out equals the amount paid. Any extra row is a duplicate refund.

# %%
n, paid = ledger()
duplicates = n - 1
print(f"refunds written: {n} | paid out: {paid} USD | the order paid: {PAID} USD")
print("duplicate refunds:", duplicates, "| PASS" if duplicates == 0 else "| FAIL")
assert duplicates == 0 and paid == PAID

# %% [markdown]
# ### Step 6: replay: the same history, from any checkpoint
# Every step leaves a checkpoint, so the thread has a history. `get_state_history` lists it, newest first. Each checkpoint says which node runs next. A replay picks an older checkpoint and runs the rest of the graph from it. Here the replay starts from the checkpoint before `refund`, so `refund` and `done` run again. The checkpoint's config holds its checkpoint id; passing it tells LangGraph where to start. A replay forks a new history from that point: the old steps stay in the list, and the new ones are added after them. The ledger still holds one refund, because the repeated `refund` uses the same key.

# %%
g = worker.build(DATA)
cfg = {"configurable": {"thread_id": RUN}, "recursion_limit": 10}
history = list(g.get_state_history(cfg))
for snap in history:
    print(f"  step {snap.metadata.get('step')}: next = {snap.next}")
before_refund = next(s for s in history if s.next == ("refund",))
g.invoke(None, {**before_refund.config, "recursion_limit": 10})  # replay from that checkpoint
print("after the replay, ledger (refunds, USD):", ledger())
g.checkpointer.conn.close()

# %% [markdown]
# ## At real scale
# - **SQLite is one writer on one host.** LangGraph's docs use `SqliteSaver` for local work and `PostgresSaver` for production. Several worker hosts need the Postgres form and a lease in Postgres, with `SELECT ... FOR UPDATE SKIP LOCKED` (a row lock: a worker takes the next free row and skips rows another worker holds; lesson 26b). Lesson 28b runs the workers in Compose.
# - **Idempotency keys have a life.** Stripe keeps a saved response for a key, may delete a key once it is at least 24 hours old, and returns an error when a reused key comes with different parameters. A key must live as long as a retry can happen.

# %% [markdown]
# - **Checkpoints grow.** Every step adds a row per run. Plan retention with the checkpointer's `prune` (it deletes old checkpoints; the cleanup call) and watch the table size. Lesson 29b covers who may read the history and what it may hold.
# - **Days-long waits need a durable engine.** A checkpointer resumes a run when the worker comes back. For runs that wait for days, with timers and history replay at fleet scale, Temporal (a durable workflow engine) is the next step (Go deeper, not in this course).

# %% [markdown]
# ## Decision guide
# | Situation | Approach | Why |
# |---|---|---|
# | One laptop, runs of minutes | `SqliteSaver` in one file, lease in the same file | Simplest; the drill proves the resume |
# | Several worker hosts | `PostgresSaver` and a Postgres lease (26b, 28b) | SQLite allows one writer on one host |
# | A side effect: refund, email, charge | A key built from the case, stored with the write, unique | A resume re-runs the node that was killed |
# | A read-only tool | No key needed | A repeated read is harmless (lesson 13) |
# | Waits of days, or many timers | A durable engine such as Temporal (Go deeper) | Replayed history and timers at fleet scale |

# %% [markdown]
# ### Wrong version: no key (the drill that fails)
# This is the same drill with `--nokey`: each try gets a new random key. Worker A writes the refund row. Worker B resumes the `refund` node, and its write uses a new key, so it writes a second row: the second refund is the duplicate. The cell raises on purpose, so you can see the check catch it.

# %% tags=["raises-exception"]
NAIVE = DATA / "naive"  # its own folder, so the keyed drill above stays as it was
NAIVE.mkdir()
shutil.copy(DATA / "proposal.json", NAIVE / "proposal.json")
crash_mid_iteration(NAIVE, "--nokey")
resume(NAIVE, "--nokey")
n, paid = ledger(NAIVE)
assert n == 1, f"this error is expected: {n} refunds written for one order, {paid} USD paid out"  # AssertionError

# %% [markdown]
# Right: build the key from the case and store it in the write, as the worker does. Worker B's resume sends the same key as worker A's write, so the ledger ignores it and the naive run's second row never appears. A lease alone does not do this: it decides who runs the step, not what the step does to the outside world.

# %% [markdown]
# ### Your check: is the run safe to resume?
# Write `safe(folder)` that returns `True` when the ledger has exactly one refund for the order. Then call it on the keyed folder (`DATA`) and on the naive one (`NAIVE`). Predict both answers first.

# %%
# your code here

# %% [markdown]
# ## Reference solution
# **Try the check above first.** The reference answer is in the hidden cell below.

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
def safe(folder):
    return ledger(folder)[0] == 1

print("keyed drill:", safe(DATA), "| naive drill:", safe(NAIVE))

# %% [markdown]
# This last code cell saves the recording of the one model call.

# %%
llm_replay.stop()  # saves the recording

# %% [markdown]
# ## Key terms
# - **checkpointer** — saves a graph's state after each step, so a new process can resume it. `SqliteSaver` here (lesson 22).
# - **thread_id** — the key that names one run's saved state. A resume passes the same one.
# - **lease** — a claim on a run with an owner, an attempt number and an expiry. A heartbeat renews it; a dead worker's lease runs out (lesson 20).
# - **idempotency key** — a key built from the case and sent with the write. A repeat with the same key is ignored (lesson 13).
# - **replay** — running a graph again from an older checkpoint. Every side effect on the way needs a key too.
# - **durability** — when a checkpoint is written: `sync` before the next step, `async` by default, `exit` only at the end.

# %% [markdown]
# **Interview:** How do you make an agent run survive a crash without repeating a side effect? Strong answer: checkpoint each step under a run id; take a lease with an expiry so another worker can take over; build an idempotency key from the case and store it with the write under a unique constraint; then test it by killing a worker after its write and counting the side effects.

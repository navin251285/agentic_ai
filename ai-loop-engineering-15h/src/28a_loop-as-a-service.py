# %% [markdown]
# # 28a · A loop as a service: a FastAPI run endpoint and an approval queue
# Level L6 · Part 4 · core · ~20 min · builds on 27
#
# ## Goal
# Serve the support-desk loop from FastAPI. `POST /runs` queues a run and returns at once. A worker takes the run from a SQLite queue. A refund waits in `waiting_approval` until `POST /runs/{id}/approve` answers it. A repeated step never writes a refund twice.
#
# ## Why it matters
# Lesson 27 runs the loop in a script that you start and watch. A service has other callers: a web page, a helpdesk tool, a nightly job. Without a queue and an approval state, this is what happens:
#
# | Without this | What goes wrong |
# |---|---|
# | The loop runs inside the web request | The browser waits for the whole loop, times out and retries. The run starts twice |
# | The refund is written as soon as the model asks | Nobody approves the refund. The model's mistake is paid out at once |
# | No queue, no status | A free worker cannot take the next run, and nobody can see which runs wait for a person |
#
# With a queue, the request returns at once with a run id. A worker takes a run when it is free. A refund waits in a state that a person can see, and the approval is one HTTP call. You do not need a service for a loop that one person runs on a laptop.

# %% [markdown]
# ## The idea
# **The API only writes rows. A worker claims the oldest queued row in one transaction, runs the loop, and stops either at an answer or at a refund that waits for a decision. The approve endpoint writes the decision and puts the run back in the queue. The worker saves the transcript when it stops, so the design lets a restarted worker resume. Every refund row has a unique key, so a repeated step cannot write the same refund twice.**
#
# Analogy: a hospital ward. Reception takes the patient's ticket and gives a number (the API). A nurse takes the next number when free (the worker). A prescription above a set dose waits for a doctor's signature (the approval). Reception never signs a prescription.

# %% [markdown]
# ## Picture
# The API and the worker never talk to each other. They share one table, and the table holds the state of every run.
#
# ```mermaid
# flowchart LR
#   C["client: POST /runs"] --> API["FastAPI"]
#   API -->|insert: queued| Q[("runs table in SQLite")]
#   W["worker tick"] -->|claim the oldest queued run| Q
#   W -->|model call and tool calls| M["model and tools"]
#   W -->|refund proposed: waiting_approval| Q
#   P["approver: POST /runs/id/approve"] --> API
#   API -->|decision, status: queued| Q
# ```

# %% [markdown]
# ## Step by step
# 1. Start the recording layer. It makes no model call.
# 2. Set up the two orders and the tools from lessons 03 to 05 and 27.
# 3. Create the queue: one `runs` table, one `refunds` table with a unique key.
# 4. Write the API: three endpoints. None of them calls the model.
# 5. Write one worker tick. The model is called here, from the worker.
# 6. Send two requests, approve one refund and reject the other, and read the states.

# %%
import sys; sys.path.insert(0, "..")
import llm_replay
llm_replay.start("28a_loop-as-a-service")  # records the model calls once, replays them later

# %% [markdown]
# ### Step 1: the orders and the tools (setup from earlier lessons)
# This is the setup from lessons 03 to 05 and 27, shortened. The orders are invented for the course. The refund tool checks the amount and writes nothing. The worker writes the refund row only after an approval, and only when the tool accepts the amount.

# %%
# setup from earlier lessons (03 to 05, 27): two invented orders and two tools
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage, messages_to_dict, messages_from_dict

ORDERS = {"BS-1042": {"customer": "C-17", "item": "Trail jacket", "paid_usd": 120.0},
          "BS-1063": {"customer": "C-30", "item": "Water bottle", "paid_usd": 45.0}}
SYSTEM = ("You are the support desk for Brightside Outfitters. Look up the order, then refund what was paid "
          "for a damaged item. Never refund more than was paid. Answer in one sentence when done.")
@tool
def get_order(order_id: str) -> str:
    """Look up one order: item and amount paid."""
    return str(ORDERS.get(order_id, f"error: no order {order_id}"))
@tool
def issue_refund(order_id: str, amount_usd: float) -> str:
    """Refund an amount on one order. The amount may not be more than the amount paid."""
    order = ORDERS.get(order_id)
    if order is None:
        return f"error: no order {order_id}"
    if amount_usd > order["paid_usd"]:
        return f"error: more than the {order['paid_usd']} paid"
    return f"refund of {amount_usd} accepted on {order_id}"
TOOLS = {t.name: t for t in (get_order, issue_refund)}
print("tools the model can call:", list(TOOLS))

# %% [markdown]
# ### Step 2: the queue (SQLite)
# SQLite is a file and a standard library module, so the queue needs no server. The file lives in `../data/28a/`, and the notebook starts it empty each time. `isolation_level=None` makes each statement its own transaction, unless the code opens one with `BEGIN IMMEDIATE`.

# %%
import json, pathlib, sqlite3

DB = pathlib.Path("../data/28a/desk.db")
DB.parent.mkdir(parents=True, exist_ok=True)
DB.unlink(missing_ok=True)  # a fresh queue each time the notebook runs
def connect():
    db = sqlite3.connect(DB, timeout=10, isolation_level=None, check_same_thread=False)
    db.row_factory = sqlite3.Row
    return db
db = connect()
db.executescript("""
CREATE TABLE runs (
  id INTEGER PRIMARY KEY,
  status TEXT NOT NULL DEFAULT 'queued',   -- queued, running, waiting_approval, answered
  request TEXT NOT NULL,
  transcript TEXT NOT NULL DEFAULT '[]',   -- the saved messages: the design lets a worker resume from here
  pending TEXT,                            -- the refund call that waits for a decision
  decision TEXT,                           -- approve or reject, set by the API
  approver TEXT, answer TEXT
);
CREATE TABLE refunds (
  run_id INTEGER, call_id TEXT, order_id TEXT, amount_usd REAL,
  UNIQUE (run_id, call_id)                 -- one row per proposed call: a repeat is ignored
);
""")
print("tables:", [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")])

# %% [markdown]
# `claim()` takes the oldest queued run. Reading the row and marking it running happen in one transaction. `BEGIN IMMEDIATE` takes the write lock before the read, so two workers cannot claim the same row. The queue is empty now, so the call returns `None`.

# %%
def claim():
    db.execute("BEGIN IMMEDIATE")  # SQLite locks the file for writing until COMMIT
    row = db.execute("SELECT id FROM runs WHERE status = 'queued' ORDER BY id LIMIT 1").fetchone()
    if row:
        db.execute("UPDATE runs SET status = 'running' WHERE id = ?", (row["id"],))
    db.execute("COMMIT")
    return row["id"] if row else None

print("claim on an empty queue:", claim())  # None: nothing is queued yet

# %% [markdown]
# ### Step 3: the API
# Three endpoints. `POST /runs` answers `202 Accepted`: the run is accepted, not finished. `POST /runs/{id}/approve` answers `409` when the run is not waiting, so a second approval cannot run a refund again.

# %%
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Brightside support desk loop")

class NewRun(BaseModel):
    request: str

class Decision(BaseModel):
    decision: str   # "approve" or "reject"
    approver: str

@app.post("/runs", status_code=202)
def start_run(body: NewRun):
    cur = db.execute("INSERT INTO runs (request) VALUES (?)", (body.request,))
    return {"run_id": cur.lastrowid, "status": "queued"}

@app.get("/runs/{run_id}")
def read_run(run_id: int):
    row = db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "no such run")
    return {"run_id": run_id, "status": row["status"],
            "pending": json.loads(row["pending"]) if row["pending"] else None, "answer": row["answer"]}

# %% [markdown]
# `decide()` is the approve endpoint. It changes the state only from `waiting_approval`, so a second approval finds no row and gets `409`. `TestClient` calls the app in memory, so no server runs. The last line calls `GET /runs/99`, a run that does not exist: it returns `404` and writes nothing.

# %%
from fastapi.testclient import TestClient

@app.post("/runs/{run_id}/approve")
def decide(run_id: int, body: Decision):
    if body.decision not in ("approve", "reject"):
        raise HTTPException(422, "decision must be approve or reject")
    cur = db.execute("UPDATE runs SET status = 'queued', decision = ?, approver = ? "
                     "WHERE id = ? AND status = 'waiting_approval'", (body.decision, body.approver, run_id))
    if cur.rowcount == 0:
        raise HTTPException(409, "the run is not waiting for a decision")
    return {"run_id": run_id, "status": "queued"}

client = TestClient(app)  # calls the app in memory: no port, no server to start
print("routes:", [r.path for r in app.routes if r.path.startswith("/runs")])
r = client.get("/runs/99")  # one real call: a run that does not exist
print(r.status_code, r.json())

# %% [markdown]
# ### Step 4: one worker tick
# A worker runs `work_once()` again and again. Each tick takes one run and runs it until it answers or proposes a refund. A resumed run first writes the answer to its pending refund: the tool checks the amount, then the refund row is written if approved, and a "rejected" message is written if not. A decision set means this is a resume; the model is called once more to write the final answer. The worker saves the transcript before it waits. The design lets a restarted worker resume at the same place.

# %%
def save(run_id, messages, **fields):
    sets = ", ".join(f"{k} = ?" for k in fields)
    db.execute(f"UPDATE runs SET transcript = ?, {sets} WHERE id = ?",
               (json.dumps(messages_to_dict(messages)), *fields.values(), run_id))

def resume(run_id, row, messages):
    call = json.loads(row["pending"])
    result = "rejected by the approver: do not retry this refund"
    if row["decision"] == "approve":
        args = call["args"]
        result = TOOLS["issue_refund"].invoke(args)  # the tool checks the amount first
        if not str(result).startswith("error"):      # only an accepted refund gets a row
            db.execute("INSERT OR IGNORE INTO refunds VALUES (?, ?, ?, ?)",  # a repeat cannot refund twice
                       (run_id, call["id"], args["order_id"], args["amount_usd"]))
    messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))

# %% [markdown]
# The next two cells need the model. The worker calls it from here, and builds on the two helpers above.

# %% tags=["needs-llm"]
from llm_setup import get_llm, DEFAULT_MODELS

llm = get_llm(model=DEFAULT_MODELS["gemini"]).bind_tools(list(TOOLS.values()))
MAX_STEPS = 4  # the cap: a run that is still going after four model replies stops here

def park(run_id, messages, reply, i, call):
    """Stop a run at its refund: the other calls of this reply wait, and the run is saved."""
    for later in reply.tool_calls[i + 1:]:
        messages.append(ToolMessage(content="not run: waiting for the refund decision", tool_call_id=later["id"]))
    save(run_id, messages, status="waiting_approval", pending=json.dumps(call), decision=None)

# %% [markdown]
# `work_once()` is one tick. It takes one queued run, calls the model, and either answers or parks the run at a refund.

# %% tags=["needs-llm"]
def work_once():
    """One tick: take one queued run and run it until it answers or waits for an approval."""
    run_id = claim()
    if run_id is None: return None
    row = db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    messages = messages_from_dict(json.loads(row["transcript"])) or [SystemMessage(SYSTEM), HumanMessage(row["request"])]
    if row["decision"]: resume(run_id, row, messages)  # resume: the person's answer goes into the transcript first
    for _ in range(MAX_STEPS):
        reply = llm.invoke(messages)
        messages.append(reply)
        if not reply.tool_calls:
            save(run_id, messages, status="answered", answer=reply.text, pending=None, decision=None)
            return run_id
        for i, call in enumerate(reply.tool_calls):
            if call["name"] == "issue_refund":  # the gate: nothing is written before a decision
                park(run_id, messages, reply, i, call)
                return run_id
            messages.append(ToolMessage(content=str(TOOLS[call["name"]].invoke(call["args"])), tool_call_id=call["id"]))
    save(run_id, messages, status="answered", answer="stopped: step cap reached", pending=None, decision=None)
    return run_id

# %% [markdown]
# ### Step 5: two requests through the service
# Request A asks for the damaged jacket. Request B asks for the leaking bottle. Both are only queued here: the API returns at once and runs no model.

# %%
a = client.post("/runs", json={"request": "Customer C-17 says the trail jacket from order BS-1042 arrived torn "
                                          "after one wash. Order BS-1042 paid 120 USD. Refund the damage."}).json()
b = client.post("/runs", json={"request": "Customer C-30 says the water bottle from order BS-1063 leaks. "
                                          "Order BS-1063 paid 45 USD. Refund the damage."}).json()
print("accepted:", a, b)
print([client.get(f"/runs/{r['run_id']}").json()["status"] for r in (a, b)])  # both queued

# %% [markdown]
# The first worker pass runs each request to its refund and stops. Each run makes one model reply here. No refund row exists yet. The `id` in `pending` is the model's tool-call id; it is the `call_id` in the refunds table.

# %% tags=["needs-llm"]
while work_once() is not None:  # the first pass: each run stops at its refund
    pass
for rid in (a["run_id"], b["run_id"]):
    print(client.get(f"/runs/{rid}").json()["status"], "| pending:", client.get(f"/runs/{rid}").json()["pending"])

# %% [markdown]
# A person approves run A and rejects run B. The second pass lets the worker answer both. Each run makes at most one more model reply, so the notebook makes four calls in all.

# %% tags=["needs-llm"]
ra = client.post(f"/runs/{a['run_id']}/approve", json={"decision": "approve", "approver": "approver-1"})
rb = client.post(f"/runs/{b['run_id']}/approve", json={"decision": "reject", "approver": "approver-1"})
print("approve A:", ra.status_code, "| reject B:", rb.status_code)

while work_once() is not None:  # the second pass: each run answers
    pass
for rid in (a["run_id"], b["run_id"]):
    print(client.get(f"/runs/{rid}").json()["status"], "|", client.get(f"/runs/{rid}").json()["answer"])
print("refunds written:", [tuple(r) for r in db.execute("SELECT run_id, order_id, amount_usd FROM refunds")])

# %% [markdown]
# **No key, or the model cells skipped?** The worker needs the model's replies. Without them the queue stays full and no refund is written. The next cell says so; no output is made up.

# %%
if not db.execute("SELECT 1 FROM runs WHERE status = 'answered'").fetchone():
    print("no answered runs in this session: the worker cells need the recording or a key (needs-llm)")

# %% [markdown]
# ### Step 6: approval is a state, not a flag in memory
# The state is in the `runs` table. Read it from a new connection, as a second worker or a restarted API would, and it is the same.

# %%
fresh = connect()  # a second connection: the same file, the same state
print([(r["id"], r["status"], r["approver"]) for r in fresh.execute("SELECT id, status, approver FROM runs ORDER BY id")])

# %% [markdown]
# ## At real scale
# - **One SQLite file has one writer.** A single host with one API and a few workers is fine. Each worker should open its own connection: the shared `check_same_thread=False` connection is only for this one-process demo. Workers on several hosts need a shared queue: Postgres `SELECT ... FOR UPDATE SKIP LOCKED` (lesson 26a) or Redis. Lesson 28b runs the API and N workers in Compose.
# - **A worker that dies leaves its run in `running`.** This lesson does not expire claims. The lease and its takeover are in lesson 26b.
# - **No login on these endpoints.** Anyone who can reach `approve` can release a refund. Identity, tenant scoping and audit come in lessons 29a and 30.
# - **Scheduled and hosted runs use the same states.** Managed Agents (beta) runs scheduled deployments with per-run budgets. Its docs describe the run and approval states this lesson builds by hand (RESEARCH section 7.5).

# %% [markdown]
# ## Decision guide
# | Situation | Approach | Why |
# |---|---|---|
# | One person runs the loop | The script of lesson 27 | No queue and no service to run |
# | A caller must not wait for the loop | Return `202`, poll `GET /runs/{id}` | The request does not hold a worker |
# | A write needs a person | A `waiting_approval` state and an approve endpoint | The state is visible and the decision is recorded |
# | Several workers on several hosts | Postgres `SKIP LOCKED` or a Redis queue | SQLite has one writer |
# | A retried step | A unique key on every write | The second attempt is ignored |

# %% [markdown]
# ## What just happened
# Each run made one model reply that proposed the refund, then stopped with the state `waiting_approval`. No refund row existed yet. The approval moved each run back to the queue, and the second pass wrote the answer. The `refunds` table holds one row for the approved run and none for the rejected one. The state lives in the file, so a second connection reads the same runs.

# %% [markdown]
# ## Common mistakes
# The easiest mistake is to write the refund in the API handler, because the handler already has the request. A retried `POST` then writes it twice. This cell writes the same refund twice into a table without a unique key, on purpose. This cell counts the rows and asserts one: the `AssertionError` is the expected failure, not a database error.

# %% tags=["raises-exception"]
db.execute("CREATE TABLE IF NOT EXISTS naive_refunds (run_id INTEGER, call_id TEXT)")  # no unique key
for _ in range(2):  # a retried write
    db.execute("INSERT INTO naive_refunds VALUES (1, 'call-x')")
# we count the rows and assert one
assert db.execute("SELECT COUNT(*) FROM naive_refunds").fetchone()[0] == 1, "this error is expected: the refund was written twice"

# %% [markdown]
# The fix is the `UNIQUE (run_id, call_id)` key and `INSERT OR IGNORE`, as in the worker. The second write does nothing.

# %% [markdown]
# ## Try it
# Approving a run that is not waiting must return `409`. Write `approve_code(run_id)` that sends an approve request for that run and returns the HTTP status code. Predict the code for run A, which has already answered.

# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
def approve_code(run_id):
    return client.post(f"/runs/{run_id}/approve", json={"decision": "approve", "approver": "approver-1"}).status_code

print("approve run A (answered):", approve_code(a["run_id"]))  # 409: it is not waiting for a decision

# %% [markdown]
# This last code cell saves the recording of the model calls.

# %%
llm_replay.stop()  # saves the recording

# %% [markdown]
# ## Key terms
# - **queue** — a table of work waiting for a worker; the API adds rows and workers take them.
# - **claim** — a worker takes the oldest queued row in one transaction, so two workers never take the same run.
# - **`202 Accepted`** — the request is accepted and the work runs later; the caller polls the run.
# - **`waiting_approval`** — the run state in which a refund waits for a person's decision.
# - **idempotency key** — a unique key on a write; a repeat with the same key is ignored (lesson 13).
# - **transcript** — the saved messages of a run, so a worker can resume it after a restart.

# %% [markdown]
# **Interview:** How do you let an agent act through an API without it writing on its own? Strong answer: the API accepts the run with `202` and a queue holds it; a worker claims it in one transaction; a risky write parks the run in a visible `waiting_approval` state until an approve call; every write carries a unique key so a retry cannot repeat it.

# %% [markdown]
# # 22 · Human approval as a loop exit: pause, show arguments, resume
# Level L5 · Part 3 · core · ~25 min · builds on 12, 13, 21
#
# ## Goal
# Pause the refund loop before a refund over 50 USD, show the reviewer the exact arguments, then resume from saved state: finish on approve, stop on reject, or escalate when the reviewer keeps holding or the step cap is near.
#
# ## Why it matters
# Lesson 13 made a refund safe to repeat. It did not make a refund right. Without a gate, in a loop like this:
#
# | Without an approval gate | What goes wrong |
# |---|---|
# | The model's refund goes straight to the ledger | A wrong amount is paid out, and nobody saw it. Money paid out is hard to take back |
# | The loop waits for the person inside the process | The process dies while it waits. The decision is lost, and a restart asks the model again |
# | The reviewer sees a summary ("refund the customer?") | They approve 120 USD without seeing the order it is for, or that the amount changed |
# | "Hold" has no limit | The case waits forever, and the loop keeps its place and its cost |
#
# With a gate, the loop stops at one named node, saves its state, and waits without a running process. The reviewer sees the real arguments. You do not need a gate for a write you can undo, or for a loop that touches no money and no customer data.

# %% [markdown]
# ## The idea
# **A loop can stop mid-run and wait for a person. LangGraph's `interrupt()` saves the graph's state to a checkpointer (a SQLite file here) under a `thread_id`. The reviewer answers later, maybe from a new process that builds the same graph and resumes with `Command(resume=...)`. The paused node runs again from its first line, so nothing before `interrupt()` may write. The loop has four exits: refunded, rejected, escalated, and a step cap.**
#
# The step cap is `recursion_limit`. LangGraph's default is 1000, which is not a cap you chose. This lesson sets 10.
#
# Analogy: a manager signs a slip for an exact amount. A different amount on the slip goes back to the desk.
#
# %% [markdown]
# ## Picture
# The gate sits between the decision and the write. Small refunds skip it. A reviewer's answer either resumes the loop, holds it, or ends it.
#
# ```mermaid
# flowchart TD
#   S["START"] --> P{"policy: amount"}
#   P -->|"more than was paid"| E["escalate"]
#   P -->|"up to 50 USD"| W["write the refund"]
#   P -->|"over 50 USD"| A["approve: interrupt, pause"]
#   A -->|"approve, same amount"| W
#   A -->|"reject"| R["end: rejected"]
#   A -->|"hold, first time: approve runs again and interrupt() pauses again"| A
#   A -->|"hold twice, or amount changed"| E
# ```
#
# A hold runs `approve` again from its first line, so `interrupt()` pauses again. The second hold is counted in `after_approve`, and it escalates.

# %% [markdown]
# ## Step by step
# ### Step 1: the case, and the model's proposal (one model call)
# The case is the one from lesson 13. Customer C-17 says the trail jacket from order BS-1042 arrived torn. The order record says it paid 120 USD. Nothing is downloaded: the order is a line of text.
#
# The desk model proposes a refund by calling `issue_refund`. Its body raises on purpose: the graph does the write, after the gate. The model's answer is recorded once and replayed later, so the cell needs no key on a rerun.

# %%
import json, shutil, sqlite3, sys
from pathlib import Path

sys.path.insert(0, "..")
import llm_replay
llm_replay.start("22_approvals-as-loop-exit")  # records the model call once, replays it later

ROOT = Path("../data/22")  # run-time files: the ledger and the checkpoint file
shutil.rmtree(ROOT, ignore_errors=True)
ROOT.mkdir(parents=True)
ORDER, PAID = "BS-1042", 120.0  # the order record

# %% [markdown]
# The next cell is the only one that calls a model. The recording is committed, so you need no key. A fresh recording needs a model key in `.env`, and this is the only cell that does. It is tagged `needs-llm`.

# %% tags=["needs-llm"]
from langchain_core.messages import HumanMessage, SystemMessage
from llm_setup import get_llm

def issue_refund(order_id: str, amount_usd: float) -> str:
    """Refund an amount on one order. The amount may not be more than the amount paid."""
    raise NotImplementedError("the graph runs the write itself, after the approval gate")

SYSTEM = ("You are the support desk for Brightside Outfitters. Refund what was paid for a damaged item, "
          "by calling issue_refund once. Never refund more than was paid.")
REQUEST = "Customer C-17 says the trail jacket from order BS-1042 arrived torn after one wash. Order BS-1042 paid 120 USD."

reply = get_llm().bind_tools([issue_refund]).invoke([SystemMessage(content=SYSTEM), HumanMessage(content=REQUEST)])
call = reply.tool_calls[0]
proposal = {"order_id": call["args"]["order_id"], "amount_usd": float(call["args"]["amount_usd"])}
(ROOT / "proposal.json").write_text(json.dumps(proposal))  # saved before any write
print("model proposed:", call["name"], proposal, "| model calls: 1")

# %% [markdown]
# ### Step 2: the loop as a graph, with a gate and a checkpointer
# The graph has three nodes. Its first routing step is plain-Python rules: more than was paid always escalates, up to 50 USD is written at once, and anything above 50 USD waits for a person. `approve` calls `interrupt()` with the arguments the reviewer must see. `write` records the refund under a key built from the case, so a retry or a restart cannot pay twice (lesson 13's idea). The reviewer's answer must echo the amount; if it does not match, the approval covers a different refund and the case escalates.

# %%
# Nothing runs yet in the next cells: these are the pieces the graph is built from.
import sqlite3
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command
from langgraph.checkpoint.sqlite import SqliteSaver

LIMIT, MAX_HOLDS = 50.0, 2  # refunds above LIMIT need a person; two holds is the most before escalation
DB = ROOT / "checkpoints.db"

class Case(TypedDict):
    case_id: str
    order_id: str
    amount_usd: float
    paid_usd: float
    holds: int
    status: str

def ledger():  # the refund ledger: one row per key, so a repeat is ignored
    db = sqlite3.connect(ROOT / "ledger.db")
    db.execute("create table if not exists refunds (key text unique, order_id text, amount_usd real)")
    return db

def policy_route(s):
    if s["amount_usd"] > s["paid_usd"]: return "escalate"
    return "write" if s["amount_usd"] <= LIMIT else "approve"

print("limit for a person (USD):", LIMIT, "| holds before escalation:", MAX_HOLDS)

# %% [markdown]
# `approve` is the gate. Its `interrupt()` call hands the reviewer the arguments and pauses the run. The reply it gets back decides the next node.

# %%
def approve(s):
    # On resume this node runs again from its first line, so nothing above interrupt() may write.
    reply = interrupt({"order_id": s["order_id"], "amount_usd": s["amount_usd"],
                       "paid_usd": s["paid_usd"], "holds_so_far": s["holds"]})
    if reply["decision"] == "hold":
        return {"status": "hold", "holds": s["holds"] + 1}
    if reply["decision"] == "reject":
        return {"status": "rejected"}
    if reply["decision"] == "approve" and reply["amount_usd"] == s["amount_usd"]:
        return {"status": "approve"}
    return {"status": "escalated"}  # another amount, or an answer the gate does not know

def after_approve(s):
    if s["status"] == "approve": return "write"
    if s["status"] == "rejected": return "end"
    if s["status"] == "hold" and s["holds"] < MAX_HOLDS: return "approve"  # pauses again at interrupt()
    return "escalate"  # a second hold, or an amount that changed

def write(s):
    key = f"{s['case_id']}:refund:{s['order_id']}"  # built from the case, so a restart builds the same key
    db = ledger()
    db.execute("insert or ignore into refunds values (?, ?, ?)", (key, s["order_id"], s["amount_usd"]))
    db.commit(); db.close()
    return {"status": "refunded"}

# %% [markdown]
# `build` wires the nodes and the exits, and attaches the SQLite checkpointer. Every call opens its own connection, the way a restarted process would.

# %%
def build(path):
    g = StateGraph(Case)
    g.add_node("approve", approve)
    g.add_node("write", write)
    g.add_node("escalate", lambda s: {"status": "escalated"})
    g.add_conditional_edges(START, policy_route, {"write": "write", "approve": "approve", "escalate": "escalate"})
    g.add_conditional_edges("approve", after_approve, {"write": "write", "approve": "approve",
                                                       "escalate": "escalate", "end": END})
    g.add_edge("write", END)
    g.add_edge("escalate", END)
    # check_same_thread=False: LangGraph may use the connection from another thread.
    # The caller closes it: graph.checkpointer.conn.close().
    return g.compile(checkpointer=SqliteSaver(sqlite3.connect(path, check_same_thread=False)))

# %% [markdown]
# `run` is the one call a process makes: it builds the graph, runs it and closes the file. The check below prints the graph's drawable structure. No run is needed for that.

# %%
def run(payload, cfg=None):  # one call = one process: build, run, close the file
    g = build(DB)
    try:
        return g.invoke(payload, cfg)
    finally:
        g.checkpointer.conn.close()

g = build(DB)
# get_graph() returns the drawable structure of the graph. No run is needed.
print("nodes:", sorted(n for n in g.get_graph().nodes if not n.startswith("__")), "| checkpointer: SQLite")
g.checkpointer.conn.close()

def paid_out():  # (refunds written, total paid out in USD)
    db = ledger()
    n, total = db.execute("select count(*), coalesce(sum(amount_usd), 0) from refunds").fetchone()
    db.close()
    return n, total

# %% [markdown]
# ### Step 3: pause, show the arguments, and stop the process
# `invoke` runs until `interrupt()`, then returns. The result holds the value the reviewer sees, in the result under `__interrupt__`. The ledger is still empty. Then the process ends: the connection closes, the graph object is deleted, and only the SQLite file is left.

# %%

case = {"case_id": "C-17", "order_id": ORDER, "amount_usd": proposal["amount_usd"],
        "paid_usd": PAID, "holds": 0, "status": "new"}
config = {"configurable": {"thread_id": "C-17"}, "recursion_limit": 10}  # the step cap is explicit

graph = build(DB)
out = graph.invoke(case, config)
print("paused. the reviewer sees:", out["__interrupt__"][0].value)
print("ledger while paused (refunds, total USD):", paid_out())
graph.checkpointer.conn.close()  # the process ends here: close the file
del graph  # the paused state is in checkpoints.db

# %% [markdown]
# ### Step 4: a new process resumes the same case
# The new process builds the same graph, opens the same file and resumes with the reviewer's answer. `run` does those steps, as a new process would. The reviewer echoes the amount they approved. `write` runs once, and the ledger holds one refund.

# %%
out = run(Command(resume={"decision": "approve", "amount_usd": 120.0}), config)
print("status:", out["status"], "| ledger (refunds, total USD):", paid_out())

# %% [markdown]
# ### Step 5: the other exits, each with its own case
# A small reviewer script drives each case. Each reply resumes the case in a new graph object. Case C-18 is held twice and escalates. Case C-19 is rejected. Case C-20 is a 30 USD partial refund, under the limit, so it never pauses.

# %%
def run_case(case_id, amount, replies):
    state = {"case_id": case_id, "order_id": ORDER, "amount_usd": amount,
             "paid_usd": PAID, "holds": 0, "status": "new"}
    cfg = {"configurable": {"thread_id": case_id}, "recursion_limit": 10}
    out = run(state, cfg)
    for reply in replies:
        if "__interrupt__" not in out: break
        shown = out["__interrupt__"][0].value
        print(f"  {case_id}: reviewer sees {shown['amount_usd']} USD on {shown['order_id']}, answers {reply['decision']}")
        out = run(Command(resume=reply), cfg)
    return out["status"]

print("C-18 ->", run_case("C-18", 120.0, [{"decision": "hold"}, {"decision": "hold"}]))
print("C-19 ->", run_case("C-19", 120.0, [{"decision": "reject"}]))
print("C-20 ->", run_case("C-20", 30.0, []), "| ledger (refunds, total USD):", paid_out())

# %% [markdown]
# ### Step 6: the step cap, when no person is in the loop
# This sample is separate from the refund gate. It only shows the step cap: a refund waiting on a delivery scan, polled until the scan arrives. The stand-in carrier never delivers.
#
# Each node run is one step. `RemainingSteps` tells a node how many steps are left before `recursion_limit`. The check gives up with fewer than 3 steps left. With `recursion_limit` 8, the loop polls 6 times, then gives up with 2 steps left. LangGraph fills `RemainingSteps` itself; do not pass it in.
#
# A chosen `recursion_limit` is better: a stuck loop stops after the few calls you picked, and the config shows the limit to the next reader.

# %%
from langgraph.managed import RemainingSteps

class Scan(TypedDict):
    polls: int
    remaining_steps: RemainingSteps
    status: str

def scan_graph(check):
    def route(s):  # with the check: give up while 3 steps are left
        return "give_up" if check and s["remaining_steps"] < 3 else "poll"
    g = StateGraph(Scan)
    g.add_node("poll", lambda s: {"polls": s["polls"] + 1})  # stand-in carrier: "in transit" every time
    g.add_node("give_up", lambda s: {"status": "escalated: no delivery scan"})
    g.add_edge(START, "poll")
    g.add_conditional_edges("poll", route, {"poll": "poll", "give_up": "give_up"})
    g.add_edge("give_up", END)
    return g.compile()

out = scan_graph(True).invoke({"polls": 0, "status": ""}, {"recursion_limit": 8})
print("with the check:", out["status"], "| polls:", out["polls"])

# %% [markdown]
# Without the check, the same loop reaches the cap and stops with an error. The cap is the only exit left.

# %% tags=["raises-exception"]
# Wrong: no check. Nothing ends the loop but the cap, so the run stops with an error.
scan_graph(False).invoke({"polls": 0, "status": ""}, {"recursion_limit": 8})  # GraphRecursionError

# %% [markdown]
# ## Under the hood
# A plain loop can express the same four exits. It cannot pause across a restart, because its position lives in a Python variable. That is the part the checkpointer adds. Below is the gate written by hand, to show the logic that the graph above implements. It is not used anywhere else in this lesson.

# %%
def gate(case_id, ask, amount, max_holds=2, max_rounds=5):
    """One approval loop with four exits. `ask` shows the case and returns the reply."""
    holds = 0
    for _ in range(max_rounds):  # the step cap, chosen by us
        reply = ask(case_id, amount)  # a real system pauses here: a queue, a page, a form
        if reply["decision"] == "reject":
            return "rejected"
        if reply["decision"] == "approve":
            return "refunded" if reply["amount_usd"] == amount else "escalated"  # echo must match
        if reply["decision"] != "hold":
            return "escalated"  # an answer the gate does not know: never guess
        holds += 1
        if holds >= max_holds:
            return "escalated"
    return "escalated"  # the cap ran out

answers = iter([{"decision": "hold"}, {"decision": "approve", "amount_usd": 120.0}])
print("hand-written gate:", gate("C-21", lambda c, a: next(answers), 120.0))

# %% [markdown]
# ## At work
# - **A coding agent's pull request is the pause.** Stripe's Minions open pull requests that people review and merge, over 1,000 a week (Stripe blog, 2026-02-09). The PR waits for a person; the merge is the approve node. → lesson 24 builds the checkpoint with approvals and isolated runs.
# - **A paused run should cost nothing.** LangGraph's `interrupt()` waits on a checkpoint, and Temporal's LangGraph plugin (preview, 2026) keeps that wait durable for days. Which store you pick is the durability choice in lesson 26a.
# - **Approval fatigue breaks the gate.** If every step asks, people click "approve" without reading. Permission modes and `canUseTool` in the Claude Agent SDK ask only for the risky calls, and least privilege limits what a loop can ask for at all. → lesson 23 sets the permissions.
#
# Go deeper: `interrupt()` with `Command(update=...)` to change state on resume, and the LangGraph human-in-the-loop docs for review UIs.
#
# %% [markdown]
# ## Common mistakes
# Wrong: resume without saying which case. A checkpointer needs a `thread_id`, so the resume has nothing to load. The error names the missing key. Fix: pass the same `config` the run started with.

# %% tags=["raises-exception"]
run(Command(resume={"decision": "approve", "amount_usd": 120.0}))  # no config: no thread_id

# %% [markdown]
# Silent mistakes: no error is raised, so check the ledger.
#
# - Wrong: a write before `interrupt()`. On resume the node runs again, so the write runs twice. Fix: put the write after the gate, as `write` does, and keep the key the same on every run.
# - Wrong: write the model's amount, not the amount the reviewer echoed. The reviewer approved the value you showed. Fix: write only the value the reviewer saw and echoed, as `approve` checks.

# %% [markdown]
# ## Production checklist
# Before a loop with approvals runs unattended, check each line. A "no" means a person must start or check the run.
#
# - [ ] Every risky write sits after a named gate, and nothing before the gate writes.
# - [ ] The reviewer sees the real arguments, not a summary, and echoes the one value that matters.
# - [ ] The state and the checkpoint live in a store that survives a restart.
# - [ ] Holds, retries and steps each have a limit, and the limit leads to escalation, not silence.
# - [ ] `recursion_limit` is set in every run's config, to a number you chose.
#
# ## Try it
# A reviewer approves 100 USD on case C-22, where the refund is for 120 USD. Predict the status, then run it: does the ledger change? Then write the reply that approves the right amount, and check that the ledger gains one refund. It uses `run_case` from Step 5.
#
# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
print("C-22 ->", run_case("C-22", 120.0, [{"decision": "approve", "amount_usd": 100.0}]))
print("ledger (refunds, total USD):", paid_out())  # unchanged: the mismatch escalates, nothing is written
print("C-23 ->", run_case("C-23", 120.0, [{"decision": "approve", "amount_usd": 120.0}]))
print("ledger (refunds, total USD):", paid_out())  # one more refund

# %% [markdown]
# The lesson's model calls are all recorded now. This last cell closes the recording.

# %%
llm_replay.stop()  # saves the recording

# %% [markdown]
# ## Recap
# - `interrupt()` pauses a run at a named node and saves its state under a `thread_id`. A new process resumes with `Command(resume=...)`.
# - The paused node runs again from its first line, so put every write after the gate. Show the reviewer the real arguments and check the echoed value.
# - Every exit is explicit: refunded, rejected, escalated. Holds are counted, and the step cap is an explicit `recursion_limit`. `RemainingSteps` lets a loop give up before the cap.
# - No model decides the gate. The model only proposed the refund, and the rules and the reviewer decided it.
#
# **Interview:** How do you add human approval to an agent loop that must survive a restart? Strong answer: pause at one named node with a checkpointer, show the exact arguments, resume on the same thread id with the reviewer's reply, and check that the approved amount is the one written. Count the holds, set an explicit recursion limit, and escalate on give-up.

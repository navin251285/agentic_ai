# %% [markdown]
# # 08 · Checkpoint: the desk loop with caps, a verifier and a stuck detector
# Level L1 · Part 1 · core · ~30 min · builds on 05, 06, 07
#
# ## Goal
# Run two loops that you assembled yourself, the support desk and the pocket-cart fix loop. Each one ends on a mechanical stop inside a budget, and every run ends in one of four exits: done, stuck, over budget or hand off.
#
# ## Why it matters
# Lessons 05, 06 and 07 each gave you one piece. Used alone, each piece leaves a gap:
#
# | Piece alone | What goes wrong |
# |---|---|
# | Caps (lesson 05) | A refund that gets the same 503 is retried until the cap ends the bill. Nothing says the customer is still owed money. |
# | Stuck check (lesson 06) | A loop that changes its arguments on every turn can spend its whole budget before a repeat shows up. |
# | Verifier (lesson 07) | The stop is right for code, but nothing caps the spend, and a desk refund has no test to run. |
#
# Together, a loop stops on a check it can read, never runs past its caps, and hands a case it cannot finish to a person. You do not need this for one model call with no tools: there is no next turn to stop.

# %% [markdown]
# The first code cell starts the recording layer. It makes no model call.

# %%
import sys; sys.path.insert(0, "..")
import llm_replay
llm_replay.start("08_checkpoint-basic")  # records the model calls once, replays them later

# %% [markdown]
# ## The idea
# **One loop controller runs the model, counts every reply against a budget, checks for repeats, and runs the tools only when every check passes. The verifier decides "done" for code. A desk run ends in one of four exits: done, stuck, over budget, or hand off when a refund is still owed and nothing was written.**
#
# Analogy: an aircraft checklist. A fuel limit (the budget), a warning light that comes on twice for the same fault (the stuck check), and an instrument reading that says the runway is clear (the verifier). The checklist decides when to land, not the pilot's feeling.

# %% [markdown]
# ## Picture
# Every reply is counted first. The caps and the stuck check run before the tools, and the stuck check runs again after them.
#
# ```mermaid
# flowchart TD
#   R["model reply"] --> C["count it: turns, tokens, dollars"]
#   C -->|"no tool call"| D["done: answered"]
#   C -->|"a cap reached"| B["over budget: the tools do not run"]
#   C -->|"under every cap"| S["stuck check, before the tools"]
#   S -->|"repeat"| K["stuck"]
#   S -->|"no repeat"| T["run the tools"]
#   T --> V["stuck check, after the tools"]
#   V -->|"same error twice, or a flat write"| K
#   V -->|"no repeat"| R
#   B -->|"refund still owed"| H["hand off to a person"]
#   K -->|"refund still owed"| H
# ```

# %% [markdown]
# ## Requirements
# 1. `run_desk(question, budget, owed)`: caps checked after each reply and before its tools run; stuck checked before and after the tools; returns one exit.
# 2. A budget with three caps (turns, tokens, dollars). Each reply is counted once, from its usage. `None` switches a cap off.
# 3. `run_fix(case, budget, propose)`: pytest's exit code decides done. The same failure lines twice is stuck. A red run is reverted with git. A test edit is refused.
# 4. A run that owes a refund and wrote none never ends as done.
# 5. This notebook makes at most 5 model calls. The 5 calls split: run 1: 1, run 2: 2, run 3: 1, fix: 1.

# %% [markdown]
# ## Build it
# Each step gives you the pieces from lessons 05 to 07 and one `your code here` cell. Write your version first. The **Answer** cell after it is one working version. The runs in this notebook use whichever version was defined last.
#
# About half of the code below is setup you already wrote; you write `finish`, `run_desk` and `run_fix` (about 60 lines).

# %% [markdown]
# ### Step 1: the setup from lessons 05 and 06 (no model call)
# Orders, the refund tool with its schema, the budget and the stuck rules. This is the earlier code in a shorter form, with the same behaviour.

# %%
# setup from earlier lessons (05 and 06): orders, refund tool, budget and stuck rules
import hashlib, json
from dataclasses import dataclass
from pydantic import BaseModel, Field, ValidationError
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

ORDERS = {  # generated for this course: four invented orders
    "BS-1042": {"customer": "C-17", "item": "Trail jacket", "paid_usd": 120.0, "status": "delivered"},
    "BS-1043": {"customer": "C-22", "item": "Rain shell", "paid_usd": 85.0, "status": "delivered"},
    "BS-1044": {"customer": "C-17", "item": "Merino socks", "paid_usd": 18.0, "status": "shipped"},
    "BS-1045": {"customer": "C-22", "item": "Rain shell", "paid_usd": 40.0, "status": "delivered"},
}
PAYMENT_DOWN = {"BS-1045"}  # the stand-in payment service answers 503 for this order, every time
REFUNDS = []  # state outside the model: a refund is written here
SYSTEM = "You are the support desk for Brightside Outfitters. Look up the order before any refund. Never refund more than was paid."
# provokes a retry loop on purpose, as in lesson 06; it also drops the look-up-first rule
RETRY_SYSTEM = ("You are the support desk for Brightside Outfitters. Never refund more than was paid. "
                 "If a refund fails, call issue_refund again with the same amount; the payment service often recovers on a retry.")

# %% [markdown]
# The refund schema and the two tools from lesson 04. A bad amount never reaches the function body.

# %%
class RefundArgs(BaseModel):
    order_id: str = Field(pattern=r"^BS-\d{4}$", description="Order id in the form BS-1042")
    amount_usd: float = Field(gt=0, description="Amount to refund in US dollars, more than 0")

@tool
def get_order(order_id: str) -> str:
    """Look up one order: customer, item, amount paid and delivery status."""
    return str(ORDERS[order_id]) if order_id in ORDERS else f"error: no order {order_id}"

@tool(args_schema=RefundArgs)
def issue_refund(order_id: str, amount_usd: float) -> str:
    """Refund an amount on one order. The amount may not be more than the amount paid."""
    order = ORDERS.get(order_id)
    if order is None:
        return f"error: no order {order_id}"
    if order_id in PAYMENT_DOWN:
        return f"error: payment service returned 503 for {order_id}"
    if amount_usd > order["paid_usd"]:
        return f"error: {amount_usd} is more than the {order['paid_usd']} paid. Refund at most the amount paid."
    REFUNDS.append({"order_id": order_id, "amount_usd": amount_usd})
    return f"refunded {amount_usd} on {order_id}"

TOOLS = [get_order, issue_refund]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}
SCHEMAS = {"issue_refund": RefundArgs}  # the tools that have a schema
WRITE_TOOLS = {"issue_refund"}
print("tools:", [t.name for t in TOOLS], "| writes:", sorted(WRITE_TOOLS))

# %% [markdown]
# `run_tool` turns a failed tool call into a message the model can read. `CHECKPOINT` keeps every run for the table at the end.

# %%
CHECKPOINT = []  # every run of this notebook, read at the end

def run_tool(call):
    """A failed tool becomes a tool message the model reads on its next turn."""
    try:
        result = str(TOOLS_BY_NAME[call["name"]].invoke(call["args"]))
    except Exception as exc:  # bad arguments or an unknown tool: the model sees the text
        result = f"error: {exc}"
    return ToolMessage(content=result, tool_call_id=call["id"])

# %% [markdown]
# The budget, the caps and the stuck rules, from lessons 05 and 06. No model call.

# %%
PRICE = {"input": 0.10, "output": 0.40}  # USD per 1M text tokens, Gemini list price read 2026-10-27 (lesson 02)

@dataclass
class Budget:
    """Caps for one run. None switches a cap off. The counters start at zero."""
    max_turns: int = 6
    max_tokens: int | None = None
    max_usd: float | None = None
    turns: int = 0
    tokens: int = 0
    usd: float = 0.0

print(Budget(max_turns=2, max_usd=0.01))

# %% [markdown]
# Counting: `record` adds a desk reply's turn, tokens and dollars. `count` is split out because the fix loop counts its own turn. The caps are checked after each reply.

# %%
def count(budget, reply):
    """Add one reply's tokens and dollars to the budget (no turn)."""
    usage = reply.usage_metadata
    budget.tokens += usage["total_tokens"]
    budget.usd += (usage["input_tokens"] * PRICE["input"] + usage["output_tokens"] * PRICE["output"]) / 1_000_000

def record(budget, reply):
    """Count one model reply: its turn, its tokens and its dollars."""
    budget.turns += 1
    count(budget, reply)

def exceeded(budget):
    """The first cap reached, or None. Called after every reply."""
    if budget.turns >= budget.max_turns:
        return "turn_cap"
    if budget.max_tokens is not None and budget.tokens >= budget.max_tokens:
        return "over_budget_tokens"
    if budget.max_usd is not None and budget.usd >= budget.max_usd:
        return "over_budget_usd"
    return None

# %% [markdown]
# The canonical text of a call, the state fingerprint and the stuck rules (lesson 06).

# %%
def canon(name, args):
    """The call as text, after the schema has fixed the types: 40 and 40.0 become one text."""
    schema = SCHEMAS.get(name)
    try:
        args = schema(**args).model_dump() if schema else args
    except ValidationError:
        pass  # the tool returns the error text, so the raw arguments are compared
    return json.dumps(args, sort_keys=True)

def state_hash():
    """A fingerprint of everything the tools can change."""
    return hashlib.sha256(json.dumps({"orders": ORDERS, "refunds": REFUNDS}, sort_keys=True).encode()).hexdigest()[:12]

# %% [markdown]
# The stuck rules: the same call three times, the same error twice, or a write that leaves the state flat.

# %%
def stuck_reason(steps, repeats=3):
    """Why the run is stuck, or None. Reads only the steps so far."""
    last = steps[-repeats:]
    # clause 1: the same call `repeats` times in a row (no run below reaches it)
    if len(last) == repeats and last[0]["calls"] and all(s["calls"] == last[0]["calls"] for s in last):
        return f"the same call {repeats} times in a row"
    # clause 2: the same error twice in a row (run 2 stops here, after its second 503)
    errors = [text for s in steps for _, text in s["results"] if text.startswith("error")]
    if len(errors) >= 2 and errors[-1] == errors[-2]:
        return "the same error twice, even with a success between"
    # clause 3: a write tried `repeats` times with the state flat (no run below reaches it)
    writes = [s["state"] for s in steps if s["state"] is not None and any(n in WRITE_TOOLS for n, _ in s["calls"])]
    if len(writes) >= repeats and len(set(writes[-repeats:])) == 1:
        return f"a write was tried {repeats} times and the state did not change"
    return None

# %% [markdown]
# ### Step 2: the model
# The model is the course default, bound to the refund and lookup tools. The helper is the one from lesson 02. The key comes from `.env`, and a recording replays without one.

# %% tags=["needs-llm"]
from llm_setup import DEFAULT_MODELS, get_llm

llm = get_llm(model=DEFAULT_MODELS["gemini"])  # the key comes from .env
llm_tools = llm.bind_tools(TOOLS)  # the tool list travels with every call

# %% [markdown]
# ### Step 3: build the desk loop
# Write `run_desk(question, budget, owed)`. It returns a dictionary with `stop`, `exit`, `answer`, `why`, `turns`, `usd`, `refunds` and `steps`. A single helper `finish(stop, answer, why, budget, steps, owed)` can build that dictionary: `why` holds the stuck reason (or `None`), and `answer` holds the model's text (or `None`).
#
# 1. Call `llm_tools.invoke(messages)`, then `record(budget, reply)`, and add one step record.
# 2. No tool call: stop `answered`. A cap reached: stop with the cap's name, and the tools of this reply do not run.
# 3. Check `stuck_reason` before the tools and again after them.
# 4. Exit: `done` if answered; `hand off` if `owed` and no refund was written; otherwise `stuck` or `over budget`.

# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
def finish(stop, answer, why, budget, steps, owed):
    """One return value for every run: the stop, the exit and the evidence."""
    # the owed refund comes first: a run that still owes one is never done
    if owed and not REFUNDS:
        exit_ = "hand off"  # a refund is still owed: a person takes the case
    elif stop == "answered":
        exit_ = "done"
    else:
        exit_ = "stuck" if stop == "stuck" else "over budget"
    return {"stop": stop, "exit": exit_, "answer": answer, "why": why, "turns": budget.turns,
            "usd": budget.usd, "refunds": list(REFUNDS), "steps": steps}

# %% [markdown]
# The loop itself: one reply per turn, counted, checked, then its tools.

# %% tags=["solution"]
def run_desk(question, budget, owed, system=SYSTEM):
    """The desk loop: caps after each reply and before its tools; stuck before and after the tools."""
    REFUNDS.clear()
    messages = [SystemMessage(content=system), HumanMessage(content=question)]
    steps = []
    while True:
        reply = llm_tools.invoke(messages)  # one paid model call: the whole list is sent again
        messages.append(reply)
        record(budget, reply)
        step = {"calls": [(c["name"], canon(c["name"], c["args"])) for c in reply.tool_calls],
                "results": [], "state": None}
        steps.append(step)
        if not reply.tool_calls:
            return finish("answered", reply.text, None, budget, steps, owed)
        if (cap := exceeded(budget)):
            return finish(cap, None, None, budget, steps, owed)  # this reply's tools do not run
        if (why := stuck_reason(steps)):
            return finish("stuck", None, why, budget, steps, owed)
        for call in reply.tool_calls:
            result = run_tool(call)
            messages.append(result)
            step["results"].append((call["name"], result.content))
        step["state"] = state_hash()
        if (why := stuck_reason(steps)):
            return finish("stuck", None, why, budget, steps, owed)

# %% [markdown]
# ### Step 4: run the desk three times
# Run 1 gets one reply, so its lookup must not run. Run 2 is the failing refund from lesson 06. It uses `RETRY_SYSTEM`, the lesson 06 prompt that tells the model to retry a failed refund and has no look-up-first rule. BS-1045 returns a 503 every time, so the model retries and the stuck check ends the run after the second identical error. The stuck check does not depend on the prompt. Run 3 is a question the desk answers without a tool.
#
# `owed` means a refund is still open: a write task the caller opened while `REFUNDS` is empty. In a real desk the ticket system sets it, never the model. Run 1 ends over budget, not hand off, because `owed` is `False` and its cap stopped it first.

# %% tags=["needs-llm"]
desk_runs = [
    ("status, a cap of one reply", "Customer C-17 asks for the status of order BS-1044. Look it up.",
     Budget(max_turns=1), False, SYSTEM),
    ("refund that keeps failing", "Customer C-22 says the rain shell from order BS-1045 arrived torn. Refund the 40 USD paid on BS-1045 now.",
     Budget(max_turns=3), True, RETRY_SYSTEM),
    ("a question from the instructions", "In one sentence: can the desk refund more than was paid?",
     Budget(max_turns=6, max_usd=0.01), False, SYSTEM),
]
for name, question, budget, owed, system in desk_runs:
    res = run_desk(question, budget, owed, system)
    CHECKPOINT.append((name, res))
    for i, step in enumerate(res["steps"], 1):
        for call_name, args in step["calls"]:
            print(f"  turn {i}: model asks {call_name}({args})")
        for call_name, text in step["results"]:
            print(f"  turn {i}: {call_name} returns {text}")
    if res["answer"]:
        print("  model says:", res["answer"])
    print(f"{name}: stop {res['stop']} -> exit {res['exit']} | turns {res['turns']} | refunds {res['refunds']}\n")

# %% [markdown]
# ### Step 5: the pocket-cart repo and its verifier (no model call)
# The example is **pocket-cart** from lesson 07: 6 modules, 12 failing tests. This checkpoint fixes `pricing.py`. The other module lesson 07 left out, the cart, is the first job of the Ralph loop in lesson 11. The repo is copied before each run, and every red run is reverted. The helpers are the ones from lesson 07, in a shorter form.

# %%
# setup from earlier lessons (07): the repo copy, the verifier and the revert
import os, shutil, subprocess, sys
from pathlib import Path

SRC = Path("../data/pocket-cart")  # generated by data/make_pocket_cart.py; read only here
WORK = Path("../data/08/work")     # run-time copies: the loop never edits SRC
PRICING = {"id": "pricing", "file": "pocket_cart/pricing.py", "tests": "tests/test_pricing.py"}

def git(work, *args):
    """Run git in a work copy. The identity is a placeholder for these local commits."""
    return subprocess.run(["git", "-c", "user.name=loop", "-c", "user.email=loop@example.com", *args],
                          cwd=work, capture_output=True, text=True, check=True).stdout

def fresh_copy(name):
    """A new copy of the repo, committed as the baseline, so a red run can be reverted."""
    work = WORK / name
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(SRC, work)
    git(work, "init", "-q")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "baseline")
    return work

# %% [markdown]
# The verifier: pytest in the copy. Only exit code 0 ends the run as done.

# %%
def verify(work, tests=()):
    """The verifier: pytest in the work copy. Returns the exit code and the FAILED lines."""
    python = os.path.abspath(sys.executable)  # a relative path breaks in another folder
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "COLUMNS": "200"}
    run = subprocess.run([python, "-m", "pytest", "-q", "--color=no", "-p", "no:cacheprovider", *tests],
                         cwd=work, capture_output=True, text=True, env=env)
    return run.returncode, [line for line in run.stdout.splitlines() if line.startswith("FAILED")]

def revert(work):
    """Undo every uncommitted edit in the work copy."""
    git(work, "checkout", "--", ".")

def touched_tests(work):
    """Files under tests/ that changed since the baseline. A run that edits a test is refused."""
    return git(work, "status", "--porcelain", "--", "tests").strip().splitlines()

code, failed = verify(fresh_copy("first-look"), [PRICING["tests"]])
print("pricing before the fix: exit code", code, "| failing lines:", failed)

# %% [markdown]
# ### Step 6: build the fix loop
# Write `run_fix(case, budget, propose)`. It returns a dictionary with `id`, `stop`, `exit`, `turns`, `green` and `ok`.
#
# 1. Copy the repo with `fresh_copy`, then run `verify` for the first failing lines.
# 2. While red: stop on a cap (`exceeded`) before the next turn. Otherwise count the turn and write `propose(work, case, failed, budget)` to the case's file. `propose` returns the whole new module text; `run_fix` writes it and adds the turn. `propose` only adds tokens and dollars, through `count`.
# 3. Verify again. The same `FAILED` lines as the turn before means stuck.
# 4. A red run is reverted. A touched test means the run is refused: exit `hand off`.
# 5. Exit: `done` if green and untouched; `hand off` if a test was touched; `stuck`; otherwise `over budget`. `ok` is true only when green and untouched, and the exit reads the same facts in that order.

# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
def run_fix(case, budget, propose):
    """The fix loop: pytest's exit code decides done; the same failure twice is stuck; a cap ends the run."""
    work = fresh_copy(case["id"])
    code, failed = verify(work, [case["tests"]])
    stop = "done"
    while code != 0:
        if (cap := exceeded(budget)):
            stop = cap
            break
        budget.turns += 1  # a proposal is one turn, whoever writes it
        (work / case["file"]).write_text(propose(work, case, failed, budget))
        previous, (code, failed) = failed, verify(work, [case["tests"]])
        if code != 0 and failed == previous:
            stop = "stuck"
            break
    touched = touched_tests(work)
    if code != 0:
        revert(work)  # a red run leaves no edits behind
    ok = code == 0 and not touched
    exit_ = "done" if ok else "hand off" if touched else "stuck" if stop == "stuck" else "over budget"
    return {"id": case["id"], "stop": stop, "exit": exit_, "turns": budget.turns, "green": code == 0, "ok": ok}

print("run_fix ready: the controls below test it before any model call")

# %% [markdown]
# ### Test your `run_fix` before you spend a model call
# Two candidates that make no model call. The first writes the file back unchanged, so the same failure comes back and the loop stops as stuck. The second edits a test, so the loop refuses the run and the exit is hand off. Lesson 07 showed this refusal; here it is checked by the same loop.

# %%
unchanged = lambda work, case, failed, budget: (work / case["file"]).read_text()  # the file as it is

def tamper(work, case, failed, budget):
    """A candidate that edits a test: the loop refuses the run (exit hand off)."""
    spec = work / case["tests"]
    spec.write_text(spec.read_text() + "\n# edited by the loop\n")
    return (work / case["file"]).read_text()

for name, candidate in [("control: the file unchanged", unchanged), ("control: a test edited", tamper)]:
    res = run_fix(PRICING, Budget(max_turns=2), candidate)
    CHECKPOINT.append((name, res))
    print(f"{name}: stop {res['stop']} -> exit {res['exit']} | turns {res['turns']} | green {res['green']}")

# %% [markdown]
# ### Step 7: the model's fix
# `model_fix` asks the model for the whole new module, from its source, its spec and the failing lines. It counts the reply's tokens and dollars in the budget. The budget gives the model one turn, so a second call cannot happen. The controls above ran first with no model call, so the loop is tested before the model is paid for.

# %% tags=["needs-llm"]
FIX_SYSTEM = ("You fix one module of a small Python shop. Reply with the complete new text of that module "
              "only: no explanation and no code fences. The tests are the spec. Never change them.")
print("fix prompt:", FIX_SYSTEM[:60] + "...")

def model_fix(work, case, failed, budget):
    """One model turn: the whole new module. Its tokens and dollars count in the budget."""
    source = (work / case["file"]).read_text()
    spec = (work / case["tests"]).read_text()
    reply = llm.invoke([SystemMessage(content=FIX_SYSTEM),
                        HumanMessage(content=f"Module:\n{source}\nSpec (tests):\n{spec}\nStill failing:\n" + "\n".join(failed))])
    count(budget, reply)
    text = reply.text.strip()
    if text.startswith("```"):  # models sometimes add code fences: keep the code only
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return text + "\n"

fix_budget = Budget(max_turns=1, max_usd=0.01)  # one model turn for this module
pricing = run_fix(PRICING, fix_budget, model_fix)
CHECKPOINT.append(("pocket-cart pricing, model fix", pricing))
print(f"{pricing['id']}: stop {pricing['stop']} -> exit {pricing['exit']} | turns {pricing['turns']} | "
      f"green {pricing['green']} | usd {fix_budget.usd:.6f}")

# %% [markdown]
# ## Reference solution
# The answers above are one working version of each loop. Expand the hidden cell for the exit table of every run in this notebook. Check two things: each run has one exit, and no run that owed a refund ended as done.

# %% tags=["solution"]
for name, res in CHECKPOINT:
    print(f"{name:34s} stop {res['stop']:<20s} exit {res['exit']:<11s} turns {res['turns']}")

# %% [markdown]
# Save the recording. This cell is the last code cell of the notebook.

# %%
llm_replay.stop()  # saves the recording

# %% [markdown]
# ## At work
# - Production loops stop on a deterministic test, caps and a no-progress rule, then hand the case to a person with the evidence. This notebook counts turns, tokens and dollars; teams add a time cap. → lesson 27 counts stop reasons per run.
# - Gates run deterministic checks first, and a model judge only where no test exists. A loop that may edit its own tests passes its own check. → lesson 14
# - A cap is a pause, not a crash. Teams save the state at the cap and resume later. → lesson 26a
# - A stuck refund goes to a person through an approval or hand-off step, never to a silent retry. → lesson 22

# %% [markdown]
# ## Recap
# - Every reply is counted before its tools run, so the caps and the stuck check see every paid call.
# - Four exits: done, stuck, over budget and hand off. The owed-refund rule: a run that owes a refund and wrote none is never done.
# - The verifier decides done for code: pytest's exit code, not the model's word.
#
# **Interview:** "Design an agent loop that cannot run away." A strong answer: caps on turns, tokens and dollars, counted from each reply's usage and checked before the tools run; a stuck check on repeated calls, repeated errors and flat writes; a deterministic verifier decides done; each run ends in one exit, and open work goes to a person with the evidence.

# %% [markdown]
# ## Key terms
# - **budget** — the caps for one run (turns, tokens, dollars, time); each cap can be off (`None`); counted in your code (lesson 05)
# - **exit (of a run)** — one of four ways a run ends: done, stuck, over budget or hand off (lesson 06)
# - **hand off** — the exit for a run that still owes work: the case goes to a person with the evidence (lesson 06)
# - **stuck** — a stop reason: a no-progress rule fired before the next paid call (lesson 06)
# - **verifier** — the check that decides whether a result is done; for code, the pytest exit code (lesson 07)

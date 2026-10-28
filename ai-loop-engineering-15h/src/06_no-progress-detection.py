# %% [markdown]
# # 06 · Knowing when the loop is stuck: repeated calls and the four exits
# Level L1 · Part 1 · core · ~20 min · builds on 03, 04, 05
#
# ## Goal
# Detect a loop that repeats itself (the same call asked again, the same error twice, a write that changes nothing), and end every run in one of four exits: done, stuck, over budget or hand off.
#
# ## Why it matters
# Without a stuck check, the loop retries a failing step until a cap ends it. The customer's refund is refused by a payment service that answers 503 every time. The loop asks again, gets the same error, asks again. With a cap of 50 turns that is 50 paid model calls and 50 identical errors, and the customer hears nothing. A cap ends the bill. It does not notice that the work is going nowhere. Loops like this are often started by a prompt that says "retry on failure", as in run A below, not by the model alone.
#
# With a stuck check, the loop reads its own history. The same error twice means the next retry will fail too, so it stops, and a person receives the case with the evidence attached.
#
# You do not need a stuck check for a task with one or two tool calls, where a repeat costs little. Use it as soon as a loop can retry a write.

# %% [markdown]
# The first code cell starts the recording layer. It makes no model call.

# %%
import sys; sys.path.insert(0, "..")
import llm_replay
llm_replay.start("06_no-progress-detection")  # records the model calls once, replays them later

# %% [markdown]
# ## The idea
# **A stuck check reads the steps so far and says "stop" when nothing new is happening. Three signals are cheap: the same call asked three times in a row, the same error twice (even with a success between), and a write whose state fingerprint stays flat. Every run ends in one of four exits: done (the model answered), stuck (a signal fired), over budget (a cap fired) or hand off (work is still owed, so a person takes it).**
#
# Analogy: a parcel tracker that says "in transit" for nine days with no new scan. You stop refreshing and call the courier, because more refreshes show the same thing.
#
# ## Picture
# Each reply goes through the checks in the order the numbers show. Checks 1 to 3 run before a reply's tools, check 4 after them.
#
# ```mermaid
# flowchart TD
#   R["model reply"] -->|"1. no tool call: done"| D["done: answered"]
#   R -->|"2. a cap reached (lesson 05)"| O["over budget"]
#   R -->|"3. same call 3 times in a row"| S["stuck"]
#   R -->|"tools run, then check 4"| T["run the tools"]
#   T -->|"4. same error twice, or a write with flat state"| S
#   O -->|"work still owed"| H["hand off to a person"]
#   S -->|"work still owed"| H
# ```

# %% [markdown]
# ## Step by step
# 1. Keep one record per model reply: the calls it asked for, their results, and a state fingerprint after the tools ran.
# 2. Before a reply's tools run, check in order: no tool call, the cap, then the identical-call rule. A stopped reply runs no tools.
# 3. After the tools run, check the same-error rule and the flat-write rule.
# 4. Map each stop to one of the four exits. Open work decides between hand off and the others.
# 5. Run three requests with a real model: one that gets stuck, one that hits a cap, and one that finishes.

# %% [markdown]
# ### Step 1: the tools, the budget and the setup from earlier lessons
# This is the setup from lessons 03 to 05: four invented orders, the refund tool with its schema, the tool runner and the turn cap. Order BS-1045 is new here. Its payment service answers 503 every time, as a stand-in for an outage. This cell makes no model call.

# %%
# setup from earlier lessons (03-05): orders, refund tool with schema, tool runner, turn cap
import hashlib, json
from dataclasses import dataclass
from pydantic import BaseModel, Field, ValidationError
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

ORDERS = {  # generated for this lesson: four invented orders
    "BS-1042": {"customer": "C-17", "item": "Trail jacket", "paid_usd": 120.0, "status": "delivered"},
    "BS-1043": {"customer": "C-22", "item": "Rain shell", "paid_usd": 85.0, "status": "delivered"},
    "BS-1044": {"customer": "C-17", "item": "Merino socks", "paid_usd": 18.0, "status": "shipped"},
    "BS-1045": {"customer": "C-22", "item": "Rain shell", "paid_usd": 40.0, "status": "delivered"},
}
PAYMENT_DOWN = {"BS-1045"}  # the stand-in payment service answers 503 for this order, every time
REFUNDS = []  # state outside the model: a refund is written here
SYSTEM = "You are the support desk for Brightside Outfitters. Never refund more than was paid."
# We force the loop by prompt: this desk prompt tells the model to retry a failed refund.
RETRY_SYSTEM = SYSTEM + " If a refund fails, call issue_refund again with the same amount; the payment service often recovers on a retry."

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
SCHEMAS = {"issue_refund": RefundArgs}  # the tools that have a schema (lesson 04)

print("orders:", list(ORDERS), "| payment down for:", sorted(PAYMENT_DOWN))
print("tools:", [t.name for t in TOOLS])

# %% [markdown]
# ### Step 1 (continued): the tool runner and the turn cap
# A failed tool becomes a tool message the model reads on its next turn. The turn cap is lesson 05's cap.

# %%
def run_tool(call):
    """Run one tool call. A failure becomes a tool message the model reads on its next turn."""
    try:
        result = str(TOOLS_BY_NAME[call["name"]].invoke(call["args"]))
    except Exception as exc:  # bad arguments or an unknown tool: the model sees the text
        result = f"error: {exc}"
    return ToolMessage(content=result, tool_call_id=call["id"])

@dataclass
class Budget:
    """The turn cap for one run (lesson 05). The counters start at zero; usd is the running cost."""
    max_turns: int = 6
    turns: int = 0
    usd: float = 0.0

def exceeded(budget):
    """The turn cap, if reached, else None. Called after every reply."""
    return "turn_cap" if budget.turns >= budget.max_turns else None

# %% [markdown]
# ### Step 2: the model and its price
# `get_llm()` is the helper from lesson 02, and the model is the course default. The backend is Gemini on Vertex AI, the kit default. The prices are the Gemini Developer API list prices that lesson 05 used (read 2026-10-27); this lesson applies them as the estimate for the Vertex AI backend.

# %% tags=["needs-llm"]
from llm_setup import DEFAULT_MODELS, get_llm

llm = get_llm(model=DEFAULT_MODELS["gemini"])  # the key comes from .env
llm_tools = llm.bind_tools(TOOLS)  # the tool list travels with every call
print("tools bound to the model:", [t.name for t in TOOLS])
PRICE = {"input": 0.10, "output": 0.40}  # USD per 1M text tokens, list price read 2026-10-27

def record(budget, reply):
    """Count one model reply: its turn and its dollars."""
    usage = reply.usage_metadata
    budget.turns += 1
    budget.usd += (usage["input_tokens"] * PRICE["input"] + usage["output_tokens"] * PRICE["output"]) / 1_000_000

# %% [markdown]
# ### Step 3: the stuck rules
# Three rules read only the steps so far. A step may not have its results yet, so each rule checks what is there. `canon` turns a call into text: the schema from lesson 04 changes `40` into `40.0` first, so the same refund always has one text. The state fingerprint hashes everything the tools can change.
#
# **Flat state means a write was tried and nothing changed.** Only steps that tried a write count toward rule 3. A loop of lookups is not caught by it. Lookups with changing arguments end at a cap. The identical-call rule asks for three repeats, not two: a status poll that asks for the same order twice is normal, and a third identical reply is the first real sign of a loop.

# %%
WRITE_TOOLS = {"issue_refund"}

def state_hash():
    """A fingerprint of everything the tools can change. Same fingerprint, same state."""
    text = json.dumps({"orders": ORDERS, "refunds": REFUNDS}, sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()[:12]

def canon(name, args):
    """The call as text, after the tool's schema has fixed the types. Bad arguments stay as they are."""
    schema = SCHEMAS.get(name)
    try:
        args = schema(**args).model_dump() if schema else args
    except ValidationError:
        pass  # the tool will return the error text, so the raw arguments are compared
    return json.dumps(args, sort_keys=True)

def stuck_reason(steps, repeats=3):
    """Why the run is stuck, or None. Each rule reads only the steps so far."""
    if repeats < 2:
        raise ValueError(f"repeats must be at least 2, got {repeats}")
    last = steps[-repeats:]
    if len(last) == repeats and last[0]["calls"] and all(s["calls"] == last[0]["calls"] for s in last):
        return f"the same call {repeats} times in a row"  # rule 1: identical calls
    errors = [(name, text) for s in steps for name, text in s["results"] if text.startswith("error")]
    if len(errors) >= 2 and errors[-1] == errors[-2]:
        return "the same error twice, even with a success between"  # rule 2
    writes = [s["state"] for s in steps if s["state"] is not None and any(n in WRITE_TOOLS for n, _ in s["calls"])]
    if len(writes) >= repeats and len(set(writes[-repeats:])) == 1:
        return f"a write was tried {repeats} times and the state did not change"  # rule 3: flat write
    return None

# %% [markdown]
# Demo with hand-built steps, no model call. Rule 3 fires when three writes leave the state flat. Three lookups with changing arguments do not fire it.

# %%
def step_of(name, args, text, state):
    """A hand-built step for the demo: one call, one result, one state fingerprint."""
    return {"calls": [(name, json.dumps(args, sort_keys=True))], "results": [(name, text)], "state": state}

flat_writes = [step_of("issue_refund", {"order_id": "BS-1045", "amount_usd": amt}, "payment pending", "9f2c")
               for amt in (10, 20, 30)]  # three different amounts, none changed the state
lookups = [step_of("get_order", {"order_id": oid}, "status: shipped", "9f2c")
           for oid in ("BS-1042", "BS-1043", "BS-1044")]
print("three writes, state flat:", stuck_reason(flat_writes))
print("three lookups, state flat:", stuck_reason(lookups))

# %% [markdown]
# ### Step 3 (continued): the loop
# This is lesson 05's loop with one record per reply and the stuck check at two points: before the tools and after them. Each call evaluates all three rules. Before the tools only the identical-call rule can fire, because the current step's results are still empty. The stuck check does not depend on the prompt.

# %%
def run_agent(question, budget, system=SYSTEM, repeats=3):
    """One run. Before a reply's tools: no-tool check, cap, identical calls. After them: errors, flat writes."""
    REFUNDS.clear()
    messages = [SystemMessage(content=system), HumanMessage(content=question)]
    steps = []  # one record per model reply
    while True:
        reply = llm_tools.invoke(messages)  # one paid model call: the whole list is sent again
        messages.append(reply)
        record(budget, reply)
        step = {"calls": [(c["name"], canon(c["name"], c["args"])) for c in reply.tool_calls],
                "results": [], "state": None}
        steps.append(step)
        if not reply.tool_calls:
            return finish("answered", reply.text, None, budget, steps)
        if (cap := exceeded(budget)):
            return finish(cap, None, None, budget, steps)
        if (why := stuck_reason(steps, repeats)):
            return finish("stuck", None, why, budget, steps)
        for call in reply.tool_calls:
            result = run_tool(call)
            messages.append(result)
            step["results"].append((call["name"], result.content))
        step["state"] = state_hash()
        if (why := stuck_reason(steps, repeats)):
            return finish("stuck", None, why, budget, steps)

def finish(stop, answer, why, budget, steps):
    """One dictionary for every exit: the stop reason, the reason text, the steps and the state."""
    return {"stop_reason": stop, "answer": answer, "why": why, "steps": steps,
            "refunds": list(REFUNDS), "turns": budget.turns, "usd": budget.usd}

def show(result):
    """Print each step: what the model asked, what came back, and the final answer if any."""
    for i, step in enumerate(result["steps"], 1):
        for name, args in step["calls"]:
            print(f"  step {i}: model asks {name}({args})")
        for name, text in step["results"]:
            print(f"  step {i}: observation from {name}: {text}")
    if result["answer"]:
        print("  model says:", result["answer"])

# %% [markdown]
# ### Step 4: three requests, three stops
# Run A's desk prompt differs from lessons 03 to 05. It tells the model to retry a failed refund, to provoke the loop. A model without that line may stop by itself. The stuck check does not depend on the prompt.
#
# **Run A: stuck.** The refund for BS-1045 fails with the same 503 each time. Step 1: the model asks for the refund, the tool returns the 503, and after the tools rule 2 has one error, so it cannot fire. Step 2: the model asks again (the second paid call), the tool returns the same 503, and after the tools the second error matches the first. The run stops at `turns: 2`. There is no third paid call. The three-turn budget is not the reason.

# %% tags=["needs-llm"]
REFUND_REQUEST = "Customer C-22 says the rain shell from order BS-1045 arrived torn. Refund the 40 USD paid."
stuck_run = run_agent(REFUND_REQUEST, Budget(max_turns=3), system=RETRY_SYSTEM)
show(stuck_run)
print(f"stop: {stuck_run['stop_reason']} | why: {stuck_run['why']} | turns: {stuck_run['turns']} | refunds written: {stuck_run['refunds']}")

# %% [markdown]
# **Run B: over budget.** A status question about another order, with a cap of one turn. The first reply asks for a lookup, and the cap is checked before the tools, so the lookup never runs.

# %% tags=["needs-llm"]
capped_run = run_agent("Customer C-17 asks for the status of order BS-1044. Look it up.", Budget(max_turns=1))
show(capped_run)
print(f"stop: {capped_run['stop_reason']} | answer: {capped_run['answer']!r} | turns: {capped_run['turns']}")

# %% [markdown]
# **Run C: done.** A question the model can answer from its own instructions. It needs no tool, so the first reply is text and the run ends as `answered`.

# %% tags=["needs-llm"]
done_run = run_agent("In one sentence: can the desk refund more than was paid?", Budget(max_turns=3))
show(done_run)
print(f"stop: {done_run['stop_reason']} | turns: {done_run['turns']} | cost: ${done_run['usd']:.6f}")

# %% [markdown]
# ### Step 5: the four exits
# The stop reason says why the loop stopped. The exit says what happens next. Open work decides first: when work is owed, the exit is hand off, whatever the stop reason. So the stuck and over budget exits occur only when nothing is owed.
#
# The caller knows whether work is owed, because it knows the task. A refund request stays open until a refund is written, so `work_open = task_is_refund and not refunds`.

# %%
def exit_of(result, work_open):
    """One of the four exits. work_open: a customer is still owed something the loop did not finish."""
    if result["stop_reason"] == "answered":
        return "done"
    if work_open:
        return "hand off"
    return "stuck" if result["stop_reason"] == "stuck" else "over budget"

task_is_refund = True  # the caller knows the task: a refund request is owed until a refund is written
work_open = task_is_refund and not stuck_run["refunds"]  # REFUNDS is empty, so True
stuck_by_hand = {"stop_reason": "stuck", "why": "the same error twice"}  # hand-built, no model call
for name, res, owed in [("run A, refund owed", stuck_run, work_open), ("run B, lookup only", capped_run, False),
                        ("run C", done_run, False), ("stuck, nothing owed", stuck_by_hand, False)]:
    print(f"{name}: stop {res['stop_reason']} -> exit {exit_of(res, owed)}")

# %% [markdown]
# A hand-off is a small record a person can act on. It needs the evidence: which calls were tried, what the errors said, and what was written. It is built in code, with no model call.

# %%
def hand_off_ticket(result, order_id, work_open):
    """What a person receives when the loop cannot finish. Built from the steps, with no model call."""
    tried = [(name, args) for step in result["steps"] for name, args in step["calls"]]
    return {"order_id": order_id, "exit": exit_of(result, work_open), "why": result["why"],
            "calls_tried": tried, "refunds_written": result["refunds"],
            "usd_spent": round(result["usd"], 6), "next": "a person refunds by hand or retries the payment"}

ticket = hand_off_ticket(stuck_run, "BS-1045", work_open)
for key, value in ticket.items():
    print(f"{key}: {value}")

# %% [markdown]
# ## Under the hood
# The identical-call rule compares text, so the same call must have the same text. JSON with sorted keys fixes the order of the keys, but not the numbers: `40` and `40.0` differ as text. Production code compares the text after the schema, which is what `canon` does inside `run_agent`. This cell makes no model call.

# %%
a = {"order_id": "BS-1045", "amount_usd": 40}
b = {"amount_usd": 40.0, "order_id": "BS-1045"}
def raw(d):
    """Sorted keys only: the text a plain comparison sees."""
    return json.dumps(d, sort_keys=True)
print("same raw text:", raw(a) == raw(b))  # False: 40 and 40.0 differ
print("same after the schema:", canon("issue_refund", a) == canon("issue_refund", b))  # True
print("state fingerprint after each step of run A:", [s["state"] for s in stuck_run["steps"]])  # equal: both refunds failed, nothing written

# %% [markdown]
# The library version of a step cap is LangGraph's `recursion_limit`, which counts graph steps and does not detect repeats. So this lesson writes the repeat rules by hand. Lesson 07 adds a verifier score, which catches the research loops that the flat-write rule misses.

# %% [markdown]
# ## At work
# - A repeated tool call with the same error is the classic runaway. Production loops treat it as a failure to stop, not as a retry; lesson 13 separates a transient error worth retrying from a repeat that will fail again.
# - Teams count stop reasons per run. A spike in `stuck` usually means a broken tool or a changed API, not a model problem. → lesson 27
# - A stuck run is handed to a person with its evidence, not dropped. Approval gates are the other kind of exit. → lesson 22
# - The same rule works with a verifier score: a score that stays flat for several steps is a stop. → lesson 07

# %% [markdown]
# ## Common mistakes
# 1. **A repeat count of one.** A count of one stops every loop on its first call, including a normal lookup.

# %% tags=["raises-exception"]
stuck_reason(stuck_run["steps"], repeats=1)  # ValueError: repeats must be at least 2

# %% [markdown]
# Fix: use three for the identical-call rule. Two can be right for a write, where a second identical error already means no progress; the same-error rule covers that case.
#
# 2. **Forgetting the exit's second input.** `exit_of` needs to know whether work is still open. Without it the function cannot choose between hand off and over budget.

# %% tags=["raises-exception"]
exit_of(capped_run)  # TypeError: missing 1 required positional argument: 'work_open'

# %% [markdown]
# Fix: pass `True` or `False` on purpose. The same stop reason gives a different exit depending on whether a customer is still owed something.

# %% [markdown]
# ## Try it
# Call `stuck_reason` on the first step of run A, then on the first two steps, and predict each answer before you run it. Then explain why one step is never enough for a stuck check.

# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
# Every rule compares against an earlier step; a single step has nothing to compare.
print(stuck_reason(stuck_run["steps"][:1]))  # one step: None, no pattern yet
print(stuck_reason(stuck_run["steps"][:2]))  # two steps: the same error twice, both refunds failed the same way

# %% [markdown]
# Save the recording. This cell is the last code cell of the notebook.

# %%
llm_replay.stop()  # saves the recording

# %% [markdown]
# ## Recap
# - Stuck signals: the same call three times in a row; the same error twice, even with a success between; a write whose state stays flat.
# - Checks 1 to 3 run before a reply's tools, check 4 after them. Each runs before the next paid call.
# - Four exits: **done**, **stuck**, **over budget**, **hand off** (work still owed, whatever the stop reason).
#
# **Interview:** "How do you stop an agent that keeps calling the same failing tool?" A strong answer: a stuck check over the steps that runs before the next paid call; caps still bound the bill; open work goes to a person with the evidence attached.

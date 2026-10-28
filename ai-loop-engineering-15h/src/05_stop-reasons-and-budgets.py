# %% [markdown]
# # 05 · Stop reasons and budgets: caps on turns, tokens, dollars and time
# Level L1 · Part 1 · core · ~25 min · builds on 03, 04
#
# ## Goal
# Stop a loop on every exit it can take in this lesson: a finished answer, or a cap on turns, tokens, dollars or time. Say why the caps are checked after a response, and why the last response can still overshoot.
#
# ## Why it matters
# Without a cap, the loop is only as careful as the model. A model that keeps asking for one more lookup keeps going, and every turn resends the whole message list (lesson 03). So the bill grows faster than the turn count. At the lesson 02 price, one run of 500 turns, assuming the list stays at 20,000 tokens, sends 10 million input tokens: about $1 for that one run. At 200 such runs a day, that is $200 a day, and nothing in the code noticed.
#
# With a cap, the worst case is written in your code: at most this many turns, at most these tokens and dollars, and the one reply that crossed the line. The model still decides what to ask next. Your code decides when the loop stops being allowed to ask.
#
# You do not need a cap when there is no loop. One model call has one bill and no next turn.

# %% [markdown]
# The first code cell starts the recording layer. It makes no model call.

# %%
import sys; sys.path.insert(0, "..")
import llm_replay
llm_replay.start("05_stop-reasons-and-budgets")  # records the model calls once, replays them later

# %% [markdown]
# ## The idea
# **A budget is a set of caps for one run, and your code counts every model reply against them. The loop stops when the model answers in text (`answered`), or when a cap is reached (`turn_cap`, `over_budget_tokens`, `over_budget_usd`, `over_time`). The caps are checked after each reply. The reply that crosses a cap has already been paid for, so the run can end a little over its limit, but its tools do not run.**
#
# Analogy: a prepaid phone card. The card does not stop the call mid-word. It stops you from starting the next call once the balance is gone, and the last call may take the balance below zero.
#
# ## Picture
# Every reply goes through the same check. A cap stops the run before the tools of that reply run, so a capped run writes nothing more.
#
# ```mermaid
# flowchart LR
#   M["model reply"] --> R["count it: turns, tokens, dollars, time"]
#   R -->|"no tool call"| A["stop: answered"]
#   R -->|"tool call, a cap reached"| C["stop: cap; the tools do not run"]
#   R -->|"tool call, under every cap"| T["run the tools"]
#   T --> M
# ```

# %% [markdown]
# ## Step by step
# 1. Set the caps for one run in a `Budget`. Each cap is a number, or `None` for no cap.
# 2. Count every reply: one turn, its tokens and its dollars. The token and dollar counts come from the reply's `usage_metadata`, as in lesson 02.
# 3. After each reply: no tool call means `answered`; otherwise check the caps before running the tools.
# 4. Run three ways: a run that finishes, a run with a tiny dollar cap, and a subagent whose spend rolls up into the parent. A *subagent* here is a second `run_agent` call that your code starts with its own `Budget`. It is not a separate agent process; lesson 25 covers real subagents.
#
# ### Step 1: the tools, from lessons 03 and 04
# This is the setup from earlier lessons: the same invented orders, the refund tool with its schema, and the tool runner. It makes no model call.

# %%
# setup from earlier lessons (03 and 04): the orders and the refund tool with its schema
import time
from dataclasses import dataclass, field
from pydantic import BaseModel, Field
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

ORDERS = {  # generated for this lesson: three invented orders
    "BS-1042": {"customer": "C-17", "item": "Trail jacket", "paid_usd": 120.0, "status": "delivered"},
    "BS-1043": {"customer": "C-22", "item": "Rain shell", "paid_usd": 85.0, "status": "delivered"},
    "BS-1044": {"customer": "C-17", "item": "Merino socks", "paid_usd": 18.0, "status": "shipped"},
}
REFUNDS = []  # state outside the model: a refund is written here
print("orders:", list(ORDERS))

class RefundArgs(BaseModel):
    order_id: str = Field(pattern=r"^BS-\d{4}$", description="Order id in the form BS-1042")
    amount_usd: float = Field(gt=0, description="Amount to refund in US dollars, more than 0")

# %% [markdown]
# The two tools. `get_order` has no schema of its own: its one string argument is plain. `issue_refund` has the schema, so a bad amount never reaches the function body.

# %%
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
    if amount_usd > order["paid_usd"]:
        return f"error: {amount_usd} is more than the {order['paid_usd']} paid. Refund at most the amount paid."
    REFUNDS.append({"order_id": order_id, "amount_usd": amount_usd})
    return f"refunded {amount_usd} on {order_id}"

TOOLS = [get_order, issue_refund]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}

def run_tool(call):
    """Run one tool call. A failure becomes a tool message the model reads on its next turn."""
    try:
        result = str(TOOLS_BY_NAME[call["name"]].invoke(call["args"]))
    except Exception as exc:  # bad arguments or an unknown tool: the model sees the text
        result = f"error: {exc}"
    return ToolMessage(content=result, tool_call_id=call["id"])

# %% [markdown]
# ### Step 2: the model and the price of one call
# `get_llm()` is the helper from lesson 02. This lesson always uses the course default model. The price row is the one lesson 02 read on 2026-10-27, for that same model. To try another model, add its price row first, or the cost function raises `KeyError`.

# %% tags=["needs-llm"]
from llm_setup import DEFAULT_MODELS, get_llm

llm = get_llm(model=DEFAULT_MODELS["gemini"])  # the key comes from .env
llm_tools = llm.bind_tools(TOOLS)  # the tool list travels with every call

# USD per 1M text tokens, Gemini Developer API list price, standard paid tier (read 2026-10-27, as in lesson 02).
PRICES = {DEFAULT_MODELS["gemini"]: {"input": 0.10, "output": 0.40}}
price = PRICES[DEFAULT_MODELS["gemini"]]

def call_cost(usage, price):
    """Dollars for one reply: input and output tokens, each at its own price per 1M tokens."""
    return (usage["input_tokens"] * price["input"] + usage["output_tokens"] * price["output"]) / 1_000_000

# %% [markdown]
# ### Step 2 (continued): the budget
# A `Budget` holds the caps and the counters for one run. The class only stores them. A cap that is zero or negative makes no sense, so the class refuses it.

# %%
@dataclass
class Budget:
    """Caps for one run. None means no cap. The counters start at zero.
    max_turns=3 means at most 3 model replies. started is a time.monotonic() reading,
    used only to measure elapsed seconds."""
    max_turns: int = 6
    max_tokens: int | None = None
    max_usd: float | None = None
    max_seconds: float | None = None
    turns: int = 0
    tokens: int = 0
    usd: float = 0.0
    started: float = field(default_factory=time.monotonic)

    def __post_init__(self):
        for name in ("max_turns", "max_tokens", "max_usd", "max_seconds"):
            value = getattr(self, name)
            if value is not None and value <= 0:
                raise ValueError(f"{name} must be more than 0, got {value}")

print(Budget(max_turns=3, max_usd=0.01))

# %% [markdown]
# Three small functions work on a budget. `record` counts one reply: its turn, its tokens and its dollars. `exceeded` returns the first cap that is reached, or `None`. `add_child` adds a subagent's spend to a parent budget.

# %%
def record(budget, reply):
    """Count one model reply: its turn, its tokens and its dollars."""
    usage = reply.usage_metadata
    budget.turns += 1
    budget.tokens += usage["total_tokens"]  # also counts reasoning tokens; call_cost prices only input and output, so check the price of those before you trust the dollar cap
    budget.usd += call_cost(usage, price)

def exceeded(budget):
    """The first cap reached or passed, or None. Called after every reply."""
    if budget.turns >= budget.max_turns:
        return "turn_cap"
    if budget.max_tokens is not None and budget.tokens >= budget.max_tokens:
        return "over_budget_tokens"
    if budget.max_usd is not None and budget.usd >= budget.max_usd:
        return "over_budget_usd"
    if budget.max_seconds is not None and time.monotonic() - budget.started >= budget.max_seconds:
        return "over_time"
    return None

def add_child(budget, child):
    """A subagent's tokens and dollars count against the parent too."""
    budget.tokens += child.tokens
    budget.usd += child.usd

print("ready:", [f.__name__ for f in (record, exceeded, add_child)])

# %% [markdown]
# ### Step 3: the loop checks the caps after each reply
# The loop has no `for` counter any more. The budget is the counter. The check comes after the reply and before its tools run. That order is the change from lesson 03, where the tools of the last turn still ran. Why: a reply that crossed the cap may ask for a refund, and a capped run should not write anything nobody has approved.
#
# `max_turns=3` means at most 3 model replies. A text answer on the last one still counts as `answered`. A capped run's message list is not resumable as it is: if the cap stops on a reply with tool calls, the list ends with a model message whose calls have no results. Do not send that list back to the model unchanged.

# %%
SYSTEM = "You are the support desk for Brightside Outfitters. Look up the order before any refund. Never refund more than was paid."

def run_agent(question, budget):
    """One run. Each reply is counted; the caps are checked before that reply's tools run."""
    messages = [SystemMessage(content=SYSTEM), HumanMessage(content=question)]
    while True:
        reply = llm_tools.invoke(messages)  # one model call: the whole list is sent again
        messages.append(reply)
        record(budget, reply)
        if not reply.tool_calls:
            stop, answer = "answered", reply.text  # the model finished
        elif (cap := exceeded(budget)):
            stop, answer = cap, None  # the reply was paid for; its tool calls do not run
        else:
            messages += [run_tool(call) for call in reply.tool_calls]
            continue
        return {"stop_reason": stop, "answer": answer, "messages": messages, "refunds": list(REFUNDS)}

# %% [markdown]
# `show` prints a run as a transcript, so you can read each turn without raw message objects.

# %%
def show(messages):
    """Print the transcript after the system message and the question."""
    for m in messages[2:]:
        if m.type == "tool":
            print(f"  observation: {m.content}")
        elif m.tool_calls:
            for c in m.tool_calls:
                print(f"  model asks: {c['name']}({c['args']})")
        else:
            print(f"  model says: {m.text}")

# %% [markdown]
# ### Step 4a: a run that finishes
# The desk has a turn cap, a token cap, a dollar cap and a time cap. The time cap is set but never reached in this run. The time cap is also checked only after a reply, so it cannot interrupt a call that hangs. The run ends on `answered`. Read the transcript, then the counters.

# %% tags=["needs-llm"]
REQUEST = "Customer C-22 says the rain shell from order BS-1043 leaked after one wash. Look up the order and refund what was paid."
desk = Budget(max_turns=6, max_tokens=50_000, max_usd=0.01, max_seconds=120)
REFUNDS.clear()  # each demo starts with no refunds written
run_a = run_agent(REQUEST, desk)
show(run_a["messages"])
print(f"stop reason: {run_a['stop_reason']} | turns: {desk.turns} | tokens: {desk.tokens} | cost: ${desk.usd:.6f}")
print("refunds written:", run_a["refunds"])

# %% [markdown]
# ### Step 4b: a run with a tiny dollar cap
# The cap below is far under what one reply costs. The first reply is still paid for, and the check then stops the run. Its tool call does not run, so no refund is written. Read the cost against the cap.

# %% tags=["needs-llm"]
tight = Budget(max_turns=6, max_usd=0.00001)  # tight on purpose: one reply is more than this
REFUNDS.clear()  # each demo starts with no refunds written
run_b = run_agent(REQUEST, tight)
show(run_b["messages"])
tool_runs = sum(m.type == "tool" for m in run_b["messages"])
print(f"stop reason: {run_b['stop_reason']} | answer: {run_b['answer']!r}")
print(f"cap ${tight.max_usd:.6f}; the reply that crossed it cost ${tight.usd:.6f} (overshoot by {tight.usd - tight.max_usd:.6f} USD)")
print(f"tool results written: {tool_runs} | refunds written: {run_b['refunds']}")

# %% [markdown]
# ### Step 4c: a subagent whose spend rolls up
# The subagent is the second `run_agent` call from step 4. It is allowed one turn. The parent's cap is checked only at the parent's own next reply. The child's cost rolls up after the child ends: `add_child` adds it to `desk`, so the parent's total is the whole tree's spend.

# %% tags=["needs-llm"]
looker = Budget(max_turns=1)  # a subagent allowed one model turn
run_c = run_agent("Look up order BS-1044 and tell me its delivery status.", looker)
print(f"subagent stop reason: {run_c['stop_reason']} | subagent cost: ${looker.usd:.6f}")
desk_own = desk.usd
add_child(desk, looker)
print(f"desk own cost: ${desk_own:.6f} | desk cost with the subagent: ${desk.usd:.6f}")

# %% [markdown]
# ## Under the hood
# The caps are plain arithmetic. This section shows the worst-case overshoot, the growth of input tokens that makes long runs expensive, and the four caps tripping. It makes no model call.

# %%
# Worst case: a run just under the cap ends at most at cap plus one reply. The reply that crosses
# the cap ends the run, so no reply starts after the cap. The 3,000/200 reply is a made-up worst case, not a measured one.
cap = 0.01
one_reply = call_cost({"input_tokens": 3000, "output_tokens": 200}, price)
print(f"cap ${cap}; one more reply adds ${one_reply:.6f}; the run ends at most at ${cap + one_reply:.6f}")
# Input tokens per reply in the finished run: each turn resends the list, so the list grows.
per_reply = [m.usage_metadata["input_tokens"] for m in run_a["messages"] if m.type == "ai"]
print("input tokens per reply in run A:", per_reply)

# %% [markdown]
# The token and time caps work the same way. Set a counter past its cap and ask `exceeded`.

# %%
for name, b in {"turns": Budget(max_turns=2, turns=2), "tokens": Budget(max_tokens=100, tokens=150),
                "usd": Budget(max_usd=0.01, usd=0.02), "time": Budget(max_seconds=1, started=time.monotonic() - 5)}.items():
    print(name, "->", exceeded(b))

# %% [markdown]
# `record` reads `total_tokens`, `input_tokens` and `output_tokens` from each reply's `usage_metadata`. LangChain normalises these three field names for every provider, so `record` works the same with either Gemini or Claude. That is why the code never needs a vendor SDK import.

# %% [markdown]
# **Enforced and advisory budgets.** The caps above are *enforced*: your code stops the loop, whatever the model thinks. An *advisory* budget tells the model its limit, for example a line in the prompt that says "you have 3 turns left". The model may slow down, but nothing stops it. Use both: the advisory line helps the model plan, and the enforced cap is the one that protects your bill. Provider features that count down for the model are advisory; the cap in your code is the enforced one.
#
# **Subagents.** A subagent's tokens and dollars are added to the parent's totals, so a parent cap covers the whole tree. A parent that only counts its own replies can be far under its cap while its subagents spend the rest.

# %% [markdown]
# ## At work
# - Production teams cap every run three ways (turns, spend, wall-clock time) and count the stop reasons of every run. A run that hits a cap is reported, not retried in silence. → lesson 27
# - Agent SDKs ship the same caps: the Claude Agent SDK's `max_turns` and `max_budget_usd` end a run with a result subtype you check in code. → lesson 10
# - A per-run cap does not stop 500 runs a day. Teams add budgets per tenant and per day above the run cap. → lesson 29a
# - Subagent fan-out multiplies spend, so parents roll child spend up, as in step 4c. → lesson 25

# %% [markdown]
# ## Common mistakes
# 1. **A cap of zero, or a negative cap.** A cap must be more than zero. Use `None` to switch a cap off.
# %% tags=["raises-exception"]
Budget(max_usd=0)  # ValueError: max_usd must be more than 0

# %% [markdown]
# Fix: pass a positive number, or `None` for no cap.
#
# 2. **Reading the answer of a run that was capped.** A capped run has no answer. Its `answer` is `None`.
# %% tags=["raises-exception"]
run_b["answer"].upper()  # AttributeError: 'NoneType' object has no attribute 'upper'

# %% [markdown]
# Fix: branch on `stop_reason` first. Only `answered` means the model finished. Any cap means the work is unfinished, and a person or a later run decides what happens next.

# %% [markdown]
# ## Try it
# Write `headroom(budget)` that returns a dict with what is left under each cap that is set: turns left, tokens left and dollars left. A cap of `None` is left out. Call it on `desk` and print the result.

# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
def headroom(b):
    left = {"turns": b.max_turns - b.turns}
    if b.max_tokens is not None:
        left["tokens"] = b.max_tokens - b.tokens
    if b.max_usd is not None:
        left["usd"] = round(b.max_usd - b.usd, 6)
    return left

print(headroom(desk))

# %% [markdown]
# Save the recording. This cell is the last code cell of the notebook.

# %%
llm_replay.stop()  # saves the recording

# %% [markdown]
# ## Recap
# - A `Budget` holds the caps for one run: turns, tokens, dollars and time. Each cap can be `None`.
# - Count every reply, then check the caps before that reply's tools run. A capped run writes nothing more.
# - The reply that crosses a cap is already paid for, so a run can end a little over its limit.
# - Stop reasons: `answered` (done), `turn_cap`, `over_budget_tokens`, `over_budget_usd`, `over_time`. Stuck and hand-off exits come in lessons 06 and 22.
# - Subagent spend adds to the parent's totals.
#
# **Interview:** "How do you stop an agent loop from running up a bill?" A strong answer: caps on turns, tokens, dollars and wall-clock time, counted in your code from the usage each reply returns; checked after every reply and before its tools run; the last reply can overshoot by one reply's cost; subagent spend rolls up into the parent; the model never decides on its own to stop for budget reasons.

# %% [markdown]
# # 03 · The agent loop by hand: tool calls, results and stop reasons
# Level L1 · Part 1 · core · ~25 min · builds on 02
#
# ## Goal
# Write the model, tool, observe cycle yourself in about 40 lines, run it on one refund request, and read why each run stopped.
#
# The notebook makes four model calls in total. Its recording is replayed on any laptop with no key.

#
# ## Why it matters
# Without a loop, a person is the loop. The model asks for an order lookup, a person looks it up and pastes the result back, the model asks for the refund, a person types it in, and so on. One refund costs three round trips by hand. At 200 tickets a week that is hundreds of pastes, and nothing stops a model that keeps asking for one more step.
#
# With a loop, your code runs the tools the model asks for, puts each result back into the conversation, and stops on a rule you wrote. The model still decides which tool to call next. Your code decides when to stop.
#
# You do not need a loop when one model answer is enough, for example a single summary of text you already have.

# %%
import sys; sys.path.insert(0, "..")
import llm_replay
llm_replay.start("03_hand-written-agent-loop")  # records the model calls once, replays them later

# %% [markdown]
# ## The idea
# **An agent loop is a `for` loop around one model call: the model either answers in text or asks for a tool, your code runs the tool, the result goes back into the message list, and the next call sees it.** A tool call names a tool and gives its arguments. The result is an *observation*: text your code returns and the model reads on its next turn. The loop stops when the model answers in text (the **stop reason** `answered`), or when your counter reaches the **turn cap** (`turn_cap`). The model cannot stop the loop by itself; your code can.
#
# Analogy: a shop assistant with a phone. The assistant asks the stock system a question, reads the answer, asks the next question, and tells the customer when the job is done. The manager sets how many calls the assistant may make before the shift ends.

# %% [markdown]
# ## Picture
# The model decides the next step. Your code runs it, feeds the result back and counts the turns. Two exits exist: a text answer, and the cap.
#
# ```mermaid
# flowchart LR
#   Q["question + tool list"] --> M[Model call]
#   M -->|"tool call: name + arguments"| T["your code runs the tool"]
#   T -->|"observation (a tool message)"| H["message list grows"]
#   H --> M
#   M -->|"text, no tool call"| A["stop: answered"]
#   H -.->|"turn counter reaches the cap"| C["stop: turn_cap"]
# ```

# %% [markdown]
# ## Step by step
# 1. Define the tools as plain Python functions with `@tool` from LangChain. The docstring and type hints become the model's schema.
# 2. Keep the state outside the model. A refund goes into a list in your code, not the model's memory.
# 3. Write one loop: one model call per turn, run every tool call in the reply, append each result, stop on text or the cap.
# 4. Run it on one request, read the transcript, then run it with a cap of one turn.
#
# ### Step 1 and 2: tools and state
# This lesson uses a three-order stand-in for the Brightside CRM, written inline so the loop stays the only new idea and the notebook runs before the CRM database exists. It has the fields order_id, customer, item, paid_usd and status. Planned lesson 04 switches the tools to `brightside_crm.sqlite`. Pydantic converts the int to a float: `120` arrives as `120.0`.

# %%
from langchain_core.tools import tool

ORDERS = {  # inline stand-in for brightside_crm.sqlite: three invented orders
    "BS-1042": {"customer": "C-17", "item": "Trail jacket", "paid_usd": 120.0, "status": "delivered"},
    "BS-1043": {"customer": "C-22", "item": "Rain shell", "paid_usd": 85.0, "status": "delivered"},
    "BS-1044": {"customer": "C-17", "item": "Merino socks", "paid_usd": 18.0, "status": "shipped"},
}
REFUNDS = []  # state outside the model: a refund is written here

@tool
def get_order(order_id: str) -> dict:
    """Look up one order: customer, item, amount paid and delivery status."""
    return ORDERS.get(order_id, {"error": f"no order {order_id}"})

@tool
def issue_refund(order_id: str, amount_usd: float) -> str:
    """Refund an amount on one order. The amount may not be more than the amount paid."""
    order = ORDERS.get(order_id)
    if order is None:
        return f"error: no order {order_id}"
    if amount_usd > order["paid_usd"]:
        return f"error: {amount_usd} is more than the {order['paid_usd']} paid"
    REFUNDS.append({"order_id": order_id, "amount_usd": amount_usd})
    return f"refunded {amount_usd} on {order_id}"

TOOLS = [get_order, issue_refund]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}
print("tools the model will see:", [t.name for t in TOOLS])

# %% [markdown]
# ### Step 3: the loop
# `get_llm()` is the helper from lesson 02. `llm.bind_tools` tells the model about the tools on every call. The loop below is the part you write yourself. It has one model call per turn, and it runs each tool call the model asks for.

# %% tags=["needs-llm"]
from dataclasses import dataclass, field
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from llm_setup import get_llm

llm = get_llm()  # the provider and its key come from .env
llm_tools = llm.bind_tools(TOOLS)  # the tool list travels with every call

@dataclass
class Run:  # holds the transcript and the counters for one run
    messages: list
    turns: int = 0
    stop_reason: str = ""
    refunds: list = field(default_factory=list)  # what this run wrote to REFUNDS
    input_tokens: list = field(default_factory=list)  # one number per model call

# %% [markdown]
# Two helpers. `run_tool` runs one tool call and wraps the result as a tool message. It never lets an exception escape, because the model needs to read the failure.

# %%
SYSTEM = "You are the support desk for Brightside Outfitters. Look up the order before any refund. Never refund more than was paid."

def run_tool(call):
    """Run one tool call the model asked for. A failure becomes text the model reads next turn."""
    tool_fn = TOOLS_BY_NAME.get(call["name"])
    if tool_fn is None:
        result = f"error: unknown tool {call['name']}"
    else:
        try:
            result = str(tool_fn.invoke(call["args"]))
        except Exception as exc:  # bad arguments: the model sees the error and can fix it
            result = f"error: {exc}"
    return ToolMessage(content=result, tool_call_id=call["id"])

# %% [markdown]
# The loop itself. Read it top to bottom: one model call per turn, one tool run per tool call, and two exits. `else` on a `for` runs only if the loop ended without `break`.

# %% tags=["needs-llm"]
def run_agent(question, max_turns):
    REFUNDS.clear()  # a fresh run starts with no refunds
    run = Run(messages=[SystemMessage(content=SYSTEM), HumanMessage(content=question)])
    for turn in range(1, max_turns + 1):
        reply = llm_tools.invoke(run.messages)  # one model call: the whole list is sent again
        run.messages.append(reply)
        run.turns = turn
        run.input_tokens.append(reply.usage_metadata["input_tokens"])
        if not reply.tool_calls:
            run.stop_reason = "answered"  # the model replied in text: our exit
            break
        for call in reply.tool_calls:
            run.messages.append(run_tool(call))  # the observation goes back in
    else:  # runs only if the loop ended without break: the cap was reached
        run.stop_reason = "turn_cap"  # our counter stopped the loop, not the model
    run.refunds = list(REFUNDS)
    return run

# %% [markdown]
# `show` prints a run as a transcript, so you can read each turn without printing raw message objects.

# %%
def show(run):
    """Print the transcript after the system message and the question."""
    for m in run.messages[2:]:
        if m.type == "tool":
            print(f"  observation: {m.content}")
        elif m.tool_calls:
            for c in m.tool_calls:
                print(f"  model asks: {c['name']}({c['args']})")
        else:
            print(f"  model says: {m.text}")

# %% [markdown]
# ### Step 4: run it, then cap it
# The first run gets six turns. Read the transcript: each line is one model call, one tool, or one observation. The second run gets one turn. In the first run the next step after the lookup was a refund; with one turn, the cap stops the loop after the lookup and no refund is written.

# %% tags=["needs-llm"]
REQUEST = "Customer C-17 says the trail jacket from order BS-1042 arrived torn after one wash. Look up the order and refund what was paid."

run = run_agent(REQUEST, max_turns=6)
show(run)
print(f"turns: {run.turns} | stop reason: {run.stop_reason} | refunds written: {run.refunds}")
print("input tokens per model call:", run.input_tokens)

# %% [markdown]
# The same request with a cap of one turn. The loop stops after one model call, even though the model has more to do. The cap stops further model calls. The tool the model asked for on the last turn still runs. Here that was the harmless lookup.

# %% tags=["needs-llm"]
capped = run_agent(REQUEST, max_turns=1)
show(capped)
print(f"turns: {capped.turns} | stop reason: {capped.stop_reason} | refunds written: {capped.refunds}")

# %% [markdown]
# ## Under the hood
# The library builds the tool list and parses each reply into `tool_calls`. The loop does the rest. This cell shows the link between a call and its result: every tool call has an id, an opaque label the library generates, and each tool message carries the id of the call it answers. This run made one call per turn, so the ids are simple here. When one turn asks for several tools, the ids are how the model matches each result to its call. Run this cell after the first run.

# %%
ids_asked = [c["id"] for m in run.messages if m.type == "ai" for c in m.tool_calls]
ids_answered = [m.tool_call_id for m in run.messages if m.type == "tool"]
print("calls the model made:", ids_asked)
print("results sent back:   ", ids_answered)
print("every call answered:", sorted(ids_asked) == sorted(ids_answered))
print("message types in order:", [m.type for m in run.messages])

# %% [markdown]
# The tool schema the library builds from the function. `convert_to_openai_tool` turns `issue_refund` into the JSON schema that `bind_tools` sends with every call. Nothing is sent here: this is a plain data object. You never write this schema by hand; the library builds it from the function's name, docstring and type hints. This cell is optional and may be skipped.

# %%
from langchain_core.utils.function_calling import convert_to_openai_tool

spec = convert_to_openai_tool(issue_refund)["function"]  # the schema LangChain built from the function
print("name:", spec["name"])
print("arguments:", sorted(spec["parameters"]["properties"]))
print("required:", sorted(spec["parameters"]["required"]))

# %% [markdown]
# ## At work
# - Production loops count turns and spend in their own code. A cap is a counter you keep, never a request that asks the model to stop. → lesson 05
# - Tool errors go back to the model as text, not as exceptions that end the run. Teams check arguments at the tool boundary before a write happens. → lesson 04
# - Each turn resends the whole message list, so input tokens grow on every call (you measured it above). Long runs need context control. → lesson 15

# %% [markdown]
# ## Common mistakes
# 1. **Calling a tool function without its arguments.** The tool's schema requires `order_id`. Calling it with none raises a validation error.

# %% tags=["raises-exception"]
get_order.invoke({})  # ValidationError: order_id is required

# %% [markdown]
# Fix: pass the arguments the schema names, or let `run_tool` turn the error into an observation, as the loop does. Lesson 04 covers the schema in depth.
#
# 2. **Reading the last message as the answer.** A capped run ends on a tool message, not a text reply. Check `stop_reason` before you read the reply.

# %% tags=["raises-exception"]
capped.messages[-1].tool_calls  # AttributeError: a tool message has no tool_calls

# %% [markdown]
# Fix: branch on `stop_reason`. Only `answered` means the model finished; `turn_cap` means the work is unfinished and a person or a later run must decide what happens next.

# %% [markdown]
# ## Try it
# Write `summarize(run)` that returns a dict with four keys: `turns`, `calls` (the number of tool calls the model made in that run), `stop_reason`, and `refunds` (the number of refunds written). Call it on `run` and on `capped`. Do not call the model; use the runs you already have.

# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
def summarize(r):
    return {
        "turns": r.turns,
        "calls": sum(len(m.tool_calls) for m in r.messages if m.type == "ai"),
        "stop_reason": r.stop_reason,
        "refunds": len(r.refunds),
    }

print(summarize(run))
print(summarize(capped))

# %% [markdown]
# Save the recording. This cell is the last code cell of the notebook.

# %%
llm_replay.stop()  # saves the recording

# %% [markdown]
# ## Recap
# - An agent loop is a `for` loop around one model call: model, tool, observation, repeat.
# - A tool call names a tool and its arguments; the observation is the text your code returns for it.
# - Two exits: `answered` (the model replied in text) and `turn_cap` (your counter stopped it). Your code owns both.
# - Each turn resends the whole message list, so input tokens grow.
# - Words to keep: **tool call**, **observation**, **stop reason**, **turn cap**.
#
# **Interview:** "What is an agent loop, and how does it stop?" A strong answer: a loop around one model call; each turn runs the tool calls the model asks for and feeds the results back; it stops when the model answers in text or when your own turn cap is reached, and the cap lives in your code, not in the model.

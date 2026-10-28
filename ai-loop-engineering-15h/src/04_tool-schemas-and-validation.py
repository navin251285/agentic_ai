# %% [markdown]
# # 04 · Tools the model can call safely: schemas, validation, errors as observations
# Level L1 · Part 1 · core · ~20 min · builds on 03
#
# ## Goal
# Give each tool a pydantic argument schema, let the library reject bad arguments before your code runs, and return the rejection to the model as an observation, so the model can fix the call on its next turn.
#
# ## Why it matters
# Without a schema, the model's arguments go straight into your function. A string amount such as `"abc"` fails deep inside your code with a `TypeError`, and a negative amount such as `-50` is written as a refund without any error. Each tool then needs its own hand-written checks, and a missing check is a bug that writes wrong data. One bad argument can end the whole run.
#
# With a schema, one class per tool says what a valid argument looks like. The library checks every call the same way, before the tool body runs. A failure becomes a short text the model reads, and the loop goes on. You do not need a schema for a tool that takes no arguments.

# %% [markdown]
# The first code cell starts the recording layer. The next cell shows the problem with no schema at all. It makes no model call.

# %%
import sys; sys.path.insert(0, "..")
import llm_replay
llm_replay.start("04_tool-schemas-and-validation")  # records the model calls once, replays them later

# %% [markdown]
# Start with no schema at all. The model's arguments would go straight into a plain function. No model is called here.

# %%
def issue_refund_raw(order_id, amount_usd):
    """A refund with no checks: the arguments go straight in."""
    return f"refunded {amount_usd} on {order_id}"

print(issue_refund_raw("BS-1042", -50))  # a negative refund is written as if it were fine
print(issue_refund_raw("BS-1042", "120"))  # a string amount is accepted here too

# %% [markdown]
# Now the check the refund tool has to make: the amount must not be more than the 120 paid. A string that is not a number breaks it.

# %% tags=["raises-exception"]
paid_usd = 120.0
amount_usd = "abc"  # a string, as a model can send it
print(amount_usd > paid_usd)  # TypeError: the check crashes in the middle of the run

# %% [markdown]
# ## The idea
# **A tool's argument schema is a pydantic class: the names, types and rules of each argument. The library checks each tool call against it before the tool runs. A failed check comes back to the model as an observation, and the model tries again.** The model sees the same schema as a JSON description, so the rules you write are also the instructions the model follows. Rules that need data, such as "not more than the amount paid", stay in the tool body, because the schema has no order data.
#
# Analogy: a customs form. The form has fixed boxes with rules (a country code, a number above zero). A clerk rejects an incomplete form before it reaches the warehouse, and gives the reason, so the sender can fix it and resubmit.

# %% [markdown]
# ## Picture
# The schema check sits between the model's call and your code. A bad call never reaches the tool body. Its reason goes back as text.
#
# ```mermaid
# flowchart LR
#   M["model: tool call with arguments"] --> S{"schema check (pydantic)"}
#   S -->|valid| T["tool body runs"]
#   S -->|invalid| E["observation: the field, the rule, the value"]
#   T --> O["observation: the result"]
#   E --> M
#   O --> M
# ```

# %% [markdown]
# ## Step by step
# 1. Write one argument schema per tool, with a rule and a description for each field. The model reads the descriptions.
# 2. Attach the schema to the tool with `@tool(args_schema=...)`. Call the tool with `.invoke`, so the check runs.
# 3. Turn a failed check into a short observation, and send it back in the loop.
# 4. Run one request through the loop and read what the model did.
#
# ### Step 1 and 2: schemas and tools
# The data is the same invented table of orders as lesson 03. No file is downloaded.
#
# Pydantic runs in lax mode by default. It converts some inputs: `{'order_id': 'BS-1042', 'amount_usd': '20'}` is accepted as the number 20.0. `Field(strict=True)` or `ConfigDict(strict=True)` turns that conversion off, and the string is rejected.

# %%
from pydantic import BaseModel, Field, ValidationError
from langchain_core.tools import tool

ORDERS = {  # generated for this lesson: three invented orders
    "BS-1042": {"customer": "C-17", "item": "Trail jacket", "paid_usd": 120.0, "status": "delivered"},
    "BS-1043": {"customer": "C-22", "item": "Rain shell", "paid_usd": 85.0, "status": "delivered"},
    "BS-1044": {"customer": "C-17", "item": "Merino socks", "paid_usd": 18.0, "status": "shipped"},
}
REFUNDS = []  # state outside the model: a refund is written here

class OrderArgs(BaseModel):
    order_id: str = Field(pattern=r"^BS-\d{4}$", description="Order id in the form BS-1042")

class RefundArgs(BaseModel):
    order_id: str = Field(pattern=r"^BS-\d{4}$", description="Order id in the form BS-1042")
    amount_usd: float = Field(gt=0, description="Amount to refund in US dollars, more than 0")
print("refund arguments:", list(RefundArgs.model_fields))

# %% [markdown]
# Attach each schema with `@tool(args_schema=...)`. `@tool` is LangChain's decorator. The function's docstring becomes the description the model reads. The check runs before the tool body, so the body never sees a bad argument.

# %%
@tool(args_schema=OrderArgs)
def get_order(order_id: str) -> str:
    """Look up one order: customer, item, amount paid and delivery status."""
    return str(ORDERS[order_id]) if order_id in ORDERS else f"error: no order {order_id}"

@tool(args_schema=RefundArgs)
def issue_refund(order_id: str, amount_usd: float) -> str:
    """Refund an amount on one order. The amount may not be more than the amount paid."""
    order = ORDERS.get(order_id)
    if order is None:
        return f"error: no order {order_id}"
    if amount_usd > order["paid_usd"]:  # a business rule: it needs the order data, so it is not in the schema
        return f"error: {amount_usd} is more than the {order['paid_usd']} paid. Refund at most the amount paid."
    REFUNDS.append({"order_id": order_id, "amount_usd": amount_usd})
    return f"refunded {amount_usd} on {order_id}"

TOOLS = [get_order, issue_refund]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}
print("tools the model will see:", [t.name for t in TOOLS])

# %% [markdown]
# ### Step 2: call the tools with bad arguments, no model
# `.invoke` runs the schema check first. Three calls, all bad in a different way. Each rejected call raises a `ValidationError` before the tool body runs. The valid call writes one refund, so the list is cleared afterwards.

# %%
bad_calls = [
    {"order_id": "1042", "amount_usd": 20},      # wrong form of the id
    {"order_id": "BS-1042", "amount_usd": -5},   # amount must be more than 0
    {"order_id": "BS-1042", "amount_usd": "abc"},  # not a number at all
]
for args in bad_calls:
    try:
        print("ran:", issue_refund.invoke(args))
    except ValidationError as exc:
        print(f"rejected before the tool ran: {exc.error_count()} error(s) for {args}")

print("ran:", issue_refund.invoke({"order_id": "BS-1042", "amount_usd": 20}))
REFUNDS.clear()

# %% [markdown]
# ### Step 3: the error becomes an observation
# A `ValidationError` holds a list of errors, one per field. Each entry of `exc.errors()` is a dict with `loc` (the field), `msg` (the rule it broke) and `input` (the value sent). `observation` turns that list into one line the model can read. The loop then sends that line back as a tool message with `status="error"`. The `tool_call_id` on that message links it back to the model's call. The loop must never let the exception stop the run.

# %%
from langchain_core.messages import ToolMessage

def observation(exc: ValidationError) -> str:
    """One line per broken field: where, what rule, what value. The model reads it on its next turn."""
    parts = []
    # no docs URL and no context dict: the model needs only the field, the rule and the value
    for e in exc.errors(include_url=False, include_context=False):
        parts.append(f"error: {'.'.join(str(p) for p in e['loc'])}: {e['msg']} (got {e['input']!r})")
    return "; ".join(parts) + ". Fix the arguments and call the tool again."

# %% [markdown]
# `run_tool` runs one call and turns every failure into a tool message. A bad argument never ends the run.

# %%
def run_tool(call):
    """Run one tool call the model asked for. Every failure becomes a tool message the model can read."""
    tool_fn = TOOLS_BY_NAME.get(call["name"])
    if tool_fn is None:
        return ToolMessage(content=f"error: unknown tool {call['name']}", tool_call_id=call["id"], status="error")
    try:
        result = str(tool_fn.invoke(call["args"]))
    except ValidationError as exc:  # the schema said no: the tool body never ran
        return ToolMessage(content=observation(exc), tool_call_id=call["id"], status="error")
    status = "error" if result.startswith("error") else "success"  # a business error from the tool body
    return ToolMessage(content=result, tool_call_id=call["id"], status=status)

# %% [markdown]
# Run the three bad calls through `run_tool`, then one call that passes the schema and breaks the business rule. The last call needs no model: 150 is a valid number, but it is more than the 120 paid, so the tool body returns an error text with `status="error"`.

# %%
demo_calls = bad_calls + [{"order_id": "BS-1042", "amount_usd": 150}]
for n, args in enumerate(demo_calls, start=1):
    msg = run_tool({"name": "issue_refund", "args": args, "id": f"demo-{n}"})
    print(msg.status, "|", msg.content)
REFUNDS.clear()

# %% [markdown]
# ### Step 4: one real run through the loop

# %% [markdown]
# Set up the model with the schemas attached. `get_llm()` reads the key from `.env`.

# %%
from langchain_core.messages import HumanMessage, SystemMessage
from llm_setup import get_llm

llm = get_llm()  # Gemini by default; the key comes from .env
llm_tools = llm.bind_tools(TOOLS)  # the schemas travel with every call
SYSTEM = "You are the support desk for Brightside Outfitters. Look up the order before any refund. Never refund more than was paid."

# %% [markdown]
# One model call per turn, one `run_tool` per tool call the model asks for, and two exits: the model answers in text, or the turn cap is reached. This is lesson 03's loop with one change: `run_tool` returns errors as observations instead of raising.

# %%
def run_agent(question, max_turns):
    REFUNDS.clear()
    messages = [SystemMessage(content=SYSTEM), HumanMessage(content=question)]
    stop_reason, turns = "turn_cap", 0  # our counter stops the loop unless the model answers first
    for turns in range(1, max_turns + 1):
        reply = llm_tools.invoke(messages)  # one model call: the whole list is sent again
        messages.append(reply)
        if not reply.tool_calls:
            stop_reason = "answered"
            break
        messages += [run_tool(call) for call in reply.tool_calls]
    return {"messages": messages, "turns": turns, "stop_reason": stop_reason, "refunds": list(REFUNDS)}

def show(messages):
    """Print the transcript after the system message and the question, one line per message."""
    for m in messages[2:]:
        if m.type == "tool":
            print(f"  observation ({m.status}): {m.content}")
        elif m.tool_calls:
            print("  model asks:", [(c["name"], c["args"]) for c in m.tool_calls])
        else:
            print("  model says:", m.text)

# %% [markdown]
# The customer asks for 150 dollars on a 120 order. This recording shows no validation error: the model asked for 120, not 150, and 120 is valid. So the error path is the one you watched in Steps 2 and 3, not one the model took here. Read the errors the model saw in the output.

# %% tags=["needs-llm"]
REQUEST = ("Customer says their jacket from order 1042 arrived torn after one wash. "
           "They ask for a refund of 150 dollars. Look up the order, then refund what is right.")
run = run_agent(REQUEST, max_turns=5)  # at most five model calls, so at most five in this notebook
show(run["messages"])
errors_seen = sum(m.status == "error" for m in run["messages"] if m.type == "tool")
print(f"turns: {run['turns']} | stop reason: {run['stop_reason']} | errors the model saw: {errors_seen} | refunds written: {run['refunds']}")

# %% [markdown]
# The model's recovery from an observation is the lesson 03 loop reading a tool message; this lesson does not show a recovery run.

# %% [markdown]
# ## Under the hood
# The library does the schema check. This cell does the same check by hand, to show what it is. It reads the JSON schema that pydantic writes for `RefundArgs` (the same description the model gets), and checks four rules: required fields, types, the pattern, and the minimum. Then it compares its answer with pydantic on four inputs. One difference is on purpose: pydantic accepts the string `"20"` as the number 20 (lax mode), and the hand check does not. Know which one your library does before you trust it.

# %%
import re

TYPE_OF = {"string": str, "number": (int, float)}

def check_args(args: dict, schema: dict) -> list[str]:
    """Check args against a JSON schema: required, type, pattern and exclusiveMinimum. Returns the problems."""
    problems = [f"{name}: field required" for name in schema.get("required", []) if name not in args]
    for name, value in args.items():
        spec = schema["properties"].get(name)
        if spec is None:
            problems.append(f"{name}: unexpected field")
        elif isinstance(value, bool) or not isinstance(value, TYPE_OF[spec["type"]]):
            problems.append(f"{name}: expected {spec['type']}, got {value!r}")
        elif "pattern" in spec and not re.search(spec["pattern"], value):
            problems.append(f"{name}: does not match {spec['pattern']}")
        elif "exclusiveMinimum" in spec and not value > spec["exclusiveMinimum"]:
            problems.append(f"{name}: must be more than {spec['exclusiveMinimum']}")
    return problems

# %% [markdown]
# The same four samples, checked both ways.

# %%
schema = RefundArgs.model_json_schema()
samples = [
    {"order_id": "BS-1042", "amount_usd": 20},
    {"order_id": "1042", "amount_usd": -5},
    {"order_id": "BS-1042", "amount_usd": "20"},
    {"order_id": "BS-1042"},
]
for s in samples:
    by_hand = check_args(s, schema)
    try:
        RefundArgs.model_validate(s)
        by_library = "accepted"
    except ValidationError as exc:
        by_library = f"rejected ({exc.error_count()} error(s))"
    print(s, "| by hand:", by_hand or "accepted", "| pydantic:", by_library)

# %% [markdown]
# ## At work
# - Production agents check tool arguments at the tool boundary, before any write. The Anthropic tool-use docs send a bad call back as a `tool_result` with `is_error: true`, and say the model retries with corrections, usually within 2 to 3 tries. A count of repeated validation errors is a loop signal in its own right. → lesson 06 (knowing when the loop is stuck)
# - A schema checks the shape of an argument, not the business rule. "Not more than the amount paid" needs order data, so it lives in the tool, and writes wait for a person when the amount is large. → lesson 22 (human approval as a loop exit)
# - Agent frameworks take the argument schema from the same pydantic class the model reads, so the rules you check and the rules you describe cannot drift apart. Go deeper: the tool and hook controls around a loop are in lesson 16.

# %% [markdown]
# ## Common mistakes
# 1. **Calling a tool without a required argument.** The schema requires `amount_usd`. Leaving it out raises a validation error.

# %% tags=["raises-exception"]
issue_refund.invoke({"order_id": "BS-1042"})  # ValidationError: amount_usd field required

# %% [markdown]
# Fix: pass every required argument, or let `run_tool` turn the error into an observation, as the loop does.
#
# 2. **Calling the function body directly.** `.func` skips the schema check, so bad arguments reach the code.

# %% tags=["raises-exception"]
issue_refund.func("BS-1042", "abc")  # TypeError: the body compares a string with a number

# %% [markdown]
# Fix: call `.invoke(args)`, which runs the schema check first. Never call `.func` on arguments that came from the model.

# %% [markdown]
# ## Try it
# Write a schema `RefundReason` with one field, `reason`: a string of 3 to 200 characters. Validate two inputs, `""` (empty) and `"torn after one wash"`. For the rejected one, print the observation text from `observation(exc)`. Do not call the model.

# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
class RefundReason(BaseModel):
    reason: str = Field(min_length=3, max_length=200, description="Why the refund is made, 3 to 200 characters")

for text in ["", "torn after one wash"]:
    try:
        RefundReason(reason=text)
        print("accepted:", repr(text))
    except ValidationError as exc:
        print("rejected:", observation(exc))

# %% [markdown]
# Save the recording. This cell is the last code cell of the notebook.

# %%
llm_replay.stop()  # saves the recording

# %% [markdown]
# ## Recap
# - A tool's argument schema is a pydantic class; `@tool(args_schema=...)` attaches it to the tool.
# - Call tools with `.invoke`, never `.func`, so the schema check runs before the body.
# - A failed check becomes an observation with status `error`: the field, the rule and the value, so the model can fix the call. This recording did not need that.
# - Rules that need data (the amount paid) stay in the tool body and return an error text.
# - Words to keep: **argument schema**, **validation error**, **observation**.
#
# **Interview:** "How do you stop a model from sending bad tool arguments?" A strong answer: a pydantic schema per tool, checked before the body runs; a failure returns as an error observation the model can fix; business rules that need data are checked in the tool and returned as text; and a repeated error counts toward the loop's stop rules.

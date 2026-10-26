# %% [markdown]
# # 19 · Agent workflows for a customer: tools, MCP servers and guardrails
#
# Level L3 · Part 2 · professional · ~30 min · builds on lesson 06, lesson 12

# %% [markdown]
# ## Goal
#
# By the end of this lesson you can put three Basket Bazaar tools behind an MCP server, let a model call only the tools on an allow-list, stop its loop after a fixed number of steps, and show that the server refuses a bad request even when the model asks for it.

# %% [markdown]
# ## Why it matters
#
# Support wants a model that looks up an order and proposes a credit, and may touch only what the team allows. Without a standard, every tool costs glue: a schema written by hand for the model, a copy of the function, and an adapter for each model app that uses it. Three tools used by two apps is six tool-app pairs, and each pair needs its own schema, copy and adapter. That is eighteen pieces to keep in step. When one changes, the other fails later, and nobody sees it.
#
# If one app uses one tool and nobody else will reuse it, a plain function with a hand-written schema is enough.
#
# The data is an invented orders file, `orders_clean.csv`, made by the lesson 05 code with a fixed seed. It holds no real customer data.

# %% [markdown]
# Setup: this lesson calls the model at most three times. `llm_replay` records those calls the first time, then replays them without a key.

# %%
import sys
sys.path.insert(0, "..")  # lets the notebook import llm_setup.py and llm_replay.py
import llm_replay
llm_replay.start("19_agent-workflows-tools-and-mcp")  # records the model calls below once

import csv
import json
from pathlib import Path

ORDERS_FILE = Path("../data/05/orders_clean.csv").resolve()
DATA = Path("../data/19")
DATA.mkdir(parents=True, exist_ok=True)
PROPOSALS = (DATA / "proposals.jsonl").resolve()
PROPOSALS.unlink(missing_ok=True)  # every run starts with no proposals

print("first three lines of the file:")
print("\n".join(ORDERS_FILE.read_text().splitlines()[:3]))
ORDERS: dict[str, list[dict]] = {}
with ORDERS_FILE.open(newline="") as f:
    for row in csv.DictReader(f):
        ORDERS.setdefault(row["order_id"], []).append(row)
print("orders loaded:", len(ORDERS))

# %% [markdown]
# ### Without MCP: one tool, one app, by hand
#
# The app needs a schema the model can read, a copy of the function, and a table that maps the model's tool name to the copy. Nothing checks that the three agree. The copies already differ in wording: the hand schema below and the server's docstring (Step 1) describe the same tool in different words.

# %%
def lookup_order_copy(order_id: str) -> str:
    lines = ORDERS.get(order_id)
    return json.dumps(lines) if lines else f"order {order_id} not found"


HAND_SCHEMA = {"type": "function", "function": {  # written by hand, for this one model app
    "name": "lookup_order", "description": "Look up one Basket Bazaar order by its order number.",
    "parameters": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]}}}
print("the hand-written schema:", json.dumps(HAND_SCHEMA))
print("the app's copy of the lookup:", lookup_order_copy("BB-1108")[:60], "...")

# %% [markdown]
# ## The idea
#
# **MCP** (Model Context Protocol) is an open protocol for tools. A tool lives in one **MCP server**. Any **MCP client** (a chat app, an agent or a test) lists its tools and calls them. The schema comes from the type hints and docstring, so there is one copy. This lesson uses the `mcp` 2.x SDK (`from mcp.server import MCPServer`, `from mcp import Client`); older guides show the v1 `FastMCP` class.
#
# The agent adds three guardrails in code, not in the prompt: an **allow-list** of the tools the model is shown, a refusal for any other tool name, and a **step limit**. The server checks every argument again. Analogy: a hotel desk. The guest asks for a room, the desk checks the booking, and the guest sees only the floors on their card.

# %% [markdown]
# ## Picture
#
# The model asks for a tool. The agent loop decides whether the tool may run. The server checks the arguments and writes a proposal, never money.

# %% [markdown]
# ```mermaid
# flowchart LR
#     M[Model] -- asks for a tool --> A[Agent loop: allow-list, step limit]
#     A -- allowed name and args --> C[MCP client]
#     C -- stdio, JSON-RPC --> S[MCP server: basket tools]
#     S -- checks args --> O[(Orders file)]
#     S -- proposal, not money --> P[(Proposals file)]
#     S -- result --> A
# ```

# %% [markdown]
# ## Step by step

# %% [markdown]
# ### Step 1: the server is a real file
#
# The server has three tools. `lookup_order` only reads. `propose_credit` checks the order and writes a proposal for a person to approve. `issue_refund` moves money in a real system, so the agent must never be offered it. The server is a file in `apps/19`, and the notebook writes it here so you can read every line.
#
# The notebook starts this file itself; you do not run it directly. It takes two path arguments, the orders file (`sys.argv[1]`) and the proposals file (`sys.argv[2]`), which the client passes.

# %%
%%writefile ../apps/19/basket_tools_server.py
"""Basket Bazaar delivery tools as an MCP server (lesson 19). Lab only: an invented orders file."""
import csv
import json
import sys
from pathlib import Path

from mcp.server import MCPServer

ORDERS: dict[str, list[dict]] = {}
with Path(sys.argv[1]).open(newline="") as f:
    for row in csv.DictReader(f):
        ORDERS.setdefault(row["order_id"], []).append(row)
PROPOSALS = Path(sys.argv[2])

mcp = MCPServer("basket-bazaar-tools")


@mcp.tool()
def lookup_order(order_id: str) -> str:
    """Look up one Basket Bazaar order by its order number, such as BB-1108. Returns its lines as JSON, or says it is not found."""
    lines = ORDERS.get(order_id)
    return json.dumps(lines) if lines else f"order {order_id} not found"


@mcp.tool()
def propose_credit(order_id: str, item: str, qty: int) -> str:
    """Propose a credit for qty units of one item on an order. A person approves it. This tool moves no money."""
    lines = ORDERS.get(order_id)
    if not lines:
        return f"refused: order {order_id} is not in the orders export"
    line = next((x for x in lines if x["item"] == item), None)
    if line is None:
        return f"refused: {item} is not on order {order_id}"
    if line["unit_base"] != "each":
        return f"refused: {item} is not sold by the each, a person checks it"
    if not 1 <= qty <= int(line["qty_base"]):
        return f"refused: qty must be from 1 to {line['qty_base']} for {item}"
    with PROPOSALS.open("a") as f:
        f.write(json.dumps({"order_id": order_id, "item": item, "qty": qty}) + "\n")
    return f"proposed: credit {qty} {item} on {order_id}, waiting for a person"


@mcp.tool()
def issue_refund(order_id: str) -> str:
    """Refund the whole order to the customer's card. Dangerous: the agent's allow-list must never offer it."""
    return f"refund issued on {order_id}"


mcp.run("stdio")  # the notebook starts this file and talks to it over stdin and stdout

# %% [markdown]
# ### Step 2: start the server and list its tools
#
# The client starts the server as a subprocess and talks to it over stdio. `stdio` means the client launches the server as a child process and they exchange messages through stdin and stdout. `Client` is the MCP client that talks to the server. `StdioServerParameters` says which command starts the server and with which arguments. The handshake finishes before the client returns, so the server is ready when the `async with` block starts. The block also stops the server at its end. Top-level `await` works in a notebook cell.

# %%
from mcp import Client, StdioServerParameters


def text_of(result) -> str:
    """The text of a tool result. Tool results are a list of content parts."""
    return "".join(part.text for part in result.content if part.type == "text")


SERVER = StdioServerParameters(
    command=sys.executable,  # the same Python that runs this notebook
    args=[str(Path("../apps/19/basket_tools_server.py").resolve()), str(ORDERS_FILE), str(PROPOSALS)],
)
async with Client(SERVER) as client:
    listed = await client.list_tools()
for tool in listed.tools:
    print(tool.name, "| arguments:", list(tool.input_schema["properties"]))

# %% [markdown]
# ### Step 3: call a tool through the client
#
# A tool reply is text. A value the server finds is JSON. A miss is plain text, and the client does not parse it.

# %%
async with Client(SERVER) as client:
    found = await client.call_tool("lookup_order", {"order_id": "BB-1108"})
    missing = await client.call_tool("lookup_order", {"order_id": "BB-9999"})
print("BB-1108 lines:", len(json.loads(text_of(found))), "| BB-9999:", text_of(missing))

# %% [markdown]
# ### Step 4: the allow-list
#
# The server offers three tools. The agent is shown two of them. The allow-list is a set in code, so it is easy to read and to test.

# %%
ALLOWED = {"lookup_order", "propose_credit"}  # issue_refund is on the server but never offered to the model
MAX_STEPS = 3                                  # the loop stops after this many model calls

print("offered to the model:", sorted(t.name for t in listed.tools if t.name in ALLOWED))

# %% [markdown]
# ### Step 5: the server refuses bad requests, with no model
#
# A model can ask for an order that does not exist, a quantity above the order, or an item that is not on it. The notebook sends those three requests itself, to test the server. Each one is refused and writes nothing.

# %%
bad_requests = [
    {"order_id": "BB-9999", "item": "milk", "qty": 1},
    {"order_id": "BB-1108", "item": "milk", "qty": 9},
    {"order_id": "BB-1108", "item": "tuna", "qty": 1},
]
async with Client(SERVER) as client:
    for args in bad_requests:
        result = await client.call_tool("propose_credit", args)
        print(args["order_id"], args["item"], args["qty"], "->", text_of(result))

# %% [markdown]
# ### Step 6: the agent loop
#
# Each step is one model call. The model either answers, or asks for a tool. The loop runs the tool, gives the result back, and calls the model again. The guardrails are in the loop: only allowed tools are offered, a tool name off the list is refused, and the loop stops at `MAX_STEPS`. A server error (`is_error`) goes back to the model as text, so the model can read it. This loop is written by hand on purpose. The guardrails (allow-list, refusal, step limit) live in the loop, and an agent framework would hide them. This cell only defines the loop. It calls nothing yet.

# %%
from langchain_core.messages import ToolMessage

from llm_setup import get_llm

SYSTEM = ("You help Basket Bazaar's support team. Look up the order first. Then propose a credit only for the quantity the customer says they paid for, and never more than the order holds.")


def as_model_tool(tool) -> dict:
    """The function format the model API accepts, built from the MCP tool's own schema."""
    return {"type": "function", "function": {"name": tool.name, "description": tool.description, "parameters": tool.input_schema}}


async def run_agent(client, message: str):
    model_tools = [as_model_tool(t) for t in (await client.list_tools()).tools if t.name in ALLOWED]
    llm = get_llm().bind_tools(model_tools)
    history = [("system", SYSTEM), ("human", message)]
    for step in range(1, MAX_STEPS + 1):
        reply = llm.invoke(history)                   # one model call per step
        history.append(reply)
        if not reply.tool_calls:
            return reply.text, step                   # the model answered: stop
        for call in reply.tool_calls:
            if call["name"] not in ALLOWED:           # guardrail: refuse a tool that is not on the list
                out = f"refused: {call['name']} is not an allowed tool"
            else:
                result = await client.call_tool(call["name"], call["args"])
                out = f"error: {text_of(result)}" if result.is_error else text_of(result)  # an error is not a success
            print(f"step {step}: {call['name']} {call['args']} -> {out[:100]}")
            history.append(ToolMessage(content=out, tool_call_id=call["id"]))
    return "stopped: the step limit was reached", MAX_STEPS  # guardrail: a loop cannot run forever

# %% [markdown]
# ### Step 7: one customer message, at most three model calls
#
# The message is invented. It is like the one in lesson 06, with the quantity added so the model can propose it. The model should look up the order, propose a credit for the milk, and then answer. Each tool call prints one line, so you can read the steps.
#
# Steps 1 and 2 call tools. Step 3 is the model's final answer, so nothing prints for it.

# %% tags=["needs-llm"]
CUSTOMER_MESSAGE = ("Order BB-1108: the milk is missing from my delivery. I paid for four. Can I get a credit?")
async with Client(SERVER) as client:
    answer, steps = await run_agent(client, CUSTOMER_MESSAGE)  # model calls: at most MAX_STEPS
print("model steps used:", steps, "| answer:", answer)

# %% [markdown]
# ### Step 8: what the run left behind
#
# The run proposed a credit and moved no money. The proposals file is the record a person reviews. Pydantic checks each line against the same shape the server writes, so a bad line fails loudly. If the run was skipped, the file does not exist.

# %%
from pydantic import BaseModel, Field


class Proposal(BaseModel):
    order_id: str = Field(pattern=r"^BB-\d+$")
    item: str
    qty: int = Field(ge=1)


if PROPOSALS.exists():
    rows = [Proposal.model_validate_json(line) for line in PROPOSALS.read_text().splitlines()]
    print(len(rows), "proposal(s):", [r.model_dump() for r in rows])
else:
    print("no proposals file: the model run was skipped")

# %% [markdown]
# ## At work
#
# - Teams keep the allow-list and the approval rule in code, outside the prompt. Least privilege per tool, and a person approves any irreversible action. A prompt is not a permission. → lesson 13 covers the identity and secrets behind each tool.
# - Each model call and each tool call should be a span under one agent trace, with token counts and the tool name. Ship it to the customer's collector. → lesson 16.
# - An agent loop with no limit is a cost risk (OWASP LLM10, unbounded consumption). Set a step limit and a budget per customer. → lesson 18 measures the cost of each call.
#
# Go deeper: durable agent workflows that wait days for an approval are not covered here.

# %% [markdown]
# ## Common mistakes
#
# - **Parsing a plain-text reply as data.** A miss is not an error for the server, so `is_error` is False. The reply is text, and `json.loads` raises on it. Check what the reply is before you parse it.

# %% tags=["raises-exception"]
async with Client(SERVER) as client:
    reply = await client.call_tool("lookup_order", {"order_id": "BB-9999"})
json.loads(text_of(reply))  # "order BB-9999 not found" is not JSON

# %% [markdown]
# The fix is to parse only a reply that starts with `[` or `{`, or to have the tool return a typed result. Next, a missing argument. The server rejects it, but the client does not raise. It returns `is_error`, and a loop that ignores that flag would treat the error as success.

# %%
async with Client(SERVER) as client:
    reply = await client.call_tool("propose_credit", {"order_id": "BB-1108", "item": "milk"})
print("is_error:", reply.is_error, "|", text_of(reply)[:60])

# %% [markdown]
# - **Adding a tool to the allow-list because the server has it.** Every tool on the server is a tool the model can use. `issue_refund` is on the server on purpose and stays off the list.

# %% [markdown]
# ## Try it
#
# Write `within_policy(name, args)`. It returns a refusal text when the agent should not run the call, and None when it may. Two rules: a tool name not in `ALLOWED` is refused, and `propose_credit` with more than two units is refused by the agent, before the server sees it. `ALLOWED` is already defined in Step 4, so you can use it. Return a refusal string, do not raise: the loop passes a refusal back to the model as a normal result.
#
# Then test it on the three calls below. The stub prints `None` three times, because `...` does nothing. With the answer, the lines print: a refusal for the four units, `None` for the two units, and a refusal for `issue_refund`.

# %%
# your code here
def within_policy(name: str, args: dict) -> str | None:
    """Return a refusal text, or None when the agent may make this call."""
    ...  # write the two rules


tests = [
    ("propose_credit", {"order_id": "BB-1108", "item": "milk", "qty": 4}),
    ("propose_credit", {"order_id": "BB-1108", "item": "milk", "qty": 2}),
    ("issue_refund", {"order_id": "BB-1108"}),
]
for name, args in tests:
    print(name, "->", within_policy(name, args))

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
def within_policy(name: str, args: dict) -> str | None:
    """Return a refusal text, or None when the agent may make this call."""
    if name not in ALLOWED:
        return f"refused: {name} is not an allowed tool"
    if name == "propose_credit" and args.get("qty", 0) > 2:
        return "refused by the agent: more than two units needs a person"
    return None


for name, args in tests:
    print(name, "->", within_policy(name, args))

# %% [markdown]
# ## Recap
#
# - **MCP** puts a tool in one server. Any client gets its tools and schemas from the server, so there is one copy.
# - An **allow-list** in code decides which tools the model is offered. The server still checks every argument.
# - A **step limit** stops the loop. A refusal is a normal result the model can read, not a crash.
# - A person approves anything that moves money. This lesson's tool only proposes.
# - Words to keep: **MCP server**, **MCP client**, **allow-list**, **step limit** (all in GLOSSARY.md).
#
# **Interview:** "An agent can look up orders and refund customers. How do you keep it from refunding the wrong order?" Strong answer: "Least privilege: the model sees only the tools it needs, the server checks every argument against the source, and money moves only after a person approves. I cap the steps and test the refusals with plain calls, not with the model."

# %%
llm_replay.stop()  # saves the recording of the model calls

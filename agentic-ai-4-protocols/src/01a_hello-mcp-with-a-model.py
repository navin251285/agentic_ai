# %% [markdown]
# # 01a · Hello MCP: a real model uses your server
# Level L1 · Part 1 · core · ~25 min · builds on 01

# %% [markdown]
# ## Goal
# By the end you can hand Trackr's MCP tools to a real model with the standard LangChain API (`MCPAdapter`, `bind_tools`, `ToolMessage`), ask "How many open issues does web have?", and read the JSON-RPC messages the question caused (`tools/list` and `tools/call`) in a wire log.

# %% [markdown]
# ## The idea
# In lesson 01 you typed JSON-RPC by hand. Real apps do not. A host adapter does the protocol for you: it asks the server for its tools (`tools/list`), turns each one into a LangChain tool, and sends a `tools/call` when the model asks for one.
#
# The model never talks to Trackr. It only reads the tool descriptions and replies with a **tool call**: a tool name and arguments. The host runs that call through MCP and returns a `ToolMessage` with the result. The model then writes the final answer.
#
# Analogy: a waiter. The guest (model) orders from the menu (tools/list) and the waiter (adapter) takes the order to the kitchen (server, tools/call) and brings back the plate (ToolMessage).

# %% [markdown]
# ## Picture
# ```mermaid
# sequenceDiagram
#   participant U as User
#   participant M as Model (Gemini)
#   participant H as Host: MCPAdapter
#   participant S as Trackr MCP server
#   H->>S: tools/list
#   S-->>H: count_open + schema
#   U->>M: How many open issues does web have?
#   M-->>H: tool call: count_open(team="web")
#   H->>S: tools/call count_open {team: web}
#   S-->>H: result: 3
#   H->>M: ToolMessage "3"
#   M-->>U: "The web team has 3 open issues."
# ```

# %% [markdown]
# ## Step by step
#
# ### 1. Check lesson 01's server and the imports
# This lesson reuses the Trackr server you wrote in lesson 01 (`../apps/01/trackr_server.py`). It also needs one small **wire tap**, written in the next cell, so you can see every message. `llm` stays `None` until the model cell runs; the cells that need it check for that.

# %%
import sys, warnings
sys.path.insert(0, "..")   # so the course helpers (llm_setup, llm_replay) import
from contextlib import AsyncExitStack
from pathlib import Path
from langchain.mcp import MCPAdapter
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

warnings.filterwarnings("ignore", message=".*langchain.mcp.*beta")  # the adapter is still beta
SERVER = Path("../apps/01/trackr_server.py")
assert SERVER.exists(), "Run lesson 01 first: it writes ../apps/01/trackr_server.py"
llm = None   # filled by the model cell; stays None if that cell is skipped
print("Trackr server:", SERVER.resolve().name)

# %% [markdown]
# ### 2. A wire tap between the host and Trackr
# A **tap** is a transparent middleman. It starts Trackr as a subprocess, passes every line between the host and Trackr unchanged, and writes one log line per message. Trackr does not know the tap is there. The tap is a few lines of plain Python, so you can read it.

# %%
%%writefile ../apps/01a/wire_tap.py
"""Lesson 01a: a transparent stdio tap. Forwards each JSON-RPC line between host and server, and logs it."""
import json, subprocess, sys, threading
from pathlib import Path

LOG = Path(__file__).with_name("wire.log")
child = subprocess.Popen([sys.executable, sys.argv[1]], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, text=True, bufsize=1)
log = open(LOG, "a", encoding="utf-8", buffering=1)

def describe(line: str) -> str:
    try:
        m = json.loads(line)
    except json.JSONDecodeError:
        return "not JSON"
    if "method" in m:   # a request (has id) or a notification (no id)
        extra = ""
        if m["method"] == "tools/call":
            p = m.get("params", {})
            extra = f" name={p.get('name')} arguments={p.get('arguments')}"
        return f"{m['method']} id={m.get('id', '-')}{extra}"
    return f"{'error' if 'error' in m else 'result'} id={m.get('id')}"

def forward(src, dst, arrow: str) -> None:
    for line in src:
        if line.strip():
            log.write(f"{arrow} {describe(line)}\n")
        dst.write(line)          # the bytes go through unchanged
        dst.flush()
    dst.close()

threading.Thread(target=forward, args=(sys.stdin, child.stdin, "host -> server"), daemon=True).start()
forward(child.stdout, sys.stdout, "host <- server")
child.wait()

# %% [markdown]
# ### 3. Start Trackr through the tap, with `MCPAdapter`
# `MCPAdapter` takes the same config dict that Claude Desktop and most hosts use: a name and a command to start the server. Here the command starts the tap, and the tap starts Trackr. `AsyncExitStack` keeps the connection open across cells until the last cell closes it.

# %%
TAP = Path("../apps/01a/wire_tap.py").resolve()
LOG = TAP.with_name("wire.log")
LOG.write_text("")                       # a fresh log for this run
CONFIG = {"mcpServers": {"trackr": {"command": sys.executable,
                                    "args": [str(TAP), str(SERVER.resolve())]}}}

stack = AsyncExitStack()
adapter = await stack.enter_async_context(MCPAdapter(CONFIG))
tools = await adapter.list_tools()      # the adapter sends tools/list for you
print("tools Trackr offers:", [t.name for t in tools])

# %% [markdown]
# ### 4. The MCP tool is now a LangChain tool
# Each MCP tool became a LangChain tool with the same name, description and argument schema. The schema came from the server's `inputSchema`, not from a copy in this notebook. If the server renames an argument, the next `tools/list` shows it.

# %%
by_name = {t.name: t for t in tools}
count = by_name["count_open"]
print("name       :", count.name)
print("description:", count.description)
print("arguments  :", count.args)

# %% [markdown]
# ### 5. A tool call, run by hand (no model)
# A model's reply that asks for a tool is a dict with a `name`, `args` and an `id`. Passing that dict to the LangChain tool runs `tools/call` and returns a `ToolMessage`. The `id` links the result back to the model's request. This step needs no model, so it always runs.

# %%
by_hand = {"name": "count_open", "args": {"team": "web"}, "id": "by_hand_1", "type": "tool_call"}
reply = await count.ainvoke(by_hand)
print(type(reply).__name__, "| tool_call_id:", reply.tool_call_id)
print("text:", reply.text)

# %% [markdown]
# ### 6. Let the model choose the tool (`needs-llm`)
# Now the real thing. `bind_tools` sends the tool descriptions to the model with the question. The model's first reply is not text: it is a list of tool calls. This course's default model is used, and the first call is recorded once, so later runs replay it with no key. The lesson makes 2 model calls in total.
#
# If this cell is skipped, a scripted tool call stands in for the model's reply, so the rest of the lesson still runs. The scripted reply is labelled as such.

# %% tags=["needs-llm"]
from llm_setup import get_llm
llm = get_llm("01a_hello-mcp-with-a-model", max_calls=2)
question = HumanMessage("How many open issues does web have?")
first = await llm.bind_tools(tools).ainvoke([question])
print("model asks for:", first.tool_calls)

# %% [markdown]
# If the model cell was skipped, this cell supplies the stand-in tool call instead.

# %%
if llm is None:   # fallback: the model cell was skipped
    first = AIMessage(content="", tool_calls=[{"name": "count_open", "args": {"team": "web"}, "id": "scripted_1"}])
    question = HumanMessage("How many open issues does web have?")
    print("SCRIPTED stand-in (no model): model asks for:", first.tool_calls)

# %% [markdown]
# ### 7. Run the requested tools and give the results back
# The host runs each requested tool through the adapter. Each run sends one `tools/call` and returns a `ToolMessage` with the matching `tool_call_id`. The messages are then sent to the model, which writes the answer (the second model call, `needs-llm`).

# %%
results = []
for call in first.tool_calls:
    results.append(await by_name[call["name"]].ainvoke(call))
for r in results:
    print("ToolMessage:", r.tool_call_id, "->", r.text)

# %% [markdown]
# The model reads the tool results and writes the answer. This is its second and last call (`needs-llm`).

# %% tags=["needs-llm"]
final = await llm.bind_tools(tools).ainvoke([question, first, *results])
print("answer:", final.text)

# %% [markdown]
# Without a model there is no written answer, so the fallback prints what the tool said.

# %%
if llm is None:   # fallback: no model, so no written answer
    print("answer: (skipped: no model here). The tool said:", results[0].text)

# %% [markdown]
# ### 8. Read the wire
# Every message that crossed the tap is in the log. When the adapter started it sent `server/discover` and `tools/list` (ids 1 and 2). Each run of a tool sent one `tools/call`: id 3 in step 5 and id 4 in step 7. Each reply has the same `id` as its request. The model itself never appears here: it only chose what the host asked for.

# %%
print(LOG.read_text(encoding="utf-8"))

# %% [markdown]
# ## At work
# - Production hosts send the model every tool's description and schema on every call, and that costs tokens. Large catalogues need trimmed descriptions and fewer tools per prompt → lesson 24 (tool catalogs) and lesson 24b (progressive discovery).
# - Tool descriptions are what the model reads to choose a tool. Teams review them in version control like code, because a vague description sends the model to the wrong tool → lesson 03.
# - The host, not the model, runs the tool. Hosts keep an audit trail of every `tools/call` → lesson 42. A tool description can also lie: a poisoned server can hide instructions in it → lesson 29.
# - In production the tap's stdio subprocess is often replaced by a remote server, but the messages are the same → lesson 06.

# %% [markdown]
# ## What just happened
# - `MCPAdapter` started Trackr (through the tap) and sent `tools/list`. Each MCP tool became a LangChain tool with the server's name, description and schema.
# - The model did not run anything. It replied with a **tool call** (name, args, id). The host turned that into a `tools/call` on the wire.
# - The result came back as a `ToolMessage` with the same `tool_call_id`. The model read it and wrote the answer.
# - The wire log shows every request and reply with its `id`. The model appears only in the chat, never on the wire.

# %% [markdown]
# ## Common mistakes
# Using the server's Python function name instead of the name the server advertises. The name in `tools/list` is what counts. Here the Python name from lesson 00 does not exist on the server:

# %% tags=["raises-exception"]
by_name["count_open_issues"].invoke({"team": "web"})

# %% [markdown]
# Fix: take the names from the tools list, as step 4 does, and check them with `print([t.name for t in tools])`.
#
# A second trap is silent. Arguments that are valid but wrong do not raise an error. `"Web"` is not a team, so Trackr counts zero issues and returns a normal result. The model may then report "0 open issues" with full confidence. Check the arguments in the wire log before you trust an answer.

# %% [markdown]
# ## Try it
# Without the model, ask Trackr for the open count of every team (`web`, `api`, `mobile`, `infra`) with one tool call each. Use ids `try-web`, `try-api`, `try-mobile`, `try-infra`, and print a small table with the total. Then print the number of `tools/call` lines in `LOG`.

# %%
# your code here

# %% [markdown]
# ## Key terms
# - **MCPAdapter** — a LangChain helper that starts an MCP server from a config, lists its tools and runs their calls.
# - **MCP tool → LangChain tool** — each tool from `tools/list` becomes a LangChain tool with the same name, description and schema.
# - **tool call** — the model's reply asking the host to run a tool: a name, arguments and an id. It is not run by the model.
# - **tool call → tools/call** — the JSON-RPC request the host sends to run that tool.
# - **ToolMessage** — the result of a tool run, with the `tool_call_id` of the request it answers.
# - **bind_tools** — attaches tool descriptions to a model so it can make tool calls.
# - **wire tap** — a transparent middleman that logs every JSON-RPC message between host and server.

# %% [markdown]
# Stop the server. Closing the adapter ends the tap, which ends Trackr. Then tell the recorder the lesson is done.

# %%
await stack.aclose()
import llm_replay
llm_replay.stop()
print("messages on the wire:", len(LOG.read_text(encoding="utf-8").splitlines()))

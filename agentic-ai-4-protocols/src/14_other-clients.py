# %% [markdown]
# # 14 · One server, many clients: vendor SDKs and hosted MCP
# Level L3 · Part 3 · core · ~35 min · builds on 06

# %% [markdown]
# ## Goal
# By the end two clients answer questions through Trackr's HTTP server from lesson 06: the LangChain host from lesson 06 and the OpenAI Agents SDK host. Each makes two model calls. The Agents SDK host sees only the read-only tools, so it cannot call `close_issue`. Anthropic's `async_mcp_tool` wraps a Trackr tool with no model call. You can also say which hosted options (Anthropic's MCP connector, OpenAI's `type: "mcp"`, Gemini's `mcp_server`) can reach your server, and which cannot.

# %% [markdown]
# ## The idea
# A server speaks MCP once. Any client that speaks MCP can use it. A vendor SDK wraps the same steps: connect, list the tools, call a tool. The difference is where the loop runs. A client in your process can reach a server on `127.0.0.1`. A hosted connector runs inside the vendor's cloud, so the vendor must reach your server over the public internet. A laptop address is not reachable that way.
#
# Analogy: a hotel's room-service menu. Guests in the hotel read the printed menu directly. A delivery company can only take orders from addresses it can find on the public street.

# %% [markdown]
# ## Picture
# ```mermaid
# flowchart LR
#   T[Trackr on 127.0.0.1:8766]
#   L[LangChain host: MCPAdapter] -->|POST /mcp| T
#   A[OpenAI Agents SDK: MCPServerStreamableHttp] -->|POST /mcp| T
#   V[Vendor cloud: hosted connector] -.->|needs a public HTTPS address| T
#   V -.->|or a Secure MCP Tunnel| T
# ```

# %% [markdown]
# ## Step by step
#
# ### 1. Start Trackr over HTTP
# The server is the one from lesson 06 (`../apps/06/trackr_http.py`). The cell starts it as its own process and waits until `server/discover` answers, as lesson 06 does. The `sys.path` line lets the model helpers import from this folder.

# %%
import atexit, subprocess, sys, time
from pathlib import Path
import httpx
sys.path.insert(0, "..")   # so llm_setup and llm_replay import
assert Path("../apps/06/trackr_http.py").exists(), "run lesson 06 first: it writes the HTTP server"
URL = "http://127.0.0.1:8766/mcp"
server_log = open("../apps/06/server.log", "w")   # closed in the last cell
proc = subprocess.Popen([sys.executable, str(Path("../apps/06/trackr_http.py").resolve())],
                        stdout=server_log, stderr=subprocess.STDOUT)
atexit.register(lambda: proc.poll() is None and proc.terminate())
DISCOVER = {"jsonrpc": "2.0", "id": 1, "method": "server/discover",
            "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
                                 "io.modelcontextprotocol/clientCapabilities": {}}}}
HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json",
           "MCP-Protocol-Version": "2026-07-28", "Mcp-Method": "server/discover"}
deadline = time.monotonic() + 20
while True:
    try:
        up = httpx.post(URL, json=DISCOVER, headers=HEADERS, timeout=10)
        break
    except httpx.ConnectError:
        if proc.poll() is not None or time.monotonic() > deadline:
            raise RuntimeError("server did not start: read ../apps/06/server.log")
        time.sleep(0.2)
print("server answered:", up.status_code, "at", URL)

# %% [markdown]
# ### 2. One list of tools, three SDK views (no model)
# The MCP `Client` from lesson 06 lists the tools. The Agents SDK lists them through `MCPServerStreamableHttp`. Anthropic's helper `async_mcp_tool` turns one MCP tool into the tool object its runner expects, and that object calls the Trackr tool directly. None of these cells calls a model.

# %%
from mcp import Client
from agents.mcp import MCPServerStreamableHttp, create_static_tool_filter
from anthropic.lib.tools.mcp import async_mcp_tool

async with Client(URL) as mcp_client:
    listed = (await mcp_client.list_tools()).tools
    print("MCP Client sees:", [t.name for t in listed])
    anthropic_tool = async_mcp_tool(next(t for t in listed if t.name == "count_open"), mcp_client.session)
    print("Anthropic helper made:", type(anthropic_tool).__name__, "named", anthropic_tool.name)
    print("Anthropic helper call, no model:", await anthropic_tool.call({"team": "web"}))

async with MCPServerStreamableHttp(params={"url": URL}, name="trackr-all") as all_server:
    print("Agents SDK sees:", [t.name for t in await all_server.list_tools()])

# %% [markdown]
# ### 3. Narrow the tools with an allow-list (no model)
# A model should see only the tools its task needs. `create_static_tool_filter` hides the rest from the vendor SDK. It is the local version of the `allowed_tools` option that OpenAI's hosted connector also has (read-along, step 6).

# %%
READ_ONLY = ["count_open", "search_issues"]
ro_filter = create_static_tool_filter(allowed_tool_names=READ_ONLY)
async with MCPServerStreamableHttp(params={"url": URL}, name="trackr-read-only",
                                   tool_filter=ro_filter) as ro_server:
    visible = [t.name for t in await ro_server.list_tools()]
print("the model would see:", visible)
assert "close_issue" not in visible, "close_issue must stay hidden from the model"

# %% [markdown]
# ### 4. The LangChain host, with a real model (`needs-llm`)
# This is the lesson 06 host. `MCPAdapter` reads the server URL from its config and hands the server's tools to the model. The notebook makes two model calls here: one to ask for a tool, and one to write the answer. The budget is four calls for both hosts together.

# %%
import logging, warnings
import llm_replay
from langchain_core._api import LangChainBetaWarning
warnings.filterwarnings("ignore", category=LangChainBetaWarning)   # the adapter is still beta
from contextlib import AsyncExitStack
from langchain.mcp import MCPAdapter
from langchain_core.messages import AIMessage, HumanMessage
logging.getLogger("httpx").setLevel(logging.WARNING)
QUESTION = "How many open issues does the web team have? Use a tool."
stack = AsyncExitStack()   # closed in the last cell
adapter = await stack.enter_async_context(MCPAdapter({"mcpServers": {"trackr": {"url": URL}}}))
lc_tools = await adapter.list_tools()
lc_by_name = {t.name: t for t in lc_tools}
print("LangChain host has:", sorted(lc_by_name))

# %% [markdown]
# The model cell below calls Gemini twice. `get_llm` picks the model and starts the recording or the replay for this notebook. Without a recording and without a key, the cell is skipped.

# %% tags=["needs-llm"]
from llm_setup import get_llm
llm = get_llm("14_other-clients", model="gemini-3.1-flash-lite", max_calls=4)
first = await llm.bind_tools(lc_tools).ainvoke([HumanMessage(QUESTION)])
results = [await lc_by_name[c["name"]].ainvoke(c) for c in first.tool_calls]
final = await llm.bind_tools(lc_tools).ainvoke([HumanMessage(QUESTION), first, *results])
print("LangChain host asks for:", [(c["name"], c["args"]) for c in first.tool_calls])
print("LangChain host answer:", final.text)

# %% [markdown]
# If the model cell was skipped, the tool still runs. The fallback calls `count_open` directly and says so.

# %%
if "final" not in globals():   # fallback: the model cell was skipped
    direct = await lc_by_name["count_open"].ainvoke(
        {"name": "count_open", "args": {"team": "web"}, "id": "no_model_1", "type": "tool_call"})
    print("NO MODEL here. The tool itself answers:", direct.text)

# %% [markdown]
# ### 5. The vendor SDK host: the OpenAI Agents SDK (`needs-llm`)
# The Agents SDK has its own MCP client, `MCPServerStreamableHttp`, and its own agent loop. It takes any model that speaks the OpenAI chat API. This course has a Google key, so the model is Gemini behind Google's OpenAI-compatible endpoint. With an OpenAI key, you would drop the `base_url` and use the default. Tracing is off, because it would upload to OpenAI.

# %% tags=["needs-llm"]
import os
from dotenv import load_dotenv
from openai import AsyncOpenAI
from agents import Agent, OpenAIChatCompletionsModel, Runner, set_tracing_disabled
load_dotenv("../.env")
set_tracing_disabled(True)
key = os.environ.get("GOOGLE_CLOUD_API_KEY") or "replay-no-key-needed"   # replay never sends it
gemini = OpenAIChatCompletionsModel(model="gemini-3.1-flash-lite",
    openai_client=AsyncOpenAI(base_url="https://generativelanguage.googleapis.com/v1beta/openai/", api_key=key))
async with MCPServerStreamableHttp(params={"url": URL}, name="trackr-read-only",
                                   cache_tools_list=True, tool_filter=ro_filter) as server:
    print("tools the SDK host offered:", [t.name for t in await server.list_tools()])
    agent = Agent(name="Trackr assistant", instructions="Answer with a tool. Be brief.",
                  model=gemini, mcp_servers=[server])
    run = await Runner.run(agent, QUESTION)
print("Agents SDK answer:", run.final_output)
print("model calls made by the SDK host:", len(run.raw_responses))

# %% [markdown]
# If the SDK cell was skipped, the fallback shows what the SDK host would get from the tool.

# %%
if "run" not in globals():   # fallback: no model call was made
    async with MCPServerStreamableHttp(params={"url": URL}, name="trackr-fallback") as server:
        out = await server.call_tool("count_open", {"team": "web"})
    print("NO MODEL here. The SDK host's tool returns:", out.structured_content)

# %% [markdown]
# ### 6. Hosted MCP: read-along, nothing is sent
# A hosted connector is different. The vendor's cloud calls your server, so the server needs a public HTTPS address (or a tunnel). Three vendors have this option:
#
# - **Anthropic MCP connector**: `mcp_servers` lists the server, and `mcp_toolset` puts its tools in the request. It needs the beta header `mcp-client-2025-11-20`. It is tools only.
# - **OpenAI Responses API**: a tool of `type: "mcp"`. `require_approval` decides which calls need a human to approve them. `allowed_tools` limits which tools are imported.
# - **Gemini Interactions API**: a tool of `type: "mcp_server"`. Use Streamable HTTP only, and no hyphen in the server name.
#
# The cells below build the three request bodies and run a rough address check. They send nothing. `PUBLIC_URL` is a placeholder; passing the check does not prove that a vendor can reach the server.
#
# No hosted response is shown because no vendor key or public server was used.

# %%
# LOCAL FALLBACK (no key, no public server): the same address check on this notebook's own URL.
from urllib.parse import urlparse

def passes_public_check(url: str) -> bool:
    """A rough check: HTTPS and not a loopback name. It does not test DNS, firewalls or the server itself."""
    host = urlparse(url).hostname or ""
    return url.startswith("https://") and host not in {"localhost", "127.0.0.1", "::1"}

print(f"LOCAL FALLBACK, no vendor contacted: {URL} passes the public-address check: {passes_public_check(URL)}")

# %% [markdown]
# The next cell builds the three hosted request bodies with a placeholder public address. It runs on every machine: it sends nothing, and it only builds and checks the JSON. A real hosted call would need a public HTTPS server.

# %%
# Hosted request bodies. Built and printed only; nothing is sent. Needs a public HTTPS server to be real.
import json
PUBLIC_URL = "https://trackr.example.com/mcp"   # placeholder: a real hosted call needs a public address
print(f"hosted connector   {PUBLIC_URL} passes the public-address check: {passes_public_check(PUBLIC_URL)}")

anthropic_request = {"headers": {"anthropic-beta": "mcp-client-2025-11-20"},
    "mcp_servers": [{"type": "url", "url": PUBLIC_URL, "name": "trackr"}],
    "tools": [{"type": "mcp_toolset", "mcp_server_name": "trackr"}]}
openai_tool = {"type": "mcp", "server_label": "trackr", "server_url": PUBLIC_URL,
    "require_approval": {"never": {"tool_names": READ_ONLY}},   # every other tool needs approval
    "allowed_tools": READ_ONLY}
gemini_tool = {"type": "mcp_server", "name": "trackr", "url": PUBLIC_URL}
print("Anthropic request body:")
print(json.dumps(anthropic_request, indent=2))
print("OpenAI tool:")
print(json.dumps(openai_tool, indent=2))
print("Gemini tool:")
print(json.dumps(gemini_tool, indent=2))

# %% [markdown]
# Read the `openai_tool` above. `close_issue` is not in `READ_ONLY`, so the OpenAI host would stop and ask a person before it ran. If you need a private server, OpenAI offers a Secure MCP Tunnel (`tunnel_id` instead of `server_url`), and tools like ngrok make a local port public. Both are read-along here. Both put a third party in front of your server, so check the data terms first (lesson 40 covers the gateway that you own).

# %% [markdown]
# ## At work
# - Hosted connectors need a public HTTPS server. Many teams keep the server private and put a gateway in front of it, with OAuth at the edge, so no vendor cloud needs an open port → lesson 15 and lesson 40.
# - `allowed_tools` and `require_approval` are the first safety net. Teams allow read tools and approve writes, then check the same policy in their own gateway, not only in the vendor's settings → lesson 40.
# - A hosted connector sends the tool results to the vendor. Some vendor features are not covered by zero-data-retention terms, so teams check the data terms before a connector sees customer issues. A gateway that you run puts that policy in one place you control → lesson 40.

# %% [markdown]
# ## What just happened
# - One server, two model clients. The LangChain host and the Agents SDK host each made two model calls and reached Trackr over the same URL.
# - The allow-list hid `close_issue` from the Agents SDK host before the model saw any tool. That is a server-side design choice, not a model instruction. The SDK cell printed the tool list the model was offered.
# - Anthropic's helper wrapped one Trackr tool and called it without a model. The hosted options were only built and checked, not sent.
# - A vendor's cloud cannot reach `127.0.0.1`, so a hosted connector needs a public address or a tunnel.

# %% [markdown]
# ## Common mistakes
# The Gemini SDK accepts a list of Python functions as tools, so it is tempting to pass an MCP session in `tools` too. The synchronous call refuses it with this error. The key is a placeholder, and the error comes before any network call:

# %% tags=["raises-exception"]
from google import genai
from google.genai import types
async with Client(URL) as session_client:
    config = types.GenerateContentConfig(tools=[session_client.session])   # an MCP session, not a function
gclient = genai.Client(vertexai=True, api_key="demo")
gclient.models.generate_content(model="gemini-3.1-flash-lite", contents=QUESTION, config=config)   # raises here

# %% [markdown]
# Fix: pass the MCP tools through a client that knows MCP, such as `MCPAdapter` plus `bind_tools` (step 4), or convert each tool to a function declaration yourself. Do not pass the session object as a tool. In the async client the same attempt fails differently (a pickling error), and the docs mark this pattern experimental.
#
# A second mistake is to use an MCP server object outside its `async with` block. The server is not connected, so listing its tools fails:

# %% tags=["raises-exception"]
loose = MCPServerStreamableHttp(params={"url": URL}, name="trackr-loose")
await loose.list_tools()   # raises: the server was never connected

# %% [markdown]
# Fix: enter the server with `async with`, or call `connect()` and `cleanup()` yourself, around every use.

# %% [markdown]
# ## Try it
# Make a second read-only server whose allow-list has only `search_issues`. List the tools it exposes, then call `search_issues` with the text `"safari"` through `call_tool` and print how many issues it finds. Use no model.

# %%
# your code here
# Start from: MCPServerStreamableHttp(params={"url": URL}, name=..., tool_filter=create_static_tool_filter(allowed_tool_names=[...]))
# Then: await server.list_tools(), and read (await server.call_tool("search_issues", {"text": "safari"})).structured_content["result"].

# %% [markdown]
# Clean up. This cell runs last: it closes the clients, stops the server and saves the recording.

# %%
await stack.aclose()
proc.terminate()
proc.wait(timeout=10)
server_log.close()
llm_replay.stop()
print("clients closed, server stopped | lesson 14 done")

# %% [markdown]
# ## Key terms
# - **vendor SDK client** — an MCP client shipped by a model vendor (here the OpenAI Agents SDK) that runs in your process and drives the agent loop.
# - **hosted MCP (connector)** — a vendor feature where the vendor's cloud calls your MCP server, so the server must be reachable over public HTTPS.
# - **allowed_tools** — a list of tool names the host may import; everything else stays hidden.
# - **require_approval** — the setting that decides which tool calls need a person to approve them before they run.
# - **Secure MCP Tunnel** — OpenAI's way to reach a private MCP server without a public address.
# - **session-as-tool pitfall** — passing an MCP session object as a model tool; the synchronous Gemini SDK refuses it. Use MCP-aware bindings instead.
# - **OpenAI-compatible endpoint** — a URL that accepts the OpenAI chat API for another vendor's model; here Google's endpoint for Gemini.

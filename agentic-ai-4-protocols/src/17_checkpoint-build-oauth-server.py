# %% [markdown]
# # 17 · Checkpoint (Build, part 1): an MCP server with OAuth and two clients
# Level L3 · Part 3 · core · ~120 min · builds on 14, 16

# %% [markdown]
# ## Goal
# By the end, Trackr runs as an OAuth-protected MCP server over Streamable HTTP, with a read scope and a write scope. Two clients log in and close an issue through a model: a LangChain agent and an OpenAI Agents SDK agent, each with its own login. A third client holds only a read token, and the server refuses its `close_issue` with `403`. Five requirements, R1 to R5, are ticked by checks at the end. The model budget is 6 calls, 8 allowed.

# %% [markdown]
# ## The idea
# Lesson 14 showed two hosts talking to one server. Lesson 16 showed a client that logs in and steps up its scope. This checkpoint joins them. The server gives every token a scope. Each client asks only for the scopes it needs. The server checks the scope on every write, so a read token cannot close an issue even when it reaches the server.
#
# Analogy: an office keycard. The front desk issues a card with the floors you may enter (the scopes). Every door checks the card again, even though you already passed the lobby.

# %% [markdown]
# ## Picture
# ```mermaid
# flowchart LR
#   A[Client A: LangChain agent, write login] -->|Bearer token, issues:write| T[Trackr MCP server :8768]
#   B[Client B: Agents SDK agent, write login] -->|Bearer token, issues:write| T
#   C[Client C: LangChain agent, read login] -->|Bearer token, issues:read| T
#   T -.->|close_issue with a read token: 403| C
#   AS[Auth server :9000] -.->|tokens with scopes| A
#   AS -.-> B
#   AS -.-> C
# ```

# %% [markdown]
# ## Requirements
# Trackr v2 is done when every box is ticked by the ship check (step 9).
# - [ ] **R1.** Trackr serves Streamable HTTP on `127.0.0.1:8768`. With no token it answers `401` and names the metadata. Client C's token carries only `issues:read`. Clients A and B step up to `issues:read issues:write`.
# - [ ] **R2.** The read token searches issues. The same token calling `close_issue` gets `403 insufficient_scope`, and the challenge names `issues:write`.
# - [ ] **R3.** Client A, the LangChain agent with a write login, closes issue 1, and its search for 'Typo' finds issue 9.
# - [ ] **R4.** Client B, the Agents SDK agent with its own write login, closes issue 17, and its search for 'Typo' finds issue 9.
# - [ ] **R5.** Client C, the LangChain agent with a read-only login, is refused `close_issue`. Issue 9 stays open.
#
# **Make it yours.** Swap in a SQLite file or GitHub with your own token. The scopes and checks stay the same.

# %% [markdown]
# ## Build it

# %% [markdown]
# ### 1. The server: lesson 16's Trackr plus one search tool
# Lesson 16 built the OAuth-protected Trackr with its write gate. This checkpoint does not rewrite it. The new file imports it and adds `search_issues`, the tool the clients need to find issues. The gate, the token check and the `403` challenge all come from lesson 16. The first cell makes the folder and checks that lesson 16's files exist.

# %%
import sys
import os, sys
sys.path.insert(0, "..")   # tut_env lives in the topic folder
from tut_env import env
for _name in ("DEV_SIGNING_KEY", "LAB_PROXY_CLIENT_SECRET", "LAB_NOTES_CLIENT_SECRET"):
    os.environ[_name] = env(_name, "")   # from .env (never in the lesson)
assert len(os.environ["DEV_SIGNING_KEY"]) >= 32, "put DEV_SIGNING_KEY (32+ characters) in .env: see .env.example"
from pathlib import Path
Path("../apps/17").mkdir(parents=True, exist_ok=True)
assert Path("../apps/16/trackr_stepup.py").exists() and Path("../apps/16/auth_server.py").exists(), \
    "run lesson 16 first: it writes the OAuth servers this checkpoint reuses"
print("apps/17 ready; lesson 16's servers found")

# %% [markdown]
# The file below is the whole new server file. Its one new tool is read-only, so the server-wide check passes any token that has `issues:read`.

# %%
%%writefile ../apps/17/trackr_checkpoint.py
"""Trackr for lesson 17: lesson 16's OAuth server plus search_issues, on 127.0.0.1:8768."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "16"))   # lesson 16's Trackr and gate
import uvicorn
import trackr_stepup as s
from mcp.types import ToolAnnotations

@s.mcp.tool(title="Search open issues", annotations=ToolAnnotations(readOnlyHint=True))
def search_issues(text: str) -> list[s.base.Issue]:
    """Find open issues whose title contains the text, in any letter case. Needs issues:read."""
    return s.base.search_issues(text)

if __name__ == "__main__":
    uvicorn.run(s.gate(s.mcp.streamable_http_app(json_response=True)), host="127.0.0.1", port=s.PORT,
                log_level="warning")

# %% [markdown]
# ### 2. Start the auth server and Trackr, and wait until both answer
# The notebook starts the lesson 16 authorization server and the new Trackr as two processes. It polls their metadata URLs, which need no token. It stops both at the end, and again if a later cell fails.
# Note: `mcp` 2.x uses `httpx2` for the OAuth client; `httpx` is used for the plain calls.

# %%
import subprocess, time, atexit, secrets
from urllib.parse import urlparse, parse_qs
import httpx, httpx2
sys.path.insert(0, "..")   # so llm_setup and llm_replay import
import llm_replay
AS_URL, RS_URL = "http://127.0.0.1:9000", "http://127.0.0.1:8768"
RESOURCE = f"{RS_URL}/mcp"                           # Trackr's audience
CLIENT_ID = "https://ops-desk.example/client.json"   # a client ID metadata document (CIMD) URL
REDIRECT = "http://127.0.0.1:9999/callback"          # where the client wants the code sent
WRITE, READ = "issues:read issues:write", "issues:read"
procs, logs = [], []
for script, folder, log_name in [("auth_server", "16", "auth_server"), ("trackr_checkpoint", "17", "trackr")]:
    log = open(f"../apps/17/{log_name}.log", "w")
    logs.append(log)
    procs.append(subprocess.Popen([sys.executable, str(Path(f"../apps/{folder}/{script}.py").resolve())],
                                  stdout=log, stderr=subprocess.STDOUT))

def stop_servers():
    for p in procs:
        if p.poll() is None:
            p.terminate(); p.wait(timeout=10)
    for log in logs:
        log.close()
_ = atexit.register(stop_servers)   # runs at exit, even if a later cell fails
print("started: auth server and Trackr v2, two processes")

# %% [markdown]
# Now poll both metadata URLs until they answer. A dead process shows its log.

# %%
for url, p, name in [(f"{AS_URL}/.well-known/oauth-authorization-server", procs[0], "auth_server"),
                     (f"{RS_URL}/.well-known/oauth-protected-resource/mcp", procs[1], "trackr")]:
    deadline = time.monotonic() + 20
    while True:
        try:
            httpx.get(url, timeout=5); break
        except httpx.ConnectError:
            if p.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError(f"{name} did not start: read ../apps/17/{name}.log")
            time.sleep(0.2)
print("auth server and Trackr v2 are up at", RS_URL, "and", AS_URL)

# %% [markdown]
# ### 3. R1, part 1: no token, so a `401` and the metadata
# A request with no token gets `401`. Its `WWW-Authenticate` header names the metadata document. The client reads that document to find the authorization server.

# %%
HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json",
           "MCP-Protocol-Version": "2026-07-28"}
META = {"io.modelcontextprotocol/protocolVersion": "2026-07-28", "io.modelcontextprotocol/clientCapabilities": {}}
R = {}   # one True or False per requirement, filled in as the checks run

def post(method, params=None, token=None, name=None):
    """One POST to /mcp, the lesson 15 and 16 helper. The bearer token, if given, goes in Authorization."""
    headers = {**HEADERS, "Mcp-Method": method, **({"Mcp-Name": name} if name else {})}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": {**(params or {}), "_meta": META}}
    return httpx.post(RESOURCE, json=body, headers=headers, timeout=10)

r = post("tools/list")
prm = httpx.get(f"{RS_URL}/.well-known/oauth-protected-resource/mcp").json()
print("no token:", r.status_code, "| names metadata:", "resource_metadata" in r.headers["www-authenticate"])
print("authorization_servers:", prm["authorization_servers"])
R["R1a"] = r.status_code == 401 and "resource_metadata" in r.headers["www-authenticate"]

# %% [markdown]
# ### 4. R1, part 2: three logins, each with the scopes it needs
# Each login is lesson 16's flow in one function. The client starts with a `401`, uses PKCE with `S256` and the `resource`, and checks the `iss` on the redirect. Lesson 16's `401` challenge names only `issues:read`, so every client first gets a read token. Asking for write up front is not what this server offers. A write client must trigger the 403 step-up, and `close_issue` on the missing id 999 does that without closing anything. Client C never asks for write. The function returns the token, the scope before the write call and the scope after it.

# %%
from mcp import Client
from mcp.client.auth import OAuthClientProvider
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.auth import AuthorizationCodeResult, OAuthClientMetadata

# %% [markdown]
# The storage keeps one login's tokens. The SDK calls these four methods to read and write them.

# %%
class MemoryStorage:
    """Token storage for one login: the four methods the SDK needs."""
    def __init__(self):
        self.tokens, self.client = None, None
    async def get_tokens(self): return self.tokens
    async def set_tokens(self, tokens): self.tokens = tokens
    async def get_client_info(self): return self.client
    async def set_client_info(self, info): self.client = info

print("token storage ready: four methods, one login at a time")

# %% [markdown]
# The login function runs the whole flow for one client and returns its token and the scopes before and after its write call.

# %%
async def login(write: bool):
    """Lesson 16's flow for one client. It starts read-only; a write client then makes one write call,
    and the 403 makes it step up. Returns (token, scope before the write call, scope after it)."""
    storage, back = MemoryStorage(), []   # back: the redirects the 'browser' got
    async def redirect_handler(url: str) -> None:
        async with httpx.AsyncClient() as c:
            back.append((await c.get(url, follow_redirects=False)).headers["location"])
    async def callback_handler() -> AuthorizationCodeResult:
        q = parse_qs(urlparse(back.pop(0)).query)
        return AuthorizationCodeResult(code=q["code"][0], state=q["state"][0], iss=q["iss"][0])
    meta = OAuthClientMetadata(client_name="Ops desk", redirect_uris=[REDIRECT], response_types=["code"],
                               token_endpoint_auth_method="none", scope=READ)
    provider = OAuthClientProvider(server_url=RESOURCE, client_metadata=meta, storage=storage,
                                   redirect_handler=redirect_handler, callback_handler=callback_handler,
                                   client_metadata_url=CLIENT_ID)
    async with httpx2.AsyncClient(auth=provider) as http:
        async with Client(streamable_http_client(RESOURCE, http_client=http)) as c:
            await c.call_tool("count_open", {"team": "web"})   # the first call runs the whole flow
            before = storage.tokens.scope
            if write:   # id 999 does not exist, so nothing closes; the point is the 403 and the step-up
                await c.call_tool("close_issue", {"issue_id": 999})
    return storage.tokens.access_token, before, storage.tokens.scope

# %% [markdown]
# Now the three logins. The printed scopes are the ones the server granted, not the ones the client asked for.

# %%
TOKENS, GRANTED = {}, {}
for who, write in [("A", True), ("B", True), ("C", False)]:
    TOKENS[who], before, GRANTED[who] = await login(write)
    print(f"client {who} wants write={write}")
    print(f"  scope before the write call: {before!r}")
    print(f"  after the write call: {GRANTED[who]!r}")
R["R1b"] = ("issues:write" in GRANTED["A"].split() and "issues:write" in GRANTED["B"].split()
            and GRANTED["C"].split() == ["issues:read"])
R["R1"] = R["R1a"] and R["R1b"]

# %% [markdown]
# ### 5. R2: the read token searches, and its close is refused (no model)
# `trackr()` calls one tool with a bearer token. If the server answers `403`, it returns the refusal as text, so a model can read it. The read token searches fine. Its `close_issue` is refused, and the challenge names the scope that was missing.

# %%
def trackr(token, name, args):
    """Call one Trackr tool with a bearer token. Returns the tool's text, or the refusal."""
    r = post("tools/call", {"name": name, "arguments": args}, token, name)
    if r.status_code == 403:
        need = r.headers["www-authenticate"].split('error_description="')[1].split('"')[0]
        return f"REFUSED with 403: {need}"
    if r.status_code != 200:
        return f"HTTP {r.status_code}"
    return " ".join(c["text"] for c in r.json()["result"]["content"])

found = trackr(TOKENS["C"], "search_issues", {"text": "Typo"})
refused = trackr(TOKENS["C"], "close_issue", {"issue_id": 9})
print("read token, search:", found)
print("read token, close_issue 9:", refused)
R["R2"] = "Typo on the pricing page" in found and refused.startswith("REFUSED with 403") and "issues:write" in refused

# %% [markdown]
# ### 6. Client A: the LangChain agent with the write token
# Client A's tools are plain LangChain tools. Each one calls Trackr with client A's token. A model turn has two steps: the model asks for tools, the host runs them, and the model writes the answer. The helper below does those steps and nothing else.

# %%
from langchain_core.tools import tool
from langchain_core.messages import AIMessage, HumanMessage

def make_tools(token):
    """LangChain tools that call Trackr with one client's token."""
    @tool("search_issues")
    def search_issues(text: str) -> str:
        """Find open issues whose title contains the text."""
        return trackr(token, "search_issues", {"text": text})
    @tool("close_issue")
    def close_issue(issue_id: int) -> str:
        """Close one issue by id. Needs issues:write."""
        return trackr(token, "close_issue", {"issue_id": issue_id})
    return [search_issues, close_issue]

def run_calls(tools, calls):
    """Run each requested tool call and return the ToolMessages."""
    by_name = {t.name: t for t in tools}
    return [by_name[c["name"]].invoke({**c, "type": "tool_call"}) for c in calls]

OUT = {}   # the text each client's tools returned
tools_a = make_tools(TOKENS["A"])
Q_A = "Close issue 1, and search open issues for 'Typo'. Make both tool calls now."
print("client A tools:", [t.name for t in tools_a])

# %% [markdown]
# The model cell asks the model which tools to call, runs them with client A's token, then asks for the answer. Two model calls. `get_llm` starts the recording or the replay for this notebook, so this cell is where it runs.

# %% tags=["needs-llm"]
from llm_setup import get_llm
llm = get_llm("17_checkpoint-build-oauth-server", model="gemini-3.1-flash-lite", max_calls=8)
first_a = llm.bind_tools(tools_a).invoke([HumanMessage(Q_A)])
results_a = run_calls(tools_a, first_a.tool_calls)
final_a = llm.bind_tools(tools_a).invoke([HumanMessage(Q_A), first_a, *results_a])
print("client A asks for:", [(c["name"], c["args"]) for c in first_a.tool_calls])
print("client A answer:", final_a.text)
OUT["A"] = [r.text for r in results_a]

# %% [markdown]
# If the model cell was skipped, a scripted pair of tool calls stands in for the model. It is labelled, and the tools still run against Trackr.

# %%
if "final_a" not in globals():   # fallback: no model here, so scripted tool calls stand in
    scripted_a = [{"name": "close_issue", "args": {"issue_id": 1}, "id": "scripted_a1"},
                  {"name": "search_issues", "args": {"text": "Typo"}, "id": "scripted_a2"}]
    print("SCRIPTED stand-in (no model): client A calls:", [(c["name"], c["args"]) for c in scripted_a])
    OUT["A"] = [r.text for r in run_calls(tools_a, scripted_a)]
print("client A tool results:", [t[:70] for t in OUT["A"]])

# %% [markdown]
# ### 7. Client B: the OpenAI Agents SDK agent with its own write login (`needs-llm`)
# Client B is a different host. The Agents SDK has its own MCP client and its own loop. It takes the bearer token as a request header. Its model is Gemini behind Google's OpenAI-compatible endpoint, as in lesson 14. Tracing is off, because it would upload the run.

# %% tags=["needs-llm"]
import os
from dotenv import load_dotenv
from openai import AsyncOpenAI
from agents import Agent, OpenAIChatCompletionsModel, Runner, set_tracing_disabled
from agents.mcp import MCPServerStreamableHttp
load_dotenv("../.env")
set_tracing_disabled(True)
key = os.environ.get("GOOGLE_CLOUD_API_KEY") or "replay-no-key-needed"   # replay never sends it
gemini = OpenAIChatCompletionsModel(model="gemini-3.1-flash-lite",
    openai_client=AsyncOpenAI(base_url="https://generativelanguage.googleapis.com/v1beta/openai/", api_key=key))
Q_B = "Close issue 17, and search open issues for 'Typo'. Make both tool calls now."
async with MCPServerStreamableHttp(params={"url": RESOURCE, "headers": {"Authorization": f"Bearer {TOKENS['B']}"}},
                                   name="trackr-sdk", cache_tools_list=True) as server:
    agent = Agent(name="Trackr assistant", instructions="Answer with the tools. Be brief.",
                  model=gemini, mcp_servers=[server])
    run_b = await Runner.run(agent, Q_B)
print("client B answer:", run_b.final_output)
print("model calls made by client B:", len(run_b.raw_responses))
OUT["B"] = [str(i.output) for i in run_b.new_items if getattr(i, "type", "") == "tool_call_output_item"]

# %% [markdown]
# If the SDK cell was skipped, the same two calls run directly with client B's token, and the output says so.

# %%
if "run_b" not in globals():   # fallback: no model here
    print("SCRIPTED stand-in (no model): client B calls close_issue 17 and searches 'Typo'")
    OUT["B"] = [trackr(TOKENS["B"], "close_issue", {"issue_id": 17}),
                trackr(TOKENS["B"], "search_issues", {"text": "Typo"})]
print("client B tool results:", [t[:70] for t in OUT["B"]])

# %% [markdown]
# ### 8. Client C: a read-only login, and the refused close (`needs-llm`)
# Client C uses the same LangChain host, but its token has only `issues:read`. The model asks to close issue 9. The server answers `403`, the tool returns that refusal as text, and the model reports it. Issue 9 stays open. Two model calls.

# %% tags=["needs-llm"]
tools_c = make_tools(TOKENS["C"])
Q_C = "Close issue 9 with a tool, then tell me what happened."
first_c = llm.bind_tools(tools_c).invoke([HumanMessage(Q_C)])
results_c = run_calls(tools_c, first_c.tool_calls)
final_c = llm.bind_tools(tools_c).invoke([HumanMessage(Q_C), first_c, *results_c])
print("client C asks for:", [(c["name"], c["args"]) for c in first_c.tool_calls])
print("client C tool said:", results_c[0].text)
print("client C answer:", final_c.text)
OUT["C"] = [r.text for r in results_c]

# %% [markdown]
# If the model cell was skipped, a scripted `close_issue` on issue 9 stands in. The refusal still comes from the live server.

# %%
if "final_c" not in globals():   # fallback: no model here, so a scripted call stands in
    scripted_c = [{"name": "close_issue", "args": {"issue_id": 9}, "id": "scripted_c1"}]
    print("SCRIPTED stand-in (no model): client C calls:", scripted_c)
    OUT["C"] = [r.text for r in run_calls(make_tools(TOKENS["C"]), scripted_c)]
print("client C tool results:", [t[:70] for t in OUT["C"]])

# %% [markdown]
# ### 9. Ship check: every requirement, ticked
# Each check reads what the clients actually received. The last check asks Trackr live, with the read token, whether issue 9 is still open. A check that failed prints `[ ]`, and the notebook does not stop, so you can see every result.

# %%
still_open = "Typo on the pricing page" in trackr(TOKENS["C"], "search_issues", {"text": "Typo"})
R["R3"] = any("closed" in t for t in OUT["A"]) and any("Typo on the pricing page" in t for t in OUT["A"])
R["R4"] = any("closed" in t for t in OUT["B"]) and any("Typo on the pricing page" in t for t in OUT["B"])
R["R5"] = any(t.startswith("REFUSED with 403") and "issues:write" in t for t in OUT["C"]) and still_open
ticks = [("R1", "Trackr over Streamable HTTP, OAuth, two scopes"),
         ("R2", "read token searches, and its close is refused with 403"),
         ("R3", "client A (LangChain, write) closes issue 1 and finds 'Typo'"),
         ("R4", "client B (Agents SDK, write) closes issue 17 and finds 'Typo'"),
         ("R5", "client C (read-only) is refused, issue 9 stays open")]
for key_, text in ticks:
    print(f"[{'x' if R[key_] else ' '}] {key_}. {text}")
print("ship check:", "PASSED" if all(R[k] for k, _ in ticks) else "NOT PASSED: read the lines above")

# %% [markdown]
# ### 10. Stop the servers and save the recording
# This is the last cell. It stops both servers and saves the model recording. If the model cells ran in record mode, `llm_replay.stop()` writes the cassette. In replay mode it changes nothing.

# %%
stop_servers()
llm_replay.stop()   # saves the recording if a model ran; a no-op otherwise
print("stopped: Trackr v2 and the auth server | lesson 17 done")

# %% [markdown]
# ## At work
# - Production teams put one authorization server in front of every MCP server, and give each client its own login. The client's identity and its scopes travel with the token. → lesson 34 (Keycloak, the organisation's one authorization server).
# - Checking scope only at the door is not enough. A gateway checks the scope of each tool before the call reaches the server, so one policy covers every server. → lesson 40.
# - Passing a user's token through to a downstream service lets that service act with the user's rights. Teams avoid this confused-deputy pattern by checking audiences and never forwarding a token. → lesson 31.

# %% [markdown]
# ## Reference solution
# <details><summary>Try the build first. Open this only to compare.</summary>
#
# The checks print these results. The tool results must match, whatever the model says:
#
# - R1: no token gives `401`. Clients A and B step up to `issues:read issues:write`. Client C keeps `issues:read`.
# - R2: the read token finds "Typo on the pricing page". Its `close_issue 9` gives `REFUSED with 403`.
# - R3: client A's close of issue 1 returns text containing `closed`. Its search for 'Typo' finds issue 9.
# - R4: client B's close of issue 17 returns text containing `closed`, wrapped in the SDK's `{'type': 'text'}` dict. Its search for 'Typo' finds issue 9.
# - R5: client C's tool says `REFUSED with 403: issues:write is needed`. Issue 9 is still open.
#
# Each login is its own token. A read token reaches the server but cannot close, because scope is checked per tool on every request.
# </details>

# %% [markdown]
# ## Key terms
# - **Trackr v2** — lesson 16's OAuth-protected Trackr with a search tool added. Two login scopes, one read-only and one with write.
# - **bearer token** — the access token sent in an `Authorization: Bearer` header. Whoever holds it can use it until it expires (lesson 15).
# - **scope** — an OAuth permission string such as `issues:read`, checked per request and per tool (lesson 15).
# - **insufficient_scope** — the error for a valid token that lacks a scope. Here it is `403` with the needed scope in the challenge (lesson 16).
# - **checkpoint** — a build that joins earlier lessons into one working system, checked by named requirements.

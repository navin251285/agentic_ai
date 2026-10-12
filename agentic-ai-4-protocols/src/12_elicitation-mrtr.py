# %% [markdown]
# # 12 · Asking the user mid-call: elicitation with Multi Round-Trip Requests
# Level L3 · Part 3 · professional · ~35 min · builds on 07

# %% [markdown]
# ## Goal
# By the end a Trackr tool pauses and asks the user "Close 3 open web issues?". You answer in code. The call then completes or aborts, and a changed pause token is refused. A real model calls that tool once and writes the final answer: 2 model calls in total.

# %% [markdown]
# ## Why it matters
# Some tool calls need a person in the loop. Closing every open issue of a team is destructive, and the server cannot know whether the caller meant it. Without elicitation there are two bad options. Close at once, and a model that misreads the request closes issues nobody approved. Or add a `confirm: bool` argument, and the model sets `confirm=True` itself, so the flag checks nothing. The cell below shows the second option in plain Python.

# %%
import sys
sys.path.insert(0, "../apps/03")
from trackr_server import ISSUES   # lesson 03's 20 issues

board = [dict(i) for i in ISSUES]   # a copy: this cell must not change the server's data

def bulk_close_naive(team, confirm=False):
    """Close every open issue of a team. The 'confirm' flag is the only check."""
    if not confirm:
        return "refused: pass confirm=True to close"
    closed = [i for i in board if i["team"] == team and i["status"] == "open"]
    for i in closed:
        i["status"] = "closed"
    return f"closed {len(closed)} {team} issues"

print(bulk_close_naive("web"))                 # the first try is refused
print(bulk_close_naive("web", confirm=True))   # the model can set this flag itself
print("a person was asked: no")

# %% [markdown]
# The point is in the last line. The model chose the flag, so no person was asked. MCP elicitation moves the question to the client's user, and the server waits for the answer before it closes anything.

# %% [markdown]
# ## The idea
# A server cannot send a question to the client in the middle of a request in MCP 2026-07-28. There is no open session to carry it. **Multi Round-Trip Requests (MRTR)** solve this with a pause and a retry. The server answers `tools/call` at once with an `InputRequiredResult`. It holds a list of `inputRequests`, here one form question, and an opaque `requestState`.
#
# The client asks its user, then sends the same call again with a new JSON-RPC id. The retry carries `inputResponses` for the server's questions, and it echoes the `requestState` unchanged. The server then finishes the call or pauses again.
#
# Analogy: a shop counter that gives you a numbered ticket and asks you to come back. The ticket says what is still pending. Only the counter that sealed it can honour it.

# %% [markdown]
# ## Picture
# ```mermaid
# sequenceDiagram
#   participant C as Client (model host + user)
#   participant S as Trackr server
#   C->>S: tools/call bulk_close(web), id 10
#   S-->>C: InputRequiredResult: inputRequests + requestState (sealed)
#   C->>C: the user is asked: close 3 open web issues?
#   C->>S: tools/call bulk_close(web), id 11, inputResponses + requestState
#   S-->>C: result: closed 3 web issues
# ```

# %% [markdown]
# ## Already know this?
# Part 2 (lessons 03–11) covered MCP tools, the stateless core, A2A and AG-UI. If you can answer these, skip to **lesson 13**:
# 1. Which `_meta` key on each 2026-07-28 request carries the protocol version?
# 2. A tool runs and says it cannot do the job. Is that a JSON-RPC error or a result with `isError: true`?
# 3. A request names a protocol version the server does not speak. Which error code comes back?
# 4. Which tool annotation tells a client that a call may destroy data?
# 5. Which AG-UI event ends a run that finished normally?
#
# <details><summary>Answers</summary>
#
# 1. `io.modelcontextprotocol/protocolVersion`. 2. A result with `isError: true`. 3. `-32022`. 4. `destructiveHint`. 5. `RUN_FINISHED`.
#
# </details>

# %% [markdown]
# ## Step by step
#
# ### 1. The server: one tool that asks before it acts
# The issues come from lesson 03. The new tool `bulk_close` has two parameters. The model fills `team`. The `confirm` value comes from a **resolver**, a function the framework runs before the tool body. `Resolve(confirm_bulk)` says the value is not the model's to set. `confirm_bulk` returns `Elicit(...)`, which asks the user a form question. The annotation `ElicitationResult[Confirm]` gives the body one of three outcomes: accept, decline or cancel.
#
# The server keeps the pause token sealed with `RequestStateSecurity`. Here the key is random for this process.

# %%
from pathlib import Path
Path("../apps/12").mkdir(parents=True, exist_ok=True)
print("app folder ready: ../apps/12")

# %% [markdown]
# The `writefile` cell below saves the server to `../apps/12/trackr_mrtr.py`.

# %%
%%writefile ../apps/12/trackr_mrtr.py
"""Trackr with an elicitation tool (lesson 12). bulk_close asks the user before it closes anything.

The issues and the Team type come from the lesson 03 server. The pause token (requestState)
is sealed by RequestStateSecurity, so a changed token is refused."""
import sys
from pathlib import Path
from typing import Annotated
from pydantic import BaseModel
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "03"))
import trackr_server as base  # lesson 03: the Team type and the 20 issues
from mcp.server import MCPServer
from mcp.server.mcpserver import (AcceptedElicitation, CancelledElicitation, DeclinedElicitation,
                                  Elicit, ElicitationResult, Resolve)
from mcp.server.request_state import RequestStateSecurity
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations


class Confirm(BaseModel):
    ok: bool


def open_in(team: str) -> list[dict]:
    return [i for i in base.ISSUES if i["team"] == team and i["status"] == "open"]


async def confirm_bulk(team: base.Team) -> Confirm | Elicit[Confirm]:
    """Runs before the tool body. With nothing open there is nothing to ask: the body closes 0."""
    n = len(open_in(team))
    if n == 0:
        return Confirm(ok=True)
    return Elicit(f"Close {n} open {team} issues? They will be marked closed.", Confirm)


mcp = MCPServer("Trackr", request_state_security=RequestStateSecurity.ephemeral())


@mcp.tool(title="Count open issues", annotations=ToolAnnotations(readOnlyHint=True))
def count_open(team: base.Team) -> int:
    return len(open_in(team))


@mcp.tool(title="Close all open issues of a team", annotations=ToolAnnotations(destructiveHint=True))
async def bulk_close(team: base.Team,
                     confirm: Annotated[ElicitationResult[Confirm], Resolve(confirm_bulk)]) -> str:
    match confirm:
        case AcceptedElicitation(data=Confirm(ok=True)):
            done = open_in(team)
            for issue in done:
                issue["status"] = "closed"
            return f"closed {len(done)} {team} issues"
        case AcceptedElicitation():
            return "kept open: the user said no"
        case DeclinedElicitation():
            return "declined: nothing closed"
        case CancelledElicitation():
            return "cancelled: nothing closed"


SECURITY = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=["127.0.0.1:8121", "localhost:8121"],
)

if __name__ == "__main__":
    mcp.run("streamable-http", host="127.0.0.1", port=8121, json_response=True, transport_security=SECURITY)

# %% [markdown]
# ### 2. Start the server and wait until it answers
# The helpers below send one modern request. Each request carries its own version in `_meta`, and the client's capabilities too. The client declares `elicitation`, so the server knows it can answer a question. Without that declaration the server refuses the call (see Common mistakes).

# %%
import atexit, subprocess, sys, time
from pathlib import Path
import httpx
URL = "http://127.0.0.1:8121/mcp"
VERSION_KEY = "io.modelcontextprotocol/protocolVersion"
META = {VERSION_KEY: "2026-07-28",
        "io.modelcontextprotocol/clientCapabilities": {"elicitation": {"form": {}}}}
HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json",
           "MCP-Protocol-Version": "2026-07-28"}

def rpc(method, params=None, req_id=1, extra=None):
    """One modern request. The version and capabilities ride in params._meta."""
    payload = {"jsonrpc": "2.0", "id": req_id, "method": method,
               "params": {**(params or {}), "_meta": META}}
    return httpx.post(URL, json=payload, headers={**HEADERS, "Mcp-Method": method, **(extra or {})}, timeout=15)

def open_count(team):
    """Open issues for a team, read through the count_open tool."""
    r = rpc("tools/call", {"name": "count_open", "arguments": {"team": team}}, req_id=20,
            extra={"Mcp-Name": "count_open"})
    return r.json()["result"]["structuredContent"]["result"]

# %% [markdown]
# Next, start the server as its own process and poll it until it answers. Its log goes to `../apps/12/server.log`, so a failed start can be read there.

# %%
log = open("../apps/12/server.log", "w")
server = subprocess.Popen([sys.executable, str(Path("../apps/12/trackr_mrtr.py").resolve())],
                          stdout=log, stderr=subprocess.STDOUT)
atexit.register(lambda: server.poll() is None and server.terminate())
deadline = time.monotonic() + 20
while True:
    try:
        rpc("server/discover")
        break
    except httpx.ConnectError:
        if server.poll() is not None or time.monotonic() > deadline:
            raise RuntimeError("server did not start: read ../apps/12/server.log")
        time.sleep(0.2)
print("Trackr MRTR server is up on", URL, "| open web issues:", open_count("web"))

# %% [markdown]
# ### 3. The first call: the server pauses and asks
# Send `bulk_close` for `web` with no answers. The server does not wait. It replies at once with `resultType: input_required`. The reply has no content, only the question and the token. Nothing is closed yet.

# %%
call = {"name": "bulk_close", "arguments": {"team": "web"}}
first = rpc("tools/call", call, req_id=10, extra={"Mcp-Name": "bulk_close"}).json()["result"]
print("resultType:", first["resultType"])
for key, req in first["inputRequests"].items():
    print("question", key, "| method:", req["method"], "| message:", req["params"]["message"])
print("requestState is opaque, length", len(first["requestState"]))

# %% [markdown]
# ### 4. The retry: answer, echo the token, send a new id
# The client sends the same call again with a new JSON-RPC id. It adds `inputResponses`, keyed by the server's own keys, and it echoes `requestState` unchanged. This answer is **decline**. The tool body runs and reports that nothing was closed.

# %%
answers = {key: {"action": "decline"} for key in first["inputRequests"]}
retry = {**call, "inputResponses": answers, "requestState": first["requestState"]}
second = rpc("tools/call", retry, req_id=11, extra={"Mcp-Name": "bulk_close"}).json()["result"]
print("resultType:", second.get("resultType", "complete"))
print("tool says:", second["content"][0]["text"])
print("open web issues still:", open_count("web"))

# %% [markdown]
# ### 5. A changed requestState is refused
# The token came back through the client, so the server treats it as untrusted. It sealed the token, so it can tell when someone changed a letter. Change one character, send an accept answer, and the server refuses before the tool body runs.

# %%
state = first["requestState"]
tampered = state[:-1] + ("A" if state[-1] != "A" else "B")
accept = {key: {"action": "accept", "content": {"ok": True}} for key in first["inputRequests"]}
r = rpc("tools/call", {**call, "inputResponses": accept, "requestState": tampered}, req_id=12,
        extra={"Mcp-Name": "bulk_close"})
print("status:", r.status_code, "| error:", r.json().get("error"))
print("open web issues still:", open_count("web"))

# %% [markdown]
# ### 6. The SDK client does the loop
# Real code does not write the retry by hand. The `Client` reads each `InputRequiredResult`, runs the callback for each question, and retries until the result is complete. The callback plays the user: it shows the message and returns the answer. The answer is kept in `USER_ANSWER`, so the notebook runs the same way each time.
#
# Team `api` has 4 open issues. This step uses it, so the web issues stay open for the model in step 8.

# %%
from mcp import Client
from mcp.client import ClientRequestContext
from mcp.types import ElicitRequestParams, ElicitRequestURLParams, ElicitResult

asked = []
USER_ANSWER = "accept"   # the scripted user; set to "decline" to take the other branch

async def user(context: ClientRequestContext, params: ElicitRequestParams) -> ElicitResult:
    """The client's user: shows the question and returns an answer."""
    if isinstance(params, ElicitRequestURLParams):
        return ElicitResult(action="decline")   # this lesson sends no URL questions
    asked.append(params.message)
    if USER_ANSWER == "decline":
        return ElicitResult(action="decline")
    return ElicitResult(action="accept", content={"ok": True})

async with Client(URL, elicitation_callback=user) as client:
    result = await client.call_tool("bulk_close", {"team": "api"})
print("questions shown:", asked)
print("tool says:", result.content[0].text)
print("open api issues now:", open_count("api"))

# %% [markdown]
# ### 7. Form versus URL elicitation
# The question in steps 3–6 is a **form**. The user types structured data that is not secret, and the answer goes to the server. A **URL** question sends the user to a web page, for a password, a payment or an OAuth login. Only that page sees the secret, not the model and not the server. The client callback above already declines URL questions. The server side of URL mode is not available through `Resolve` in mcp 2.3.0, so this cell prints the shape of the URL question the server would send, and does not run it.

# %%
example = ElicitRequestURLParams(mode="url", message="Connect your tracker account to continue.",
                                 url="https://tracker.example/connect", elicitation_id="link-1")
print(example.model_dump(by_alias=True, exclude_none=True))  # shape only: not sent to any server

# %% [markdown]
# ### 8. A real model calls the tool once and writes the answer (`needs-llm`)
# The model gets one tool, `bulk_close`, through the MCP `Client`. The first model call picks the tool. The call goes to the server, the scripted user accepts, and the result goes back to the model. The second and last model call writes the answer. That is 2 model calls, within the budget of 2 for this lesson.
#
# The setup cell imports the course helpers and LangChain. The model is chosen in the next cell.

# %%
import sys
sys.path.insert(0, "..")   # so the course helpers (llm_setup, llm_replay) import
import llm_replay
import logging
logging.getLogger("httpx").setLevel(logging.WARNING)   # hide httpx's INFO line, which prints the model project path
logging.getLogger("google_genai").setLevel(logging.WARNING)   # the Vertex SDK's INFO lines show the project id
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
QUESTION = HumanMessage("Close all open web issues on the Trackr desk. Use the tools, then tell me what happened.")
llm = None        # filled by the model cell; stays None if that cell is skipped
model_ran = False
print("question:", QUESTION.content)

# %% [markdown]
# The model cell below is tagged `needs-llm`. `get_llm` picks the model and starts the recording or the replay for this lesson. Its output is the tool call and the final answer.
#
# The plain `Client` takes `elicitation_callback` and runs the retry loop, which is the point here. `StructuredTool.from_function(coroutine=...)` wraps one `Client.call_tool` as a model tool by hand: `langchain-mcp-adapters` is archived and caps `mcp<2`, so it will not install with mcp 2.3.0, and this lesson wraps the call by hand so the callback stays visible. The `async with Client` block stays open while the model calls the tool.

# %% tags=["needs-llm"]
from llm_setup import get_llm
llm = get_llm("12_elicitation-mrtr", max_calls=2)
USER_ANSWER = "accept"
async with Client(URL, elicitation_callback=user) as client:
    async def close_team(team: str) -> str:
        """Close every open issue of one team. The user is asked to confirm first."""
        return (await client.call_tool("bulk_close", {"team": team})).content[0].text
    close_tool = StructuredTool.from_function(coroutine=close_team, name="bulk_close")
    first_reply = await llm.bind_tools([close_tool]).ainvoke([QUESTION])
    results = [ToolMessage(content=await close_tool.ainvoke(c["args"]), tool_call_id=c["id"])
               for c in first_reply.tool_calls]
    final = await llm.bind_tools([close_tool]).ainvoke([QUESTION, first_reply, *results])
    model_ran = True
print("model asked for:", [(c["name"], c["args"]) for c in first_reply.tool_calls])
print("tool results:", [m.content for m in results])
print("final answer:", final.content)

# %% [markdown]
# If the model cell was skipped, this fallback makes the same tool call by hand. Either way, the last line checks that the web issues closed.

# %%
# Fallback when the model cell was skipped: the same tool call, made by hand.
if not model_ran:
    async with Client(URL, elicitation_callback=user) as client:
        out = await client.call_tool("bulk_close", {"team": "web"})
    print("no model: the tool was called by hand ->", out.content[0].text)
print("open web issues now:", open_count("web"))

# %% [markdown]
# ## At work
# - **Confirm before a destructive tool.** Teams put a user-visible confirmation in front of close, delete and deploy tools, and log who said yes. Who may call the tool is a separate question: → lesson 15.
# - **A pause must survive a replica.** A retry can land on any worker. Every replica needs the same `RequestStateSecurity(keys=[…])` and server name. Otherwise the retry fails with "Invalid or expired requestState", the first failure to drill before launch: → lesson 33.
# - **Secrets go to URL mode.** Passwords, payments and OAuth logins must not pass through a form that the model or the server could read. → lesson 16 covers the OAuth client flow.
# - **Declines are normal.** A client may decline or cancel, and the tool must end cleanly, as `bulk_close` does. Long work that outlives a pause is a Task, not a held connection: → lesson 13.

# %% [markdown]
# ## What just happened
# - The server answered the first call at once with a question and a sealed token. It did not wait for the user.
# - A decline closed nothing. An accept closed the team's open issues, and the count shows it.
# - The retry with a changed token was refused with `Invalid or expired requestState`, before the tool body ran.
# - The SDK `Client` ran the same loop by itself: one call, one question, one retry.
# - The model made one tool call and one final answer. The question went to the user, not to the model.
# - Roots, sampling and logging were server-to-client features too. They are deprecated in 2026-07-28 (SEP-2577). You may meet them in old servers; this lesson does not teach them.

# %% [markdown]
# ## Common mistakes
# Reading a pause as the answer. The first reply has no `content`, only a question. This cell reads it as if it were the result:

# %% tags=["raises-exception"]
print(first["content"][0]["text"])   # the first reply is a question, not a result

# %% [markdown]
# Fix: check `resultType` first. If it is `input_required`, answer the questions and retry with the echoed `requestState`.
#
# A second mistake is to leave out the client's capabilities. The server must know the client can answer a question. A request without the `clientCapabilities` key in `_meta` is refused, and the error names the missing key:

# %%
bare = {"jsonrpc": "2.0", "id": 15, "method": "tools/call",
        "params": {"name": "bulk_close", "arguments": {"team": "web"},
                   "_meta": {VERSION_KEY: "2026-07-28"}}}   # no clientCapabilities
r = httpx.post(URL, json=bare, headers={**HEADERS, "Mcp-Method": "tools/call", "Mcp-Name": "bulk_close"},
               timeout=15)
print("status:", r.status_code, "| error:", r.json().get("error"))

# %% [markdown]
# Fix: send `io.modelcontextprotocol/clientCapabilities` in `_meta`, listing the capabilities the client really has (here `elicitation`). The `Client` does this for you.

# %% [markdown]
# ## Try it
# Set the user to decline and call `bulk_close` for team `mobile` through the SDK `Client`. Print the tool's text and the number of open `mobile` issues afterwards. Then set the user back to accept. Hint: the callback reads `USER_ANSWER`. No model is needed.

# %%
# your code here
# Start from: USER_ANSWER = "decline", then async with Client(URL, elicitation_callback=user) as client: ...

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
USER_ANSWER = "decline"
async with Client(URL, elicitation_callback=user) as client:
    out = await client.call_tool("bulk_close", {"team": "mobile"})
USER_ANSWER = "accept"
print("tool says:", out.content[0].text)
print("open mobile issues:", open_count("mobile"))

# %% [markdown]
# Clean up: stop the server and tell the recorder the lesson is done. This cell runs last.

# %%
server.terminate()
server.wait(timeout=10)
log.close()
llm_replay.stop()
print("server stopped | lesson 12 done")

# %% [markdown]
# ## Key terms
# - **Multi Round-Trip Request (MRTR)** — the 2026-07-28 pattern: the server pauses a request, and the client retries it with answers.
# - **InputRequiredResult** — the reply with `resultType: input_required`, carrying `inputRequests` and/or `requestState`.
# - **requestState** — an opaque token the server seals; the client echoes it unchanged.
# - **elicitation** — the server asks the user for input during a request.
# - **form elicitation** — a question with a schema for structured, non-secret data.
# - **URL elicitation** — a question that sends the user to a web page for a secret.
# - **Resolve / Elicit** — the SDK's resolver (`Resolve`) and the question it returns (`Elicit`).
# - **deprecated roots / sampling / logging** — server-to-client features deprecated in 2026-07-28 (SEP-2577); not taught here.

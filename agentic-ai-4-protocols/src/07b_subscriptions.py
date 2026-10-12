# %% [markdown]
# # 07b · Change notifications: subscriptions/listen
# Level L2 · Part 2 · professional · ~30 min · builds on 07

# %% [markdown]
# ## Goal
# By the end you open one `subscriptions/listen` stream on a Trackr worker. You read its acknowledgment and its `subscriptionId`. You then see a tool change and a runbook edit arrive as events, without asking. Last, you drop the stream, make a change while it is down, and re-listen. You see that the change is not replayed, so you refetch to catch up. No model is needed.

# %% [markdown]
# ## Why it matters
# Without a listen stream, a host that shows Trackr's tools and runbooks has to ask again and again. A change is seen only at the next ask. Polling `tools/list` every 30 seconds for two lists costs 240 requests an hour per host, and a new tool can be 30 seconds late. Most of those requests return nothing new.
#
# With a listen stream, an idle host makes no calls. The server sends one event when a tool or a runbook changes, and the host refetches only then.
#
# You do not need it for a single stdio server with a fixed tool list, or for a one-shot script that asks once and exits.

# %% [markdown]
# ## The idea
# A `subscriptions/listen` request asks the server to keep its response open and send change events on it. The request names what you want: `toolsListChanged`, `resourcesListChanged`, or `resourceSubscriptions` for particular URIs. The first frame is an acknowledgment. It states the subset the server agreed to send, and it carries a `subscriptionId`. That id is the listen request's own JSON-RPC id, and every later frame of the stream repeats it.
#
# The events carry no data about the change. A `tools/list_changed` event says "the tool list changed", and the client asks for the list again. Streams do not resume. If the stream drops, the client opens a new one and refetches what it depends on.
#
# Analogy: a shop bell over the door. It rings when someone comes in. It does not tell you who came in or what they bought, and it does not ring for the time you were out.

# %% [markdown]
# ## Picture
# ```mermaid
# sequenceDiagram
#   participant C as Client
#   participant S as Trackr worker
#   C->>S: subscriptions/listen (id 100: tools, runbook://web)
#   S-->>C: ack: honored filter, subscriptionId 100
#   C->>S: tools/call enable_escalation
#   S-->>C: notifications/tools/list_changed (subscriptionId 100)
#   C->>S: tools/list (refetch)
#   Note over C,S: stream drops: no replay
#   C->>S: subscriptions/listen (id 200)
# ```

# %% [markdown]
# ## Step by step
#
# ### 1. Check the lesson 03 server and write the listen worker
# The worker is the lesson 03 Trackr server with three additions. It has a web runbook at `runbook://web`, a tool that edits the runbook, and a tool that is added while the server runs. Each change tells the stream. The first cell checks that lesson 03 exists. The next cell writes the worker file.

# %%
from pathlib import Path
TRACKR_DIR = Path("../apps/03").resolve()
assert (TRACKR_DIR / "trackr_server.py").exists(), "run lesson 03 first: it writes the Trackr server"
Path("../apps/07b").mkdir(parents=True, exist_ok=True)
print("Trackr server found: ../apps/03/trackr_server.py")

# %% [markdown]
# The worker below is the lesson 03 server with the three additions. It uses the same security settings as lesson 07. Its runbook text is the lesson 04 web runbook, shortened to what this lesson needs.

# %%
%%writefile ../apps/07b/trackr_listen_worker.py
"""Trackr listen worker (lesson 07b): the lesson 03 server plus a web runbook, a tool that edits it,
and a tool that is added while the server runs. Every change is announced on subscriptions/listen."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "03"))  # the lesson 03 server
from mcp.server.mcpserver import Context
from mcp.server.transport_security import TransportSecuritySettings
from trackr_server import mcp, ISSUES, Issue, Severity

RUNBOOK = {"web": "Web runbook\n1. Check the CDN status page.\n2. Roll back the last front-end deploy if errors rise.\n3. Page web on-call for high or critical."}
ENABLED = {"escalation": False}

@mcp.resource("runbook://web", title="Web runbook", mime_type="text/plain")
def web_runbook() -> str:
    """The web runbook. Its text can change while the server runs."""
    return RUNBOOK["web"]

@mcp.tool(title="Edit the web runbook")
async def edit_web_runbook(text: str, ctx: Context) -> str:
    """Replace the web runbook text and announce that runbook://web changed."""
    RUNBOOK["web"] = text
    await ctx.notify_resource_updated("runbook://web")
    return "runbook://web updated"

def escalate_issue(issue_id: int, severity: Severity) -> Issue:
    """Set one issue's severity. This tool is added to the server at run time."""
    for issue in ISSUES:
        if issue["id"] == issue_id:
            issue["severity"] = severity
            return issue
    raise ValueError(f"Issue {issue_id} does not exist")

@mcp.tool(title="Enable the escalation tool")
async def enable_escalation(ctx: Context) -> str:
    """Add escalate_issue to the tool list and announce that the tool list changed. Runs once."""
    if ENABLED["escalation"]:
        return "escalate_issue is already added"
    mcp.add_tool(escalate_issue, name="escalate_issue", title="Escalate an issue",
                 description="Set one issue's severity.")
    ENABLED["escalation"] = True
    await ctx.notify_tools_changed()
    return "escalate_issue added"

PORT = int(sys.argv[1])   # the notebook passes the port
SECURITY = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=[f"127.0.0.1:{PORT}", f"localhost:{PORT}"],
)

if __name__ == "__main__":
    mcp.run("streamable-http", host="127.0.0.1", port=PORT, json_response=True,
            transport_security=SECURITY)

# %% [markdown]
# ### 2. The helpers: each request carries its own version
# `body` and `post` are the lesson 07 helpers. A `resources/read` request also repeats its URI in the `Mcp-Name` header, so the helper takes an extra header argument. The notebook uses one worker on port 10070.

# %%
import asyncio, json
import httpx
VERSION_KEY = "io.modelcontextprotocol/protocolVersion"
SUB_KEY = "io.modelcontextprotocol/subscriptionId"
META = {VERSION_KEY: "2026-07-28", "io.modelcontextprotocol/clientCapabilities": {}}
PORT = 10070
URL = f"http://127.0.0.1:{PORT}/mcp"
BASE_HEADERS = {"Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
                "MCP-Protocol-Version": "2026-07-28"}

def body(method, params=None, req_id=1):
    """A JSON-RPC request. The version and capabilities ride in params._meta."""
    return {"jsonrpc": "2.0", "id": req_id, "method": method, "params": {**(params or {}), "_meta": META}}

def post(payload, extra=None):
    """One POST to the worker. The headers repeat the method, and extra can add a name."""
    headers = {**BASE_HEADERS, "Mcp-Method": payload["method"], **(extra or {})}
    return httpx.post(URL, json=payload, headers=headers, timeout=10)

# %% [markdown]
# `Listen` is new. It opens one `subscriptions/listen` stream in the background and puts each `data:` frame on a queue. `next()` waits for the next frame, and `close()` drops the connection, as a client that went away would.

# %%
class Listen:
    """One subscriptions/listen stream, read in the background. close() drops the connection."""
    def __init__(self, notifications, req_id):
        self.req_id = req_id
        self.frames = asyncio.Queue()
        payload = {"jsonrpc": "2.0", "id": req_id, "method": "subscriptions/listen",
                   "params": {"notifications": notifications, "_meta": META}}
        self.task = asyncio.create_task(self._read(payload))

    async def _read(self, payload):
        headers = {**BASE_HEADERS, "Mcp-Method": "subscriptions/listen"}
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", URL, json=payload, headers=headers) as r:
                if r.status_code != 200:
                    raise RuntimeError(f"listen refused: HTTP {r.status_code}")
                async for line in r.aiter_lines():
                    if line.startswith("data:"):
                        await self.frames.put(json.loads(line[len("data:"):]))

    async def next(self, timeout=5):
        """The next frame: the ack first, then events. Raises TimeoutError if none comes in time."""
        return await asyncio.wait_for(self.frames.get(), timeout)

    async def close(self):
        self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)

# %% [markdown]
# ### 3. Start the worker and wait until it answers
# The notebook starts the worker on port 10070 and polls it with `server/discover`. It gives up after 20 seconds.

# %%
import atexit, subprocess, sys, time
try:
    httpx.get(URL, timeout=1)
    raise RuntimeError(f"port {PORT} already answers: a worker from an earlier run is still up; stop it first")
except httpx.ConnectError:
    pass   # the port is free
log = open("../apps/07b/worker.log", "w")   # closed in the clean-up cell
proc = subprocess.Popen([sys.executable, str(Path("../apps/07b/trackr_listen_worker.py").resolve()), str(PORT)],
                        stdout=log, stderr=subprocess.STDOUT)
atexit.register(lambda: proc.poll() is None and proc.terminate())
deadline = time.monotonic() + 20
while True:
    try:
        post(body("server/discover"))
        break
    except httpx.ConnectError:
        if proc.poll() is not None or time.monotonic() > deadline:
            raise RuntimeError("worker did not start: read ../apps/07b/worker.log")
        time.sleep(0.2)
print(f"worker is up on port {PORT}")

# %% [markdown]
# ### 4. Without a stream, the client asks again
# Here is the version without a listen stream. The client reads the runbook, the runbook changes, and the client reads it again. It learns of the change only because it asked a second time. It cannot know when to ask, so it asks on a timer. The edit runs before any stream is open.

# %%
def read_runbook():
    text = post(body("resources/read", {"uri": "runbook://web"}), {"Mcp-Name": "runbook://web"}).json()["result"]["contents"][0]["text"]
    return text.splitlines()[0]

reads = 1
print("read 1, first line:", read_runbook())
post(body("tools/call", {"name": "edit_web_runbook", "arguments": {"text": "Web runbook v2\n1. Check the CDN status page."}}, req_id=2),
     {"Mcp-Name": "edit_web_runbook"})
reads += 1
print(f"read {reads}, first line:", read_runbook(), "| reads needed to see one change:", reads)

# %% [markdown]
# ### 5. Open a listen stream and read the ack
# Open the stream with the request id 100. It asks for tool-list changes, for `resourcesListChanged`, and for changes to `runbook://web`. Entering the stream returns the ack first. The ack lists the filter the server honored, and its `_meta` carries the `subscriptionId`. The notebook checks that the id is the request id.

# %%
listen = Listen({"toolsListChanged": True, "resourcesListChanged": True,
                 "resourceSubscriptions": ["runbook://web"]}, req_id=100)
ack = await listen.next()
print("method:", ack["method"])
print("honored:", ack["params"]["notifications"])
print("subscriptionId:", ack["params"]["_meta"][SUB_KEY], "| listen request id:", listen.req_id)
assert ack["params"]["_meta"][SUB_KEY] == listen.req_id

# %% [markdown]
# ### 6. A tool change arrives as an event
# Call `enable_escalation`. It adds `escalate_issue` to the server while it runs and announces the change on the stream. The event carries the stream's `subscriptionId`. It has no tool list in it, so the client asks for the list again.

# %%
reply = post(body("tools/call", {"name": "enable_escalation", "arguments": {}}, req_id=3),
             {"Mcp-Name": "enable_escalation"})
print("tool replied:", reply.json()["result"]["content"][0]["text"])
event = await listen.next()
print("event:", event["method"], "| subscriptionId:", event.get("params", {}).get("_meta", {}).get(SUB_KEY))
names = [t["name"] for t in post(body("tools/list", req_id=4)).json()["result"]["tools"]]
print("client refetched tools/list, escalate_issue listed:", "escalate_issue" in names)

# %% [markdown]
# ### 7. A runbook edit arrives as a resource event
# Edit `runbook://web`. The event names the URI that changed. The client reads the resource again to get the new text. The filter asked for this URI, so the server sends the event. A resource the client did not name would produce no event.

# %%
post(body("tools/call", {"name": "edit_web_runbook", "arguments": {"text": "Web runbook v3\n1. Check the CDN status page."}}, req_id=5),
     {"Mcp-Name": "edit_web_runbook"})
event = await listen.next()
print("event:", event["method"], "| uri:", event["params"]["uri"])
print("client re-reads runbook://web, first line:", read_runbook())

# %% [markdown]
# ### 8. Drop the stream and re-listen: no replay
# Close the stream on the client side. Then edit the runbook while nothing is listening. Open a new stream with request id 200. Its ack has a new `subscriptionId`. The edit made while the stream was down is not sent. The client has to refetch the runbook to catch up.

# %%
await listen.close()
print("stream dropped on the client side")
post(body("tools/call", {"name": "edit_web_runbook", "arguments": {"text": "Web runbook v4\n1. Check the CDN status page."}}, req_id=6),
     {"Mcp-Name": "edit_web_runbook"})
listen = Listen({"toolsListChanged": True, "resourceSubscriptions": ["runbook://web"]}, req_id=200)
ack = await listen.next()
print("re-listen ack, subscriptionId:", ack["params"]["_meta"][SUB_KEY])
try:
    missed = await listen.next(timeout=2)
    print("replayed:", missed["method"])
except TimeoutError:
    print("no replay: the edit made while the stream was down was not sent")
print("refetch catches up, first line:", read_runbook())

# %% [markdown]
# ## At work
# - Streams are not shared across replicas. The SDK's bus is in-process, so a change made on one worker does not reach a stream open on another. Teams put a shared `SubscriptionBus` on their pub/sub → lesson 23.
# - A tool list that changes after approval is the rug-pull pattern. Pin the `tools/list` output and alert on a diff, so a `list_changed` event triggers a check, not only a refresh → lesson 29.
# - Streams are long-held connections. Gateways and load balancers must not cut them short, or clients miss changes and must re-listen and refetch → lesson 40.

# %% [markdown]
# ## What just happened
# - The ack came first. It stated the filter the server honored, and its `subscriptionId` matched the listen request's id.
# - A tool change and a runbook edit each arrived as one event. The events named no data, so the client refetched what it needed.
# - After the drop, the edit made in the gap was not replayed. The new stream had a new id, and the client caught up by reading the runbook.

# %% [markdown]
# ## Common mistakes
# The listen request needs an SSE `Accept` header. Without `text/event-stream` the server refuses to open the stream. This cell sends the request with only `application/json`, so the error prints:

# %%
no_sse = {**BASE_HEADERS, "Accept": "application/json", "Mcp-Method": "subscriptions/listen"}
listen_payload = {"jsonrpc": "2.0", "id": 900, "method": "subscriptions/listen",
                  "params": {"notifications": {"toolsListChanged": True}, "_meta": META}}
print("status:", httpx.post(URL, json=listen_payload, headers=no_sse, timeout=10).status_code)

# %% [markdown]
# Calling `raise_for_status()` on the same request turns the status into an exception. This is the cell that fails:

# %% tags=["raises-exception"]
httpx.post(URL, json=listen_payload, headers=no_sse, timeout=10).raise_for_status()   # raises 406

# %% [markdown]
# Fix: send `Accept: application/json, text/event-stream`, as `BASE_HEADERS` does. A listen stream is never a single JSON reply.
#
# A second mistake is to expect a replay. A client that re-listens and assumes it got every earlier event will miss the change made while it was down. Step 8 shows that. Fix: after every re-listen, refetch what the stream was watching.

# %% [markdown]
# ## Try it
# Open a stream that asks only for `resourceSubscriptions` on `runbook://web`, with request id 300. Print the honored filter from the ack. Then call `enable_escalation` and print its reply: the tool is already added, so no tool event should follow. Then edit `runbook://web` and print the method and uri of the event. Close the stream. No model is needed.

# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
t = Listen({"resourceSubscriptions": ["runbook://web"]}, req_id=300)
ack = await t.next()
print("honored:", ack["params"]["notifications"])
reply = post(body("tools/call", {"name": "enable_escalation", "arguments": {}}, req_id=301),
             {"Mcp-Name": "enable_escalation"})
print("enable replied:", reply.json()["result"]["content"][0]["text"])
try:
    print("tool event:", (await t.next(timeout=2))["method"])
except TimeoutError:
    print("no tool event: the filter did not ask for toolsListChanged")
post(body("tools/call", {"name": "edit_web_runbook", "arguments": {"text": "Web runbook v5\n1. Check the CDN status page."}}, req_id=302),
     {"Mcp-Name": "edit_web_runbook"})
event = await t.next()
print("event:", event["method"], "| uri:", event["params"]["uri"])
await t.close()

# %% [markdown]
# Clean up: close the stream and stop the worker. This cell runs last.

# %%
await listen.close()
proc.terminate()
proc.wait(timeout=10)
log.close()
print("worker stopped | lesson 07b done")

# %% [markdown]
# ## Key terms
# - **subscriptions/listen** — the 2026-07-28 request that opens one long-lived stream of server change events. The first frame is the ack.
# - **listChanged notification** — a server event that says a list (tools, prompts or resources) changed, so the client should fetch it again.
# - **resource subscription** — an opt-in in a listen request for change events on named URIs, such as `runbook://web`.
# - **subscriptionId** — the listen request's id. Every frame of that stream carries it in `_meta`.
# - **re-listen** — open a new listen stream after a drop, then refetch what you depend on. Streams do not resume.

# %% [markdown]
# # 32a · Releasing changes: protocol revisions and tool descriptions
# Level L5 · Part 6 · professional · ~40 min · builds on 07a, 12, 27a

# %% [markdown]
# ## Goal
# By the end you roll out a change to Trackr in two places without breaking a client. On the protocol side, one endpoint serves both eras, the legacy era carries `Deprecation` and `Sunset` headers, and a new `requestState` key ring rolls through the replicas in three phases. On the description side, a candidate that lowers the eval score is blocked, the fixed candidate passes, and it reaches 10% of clients by a stable cohort and then rolls back in one step. Four model calls in total.

# %% [markdown]
# ## Why it matters
# A protocol revision or a description change reaches clients you do not control. Without a release process each change is a surprise:
#
# | Change | Without a release process | What the release process gives you |
# |---|---|---|
# | Remove the legacy `initialize` route | Old clients fail on the day of the deploy, and nobody has told them | A dated `Deprecation` and `Sunset` on every legacy reply, and a count of who still calls it |
# | Rotate the `requestState` key | A replica that has the new key only refuses the pauses sealed by the old one, so retries fail | Three phases, one TTL apart, so every in-flight pause can still be read |
# | Trim a tool description | A reworded description sends `close_issue` to the wrong tool, and no test fails | An eval gate that blocks the change, a canary slice, and a one-step rollback |
#
# Skip the process for a private server that only your own team calls.

# %% [markdown]
# ## The idea
# A release has three parts. Old and new behaviour run side by side for a published window, and the old one says so on every reply. A shared secret rolls in phases, so no replica needs a key it does not have yet. A change a model reads goes through a score, then a slice of traffic, and it can be reverted in one step.
#
# The window is the important number. The MCP feature lifecycle requires a deprecated feature to stay deprecated for at least twelve months before removal, and Trackr adopts the same floor. The steps below use that rule.
#
# Analogy: a shop that changes its opening hours. It puts the new hours on the door for months before it changes them, it changes the lock in stages so every staff key still works, and it tries the new hours on one street before the whole city.

# %% [markdown]
# ## Picture
# ```mermaid
# flowchart LR
#   L[Legacy client 2025-11-25] -->|initialize, Mcp-Session-Id| R[Release endpoint /mcp]
#   M[Modern client 2026-07-28] -->|_meta, no session| R
#   R -->|Deprecation and Sunset headers| L
#   K[Candidate descriptions] --> G{Eval gate}
#   G -->|score below baseline| B[Blocked]
#   G -->|score holds| C{Canary cohort 10%}
#   C -->|hash in cohort| N[Candidate descriptions]
#   C -->|rest| S[Stable descriptions]
#   C -.->|rollback: canary 0%| S
# ```

# %% [markdown]
# ## Step by step
#
# ### 1. The lifecycle as a rule
# The rule is plain date arithmetic. A feature is marked Deprecated on a day, and its earliest removal is twelve months later. An expedited removal needs an active security risk and approval, and it still leaves at least ninety days. The code below computes both dates for the legacy era.

# %%
from datetime import date, timedelta

def add_months(day: date, months: int) -> date:
    """The same day of the month, `months` later."""
    year, month0 = divmod(day.month - 1 + months, 12)
    return date(day.year + year, month0 + 1, day.day)

DEPRECATED_ON = date(2026, 10, 12)   # the release that marked the legacy era Deprecated; the release server uses this date too
print("deprecated on:    ", DEPRECATED_ON)
print("earliest removal: ", add_months(DEPRECATED_ON, 12), "(the twelve-month floor)")
print("expedited floor:  ", DEPRECATED_ON + timedelta(days=90), "(only for an active security risk, with approval)")

# %% [markdown]
# ### 2. Start the release endpoint and wait until it answers
# The release endpoint is `../apps/32a/release_server.py`. It serves the stable descriptions (v1) on one `/mcp` route, for both eras. A middleware adds the two headers to every legacy-era reply. The notebook starts it as its own process, polls it, and writes its log to `../data/32a/`.

# %%
import atexit, subprocess, sys, time
from pathlib import Path
import httpx
PORT = 9321
URL = f"http://127.0.0.1:{PORT}/mcp"
ACCEPT = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
    "protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "lesson-32a", "version": "1.0"}}}
Path("../data/32a").mkdir(parents=True, exist_ok=True)
log = open("../data/32a/release_server.log", "w")   # closed in the clean-up cell
server = subprocess.Popen([sys.executable, str(Path("../apps/32a/release_server.py").resolve()), str(PORT)],
                          stdout=log, stderr=subprocess.STDOUT)
atexit.register(lambda: server.poll() is None and server.terminate())
deadline = time.monotonic() + 20
while True:
    try:
        httpx.post(URL, json=INIT, headers=ACCEPT, timeout=10)
        break
    except httpx.ConnectError:
        if server.poll() is not None or time.monotonic() > deadline:
            raise RuntimeError("release server did not start: read ../data/32a/release_server.log")
        time.sleep(0.2)
print("release endpoint is up on", URL)

# %% [markdown]
# ### 3. Dual stack: both eras use the same endpoint
# During the migration an old client and a new client both call the same URL. The old one pins `mode="legacy"`. The new one lets the SDK probe. Both list the same six tools and get the same answer. Nothing has to move yet.

# %%
from mcp import Client
async with Client(URL, mode="legacy") as old:
    old_tools = [t.name for t in (await old.list_tools()).tools]
    old_answer = (await old.call_tool("count_open", {"team": "web"})).content[0].text
    print("legacy client -> protocol", old.protocol_version, "| tools:", len(old_tools), "|", old_answer)
async with Client(URL) as new:
    new_tools = [t.name for t in (await new.list_tools()).tools]
    print("modern client -> protocol", new.protocol_version, "| tools:", len(new_tools))
print("same tools for both:", old_tools == new_tools)

# %% [markdown]
# ### 4. The deprecation signal on the wire
# The old client never reads a changelog. It reads the reply. A legacy-era reply carries `Deprecation`, which says when the feature was deprecated, and `Sunset`, the earliest removal date. The modern reply carries neither. The headers come from the middleware, so the tool code does not change. `Deprecation` uses the RFC 9745 form `@<Unix seconds>`; 1791763200 is 2026-10-12 00:00 UTC. `Sunset` is an HTTP date.

# %%
MODERN = {"jsonrpc": "2.0", "id": 2, "method": "server/discover", "params": {"_meta": {
    "io.modelcontextprotocol/protocolVersion": "2026-07-28", "io.modelcontextprotocol/clientCapabilities": {}}}}
legacy_reply = httpx.post(URL, json=INIT, headers=ACCEPT, timeout=10)
modern_reply = httpx.post(URL, json=MODERN, timeout=10, headers={
    **ACCEPT, "MCP-Protocol-Version": "2026-07-28", "Mcp-Method": "server/discover"})
for name, r in [("legacy initialize", legacy_reply), ("modern server/discover", modern_reply)]:
    print(f"{name:24} status {r.status_code} | Deprecation: {r.headers.get('deprecation')} | Sunset: {r.headers.get('sunset')}")

# %% [markdown]
# ### 5. Roll a `requestState` key ring through three replicas
# A pause from lesson 12 is sealed with a key, and the retry may land on any replica. A new key therefore rolls in three phases. Phase 1 gives every replica `[old, new]`: it seals with the old key and reads both. Phase 2 gives `[new, old]`: it seals with the new key and still reads the old one. Phase 3, after one TTL, gives `[new]`. The table shows which replica can read a pause that another replica sealed.
#
# The keys below are random for this run. Production reads them from a secret store.

# %%
import secrets
from mcp.server.request_state import RequestStateSecurity
OLD, NEW = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
RING = {"phase 1": [OLD, NEW], "phase 2": [NEW, OLD], "phase 3": [NEW]}

def reads(ring_keys: list[str], token: str) -> str:
    """Can a replica with this key ring unseal the token? The codec checks the key only."""
    try:
        RequestStateSecurity(keys=ring_keys).codec.unseal(token)
        return "reads"
    except Exception as err:
        return f"refused ({type(err).__name__})"

print(f"{'sealed by (sealer)':22} | " + " | ".join(f"reader {p}" for p in RING))
for sealer, ring in RING.items():
    token = RequestStateSecurity(keys=ring).codec.seal(b'{"step": 1}')   # seals with ring[0]
    print(f"{sealer + ' (' + ('old' if ring[0] == OLD else 'new') + ' key)':22} | "
          + " | ".join(f"{reads(keys, token):18}" for keys in RING.values()))
print("token lifetime (TTL) in seconds:", RequestStateSecurity(keys=[NEW]).ttl)

# %% [markdown]
# Read the table. A token sealed in phase 2 or 3 is readable by every replica, because every ring from phase 1 on holds the new key. Only a phase-1 pause (the table row 'phase 1'), read by a replica that has already left phase 2, is refused. That is why phase 3 waits one TTL: after 600 seconds no pause sealed in phase 1 can still be in flight.

# %% [markdown]
# ### 6. A2A: the version header and the 0.3 compatibility mode
# A2A 1.0 names its version in the `A2A-Version` header, and its methods are named differently from 0.3 (`SendMessage`, not `message/send`). A 1.0 agent that still serves 0.3 peers sets `enable_v0_3_compat=True`. The SDK treats a request with no header as 0.3, so an old peer does not need to change. The agent below answers a fixed string; the version checks need no model.

# %%
from a2a.helpers import new_task_from_user_message, new_text_part
from a2a.server.agent_execution import AgentExecutor
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from starlette.applications import Starlette
import logging
logging.getLogger("a2a").setLevel(logging.CRITICAL)   # the SDK logs each refused version; the replies show it

class TriageEcho(AgentExecutor):
    """Completes every task with one fixed reply."""
    async def execute(self, context, event_queue):
        task = context.current_task or new_task_from_user_message(context.message)
        await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.complete(updater.new_agent_message([new_text_part("triaged: bug")]))

    async def cancel(self, context, event_queue):
        pass

# %% [markdown]
# The agent card names the version of the interface. Then `build_agent` mounts the card and the JSON-RPC route, with or without compat.

# %%
CARD = AgentCard(name="Triage", description="Labels one issue.", version="1.1.0",
                 supported_interfaces=[AgentInterface(url="http://triage.test/", protocol_binding="JSONRPC",
                                                      protocol_version="1.0")],
                 capabilities=AgentCapabilities(), default_input_modes=["text/plain"],
                 default_output_modes=["text/plain"],
                 skills=[AgentSkill(id="triage", name="Triage", description="Label an issue.", tags=["triage"])])

def build_agent(compat: bool) -> Starlette:
    handler = DefaultRequestHandler(agent_executor=TriageEcho(), task_store=InMemoryTaskStore(), agent_card=CARD)
    return Starlette(routes=[*create_agent_card_routes(CARD),
                             *create_jsonrpc_routes(handler, "/", enable_v0_3_compat=compat)])

# %% [markdown]
# Two agents are built from the same code: one with compat, one without. The next cell sends them JSON-RPC calls in each version.

# %%
async def rpc(app, method: str, message: dict, headers: dict | None = None) -> dict:
    """One JSON-RPC call to an in-process agent. No port is opened."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://triage.test") as c:
        reply = await c.post("/", json={"jsonrpc": "2.0", "id": 1, "method": method,
                                        "params": {"message": message}}, headers=headers or {})
    return reply.json()

MSG_03 = {"kind": "message", "messageId": "a1", "role": "user", "parts": [{"kind": "text", "text": "login is slow"}]}
MSG_10 = {"messageId": "a2", "role": "ROLE_USER", "parts": [{"text": "login is slow"}]}

def summary(reply: dict) -> str:
    if "error" in reply:
        return f"error {reply['error']['code']}: {reply['error']['message'][:58]}"
    result = reply["result"].get("task", reply["result"])
    return "ok: " + str(result.get("status", {}).get("state", result.get("kind", "?")))

compat_app, plain_app = build_agent(compat=True), build_agent(compat=False)
CASES = [("0.3 peer: message/send, no header", "message/send", MSG_03, {}),
         ("1.0 client: SendMessage, A2A-Version 1.0", "SendMessage", MSG_10, {"A2A-Version": "1.0"}),
         ("1.0 client: SendMessage, A2A-Version 2.0", "SendMessage", MSG_10, {"A2A-Version": "2.0"}),
         ("1.0 method, header forgotten", "SendMessage", MSG_10, {})]
for label, method, message, headers in CASES:
    print(f"{label:42} compat: {summary(await rpc(compat_app, method, message, headers))}")
print(f"{'0.3 peer on an agent without compat':42} plain:  {summary(await rpc(plain_app, 'message/send', MSG_03))}")

# %% [markdown]
# The compat agent answers the 0.3 peer and the 1.0 client on one endpoint. It refuses a version it does not speak, and a 1.0 method with no header is refused too, because the SDK reads "no header" as 0.3. The agent without compat does not know the 0.3 method at all.

# %% [markdown]
# ### 7. The description release pipeline: one model per stage (`needs-llm`)
# Now the descriptions. The stable set is v1 from lesson 27a. Version 2 is the tidy-up from lesson 27a: it saves tokens, and it swaps the texts of `close_issue` and `archive_issue`. Version 3 corrects the swap and restores the "when to use" hints that the tidy-up removed. The gate runs all eight requests from lesson 27a in one model call per candidate, then the canary runs four of them in one call. The notebook makes **four model calls in total**.
#
# This setup cell defines the descriptions, the requests and the scoring. It makes no model call.

# %%
import hashlib, json, logging, sys
from langchain_core.messages import HumanMessage
sys.path.insert(0, "..")            # llm_setup and llm_replay live in the topic folder
sys.path.insert(0, "../apps/32a")   # release_tools.py: the six tools, with descriptions passed in
from release_tools import build_server
logging.getLogger("httpx").setLevel(logging.WARNING)
NAMES = ["count_open", "search_issues", "create_issue", "close_issue", "reopen_issue", "archive_issue"]
TEXTS = {"v1": json.loads(Path("../apps/27a/descriptions_v1.json").read_text()),   # stable, approved
         "v2": json.loads(Path("../apps/27a/descriptions_v2.json").read_text()),   # 27a tidy-up with the swap
         "v3": json.loads(Path("../apps/32a/descriptions_v3.json").read_text())}   # the fix
for version, texts in TEXTS.items():
    assert set(texts) == set(NAMES), f"{version} lacks a description"   # lint: every tool has one
print("descriptions that differ between v2 and v3 (swap fixed and hints restored):", [n for n in NAMES if TEXTS["v2"][n] != TEXTS["v3"][n]])

# %% [markdown]
# The eight requests from lesson 27a, and the four the canary takes from them.

# %%
PROMPTS = [
    ("How many open issues does the mobile team have?", "count_open", {"team": "mobile"}),
    ("Which open issues mention login?", "search_issues", {"text": "login"}),
    ("Open a new issue for the api team: checkout times out.", "create_issue", {"team": "api"}),
    ("Close issue 7, it is a duplicate of issue 3.", "close_issue", {"issue_id": 7}),
    ("Reopen issue 12, the fix did not ship.", "reopen_issue", {"issue_id": 12}),
    ("Issue 9 was closed last week. Take it off the default board.", "archive_issue", {"issue_id": 9}),
    ("How many open issues does the web team have?", "count_open", {"team": "web"}),
    ("Which open issues mention push?", "search_issues", {"text": "push"}),
]
CANARY_IDX = (1, 3, 4, 5)   # four requests for the canary: search, close, reopen, archive
print(len(PROMPTS), "requests; the canary takes", [PROMPTS[i][1] for i in CANARY_IDX])

# %% [markdown]
# The scoring helpers. A call answers a request when its tool name and every expected argument match.

# %%
def numbered(prompts) -> str:
    return "Answer each numbered request with one tool call.\n" + "\n".join(
        f"{n}. {request}" for n, (request, _, _) in enumerate(prompts, 1))

def same(call, tool, args) -> bool:
    return call["name"] == tool and all(str(call["args"].get(k, "")).lower() == str(v).lower() for k, v in args.items())

def score(calls, prompts):
    """One mark per request, and the calls that answer no request."""
    left, marks = list(calls), []
    for _, tool, args in prompts:
        match = next((c for c in left if same(c, tool, args)), None)
        marks.append(match is not None)
        if match is not None:
            left.remove(match)
    return marks, left

llm = None        # the model cell sets this; it stays None if that cell is skipped
print(numbered(PROMPTS[:2]))

# %% [markdown]
# `ask` sends every request in one message, then checks each returned call on the live server.

# %%
async def ask(version: str, prompts) -> dict:
    """One model call: all the requests in one message, the tools as this description set defines them."""
    async with Client(build_server(TEXTS[version])) as c:
        defs = [{"type": "function", "function": {"name": t.name, "description": t.description,
                                                  "parameters": t.input_schema}}
                for t in (await c.list_tools()).tools]
        reply = await llm.bind_tools(defs).ainvoke([HumanMessage(numbered(prompts))])
        calls = [{"name": x["name"], "args": x["args"]} for x in reply.tool_calls]
        rejected = [(await c.call_tool(x["name"], x["args"])).is_error for x in calls]   # the live server runs each call
    marks, extra = score(calls, prompts)
    return {"version": version, "marks": marks, "right": sum(marks), "rejected": sum(rejected),
            "extra": [x["name"] for x in extra], "calls": calls}

RESULTS = {}
print('ready: the four model cells below fill RESULTS')

# %% [markdown]
# Model call 1 is the baseline: the stable set (v1) on all eight requests. The recorder starts here and stops in the last cell.

# %% tags=["needs-llm"]
import llm_replay
llm_replay.start("32a_protocol-and-description-releases")
from llm_setup import get_llm
llm = get_llm()
RESULTS["v1"] = await ask("v1", PROMPTS)
print(f"v1 (stable): {RESULTS['v1']['right']} of 8 right, {RESULTS['v1']['rejected']} calls rejected by the live server")

# %% [markdown]
# Model call 2 is the candidate v2, the 27a tidy-up. The gate compares it with the baseline on the same eight requests.

# %% tags=["needs-llm"]
RESULTS["v2"] = await ask("v2", PROMPTS)
print(f"v2 (candidate): {RESULTS['v2']['right']} of 8 right; calls that answer no request: {RESULTS['v2']['extra'] or 'none'}")

# %% [markdown]
# Model call 3 is the fixed candidate v3: the tidy-up with the swap corrected and the 'when to use' hints restored.

# %% tags=["needs-llm"]
RESULTS["v3"] = await ask("v3", PROMPTS)
print(f"v3 (fixed candidate): {RESULTS['v3']['right']} of 8 right; calls that answer no request: {RESULTS['v3']['extra'] or 'none'}")

# %% [markdown]
# Model call 4 is the canary: the candidate v3 on four requests from the cohort's traffic, in one message. Four single-call examples would need four calls, so the canary uses one.

# %% tags=["needs-llm"]
RESULTS["canary"] = await ask("v3", [PROMPTS[i] for i in CANARY_IDX])
print(f"canary (v3, four requests): {RESULTS['canary']['right']} of 4 right")

# %% [markdown]
# If the model cells were skipped, the stand-in below loads the output of the course run, and it says so. Every later cell reads only `RESULTS`.

# %%
if "v3" not in RESULTS:   # fallback: the model cells were skipped
    saved = json.loads(Path("../data/recorded/32a.json").read_text())
    RESULTS.update(saved)
    print("SAVED stand-in (no model here): the output of the course run is loaded for v1, v2, v3 and the canary")

# %% [markdown]
# ### 8. The gate, the canary and the release state
# The gate is one rule: a candidate ships only when it gets at least as many requests right as the baseline on the same requests. The table shows each request for the baseline and the two candidates.

# %%
def gate(candidate: dict, baseline: dict) -> bool:
    return candidate["right"] >= baseline["right"]

print(f"{'#':>2} {'expected tool':16} {'v1':>3} {'v2':>3} {'v3':>3}")
for n, (_, tool, _) in enumerate(PROMPTS):
    cell = lambda run: "yes" if run["marks"][n] else "no"
    print(f"{n + 1:>2} {tool:16} {cell(RESULTS['v1']):>3} {cell(RESULTS['v2']):>3} {cell(RESULTS['v3']):>3}")
print()
print("gate v2 (27a tidy-up):", "PASSED" if gate(RESULTS["v2"], RESULTS["v1"]) else "BLOCKED: it scores below v1, so it does not ship")
print("gate v3 (fixed):      ", "PASSED" if gate(RESULTS["v3"], RESULTS["v1"]) else "BLOCKED")

# %% [markdown]
# The cohort rule decides who gets the candidate. A client id is hashed, and the hash picks a bucket from 0 to 99. A client in the first `canary_percent` buckets gets the candidate. The same client always lands in the same bucket, so its experience does not change between requests.

# %%
def in_canary(client_id: str, percent: int) -> bool:
    return int.from_bytes(hashlib.sha256(client_id.encode()).digest()[:4], "big") % 100 < percent

def version_for(client_id: str, release: dict) -> str:
    return release["candidate"] if in_canary(client_id, release["canary_percent"]) else release["stable"]

RELEASE = {"stable": "v1", "candidate": None, "canary_percent": 0}
CLIENTS = [f"client-{i:04d}" for i in range(1000)]
LOG = []

if gate(RESULTS["v3"], RESULTS["v1"]) and sum(RESULTS["canary"]["marks"]) >= sum(RESULTS["v1"]["marks"][i] for i in CANARY_IDX):
    RELEASE.update(candidate="v3", canary_percent=10)
    LOG.append("gate passed; canary on v3 at 10%")
print("release state:", RELEASE)
print("clients on v3 out of 1,000:", sum(version_for(c, RELEASE) == "v3" for c in CLIENTS))

# %% [markdown]
# ### 9. Roll back in one step
# A bad canary is reverted by one setting. The stable set never changed, so setting the canary to 0% sends every client back to v1 at once. The next cell does that and records it.

# %%
RELEASE["canary_percent"] = 0
LOG.append("rollback: canary set to 0%")
print("release state after rollback:", RELEASE)
print("clients on v3 out of 1,000:", sum(version_for(c, RELEASE) == "v3" for c in CLIENTS))

# %% [markdown]
# ## At work
# - Teams publish a deprecation date and a sunset date with each old route, and count the callers still using it. They remove it only after the window and when the count is near zero → lesson 40 (the gateway routes by version).
# - A rotated secret needs the same phased order on every replica. Teams drill the wrong order once before launch → lesson 33 (checkpoint: production Trackr).
# - Tool descriptions ship like code: reviewed, scored, canaried, reverted by one setting → lesson 40a (gateway failure modes, measured).
# - A2A peers that are not yet upgraded keep the compat mode until they retire. A multi-tenant server routes on `A2A-Version` → lesson 38 (multi-tenant MCP servers and A2A agents).

# %% [markdown]
# ## What just happened
# - One endpoint answered both eras. The legacy reply carried `Deprecation` and `Sunset`, and the modern reply carried neither.
# - The key ring rolled in three phases. A phase-1 token stayed readable through phase 2, and only phase 3 refused it, after the TTL.
# - The A2A agent answered the 0.3 peer and the 1.0 client on one endpoint. It refused the version it does not speak.
# - The gate blocked the v2 tidy-up, which swapped two descriptions. The fixed v3 passed. The canary reached 10% of clients by a stable hash, and one setting brought them back to v1.

# %% [markdown]
# ## Common mistakes
# **Mistake 1: a replica that has only the new key.** Rolling `[new]` before every replica holds `[new, old]` makes the old replicas refuse new pauses. The cell below builds that state and reads a new-key token on an old-only replica:

# %% tags=["raises-exception"]
new_only = RequestStateSecurity(keys=[NEW])     # phase 3 applied too early
old_only = RequestStateSecurity(keys=[OLD])     # a replica that never got the new key
token = new_only.codec.seal(b'{"step": 2}')
old_only.codec.unseal(token)                    # raises InvalidRequestState: unknown key

# %% [markdown]
# Fix: roll the phases in order and let every replica finish each phase before the next one starts.
#
# **Mistake 2: a 1.0 client that forgets the header.** The SDK reads a missing `A2A-Version` as 0.3, so a 1.0 method without the header is refused. This cell raises the error the caller would see:

# %% tags=["raises-exception"]
reply = await rpc(compat_app, "SendMessage", MSG_10)   # the 1.0 method, no A2A-Version header
if "error" in reply:
    raise RuntimeError(reply["error"]["message"])

# %% [markdown]
# Fix: send `A2A-Version: 1.0` with every 1.0 request, and read the version the server answers with.

# %% [markdown]
# ## Production checklist
# - [ ] Every legacy route has a Deprecated date, a Sunset date at least twelve months later, and a migration note.
# - [ ] The `Deprecation` and `Sunset` headers go out on every legacy reply, and a dashboard counts legacy calls until they reach zero.
# - [ ] `requestState` keys roll in three phases, one TTL apart, and an old key is removed only after every pause sealed with it has expired.
# - [ ] An A2A server names the versions it accepts, refuses the others with an explicit error, and keeps the compat mode for 0.3 peers until they are retired.
# - [ ] A description change passes the gate, reaches a stable canary cohort first, and rolls back by setting the canary to 0%.

# %% [markdown]
# ## Try it
# Predict first: with `canary_percent` at 25 instead of 10, how many of the 1,000 clients get v3? Copy `RELEASE`, set the copy to 25, count, then compare with the answer. No model is needed.

# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
trial = {**RELEASE, "candidate": "v3", "canary_percent": 25}
print("clients on v3 out of 1,000 at 25%:", sum(version_for(c, trial) == "v3" for c in CLIENTS))
print("the cohort is a fixed hash, so the same clients stay in the canary as the percentage grows")

# %% [markdown]
# ## Key terms
# - **earliest removal** — the first date a deprecated feature may be removed: twelve months after it was marked Deprecated.
# - **Deprecation header** — the reply header (RFC 9745) that says when a feature was deprecated.
# - **Sunset header** — the reply header (RFC 8594) that gives the date an endpoint may stop answering.
# - **dual stack** — old and new behaviour served side by side on one endpoint during a migration.
# - **key ring** — the list of keys for `requestState`: the first key seals, every key reads.
# - **A2A-Version** — the header that names the A2A protocol version a request uses. A missing header means 0.3.
# - **compat mode** — `enable_v0_3_compat=True`: the agent also answers 0.3 peers on the same endpoint.
# - **canary cohort** — the clients a candidate reaches first, chosen by a stable hash of the client id.
# - **rollback** — reverting a release by one setting, with the stable version unchanged.

# %%
server.terminate()
server.wait(timeout=10)
log.close()
if "llm_replay" in globals():   # the import sits in the needs-llm cell; skipped model cells leave it unset
    llm_replay.stop()
Path("../data/32a/results.json").write_text(json.dumps(RESULTS, indent=2))
Path("../data/32a/release_log.json").write_text(json.dumps(LOG, indent=2))
print("release endpoint stopped | lesson 32a done | log:", LOG)

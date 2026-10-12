# %% [markdown]
# # 38 · Multi-tenant MCP servers and A2A agents
# Level L6 · Part 7 · professional · ~40 min · builds on 35, 37

# %% [markdown]
# ## Goal
# By the end, one Trackr serves two teams, `web` and `api`, and one triage agent serves both. Trackr takes the tenant from the caller's verified token, never from a tool argument. Twelve cross-tenant reads and writes are refused with the same answer as a missing issue. A handle works only for the user who made it. A flood from one tenant is throttled, so the other tenant's median latency stays about the same and its worst case shrinks (measured). Each team's agent asks one question, 2 model calls each.

# %% [markdown]
# ## Why it matters
# One server that holds several teams' data is one bug away from a leak. Without tenancy, the easy design is a tool that takes the team as an argument. The model fills that argument in, so the model decides whose data it reads. Here is that design in plain Python, with twelve issues in two teams.

# %%
import json
from pathlib import Path
DATA = Path("../data/38").resolve(); DATA.mkdir(parents=True, exist_ok=True)
ISSUES = [
    {"id": 101, "title": "Checkout button does nothing on Safari", "team": "web", "status": "open", "severity": "high"},
    {"id": 102, "title": "Invoice PDF drops the tax line", "team": "web", "status": "open", "severity": "medium"},
    {"id": 103, "title": "Dark mode hides the save icon", "team": "web", "status": "closed", "severity": "low"},
    {"id": 104, "title": "Session expires during export", "team": "web", "status": "open", "severity": "high"},
    {"id": 105, "title": "Search box loses focus on mobile", "team": "web", "status": "open", "severity": "low"},
    {"id": 106, "title": "Cart count shows zero after refresh", "team": "web", "status": "open", "severity": "medium"},
    {"id": 201, "title": "Rate limit header missing on /v2/orders", "team": "api", "status": "open", "severity": "high"},
    {"id": 202, "title": "Webhook retries send duplicate events", "team": "api", "status": "open", "severity": "high"},
    {"id": 203, "title": "Bulk import times out above 5000 rows", "team": "api", "status": "open", "severity": "medium"},
    {"id": 204, "title": "Token refresh returns 500 once a day", "team": "api", "status": "open", "severity": "high"},
    {"id": 205, "title": "Pagination cursor skips the last page", "team": "api", "status": "open", "severity": "medium"},
    {"id": 206, "title": "Old API key still accepted after rotation", "team": "api", "status": "open", "severity": "high"},
]
(DATA / "issues.json").write_text(json.dumps(ISSUES, indent=1))

def naive_list(team: str) -> list[str]:
    """One tool for everyone: the caller passes the team, so the caller picks whose issues it reads."""
    return [i["title"] for i in ISSUES if i["team"] == team and i["status"] == "open"]

print("web's own list:", len(naive_list("web")), "open issues")
print("a web user (or the model) passes team='api':", naive_list("api")[:2], "...")

# %% [markdown]
# That leak takes one argument. The fix is to take the team from something the caller cannot edit: a token that the server signed after it checked who the user is. A June 2025 report on Asana's MCP server described a similar flaw, where one organisation's projects and tasks were visible to another. You don't need this for a server that serves one team and one user on a laptop. It pays as soon as one server holds data for several teams.

# %% [markdown]
# ## The idea
# A **tenant** is the group a piece of data belongs to. Here the tenants are teams. The authorization server keeps the user-to-tenant record and puts the tenant in the token it signs. Trackr trusts only that claim, so every query, write and handle is scoped to it. A refusal must look the same as a missing thing, or the answer reveals which issues exist elsewhere. Two more controls protect the other tenants from a busy one: a per-tenant quota, and per-tenant encryption of stored results. The A2A form of the same rule is the request's `tenant` field, which must match the caller's token.
#
# Analogy: an office building with one lobby. Each badge opens only its own floor. The lift does not ask which floor you want, the badge decides, and a locked door looks the same whether the room is empty or someone else's.

# %% [markdown]
# ## Picture
# ```mermaid
# sequenceDiagram
#   participant U as Web team agent
#   participant AS as Authorization server :8380
#   participant T as Trackr :8381
#   participant A as Triage agent :8382 (A2A)
#   U->>AS: sign in as ana (the record says: tenant web)
#   AS-->>U: token: sub = ana, tenant = web, aud = Trackr
#   U->>T: list_issues (no tenant argument)
#   T->>T: tenant from the verified token; query scoped to web
#   T-->>U: web's issues only
#   U->>A: SendMessage, tenant = web, token aud = triage
#   A->>A: request tenant == token tenant?
#   A-->>U: COMPLETED; the result is stored encrypted under web's key
# ```

# %% [markdown]
# ## Step by step
#
# ### 1. Set up
# The ports are 8380 (the authorization server), 8381 (Trackr) and 8382 (the triage agent, run inside this notebook). The store's master key comes from `.env`. Empty means a random key for this run. Each tenant's results are encrypted under a key derived from it.

# %%
import sys, os, time, subprocess, atexit, asyncio, shutil, secrets
import httpx, httpx2, jwt
sys.path.insert(0, "..")
import tut_env
from tut_env import env
tut_env.load()
ISSUER, TRACKR, TRIAGE = "http://127.0.0.1:8380", "http://127.0.0.1:8381/mcp", "http://127.0.0.1:8382/"
ISSUES_FILE, STORE = DATA / "issues.json", DATA / "store"
shutil.rmtree(STORE, ignore_errors=True)                 # a fresh run starts with an empty store
MASTER = (env("TASK_STORE_MASTER_KEY", "") or secrets.token_urlsafe(32)).encode()
TEAM = {"ana": "web", "pat": "web", "ben": "api"}        # the names the lab uses; the tenant comes from the server's record
procs = []
atexit.register(lambda: [p.terminate() for p in procs])
print("ports 8380-8382 | master key set from .env:", bool(env("TASK_STORE_MASTER_KEY", "")))

# %% [markdown]
# The two helpers start a server from `../apps/38` and wait until it answers. They poll; they never sleep for a fixed time.

# %%
def start(script, *args):
    """Start one server from ../apps/38 with a log file for its errors."""
    log = open(DATA / (Path(script).stem + ".err"), "w")
    p = subprocess.Popen([sys.executable, str(Path("../apps/38", script).resolve()), *args],
                         stdout=subprocess.DEVNULL, stderr=log, env=os.environ)
    procs.append(p)
    return p

def wait_for(url, ok=lambda r: r.status_code < 500, timeout=60):
    """Poll until the URL answers the way ok() wants. No fixed sleep."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            if ok(httpx.get(url, timeout=2)):
                return
        except httpx.HTTPError:
            pass
        if time.monotonic() > deadline:
            raise RuntimeError(f"no answer from {url}; see the .err files in ../data/38")
        time.sleep(0.5)

# %% [markdown]
# ### 2. The authorization server owns the user-to-tenant record
# The stand-in server (lesson 34 ran Keycloak for the same job) keeps one record: ana and pat are in `web`, ben is in `api`. Its sign-in endpoint takes a user and an audience, and writes the tenant from the record. Below, ana asks for `tenant=api` anyway, and the server ignores it.

# %%
%%writefile ../apps/38/tenant_as.py
"""Stand-in authorization server for lesson 38, on 127.0.0.1:8380 (no Docker needed).
Real here: RS256 tokens with published keys (JWKS), a user-to-tenant record that only the server owns,
one audience per resource, and a short lifetime. Stand-in: lesson 34's browser sign-in is /dev/sign-in."""
import time
import uvicorn
from joserfc import jwt
from joserfc.jwk import RSAKey
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

ISSUER = "http://127.0.0.1:8380"
AUDIENCES = {"trackr": "http://127.0.0.1:8381/mcp", "triage": "http://127.0.0.1:8382/"}
USERS = {"ana": "web", "pat": "web", "ben": "api"}          # the record: user -> tenant (the team)
KEY = RSAKey.generate_key(2048, {"kid": "tut-38", "alg": "RS256", "use": "sig"})

async def jwks(request):
    return JSONResponse({"keys": [KEY.as_dict(private=False)]})

async def sign_in(request):
    """Mints the user's token for one audience. The tenant comes from the record; the caller cannot choose it."""
    user, aud = request.query_params.get("user", ""), AUDIENCES.get(request.query_params.get("aud", ""))
    if user not in USERS or aud is None:
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    now = int(time.time())
    claims = {"iss": ISSUER, "sub": user, "tenant": USERS[user], "aud": aud,
              "scope": "issues:read issues:write triage:run", "iat": now, "exp": now + 3600}
    return JSONResponse({"access_token": jwt.encode({"alg": "RS256", "kid": "tut-38"}, claims, KEY),
                         "token_type": "Bearer", "expires_in": 3600})

app = Starlette(routes=[Route("/jwks", jwks), Route("/dev/sign-in", sign_in)])

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8380, log_level="warning")


# %% [markdown]
# The file above is the stand-in authorization server. Start it, wait until its keys answer, then sign the users in.

# %%
as_proc = start("tenant_as.py")
print("authorization server up at", ISSUER)
wait_for(f"{ISSUER}/jwks", ok=lambda r: r.status_code == 200)

def token(user, aud, **extra):
    """Ask the authorization server to sign the user in for one audience."""
    r = httpx.get(f"{ISSUER}/dev/sign-in", params={"user": user, "aud": aud, **extra}, timeout=5)
    r.raise_for_status()
    return r.json()["access_token"]

forged = token("ana", "trackr", tenant="api")             # the caller asks for another team
claims = jwt.decode(forged, options={"verify_signature": False})
print("ana asked for tenant=api; the token says:", {k: claims[k] for k in ["sub", "tenant", "aud"]})
TOK = {u: token(u, "trackr") for u in TEAM}               # Trackr tokens
TOK_TRIAGE = {u: token(u, "triage") for u in ("ana", "ben")}   # tokens for the triage agent

# %% [markdown]
# ### 3. Trackr takes the tenant from the verified token
# Trackr is one MCP server for every team. Its tools take no tenant argument. The token's `tenant` claim is read on every call, after the signature, issuer and audience are checked. The quota is on in this run (step 8 compares it with a run where it is off).

# %%
%%writefile ../apps/38/tenant_trackr.py
"""Trackr for lesson 38, on 127.0.0.1:8381: one MCP server for every team (each team is a tenant).
The tenant and the user come from the verified token, never from a tool argument. Every lookup is scoped to the
caller's tenant, so another tenant's issue and a missing issue get the same answer. Export handles are kept under
the (tenant, user) that made them. Quotas per tenant: a token bucket and at most one call in flight, over a shared
pool of 2 worker slots. argv: issuer, JWKS URL, issues file, quotas (on|off). Off is the noisy-neighbour baseline."""
import asyncio, json, secrets, sys, time
from pathlib import Path
import jwt
from mcp.server import MCPServer
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

PORT = 8381
RESOURCE = f"http://127.0.0.1:{PORT}/mcp"
ISSUER, JWKS_URL, ISSUES_PATH, QUOTAS = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] == "on"
SLOTS = asyncio.Semaphore(2)                  # the shared worker pool, first come first served
BUCKET_SIZE, REFILL_PER_S, WORK_S = 30, 20.0, 0.03
ISSUES = {i["id"]: i for i in json.loads(Path(ISSUES_PATH).read_text())}
EXPORTS = {}                                  # (tenant, user) -> {handle: [issue ids]}
buckets, inflight = {}, {}                    # tenant -> (tokens, last time); tenant -> calls in flight

class OrgVerifier:
    """Signature from the authorization server's keys, the issuer, and the audience = Trackr's own URI."""
    def __init__(self):
        self.keys = jwt.PyJWKClient(JWKS_URL)

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            key = self.keys.get_signing_key_from_jwt(token).key
            c = jwt.decode(token, key, algorithms=["RS256"], audience=RESOURCE, issuer=ISSUER)
        except jwt.PyJWTError:
            return None
        return AccessToken(token=token, client_id=c["sub"], scopes=c["scope"].split(), expires_at=c["exp"],
                           resource=RESOURCE, subject=c["sub"], claims=c)

def caller() -> tuple[str, str]:
    """(tenant, user) from the verified token. Nothing else is trusted for identity."""
    token = get_access_token()
    if token is None:
        raise ToolError("unauthorised")
    return token.claims["tenant"], token.claims["sub"]

def admit(tenant: str) -> None:
    """Per-tenant limits. Refuses at once (no queueing) when the tenant is over its rate or has a call in flight."""
    now = time.monotonic()
    tokens, last = buckets.get(tenant, (BUCKET_SIZE, now))
    tokens = min(BUCKET_SIZE, tokens + (now - last) * REFILL_PER_S)
    if tokens < 1 or inflight.get(tenant, 0) >= 1:
        buckets[tenant] = (tokens, now)
        raise ToolError(f"quota_exceeded: this team may run one call at a time and {REFILL_PER_S:.0f} a second")
    buckets[tenant] = (tokens - 1, now)

async def run(tenant: str, work):
    """Every tool call: its tenant's limits (when on), then a worker slot, then the work (a simulated database trip)."""
    if QUOTAS:
        admit(tenant)
    inflight[tenant] = inflight.get(tenant, 0) + 1
    try:
        async with SLOTS:
            await asyncio.sleep(WORK_S)
            return work()
    finally:
        inflight[tenant] -= 1

def visible(tenant: str, issue_id: int) -> dict:
    """The issue, only if it belongs to the caller's tenant. Another tenant's issue and a missing one get the same answer."""
    issue = ISSUES.get(issue_id)
    if issue is None or issue["team"] != tenant:
        raise ToolError("not found: no such issue for your team")
    return issue

mcp = MCPServer("Trackr", token_verifier=OrgVerifier(), auth=AuthSettings(
    issuer_url=ISSUER, resource_server_url=RESOURCE, required_scopes=["issues:read"], validate_token_resource=True))

# %% [markdown]
# The rest of the file holds the tools. Each one reads its tenant from the verified token, and each runs through the quota.

# %%
%%writefile -a ../apps/38/tenant_trackr.py
@mcp.tool(title="List open issues", annotations=ToolAnnotations(readOnlyHint=True))
async def list_issues() -> str:
    tenant, _ = caller()
    def work():
        rows = [f"{i['id']} {i['title']}" for i in ISSUES.values() if i["team"] == tenant and i["status"] == "open"]
        return "\n".join(rows) or "no open issues"
    return await run(tenant, work)

@mcp.tool(title="Get one issue", annotations=ToolAnnotations(readOnlyHint=True))
async def get_issue(issue_id: int) -> str:
    tenant, _ = caller()
    return await run(tenant, lambda: json.dumps(visible(tenant, issue_id)))

@mcp.tool(title="Close an issue", annotations=ToolAnnotations(destructiveHint=True))
async def close_issue(issue_id: int) -> str:
    tenant, _ = caller()
    def work():
        visible(tenant, issue_id)["status"] = "closed"
        return f"closed {issue_id}"
    return await run(tenant, work)

@mcp.tool(title="Start an export", annotations=ToolAnnotations(readOnlyHint=True))
async def export_issues() -> str:
    tenant, user = caller()
    def work():
        handle = secrets.token_urlsafe(8)
        EXPORTS.setdefault((tenant, user), {})[handle] = [i for i, v in ISSUES.items() if v["team"] == tenant]
        return handle
    return await run(tenant, work)

@mcp.tool(title="Read an export", annotations=ToolAnnotations(readOnlyHint=True))
async def read_export(handle: str) -> str:
    tenant, user = caller()
    def work():
        ids = EXPORTS.get((tenant, user), {}).get(handle)   # looked up only under the user who made it
        if ids is None:
            raise ToolError("not found: no such export for you")
        return "\n".join(f"{i} {ISSUES[i]['title']}" for i in ids)
    return await run(tenant, work)

if __name__ == "__main__":
    mcp.run("streamable-http", host="127.0.0.1", port=PORT, json_response=True)


# %% [markdown]
# Start Trackr with its quotas on. It is ready when its protected-resource metadata answers.

# %%
trk = start("tenant_trackr.py", ISSUER, f"{ISSUER}/jwks", str(ISSUES_FILE), "on")
wait_for("http://127.0.0.1:8381/.well-known/oauth-protected-resource/mcp")

from mcp import Client
from mcp.client.streamable_http import streamable_http_client

async def call(token_value, name, args):
    """One MCP session as one user. The token goes on every request. Returns the text, prefixed ERROR when refused."""
    http = httpx2.AsyncClient(headers={"Authorization": f"Bearer {token_value}"}, timeout=10)
    try:
        async with Client(streamable_http_client(TRACKR, http_client=http)) as c:
            res = await c.call_tool(name, args)
    finally:
        await http.aclose()
    return ("ERROR " if res.is_error else "") + res.content[0].text

http = httpx2.AsyncClient(headers={"Authorization": f"Bearer {TOK['ana']}"}, timeout=10)
async with Client(streamable_http_client(TRACKR, http_client=http)) as c:
    tools = (await c.list_tools()).tools
await http.aclose()
for t in tools:
    print(t.name, "takes:", list(t.input_schema.get("properties", {})))

# %% [markdown]
# Now the same server, called as each user: ana and ben, then ana adding a `tenant` argument of her own.

# %%
print("ana (web):", (await call(TOK["ana"], "list_issues", {})).replace("\n", " | "))
print("ben (api):", (await call(TOK["ben"], "list_issues", {})).replace("\n", " | "))
print("ana adds tenant='api' to the arguments:", (await call(TOK["ana"], "list_issues", {"tenant": "api"})).replace("\n", " | "))

# %% [markdown]
# ### 4. Twelve cross-tenant reads and writes
# Ana is in `web`. Below she tries to read and to close each of the six `api` issues, which makes twelve attempts. She also asks for an issue that does not exist. Trackr answers every attempt with the same text, so the answer reveals nothing about the other team's issues.

# %%
api_ids = [i["id"] for i in ISSUES if i["team"] == "api"]
attempts = []
for issue_id in api_ids:
    attempts.append(await call(TOK["ana"], "get_issue", {"issue_id": issue_id}))
    attempts.append(await call(TOK["ana"], "close_issue", {"issue_id": issue_id}))
# the same two tools on an id that does not exist
missing = {"get_issue": await call(TOK["ana"], "get_issue", {"issue_id": 999}),
           "close_issue": await call(TOK["ana"], "close_issue", {"issue_id": 999})}
expected = [missing["get_issue" if k % 2 == 0 else "close_issue"] for k in range(len(attempts))]
print(f"ana (web) on api's issues: {len(attempts)} reads and writes, {sum(a.startswith('ERROR') for a in attempts)} refused")
print("the refusal:", attempts[0])
print("same answer as a missing issue, tool by tool:", attempts == expected)
print("api still has", len((await call(TOK['ben'], 'list_issues', {})).splitlines()), "open issues: nothing was closed")

# %% [markdown]
# ### 5. Handles are bound to the user and the tenant
# An export handle is a key into a table. Here it is only usable by the user who made it. Pat is in the same team as ana and still cannot read her handle. Ben's team cannot either. For each of them, the answer is the same as for a handle that was never made.

# %%
handle = await call(TOK["ana"], "export_issues", {})
pat_try = await call(TOK["pat"], "read_export", {"handle": handle})        # same team, other user
ben_try = await call(TOK["ben"], "read_export", {"handle": handle})        # another team
unknown = await call(TOK["ana"], "read_export", {"handle": "no-such-handle"})
print("pat (same team, other user):", pat_try)
print("ben (another team):", ben_try)
print("ana reads her own:", (await call(TOK["ana"], "read_export", {"handle": handle})).replace("\n", " | "))
print("the refusals equal the unknown-handle answer:", pat_try == ben_try == unknown, "|", unknown)

# %% [markdown]
# ### 6. Each team's agent asks one question (`needs-llm`)
# Each team's agent gets one tool, `list_issues`. The tool takes no team argument, so the model cannot ask for another team. The token it holds decides the tenant. Each agent makes two model calls: one to pick the tool, one to write the answer. The recording covers both agents, 4 calls in all. If the model is skipped, the tool answers on its own, as the agent would.

# %%
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage

def team_tool(token_value: str):
    """The one tool a team's agent gets. It takes no team argument: the token decides the tenant."""
    @tool("list_issues")
    async def list_issues_tool() -> str:
        """List the open issues of the team this agent works for."""
        return await call(token_value, "list_issues", {})
    return list_issues_tool

Q = HumanMessage("Which issues are open for our team? Use the tool.")
print("tool ready:", team_tool(TOK["ana"]).name)

# %% [markdown]
# The recording opens here and covers both agents: the model calls and the Trackr calls the tools make in between.

# %% tags=["needs-llm"]
import llm_replay
llm_replay.start("38_multi-tenant-servers")
from llm_setup import get_llm
llm = get_llm(max_calls=4)

async def ask(user):
    """Two model calls: one to choose the tool, one to write the answer. The tool runs in between, as this user."""
    tool_ = team_tool(TOK[user])
    first = await llm.bind_tools([tool_]).ainvoke([Q])                       # model call 1
    results = [await tool_.ainvoke(c) for c in first.tool_calls]             # Trackr, with this user's token
    final = await llm.bind_tools([tool_]).ainvoke([Q, first, *results])      # model call 2
    return [c["args"] for c in first.tool_calls], final.text

ANSWERS = {}
for user in ("ana", "ben"):
    ANSWERS[user] = await ask(user)

# %% [markdown]
# If the model cell did not run, the tool answers on its own, so the rest of the lesson still works.

# %%
if "ANSWERS" not in globals():
    ANSWERS = {}
    for user in ("ana", "ben"):
        ANSWERS[user] = (["no model in this run"], await team_tool(TOK[user]).ainvoke({}))
    print("no model here: the tool answers on its own, as the agent would.")
for user, (calls, text) in ANSWERS.items():
    print(f"{TEAM[user]} ({user}) | tool arguments the model chose: {calls}")
    print("  answer:", text.replace("\n", " | "))

# %% [markdown]
# The recording closes here. Everything after this makes no model call.

# %% tags=["needs-llm"]
llm_replay.stop()

# %% [markdown]
# ### 7. The triage agent: the A2A tenant field
# The triage agent is an A2A server, one URL for every team. Its card has one interface per tenant, and each interface names its tenant. A request carries a `tenant` field in its body. The agent accepts a request only when that field equals the tenant in the caller's token. Any other request gets the same refusal. Results are encrypted under the tenant's own key. The agent runs in this notebook, as lesson 37 did, and it makes no model call.

# %%
%%writefile ../apps/38/tenant_triage.py
"""Triage agent for lesson 38, served by the notebook on 127.0.0.1:8382 over A2A. One agent for every team.
Real here: a request's tenant field must equal the tenant in the caller's verified token, or the task is refused
with the same answer for every other tenant; the token's audience must be this agent; each tenant's results are
encrypted under that tenant's own key (HKDF of the store's master key, with the tenant name as context).
Stand-in: the label is a keyword rule, so this agent makes no model call."""
import base64
from pathlib import Path
import jwt
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from a2a.helpers import get_message_text, new_task_from_user_message, new_text_message, new_text_part
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from starlette.applications import Starlette
from starlette.responses import JSONResponse

AUDIENCE = "http://127.0.0.1:8382/"
REFUSAL = "no triage agent for your team at this tenant"

class Caller:
    """The verified claims of the bearer token for this agent (signature, issuer, audience, expiry), or None."""
    def __init__(self, issuer: str, jwks_url: str):
        self.issuer, self.keys = issuer, jwt.PyJWKClient(jwks_url)

    def claims(self, header: str) -> dict | None:
        token = header[7:] if header.startswith("Bearer ") else ""
        try:
            key = self.keys.get_signing_key_from_jwt(token).key
            return jwt.decode(token, key, algorithms=["RS256"], audience=AUDIENCE, issuer=self.issuer)
        except jwt.PyJWTError:
            return None

class TenantVault:
    """Each tenant's results are encrypted under a key derived from the master key and that tenant's name."""
    def __init__(self, master: bytes, store: Path):
        self.master, self.store = master, store

    def fernet(self, tenant: str) -> Fernet:
        raw = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"tenant:" + tenant.encode()).derive(self.master)
        return Fernet(base64.urlsafe_b64encode(raw))

    def put(self, tenant: str, task_id: str, text: str) -> Path:
        path = self.store / tenant / f"{task_id}.bin"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.fernet(tenant).encrypt(text.encode()))
        return path

def scripted_label(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ("crash", "error", "fails", "does nothing", "wrong")):
        return "bug"
    if any(w in t for w in ("add", "support", "would be nice")):
        return "feature"
    return "question"

# %% [markdown]
# The rest of the file holds the executor. Its refusal and its encryption are the two checks the rest of this lesson relies on.

# %%
%%writefile -a ../apps/38/tenant_triage.py
class TriageExecutor(AgentExecutor):
    def __init__(self, caller: Caller, vault: TenantVault):
        self.caller, self.vault = caller, vault

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        if context.current_task is None:
            await event_queue.enqueue_event(new_task_from_user_message(context.message))
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.start_work()
        header = context.call_context.state.get("headers", {}).get("authorization", "")
        claims = self.caller.claims(header) or {}
        if not claims or context.tenant != claims.get("tenant"):    # the A2A tenant field must be the caller's own
            await updater.failed(new_text_message(REFUSAL))
            return
        text = get_message_text(context.message)
        label = scripted_label(text)
        self.vault.put(claims["tenant"], context.task_id, f"{label} | {text}")
        await updater.add_artifact(parts=[new_text_part(label)], name="rule")
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        await TaskUpdater(event_queue, context.task_id, context.context_id).cancel()

class RequireToken:
    """ASGI wrapper: every request except the public card needs a token for this agent."""
    def __init__(self, app, caller: Caller):
        self.app, self.caller = app, caller

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] == "/.well-known/agent-card.json":
            return await self.app(scope, receive, send)
        header = dict(scope["headers"]).get(b"authorization", b"").decode()
        if self.caller.claims(header) is None:
            return await JSONResponse({"error": "invalid_token"}, status_code=401)(scope, receive, send)
        return await self.app(scope, receive, send)

def build_app(public_card, issuer: str, jwks_url: str, master: bytes, store: Path):
    caller = Caller(issuer, jwks_url)
    handler = DefaultRequestHandler(agent_executor=TriageExecutor(caller, TenantVault(master, store)),
                                    task_store=InMemoryTaskStore(), agent_card=public_card)
    app = Starlette(routes=[*create_agent_card_routes(public_card), *create_jsonrpc_routes(handler, "/")])
    return RequireToken(app, caller)


# %% [markdown]
# The triage agent runs in this notebook on its own port, as lesson 37 did. Its card lists one interface per tenant.

# %%
import uvicorn
from a2a.client import ClientConfig, create_client
from a2a.helpers import get_artifact_text, get_message_text, new_text_message
from a2a.types import AgentCard, AgentInterface, AgentSkill, Role, SendMessageRequest, TaskState
from cryptography.fernet import InvalidToken
sys.path.insert(0, str(Path("../apps/38").resolve()))
from tenant_triage import TenantVault, build_app

def public_card() -> AgentCard:
    """One agent, one URL, one interface per tenant: the card says which tenant each interface serves."""
    return AgentCard(name="triage-agent", description="Labels Trackr issues as bug, feature or question, for each team.",
        version="1.0.0", default_input_modes=["text/plain"], default_output_modes=["text/plain"],
        supported_interfaces=[AgentInterface(url=TRIAGE, protocol_binding="JSONRPC", protocol_version="1.0", tenant=t)
                              for t in ("web", "api")],
        skills=[AgentSkill(id="classify_issue", name="Classify an issue", tags=["triage"],
                           description="One label per issue, for the caller's own team.")])

PUBLIC = public_card()
print("card interfaces:", [(i.url, i.tenant) for i in PUBLIC.supported_interfaces])

# %% [markdown]
# The server is an ASGI app run as a task of this event loop. It is ready when its card answers.

# %%
class AgentServer:
    """The ASGI app served as a task of this notebook's event loop, as in lesson 37."""
    def __init__(self, app, port: int):
        self.url = f"http://127.0.0.1:{port}"
        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))

    async def start(self, timeout: float = 15.0) -> "AgentServer":
        self.task = asyncio.create_task(self.server.serve())
        async with httpx.AsyncClient(timeout=1) as http:
            for _ in range(int(timeout / 0.2)):                 # poll the card until it answers
                try:
                    if (await http.get(self.url + "/.well-known/agent-card.json")).status_code == 200:
                        return self
                except httpx.TransportError:
                    pass
                await asyncio.sleep(0.2)
        raise RuntimeError("the triage agent did not answer its card URL in time")

    async def stop(self) -> None:
        self.server.should_exit = True
        await self.task

triage = await AgentServer(build_app(PUBLIC, ISSUER, f"{ISSUER}/jwks", MASTER, STORE), 8382).start()
print("triage agent up at", triage.url)

# %% [markdown]
# Each team gets its own copy of the card, with only its own interface. Then each user sends a message through it.

# %%
def card_for(team: str) -> AgentCard:
    """The team's own copy of the card: only the interface for its tenant."""
    card = AgentCard()
    card.CopyFrom(PUBLIC)
    keep = [i for i in PUBLIC.supported_interfaces if i.tenant == team]
    del card.supported_interfaces[:]
    card.supported_interfaces.extend(keep)
    return card

# %% [markdown]
# `send` makes one A2A call as one user. Its `tenant` argument becomes the request's tenant field.

# %%
async def send(user, text, tenant=""):
    """One A2A message as this user. The request's tenant field is `tenant`; empty means the card's own tenant."""
    http = httpx.AsyncClient(headers={"Authorization": f"Bearer {TOK_TRIAGE[user]}"}, timeout=10)
    client = await create_client(agent=card_for(TEAM[user]), client_config=ClientConfig(streaming=False, httpx_client=http))
    task = None
    try:
        request = SendMessageRequest(tenant=tenant, message=new_text_message(text, role=Role.ROLE_USER))
        async for chunk in client.send_message(request):
            if chunk.WhichOneof("payload") == "task":
                task = chunk.task
    finally:
        await client.close()
        await http.aclose()
    return task

ok_task = await send("ana", "The CSV export crashes on empty rows")
print("ana, her own tenant:", TaskState.Name(ok_task.status.state), "| label:", get_artifact_text(ok_task.artifacts[0]))
bad_task = await send("ana", "Add a dark theme", tenant="api")
print("ana, request tenant 'api':", TaskState.Name(bad_task.status.state), "|", get_message_text(bad_task.status.message))

# %% [markdown]
# The result of the first task is on disk, encrypted. Web's key reads it. Api's key does not. Each tenant's key is derived from the master key and the tenant's name, so one team's key cannot open another team's file.

# %%
files = sorted(STORE.rglob("*.bin"))
print("stored results:", [str(f.relative_to(STORE)) for f in files])
vault = TenantVault(MASTER, STORE)
web_file = next(f for f in files if f.parent.name == "web")
print("on disk:", web_file.read_bytes()[:24], "...")
print("web's key reads it:", vault.fernet("web").decrypt(web_file.read_bytes()).decode())
try:
    vault.fernet("api").decrypt(web_file.read_bytes())
except InvalidToken:
    print("api's key cannot read web's result: InvalidToken")

# %% [markdown]
# ### 8. Noisy neighbour: one tenant floods, the other measures
# Trackr has 2 worker slots, and each call holds one for about 30 ms. With quotas on, a tenant gets one call in flight and a token bucket. Its extra calls are refused at once. With quotas off, every call queues for the same two slots. Forty web calls arrive at once, and the api team makes twenty calls while they run. The latencies are measured, so the numbers differ from run to run; the figures printed below are from one run. Compare the median with the worst case.

# %%
async def victim(n: int = 20):
    """The api team's calls, one after another, timed in milliseconds."""
    lat = []
    for _ in range(n):
        t0 = time.perf_counter()
        await call(TOK["ben"], "list_issues", {})
        lat.append((time.perf_counter() - t0) * 1000)
    return lat

async def measure(label: str):
    """Forty web calls at once, and the api team's calls while they run."""
    flood = [call(TOK["ana"], "list_issues", {}) for _ in range(40)]
    *texts, lat = await asyncio.gather(*flood, victim())
    refused = sum(t.startswith("ERROR") for t in texts)
    lat.sort()
    print(f"{label}: web sent 40 calls, {40 - refused} ran, {refused} refused | "
          f"api median {lat[len(lat) // 2]:.0f} ms, worst {lat[-1]:.0f} ms")

# One or two ran: the other calls arrive while the first call is still in flight, so they are refused. Exact counts vary by run.
await measure("quotas on ")
trk.terminate(); trk.wait()                                  # the same server, with the per-tenant limits switched off
trk = start("tenant_trackr.py", ISSUER, f"{ISSUER}/jwks", str(ISSUES_FILE), "off")
wait_for("http://127.0.0.1:8381/.well-known/oauth-protected-resource/mcp")
await measure("quotas off")

# %% [markdown]
# ### 9. Stop the servers

# %%
await triage.stop()
for p in procs:
    p.terminate()
print("lesson 38 done: one server, two teams' rules, and every refusal looked the same")

# %% [markdown]
# ## At real scale
# - **The tenant is a claim the server signed, never an argument.** Put the team in the record of the authorization server (lesson 34), and check the audience on every server.
# - **Refusals must not leak.** A cross-tenant read, a missing id and someone else's handle get one answer. Test every tool as every tenant (lesson 27).
# - **Quotas are per tenant, and they must refuse early.** A queue is shared. A flood that waits in line slows everyone (step 8). Uber's MCP gateway (800+ servers, 5,000+ tools, Uber engineering blog, 2026-10-01) starts every new tool disabled and checks per-tool access policies before a request reaches a server.
# - **Encrypt per tenant.** One key for every tenant means one leaked key exposes every team's results. Derive or wrap keys per tenant, and keep the master key in a key service, not in `.env`.

# %% [markdown]
# ## Decision guide
# | Choice | Use it when | What it costs |
# | --- | --- | --- |
# | One deployment per tenant | a regulator or contract needs hard separation | N deployments to run and upgrade |
# | One shared server, tenant from the token, scoped queries (this lesson) | many small teams, one product | one missed filter leaks everything, so every tool needs a cross-tenant test |
# | One shared server, team as a tool argument | never for data a model or user should not see | the model and the caller choose the tenant |
# | Per-tenant keys for stored results | results may be sensitive | key management per tenant |
# | One key for all results | results are not sensitive | one leaked key exposes all tenants |

# %% [markdown]
# ## What just happened
# One Trackr served two teams. The token named the tenant, the tools took no tenant argument, and cross-tenant attempts got the same answer as missing issues. Handles stayed with their owner. The A2A agent refused a request whose tenant field did not match the token. With quotas on, one team's flood was refused at the door: the other team's median stayed about the same, and its worst call was under half as long as without quotas (one run; the figures vary). The store kept each team's results under its own key.

# %% [markdown]
# ## Common mistakes
# **Mistake 1: trusting the request's tenant field.** An A2A agent that reads `context.tenant` and stops there lets any caller name any team. Compare it with the verified token, as step 7 does: its `TASK_STATE_FAILED` line shows ana's request with tenant `api` refused. Without that comparison, the request would have completed.
#
# **Mistake 2: using the wrong tenant's key.** For example, deriving the key from the request's tenant field instead of the token's tenant. A result stored under one team's key cannot then be read with another team's key. The cell below shows the failure: api's key on web's file raises `InvalidToken`. The fix is to derive the key from the verified token's tenant, as the store does.

# %% tags=["raises-exception"]
TenantVault(MASTER, STORE).fernet("api").decrypt(web_file.read_bytes())

# %% [markdown]
# ## Try it
# Write `find_export`. It returns the issue ids of one export, but only for the user who made it. For anyone else it returns `None`, as the server does. The exports dict uses `(tenant, user)` as its key.

# %%
# your code here
def find_export(exports: dict, tenant: str, user: str, handle: str):
    # your code here
    return None

print(find_export({("web", "ana"): {"h1": [101, 102]}}, "web", "ana", "h1"),
      find_export({("web", "ana"): {"h1": [101, 102]}}, "web", "pat", "h1"))

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
def find_export(exports: dict, tenant: str, user: str, handle: str):
    return exports.get((tenant, user), {}).get(handle)

print(find_export({("web", "ana"): {"h1": [101, 102]}}, "web", "ana", "h1"),
      find_export({("web", "ana"): {"h1": [101, 102]}}, "web", "pat", "h1"))

# %% [markdown]
# ## Key terms
# - **tenant** — the group a piece of data belongs to (here, a team). A shared server takes it from the caller's verified token (lesson 38).
# - **existence leak** — an answer that tells a caller something exists, by refusing it differently from a missing thing. Refusals must match (lesson 38).
# - **handle binding** — a handle that works only for the user, and the tenant, that made it (lesson 38).
# - **noisy neighbour** — one tenant's load that slows another tenant on shared capacity (lesson 38).
# - **token bucket** — a limit that refills at a fixed rate and allows a burst up to its size (lesson 38).
# - **A2A tenant field** — the `tenant` value in an A2A request, and on an agent interface in its card. The server must check it against the caller's tenant (lesson 38).

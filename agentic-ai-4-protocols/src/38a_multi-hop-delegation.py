# %% [markdown]
# # 38a · Multi-hop delegation: chained token exchange
# Level L6 · Part 7 · professional · ~35 min · builds on 35, 18

# %% [markdown]
# ## Goal
# By the end, a user's request goes user → orchestrator → triage-agent (A2A) → Trackr (MCP), and each hop holds a token issued to it. The token that reaches Trackr names alice as `sub` and the chain of actors in `act`. A hop that asks for a wider scope is refused, a hop that tries to skip ahead is refused, and every hop writes its own audit line. The model makes 2 calls.

# %% [markdown]
# ## Why it matters
# A user asks the orchestrator to triage her team's issues. The work passes through two more services. Without a chain of exchanges, each hop does one of three bad things.
#
# | | Forward the user's token to every hop | One service account for the whole chain | Chained token exchange |
# | --- | --- | --- | --- |
# | Who Trackr sees | alice, with no sign of the agents | the service account, for every user | alice, acting through triage-agent, which the orchestrator started |
# | Audience of the token | the orchestrator's, reused everywhere (the token passthrough that lesson 31 forbids) | Trackr's, for any user | the audience of the hop it is sent to |
# | What a hop may do | everything alice can do | everything the account can do | the scope the previous hop passed on, never more |
#
# Skip this for one service that calls one API for one user. It pays when a user's request crosses two or more services that each act on it.

# %% [markdown]
# ## The idea
# Each hop gets a new token. The hop sends the token it received as the *subject token*, and its own token as the *actor token*. The authorization server checks both, and it refuses the exchange unless the subject was issued to the caller. The new token keeps `sub` = alice, sets a new `aud` for the next hop, and narrows the scope. Its `act` claim names the caller, and it nests the previous `act` inside. Trackr's token therefore carries the whole chain: triage-agent, acting for the orchestrator, acting for alice.
#
# Analogy: a visitor's pass to a building. The front desk gives a pass for the lobby. The lobby guard swaps it for a pass for one floor, and writes both names on it. A pass for the lobby does not open the floor, and a floor pass never opens the vault.

# %% [markdown]
# ## Picture
# ```mermaid
# sequenceDiagram
#   participant U as alice
#   participant O as Orchestrator (model)
#   participant S as Authorization server :9380
#   participant T as triage-agent A2A :9382
#   participant M as Trackr MCP :9381
#   U->>O: sign-in: token aud = orchestrator, scope triage:run issues:read
#   O->>S: exchange: subject = alice's token, actor = orchestrator
#   S-->>O: token aud = triage-agent, act = orchestrator
#   O->>T: A2A message with that token (one hop)
#   T->>S: exchange: subject = that token, actor = triage-agent
#   S-->>T: token aud = Trackr, scope issues:read, act = triage-agent > orchestrator
#   T->>M: list_open_issues with that token
#   M-->>T: the issues, one audit line
#   T-->>O: artifact (classified, with a receipt of the chain)
# ```

# %% [markdown]
# ## Step by step
#
# ### 1. Set up
# The ports are 9380 (the authorization server), 9381 (Trackr) and 9382 (the triage agent). The two client secrets come from `.env`; the lab values are for the local lab servers only. The logs are cleared at the start, and each server's stderr goes to a file in `../data/38a`.

# %%
import sys, os, json, time, subprocess, atexit, asyncio, socket
from pathlib import Path
import httpx, httpx2, jwt, uvicorn
sys.path.insert(0, "..")
import tut_env, llm_replay
from tut_env import env
tut_env.load()
ISSUER, TRACKR, SELF = "http://127.0.0.1:9380", "http://127.0.0.1:9381/mcp", "http://127.0.0.1:9382/"
ORCH_AUD, TRIAGE_AUD, TRACKR_AUD = "urn:trackr:ops-orchestrator", SELF, TRACKR
TOKEN_TYPE = "urn:ietf:params:oauth:token-type:access_token"
TOKEN_EXCHANGE = "urn:ietf:params:oauth:grant-type:token-exchange"
DATA = Path("../data/38a").resolve(); DATA.mkdir(parents=True, exist_ok=True)
Path("../apps/38a").mkdir(parents=True, exist_ok=True)
for name in ["as_audit.log", "trackr_audit.log"]:
    (DATA / name).unlink(missing_ok=True)          # a fresh run starts with empty logs
procs, tokens, hop_claims = [], {}, []           # servers; the tokens of each hop; the claims the orchestrator saw
llm, first, result = None, None, None            # set by the model cell; stay None if it is skipped
atexit.register(lambda: [p.terminate() for p in procs])
print("ports 9380-9382 | secrets set:", bool(env("ORCHESTRATOR_CLIENT_SECRET")), bool(env("TRIAGE_AGENT_CLIENT_SECRET")))

# %% [markdown]
# ### 2. The stand-in authorization server (no Docker)
# This server issues RS256 tokens and publishes its keys. It has two clients. Each client has its own audience and may exchange only for the targets on its list. `ops-orchestrator` may hand a token to triage-agent, and triage-agent may hand one to Trackr. Each client may hold only the scopes on its list.
#
# The file is split in two. `as_keys.py` holds the keys, the clients and the helpers. `as_server.py` holds the endpoints.

# %%
%%writefile ../apps/38a/as_keys.py
"""Lesson 38a: the stand-in authorization server's keys, clients and token helpers (imported by as_server.py)."""
import base64, os, secrets, time
from joserfc import jwt
from joserfc.jwk import RSAKey

ISSUER = "http://127.0.0.1:9380"
ORCH_AUD = "urn:trackr:ops-orchestrator"      # the orchestrator's audience: the user's token is issued to it
TRIAGE_AUD = "http://127.0.0.1:9382/"         # the triage agent's audience
TRACKR_AUD = "http://127.0.0.1:9381/mcp"      # Trackr's audience
TOKEN_EXCHANGE = "urn:ietf:params:oauth:grant-type:token-exchange"
TOKEN_TYPE = "urn:ietf:params:oauth:token-type:access_token"
KEY = RSAKey.generate_key(2048, {"kid": "tut-38a", "alg": "RS256", "use": "sig"})
# Each client: its secret, its own audience, its grants, the scopes it may hold, and the audiences it may exchange to.
CLIENTS = {
    "ops-orchestrator": {"secret": os.environ["ORCHESTRATOR_CLIENT_SECRET"], "audience": ORCH_AUD,
                         "grants": {"client_credentials", TOKEN_EXCHANGE},
                         "scopes": {"triage:run", "issues:read"}, "targets": {TRIAGE_AUD}},
    "triage-agent": {"secret": os.environ["TRIAGE_AGENT_CLIENT_SECRET"], "audience": TRIAGE_AUD,
                     "grants": {"client_credentials", TOKEN_EXCHANGE},
                     "scopes": {"issues:read"}, "targets": {TRACKR_AUD}},
}

def issue(claims, audience, scope, lifetime):
    now = int(time.time())
    body = {"iss": ISSUER, "aud": audience, "iat": now, "exp": now + lifetime, "scope": scope, **claims}
    return jwt.encode({"alg": "RS256", "kid": "tut-38a"}, body, KEY)

def verified(token):
    """Our own tokens only: signature, issuer and expiry. Returns the claims, or None."""
    try:
        c = jwt.decode(token, KEY).claims
    except Exception:
        return None
    return c if c.get("iss") == ISSUER and c.get("exp", 0) > time.time() else None

def client_of(request, form):
    """client_secret_basic (header) or client_secret_post (form). Returns the client id, or None."""
    auth = request.headers.get("authorization", "")
    if auth.startswith("Basic "):
        cid, _, secret = base64.b64decode(auth[6:]).decode().partition(":")
    else:
        cid, secret = form.get("client_id", ""), form.get("client_secret", "")
    client = CLIENTS.get(cid)
    return cid if client and secrets.compare_digest(client["secret"], secret) else None

def chain(act):
    """The actors in an act claim, newest first: ['triage-agent', 'ops-orchestrator']."""
    names = []
    while act:
        names.append(act["sub"])
        act = act.get("act")
    return names

# %% [markdown]
# The endpoints: a sign-in stand-in, the client-credentials grant for a client's own actor token, and the token exchange. The exchange has four checks, and each refusal is one audit line.

# %%
%%writefile ../apps/38a/as_server.py
"""Stand-in authorization server for lesson 38a, on 127.0.0.1:9380 (no Docker).
Real here: client authentication, client credentials, and RFC 8693 token exchange with four checks:
the subject token was issued to the caller, the actor token is the caller's own, the target is on the
caller's list, and the scope sits inside the subject's grant and the client's list.
Stand-in: /dev/sign-in replaces lesson 34's browser sign-in and gives the demo user alice her token."""
import json, sys
from pathlib import Path
from urllib.parse import parse_qs
import uvicorn
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from as_keys import CLIENTS, ISSUER, KEY, ORCH_AUD, TOKEN_EXCHANGE, TOKEN_TYPE, chain, client_of, issue, verified

AUDIT = Path(sys.argv[1])

def log(record):
    with AUDIT.open("a") as f:
        f.write(json.dumps(record) + "\n")

def refuse(cid, form, code, text):
    log({"event": "refused", "caller": cid, "grant": form.get("grant_type", ""), "reason": code, "detail": text})
    return JSONResponse({"error": code, "error_description": text}, status_code=400)

async def metadata(request):
    return JSONResponse({"issuer": ISSUER, "token_endpoint": f"{ISSUER}/token", "jwks_uri": f"{ISSUER}/jwks",
                         "grant_types_supported": ["client_credentials", TOKEN_EXCHANGE]})

async def jwks(request):
    return JSONResponse({"keys": [KEY.as_dict(private=False)]})

async def sign_in(request):
    """Stand-in for the browser sign-in: alice's token, issued to the orchestrator."""
    if request.query_params.get("user") != "alice":
        return JSONResponse({"error": "unknown_user"}, status_code=404)
    tok = issue({"sub": "alice", "azp": "ops-web"}, ORCH_AUD, "triage:run issues:read", 3600)
    log({"event": "signed_in", "sub": "alice", "aud": ORCH_AUD, "scope": "triage:run issues:read"})
    return JSONResponse({"access_token": tok, "token_type": "Bearer"})

async def token(request):
    form = {k: v[0] for k, v in parse_qs((await request.body()).decode()).items()}
    cid = client_of(request, form)
    if cid is None:
        return JSONResponse({"error": "invalid_client"}, status_code=401)
    client, scope = CLIENTS[cid], set(form.get("scope", "").split())
    resource = form.get("resource", "")
    if form.get("grant_type") == "client_credentials":
        if "client_credentials" not in client["grants"] or resource != client["audience"]:
            return refuse(cid, form, "invalid_target", "a client asks only for its own token")
        if not scope <= client["scopes"]:
            return refuse(cid, form, "invalid_scope", f"{cid} may not hold {sorted(scope - client['scopes'])}")
        tok = issue({"sub": cid, "azp": cid}, resource, " ".join(sorted(scope)), 300)
        log({"event": "issued", "grant": "client_credentials", "sub": cid, "aud": resource})
        return JSONResponse({"access_token": tok, "token_type": "Bearer", "expires_in": 300})
    if form.get("grant_type") != TOKEN_EXCHANGE or TOKEN_EXCHANGE not in client["grants"]:
        return refuse(cid, form, "unsupported_grant_type", "this client may not use that grant")
    subject, actor = verified(form.get("subject_token", "")), verified(form.get("actor_token", ""))
    if subject is None or actor is None:
        return refuse(cid, form, "invalid_request", "subject_token and actor_token must be unexpired tokens from this server")
    if subject.get("aud") != client["audience"]:
        return refuse(cid, form, "invalid_target", "the subject token was not issued to this caller: no skipping a hop")
    if actor.get("sub") != cid:
        return refuse(cid, form, "invalid_request", "the actor token must be the caller's own token")
    if resource not in client["targets"]:
        return refuse(cid, form, "invalid_target", f"{cid} may not get tokens for {resource}")
    if not scope <= set(subject["scope"].split()) or not scope <= client["scopes"]:
        return refuse(cid, form, "invalid_scope", "the scope must be in the subject's grant and in this client's list")
    # RFC 8693 act claim: the caller is named as the actor; the previous actor, if any, nests inside it.
    act = {"sub": cid, **({"act": subject["act"]} if "act" in subject else {})}
    out = issue({"sub": subject["sub"], "azp": cid, "act": act}, resource, " ".join(sorted(scope)), 300)
    log({"event": "exchanged", "caller": cid, "sub": subject["sub"], "act": chain(act), "aud": resource,
         "scope": " ".join(sorted(scope))})
    return JSONResponse({"access_token": out, "issued_token_type": TOKEN_TYPE, "token_type": "Bearer",
                         "expires_in": 300, "scope": " ".join(sorted(scope))})

app = Starlette(routes=[Route("/.well-known/oauth-authorization-server", metadata), Route("/jwks", jwks),
                        Route("/dev/sign-in", sign_in), Route("/token", token, methods=["POST"])])

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=9380, log_level="warning")

# %% [markdown]
# The helper starts a server with its own error file, and waits until the server answers. It polls; it does not sleep for a fixed time.

# %%
def start(script, *args):
    """Start one server from ../apps/38a with a file for its errors."""
    log = open(DATA / (Path(script).stem + ".err"), "w")
    p = subprocess.Popen([sys.executable, str(Path("../apps/38a", script).resolve()), *args],
                         stdout=subprocess.DEVNULL, stderr=log, env=os.environ)
    procs.append(p)
    return p

def wait_for(url, ok=lambda r: r.status_code < 500, timeout=60):
    """Poll until the URL answers the way ok() wants."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            if ok(httpx.get(url, timeout=2)):
                return
        except httpx.HTTPError:
            pass
        if time.monotonic() > deadline:
            raise RuntimeError(f"no answer from {url}; see the .err files in ../data/38a")
        time.sleep(0.5)

start("as_server.py", str(DATA / "as_audit.log"))
wait_for(f"{ISSUER}/.well-known/oauth-authorization-server")
print("authorization server up:", httpx.get(f"{ISSUER}/.well-known/oauth-authorization-server").json()["issuer"])

# %% [markdown]
# ### 3. Trackr: the last hop
# Trackr has one tool, `list_open_issues(team)`. It accepts only a token whose audience is Trackr and that carries `issues:read`. Each call writes one audit line with the caller (`azp`), the person (`sub`) and the whole actor chain (`act`). The issues are a small file that the notebook writes; it is the team desk from lesson 35.

# %%
issues = [{"id": 4, "team": "web", "state": "open", "title": "Login page flickers on Safari"},
          {"id": 9, "team": "web", "state": "open", "title": "Export CSV drops the owner column"},
          {"id": 12, "team": "web", "state": "closed", "title": "Typo in the footer"},
          {"id": 15, "team": "api", "state": "open", "title": "Rate limit header missing"}]
(DATA / "issues.json").write_text(json.dumps(issues))
print("issues written:", len(issues))

# %% [markdown]
# Trackr's server file. It reads the issues file, checks the token against the authorization server's keys, and checks the audience against its own URI.

# %%
%%writefile ../apps/38a/trackr_chain.py
"""Trackr for lesson 38a, on 127.0.0.1:9381. One tool: list_open_issues(team).
It accepts only a token whose audience is Trackr and that carries issues:read, and writes one audit
line per call: the caller (azp), the person (sub) and the whole actor chain (act)."""
import json, sys
from pathlib import Path
import jwt
from mcp.server import MCPServer
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

PORT = 9381
RESOURCE = f"http://127.0.0.1:{PORT}/mcp"
ISSUER, JWKS_URL = "http://127.0.0.1:9380", "http://127.0.0.1:9380/jwks"
ISSUES, AUDIT = Path(sys.argv[1]), Path(sys.argv[2])

def chain(act):
    names = []
    while act:
        names.append(act["sub"])
        act = act.get("act")
    return names

class OrgVerifier:
    """The signature from the authorization server's keys, the issuer, and the audience = Trackr's own URI."""
    def __init__(self):
        self.keys = jwt.PyJWKClient(JWKS_URL)

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            key = self.keys.get_signing_key_from_jwt(token).key
            c = jwt.decode(token, key, algorithms=["RS256"], audience=RESOURCE, issuer=ISSUER)
        except jwt.PyJWTError:
            return None
        return AccessToken(token=token, client_id=c.get("azp", ""), scopes=c.get("scope", "").split(),
                           expires_at=c["exp"], resource=RESOURCE, subject=c.get("sub"), claims=c)

mcp = MCPServer("Trackr", token_verifier=OrgVerifier(), auth=AuthSettings(
    issuer_url=ISSUER, resource_server_url=RESOURCE, required_scopes=["issues:read"], validate_token_resource=True))

@mcp.tool(title="List open issues", annotations=ToolAnnotations(readOnlyHint=True))
async def list_open_issues(team: str) -> str:
    token = get_access_token()
    if token is None or "issues:read" not in token.scopes:
        raise ToolError("insufficient_scope: this tool needs issues:read")
    rows = [f"{i['id']}: {i['title']}" for i in json.loads(ISSUES.read_text())
            if i["team"] == team and i["state"] == "open"]
    with AUDIT.open("a") as log:
        log.write(json.dumps({"event": "tool_call", "tool": "list_open_issues", "team": team, "azp": token.client_id,
                              "sub": token.claims["sub"], "act": chain(token.claims.get("act")),
                              "rows": len(rows)}) + "\n")
    return "\n".join(rows)

if __name__ == "__main__":
    mcp.run("streamable-http", host="127.0.0.1", port=PORT, json_response=True)

# %% [markdown]
# The helper starts Trackr and waits for its protected-resource metadata.

# %%
start("trackr_chain.py", str(DATA / "issues.json"), str(DATA / "trackr_audit.log"))
wait_for("http://127.0.0.1:9381/.well-known/oauth-protected-resource/mcp")
print("Trackr up")

# %% [markdown]
# ### 4. triage-agent: the middle hop
# triage-agent is an A2A agent. It is a file in `../apps/38a` that the notebook imports. It has the same parts as lesson 18: a card, an executor and an app. Two things are new. The app checks that the token it was sent is issued to it (audience = itself, scope `triage:run`). The executor exchanges that token for a Trackr token before it reads anything. The file is written in the next cell; read the executor and the wrapper.

# %%
%%writefile ../apps/38a/chain_triage_agent.py
"""Lesson 38a: triage-agent, an A2A agent on 127.0.0.1:9382, served from the notebook.
It accepts only a token issued to itself (audience = itself, scope triage:run). It exchanges that token for a Trackr
token, adding itself as the actor and narrowing the scope to issues:read. It reads the team's open issues over MCP and
classifies them in one model call. LLM is set by the notebook; None means no model ran."""
import os
import httpx2, jwt
from a2a.helpers import get_message_text, new_task_from_user_message, new_text_part
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from starlette.applications import Starlette
from starlette.responses import JSONResponse

AS, TRACKR, SELF = "http://127.0.0.1:9380", "http://127.0.0.1:9381/mcp", "http://127.0.0.1:9382/"
TOKEN_EXCHANGE = "urn:ietf:params:oauth:grant-type:token-exchange"
TOKEN_TYPE = "urn:ietf:params:oauth:token-type:access_token"
LLM = None   # the notebook sets the real model here; None means no model ran

def chain(act):
    names = []
    while act:
        names.append(act["sub"])
        act = act.get("act")
    return names

async def exchange_for_trackr(incoming: str) -> str:
    """Hop 3: the same two requests as the notebook's hop 2, with this agent as the caller."""
    secret = os.environ["TRIAGE_AGENT_CLIENT_SECRET"]
    async with httpx2.AsyncClient(timeout=10) as http:
        me = await http.post(f"{AS}/token", auth=("triage-agent", secret), data={
            "grant_type": "client_credentials", "resource": SELF})
        r = await http.post(f"{AS}/token", auth=("triage-agent", secret), data={
            "grant_type": TOKEN_EXCHANGE, "subject_token": incoming, "subject_token_type": TOKEN_TYPE,
            "actor_token": me.json()["access_token"], "actor_token_type": TOKEN_TYPE,
            "resource": TRACKR, "scope": "issues:read"})
    if r.status_code != 200:
        raise RuntimeError(f"token exchange refused: {r.json()['error']}")
    return r.json()["access_token"]

async def read_issues(token: str, team: str) -> str:
    async with httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"}) as http:
        async with Client(streamable_http_client(TRACKR, http_client=http)) as mcp:
            reply = await mcp.call_tool("list_open_issues", {"team": team})
    if reply.is_error:
        raise RuntimeError(reply.content[0].text)
    return reply.content[0].text

async def classify(titles: str) -> tuple[str, str]:
    if LLM is None:
        return titles + "\n(no model ran: the titles are not classified)", "not classified"
    prompt = ("Classify each issue as exactly one word: bug, feature or question.\n"
              "Reply with one line per issue, in the form '<id>: <label>', and nothing else.\n" + titles)
    reply = await LLM.ainvoke(prompt)          # one model call for the whole team
    return reply.text.strip(), "model"

class TriageExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        if context.current_task is None:
            await event_queue.enqueue_event(new_task_from_user_message(context.message))
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.start_work()
        incoming = context.call_context.state["headers"].get("authorization", "")[7:]
        team = get_message_text(context.message).strip()
        token = await exchange_for_trackr(incoming)
        titles = await read_issues(token, team)
        answer, source = await classify(titles)
        seen = jwt.decode(token, options={"verify_signature": False})   # a receipt of what this hop got
        receipt = f"receipt: sub={seen['sub']} aud=trackr scope={seen['scope']} act={' > '.join(chain(seen['act']))}"
        await updater.add_artifact(parts=[new_text_part(answer + "\n" + receipt)], name=source)
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        await TaskUpdater(event_queue, context.task_id, context.context_id).cancel()

# %% [markdown]
# The same file, second half: the card, the wrapper that checks the token this agent was sent, and the app that serves the card and the A2A endpoint.

# %%
%%writefile -a ../apps/38a/chain_triage_agent.py
def build_card(port: int) -> AgentCard:
    return AgentCard(
        name="triage-agent",
        description="Classifies one team's open Trackr issues as bug, feature or question. It acts only with a token issued to it.",
        version="1.0.0",
        supported_interfaces=[AgentInterface(url=f"http://127.0.0.1:{port}/", protocol_binding="JSONRPC", protocol_version="1.0")],
        capabilities=AgentCapabilities(streaming=False, push_notifications=False),
        default_input_modes=["text/plain"], default_output_modes=["text/plain"],
        skills=[AgentSkill(id="triage_team", name="Triage a team", description="Reads the open issues of one team and labels each.",
                           tags=["triage"], examples=["web"], input_modes=["text/plain"], output_modes=["text/plain"])])


# %% [markdown]
# The wrapper checks the token this agent was sent. The app serves the card and the A2A endpoint behind that check.

# %%
%%writefile -a ../apps/38a/chain_triage_agent.py
class RequireHopToken:
    """ASGI wrapper: every call except the public card needs a token issued to this agent with triage:run."""
    def __init__(self, app):
        self.app, self.keys = app, jwt.PyJWKClient(f"{AS}/jwks")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] == "/.well-known/agent-card.json":
            return await self.app(scope, receive, send)
        raw = dict(scope["headers"]).get(b"authorization", b"").decode()[7:]
        try:
            key = self.keys.get_signing_key_from_jwt(raw).key
            c = jwt.decode(raw, key, algorithms=["RS256"], audience=SELF, issuer=AS)
            ok = "triage:run" in c.get("scope", "").split()
        except jwt.PyJWTError:
            ok = False
        if not ok:
            reply = JSONResponse({"error": "invalid_token"}, status_code=401,
                                 headers={"WWW-Authenticate": 'Bearer error="invalid_token"'})
            return await reply(scope, receive, send)
        return await self.app(scope, receive, send)

def build_app(card: AgentCard):
    handler = DefaultRequestHandler(agent_executor=TriageExecutor(), task_store=InMemoryTaskStore(), agent_card=card)
    return RequireHopToken(Starlette(routes=[*create_agent_card_routes(card), *create_jsonrpc_routes(handler, "/")]))

# %% [markdown]
# Imports for the A2A client and the triage agent's module.

# %%
from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers import get_artifact_text, new_text_message
from a2a.types import Role, SendMessageRequest, TaskState
sys.path.insert(0, str(Path("../apps/38a").resolve()))
import chain_triage_agent

# %% [markdown]
# The helper below serves an ASGI app as a task of this notebook's event loop, as lesson 18 did. It polls the card URL until the agent answers. Nothing in it is specific to triage.

# %%
class AgentServer:
    """One ASGI app served as a task of this notebook's event loop."""
    def __init__(self, app, port: int):
        self.url = f"http://127.0.0.1:{port}"
        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))

    async def start(self, timeout: float = 15.0) -> "AgentServer":
        self.task = asyncio.create_task(self.server.serve())
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        async with httpx.AsyncClient(timeout=1) as http:
            while loop.time() < deadline:
                try:
                    if (await http.get(self.url + "/.well-known/agent-card.json")).status_code == 200:
                        return self
                except httpx.TransportError:
                    pass                       # not up yet
                await asyncio.sleep(0.1)
        raise RuntimeError("the triage agent did not answer its card URL in time")

    async def stop(self) -> None:
        self.server.should_exit = True
        await self.task

# %% [markdown]
# Start the triage agent on port 9382, then fetch its public card the way any client does. The client learns the URL and the skills from the card.

# %%
agent = await AgentServer(chain_triage_agent.build_app(chain_triage_agent.build_card(9382)), 9382).start()
async with httpx.AsyncClient(timeout=10) as http:
    found = await A2ACardResolver(http, agent.url).get_agent_card()   # the public card, no token
print("found:", found.name, "| skills:", [s.id for s in found.skills])

# %% [markdown]
# ### 5. Alice signs in, and her token is for the orchestrator
# The stand-in sign-in gives alice a token. Read it: `sub` is alice, `aud` is the orchestrator, and there is no `act` yet, because nobody has acted for her. The orchestrator holds this token and must never send it on as it is.

# %%
ALICE = httpx.get(f"{ISSUER}/dev/sign-in", params={"user": "alice"}, timeout=10).json()["access_token"]
claims = jwt.decode(ALICE, options={"verify_signature": False})
print({k: claims[k] for k in ["sub", "aud", "scope"]}, "| act:", claims.get("act"))

# %% [markdown]
# ### 6. Each hop asks for its own token
# A service that calls the next hop does two requests. First it gets its own token with client credentials (its actor token). Then it exchanges the token it received for one with the next audience and a narrower scope (RFC 8693). The function below is that code for the orchestrator. triage-agent has the same code in its file (`exchange_for_trackr`).

# %%
CREDS = {"ops-orchestrator": env("ORCHESTRATOR_CLIENT_SECRET"), "triage-agent": env("TRIAGE_AGENT_CLIENT_SECRET")}
AUDIENCE = {"ops-orchestrator": ORCH_AUD, "triage-agent": TRIAGE_AUD}

def chain(act):
    """The actors in an act claim, newest first."""
    names = []
    while act:
        names.append(act["sub"])
        act = act.get("act")
    return names

async def hop(caller: str, subject: str, resource: str, scope: str) -> httpx2.Response:
    """What `caller` does before it calls the next hop. Returns the authorization server's reply."""
    async with httpx2.AsyncClient(timeout=10) as http:
        me = await http.post(f"{ISSUER}/token", auth=(caller, CREDS[caller]),
                             data={"grant_type": "client_credentials", "resource": AUDIENCE[caller]})
        return await http.post(f"{ISSUER}/token", auth=(caller, CREDS[caller]), data={
            "grant_type": TOKEN_EXCHANGE, "subject_token": subject, "subject_token_type": TOKEN_TYPE,
            "actor_token": me.json()["access_token"], "actor_token_type": TOKEN_TYPE,
            "resource": resource, "scope": scope})

# %% [markdown]
# The orchestrator makes hop 2 before its model is asked anything. The result is the token the tool will send to triage-agent. This request is made before the recorder starts, so the authorization server answers live in every run.

# %%
r = await hop("ops-orchestrator", ALICE, TRIAGE_AUD, "triage:run issues:read")   # hop 2
assert r.status_code == 200, r.text
tokens["T2"] = r.json()["access_token"]
hop_claims.append(jwt.decode(tokens["T2"], options={"verify_signature": False}))
print("hop 2 token for triage-agent:", {k: hop_claims[-1][k] for k in ["sub", "aud", "scope"]},
      "| act:", chain(hop_claims[-1]["act"]))

# %% [markdown]
# ### 7. The orchestrator's model picks the tool (`needs-llm`)
# The orchestrator is this notebook. Its model sees one tool, `ask_triage_agent`, and must choose it. The recorder opens just before the first model call and closes after the last one. The tool sends the hop 2 token over A2A.

# %%
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage

@tool("ask_triage_agent")
async def ask_triage_agent(team: str) -> str:
    """Ask triage-agent to classify the open issues of one team (web or api). Use it for any triage request."""
    http = httpx.AsyncClient(headers={"Authorization": f"Bearer {tokens['T2']}"}, timeout=120)
    client = await create_client(agent=found, client_config=ClientConfig(streaming=False, httpx_client=http))
    try:
        task = None
        async for chunk in client.send_message(SendMessageRequest(message=new_text_message(team, role=Role.ROLE_USER))):
            if chunk.WhichOneof("payload") == "task":
                task = chunk.task
    finally:
        await http.aclose()
    assert TaskState.Name(task.status.state) == "TASK_STATE_COMPLETED", task.status
    return get_artifact_text(task.artifacts[0])

SYSTEM = SystemMessage("You are the Trackr ops orchestrator. Triage requests go to triage-agent through ask_triage_agent. Do not classify issues yourself.")
QUESTION = HumanMessage("Classify the open issues of the web team as bug, feature or question.")
print("tool ready:", ask_triage_agent.name)

# %% [markdown]
# The model call comes next. The recorder opens just before it.

# %% tags=["needs-llm"]
import llm_replay
llm_replay.start("38a_multi-hop-delegation")   # the window opens here: the first model call is the first recorded one
from llm_setup import get_llm
llm = get_llm(max_calls=2)                     # at most 2 calls: this pick, and triage-agent's classification
chain_triage_agent.LLM = llm                   # the remote agent answers with the same model
first = await llm.bind_tools([ask_triage_agent]).ainvoke([SYSTEM, QUESTION])
print("orchestrator asks for:", [(c["name"], c["args"]) for c in first.tool_calls])

# %% [markdown]
# The orchestrator runs the tool the model picked. This sends the hop 2 token over A2A. Live, triage-agent then runs hop 3 and reads Trackr; in a replay run its answer is replayed. Its one model call happens inside this cell. The artifact that returns is the answer, so no third model call is needed.

# %% tags=["needs-llm"]
if first is not None and first.tool_calls:
    result = await ask_triage_agent.ainvoke(first.tool_calls[0]["args"])
    print(result)

# %% [markdown]
# If the model cell was skipped, the same chain runs with the team the model would have picked. The orchestrator writes that call by hand, and triage-agent has no model, so its titles come back unclassified. This is a stand-in for the model's choice, not model output.

# %%
if result is None:
    result = await ask_triage_agent.ainvoke({"team": "web"})
    print("the model did not run here; the orchestrator called the tool itself:")
    print(result)

# %% [markdown]
# The recording closes here. Everything after this cell runs live.

# %%
llm_replay.stop()

# %% [markdown]
# ### 7b. Hop 3 runs live, here
# In a replay run the triage agent's answer is replayed, so the agent did not run hop 3 there. This cell runs hop 3 itself, as triage-agent: the same two requests as hop 2 (client credentials, then exchange), and then Trackr's `list_open_issues` with the hop 3 token. It is model-free, and Trackr writes its audit line here.

# %%
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

r3 = await hop("triage-agent", tokens["T2"], TRACKR_AUD, "issues:read")   # hop 3
assert r3.status_code == 200, r3.text
tokens["T3"] = r3.json()["access_token"]
hop_claims.append(jwt.decode(tokens["T3"], options={"verify_signature": False}))
async with httpx2.AsyncClient(headers={"Authorization": f"Bearer {tokens['T3']}"}) as http:
    async with Client(streamable_http_client(TRACKR, http_client=http)) as mcp:
        reply = await mcp.call_tool("list_open_issues", {"team": "web"})
assert not reply.is_error, reply.content[0].text
print("Trackr answered hop 3 with:", reply.content[0].text.replace("\n", " | "))

# %% [markdown]
# ### 8. Read the chain, hop by hop
# The orchestrator saw the token it sent to triage-agent (hop 2). Hop 3 is the token triage-agent sent to Trackr, made and decoded live in step 7b. The replayed artifact carries triage-agent's receipt for the same hop. Read `act`: the newest actor first, and the orchestrator last.

# %%
t2, t3 = hop_claims[0], hop_claims[1]
print("hop 2 token -> triage-agent:", {k: t2[k] for k in ["sub", "aud", "scope"]}, "| act:", chain(t2["act"]))
print("hop 3 token -> Trackr:      ", {k: t3[k] for k in ["sub", "aud", "scope"]}, "| act:", chain(t3["act"]))
print("hop 3 receipt (the replayed artifact):", result.splitlines()[-1])

# %% [markdown]
# ### 9. Refusals at each hop
# Three requests that must fail. Each one is a real exchange with the authorization server, made live after the recording.
# 1. The orchestrator asks for `issues:write`, which alice never granted.
# 2. triage-agent asks Trackr for `issues:write`, which the hop 2 token does not hold.
# 3. triage-agent uses alice's own token, which was issued to the orchestrator: it tries to skip hop 2.

# %%
refused = {
    "orchestrator asks for issues:write": await hop("ops-orchestrator", ALICE, TRIAGE_AUD, "triage:run issues:write"),
    "triage-agent asks Trackr for issues:write": await hop("triage-agent", tokens["T2"], TRACKR_AUD, "issues:read issues:write"),
    "triage-agent skips hop 2 with alice's token": await hop("triage-agent", ALICE, TRACKR_AUD, "issues:read"),
}
for what, r in refused.items():
    print(f"{what}: {r.status_code} {r.json()['error']}")

# %% [markdown]
# ### 10. Each hop wrote its own audit line
# The authorization server writes one line per exchange, sign-in and refusal. Trackr writes one line per call. Read the actor chain in each line. In a replay run the triage agent's answer is replayed, so the agent did not run hop 3 there. Step 7b runs hop 3 itself, live, so its exchange and Trackr's call are in these logs.

# %%
for path in [DATA / "as_audit.log", DATA / "trackr_audit.log"]:
    if not path.exists():
        print(path.name, "(no lines: this service did not run live)")
        continue
    for line in path.read_text().splitlines():
        rec = json.loads(line)
        print(path.stem, {k: rec[k] for k in rec if k in ("event", "caller", "sub", "act", "aud", "scope", "reason", "tool", "azp")})

# %% [markdown]
# ## At real scale
# - **One audience and one narrower scope per token.** RESEARCH.md §8 ("Audience & passthrough") says never forward the inbound token; exchange it for the next audience. Lesson 31 showed the passthrough attack this stops.
# - **The current actor decides access.** RFC 8693 §4.1: "The outermost `act` claim represents the current actor while nested `act` claims represent prior actors." A resource must consider only the top-level claims and the current actor. Prior actors are "informational only", so Trackr checks `sub`, `aud` and `scope`, and the nested actors go to the log.
# - **Logs must name the whole chain.** Each service writes `azp`, `sub` and `act`. Without the chain, the log says "triage-agent did it". Lesson 28 covers how these lines reach tracing.
# - **Depth and lifetimes are local policy.** RFC 8693 §4.1 sets no maximum chain length. The five-minute lifetimes here are a lab choice. A hop that needs longer should exchange again.

# %% [markdown]
# **Latency of one hop.** The cell below runs `hop()` 20 times live. Each run is two requests to the authorization server, and each one adds lines to the audit log. The median is the cost of one exchange.

# %%
import statistics
times = []
for _ in range(20):
    t0 = time.perf_counter()
    r = await hop("ops-orchestrator", ALICE, TRIAGE_AUD, "triage:run issues:read")
    times.append((time.perf_counter() - t0) * 1000)
    assert r.status_code == 200, r.text
med = statistics.median(times)
print(f"hop() over {len(times)} live runs: median {med:.1f} ms (two requests each)")
print(f"latency maths: N exchanges per chain x {med:.1f} ms; this chain has N = 2 (hops 2 and 3), so about {2 * med:.0f} ms of token work")

# %% [markdown]
# ## Decision guide
# | Question | If yes | If no |
# | --- | --- | --- |
# | Does the next service act for the user? | Exchange the token for that audience, adding yourself as actor. | Use your own client-credentials token (lesson 35). |
# | Does the next service need less than you hold? | Exchange with the narrower scope. | Exchange with the same scope; never a wider one. |
# | Does the incoming token's audience equal yours? | Continue: check the scope and exchange for the next hop. | Refuse: the token skipped a hop or is a passthrough. |

# %% [markdown]
# ## What just happened
# - Alice's token reached Trackr through two exchanges. Trackr's token names alice as `sub`, with the chain triage-agent > ops-orchestrator in `act`.
# - Each hop held a token issued to it, and each one narrowed the scope to what the next hop needed.
# - The hop 3 chain was also decoded live in step 7b, so the chain Trackr saw is checked in this run, not only in the replayed answer.
# - Three requests were refused: a wider scope at the orchestrator, a wider scope at triage-agent, and an attempt to skip a hop.
# - The model made 2 calls: one to pick the tool, one for the triage classification.

# %% [markdown]
# ## Common mistakes
# Sending the user's token straight to Trackr. Trackr checks the audience, and this token is for the orchestrator, so Trackr refuses it with 401.

# %% tags=["raises-exception"]
r = httpx.post(TRACKR, headers={"Authorization": f"Bearer {ALICE}", "Accept": "application/json, text/event-stream"},
               json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, timeout=10)
r.raise_for_status()

# %% [markdown]
# Fix: exchange alice's token for the audience of the next hop (step 6), and send that token. Trackr's audience is `http://127.0.0.1:9381/mcp`, and the raise above is `httpx.HTTPStatusError: 401 Unauthorized`.
#
# A second mistake is to let the exchange pass the wider scope on. The chain only narrows. If a hop needs more than it holds, the answer is a new grant for the user, not a wider exchange.

# %% [markdown]
# ## Try it
# triage-agent holds `issues:read` and nothing else, and the hop 2 token holds `triage:run` too. Ask for a Trackr token with the scope `triage:run`, using the hop 2 token and triage-agent's identity. Print the status and the error. In one sentence, say why the scope can only narrow at each hop.

# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below

# %% tags=["solution"]
r = await hop("triage-agent", tokens["T2"], TRACKR_AUD, "triage:run")
print("status:", r.status_code, "| error:", r.json()["error"])
print("Each hop holds only what the previous hop passed on, so a scope can shrink at each hop but never grow.")

# %% [markdown]
# Clean up: stop the triage agent and the two servers. The audit logs stay in `../data/38a`.

# %%
await agent.stop()
for p in procs:
    p.terminate()
for p in procs:
    p.wait(timeout=10)
print("triage agent and servers stopped | audit logs kept in ../data/38a")

# %% [markdown]
# ## Key terms
# - **Delegation chain** — the services a user's authority passes through, each exchanging the token it got for the next hop's token (lesson 38a).
# - **Subject token / actor token** — the token being exchanged (the user's, or the previous hop's) and the caller's own token that asks (lesson 35).
# - **`act` claim** — who is acting for `sub`. With more hops it nests: the newest actor first, the one before inside it (lesson 35, lesson 38a).
# - **Scope narrowing per hop** — each hop may keep or shrink the scope it received, never widen it (lesson 38a).
# - **Per-hop audit** — one audit line at every service, naming the caller and the chain (lesson 38a).

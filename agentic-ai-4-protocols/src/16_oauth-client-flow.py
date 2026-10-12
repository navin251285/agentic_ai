# %% [markdown]
# # 16 · Getting a token: the MCP OAuth client flow and step-up
# Level L3 · Part 3 · core · ~40 min · builds on 15

# %% [markdown]
# ## Goal
# By the end you run the client side of MCP OAuth against a local authorization server. The client finds the server through the protected-resource metadata, uses a client ID metadata document (no registration), and runs authorization code with PKCE S256 and a resource indicator. It checks the `iss` in the redirect and stores the token. When `close_issue` gets `403 insufficient_scope`, the client asks for more scope and retries. A real model counts the web issues with a read token, then closes issue 2.

# %% [markdown]
# ## The idea
# Lesson 15 made Trackr check tokens. Now the client gets one. The client does not know the server's login page. It starts from a `401` and follows the links in the metadata. It sends the server's own address as the `resource`, so the token is only good for Trackr. It proves it started the request with a PKCE code verifier. It checks the `iss` on the redirect, so a wrong server cannot swap codes in. When the token lacks a scope, the server answers `403` and names the scopes needed. The client then runs the flow again and asks for the union of the old and new scopes.
#
# Analogy: a hotel check-in. The front desk tells you where to sign (metadata). You prove you are the person who booked (PKCE). The key only opens this hotel (resource). When you ask for the gym too, you sign again and get one key that opens both.

# %% [markdown]
# ## Picture
# ```mermaid
# sequenceDiagram
#   participant C as Client (model host)
#   participant T as Trackr :8768
#   participant A as Auth server :9000
#   C->>T: POST /mcp, no token
#   T-->>C: 401 resource_metadata=...
#   C->>T: GET protected-resource metadata
#   C->>A: GET AS metadata, then /authorize (resource, PKCE S256, client_id = CIMD URL)
#   A-->>C: 302 to redirect_uri with code, state and iss
#   C->>A: POST /token (code_verifier, resource)
#   A-->>C: access token (aud = Trackr, scope = issues:read)
#   C->>T: close_issue with read token
#   T-->>C: 403 insufficient_scope, scope = issues:read issues:write
#   C->>A: /authorize again with the union of scopes
#   A-->>C: new token, then the retry closes issue 2
# ```

# %% [markdown]
# ## Step by step
#
# ### 1. Write the two servers
# The authorization server is new. It is built with Authlib for PKCE and with joserfc for the JWT. It runs as its own process, as it would on a real network. It skips the consent screen and keeps a copy of the client document locally, both labelled in the file.

# %%
%%writefile ../apps/16/auth_server.py
"""Dev authorization server for lesson 16 (Authlib for PKCE, joserfc for the JWT). Runs on 127.0.0.1:9000.
Real here: PRM-matching audience (resource indicator), PKCE S256 check, one-time codes, RFC 9207 iss in the redirect.
Labelled stand-ins: the CIMD document is read from a dict (no HTTPS fetch), the consent screen is skipped, the key is a dev secret."""
import secrets, time
from urllib.parse import parse_qs, urlencode
import uvicorn
from joserfc import jwt
from joserfc.jwk import OctKey
from authlib.oauth2.rfc7636.challenge import compare_s256_code_challenge
from starlette.applications import Starlette
from starlette.responses import JSONResponse, RedirectResponse
from starlette.routing import Route

ISSUER = "http://127.0.0.1:9000"
RESOURCE = "http://127.0.0.1:8768/mcp"                 # the audience this AS may issue for
import os
DEV_KEY = os.environ["DEV_SIGNING_KEY"]
SCOPES = ["issues:read", "issues:write"]
CLIENT_ID = "https://ops-desk.example/client.json"      # a CIMD: the client_id IS this https URL
CIMD = {CLIENT_ID: {"client_id": CLIENT_ID, "client_name": "Ops desk",
                    "redirect_uris": ["http://127.0.0.1:9999/callback"],
                    "grant_types": ["authorization_code"], "response_types": ["code"],
                    "token_endpoint_auth_method": "none"}}
CODES = {}                                              # code -> grant, popped on first use

def error(code, text, status=400):
    return JSONResponse({"error": code, "error_description": text}, status_code=status)

async def metadata(request):
    return JSONResponse({"issuer": ISSUER, "authorization_endpoint": f"{ISSUER}/authorize",
        "token_endpoint": f"{ISSUER}/token", "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"], "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"], "scopes_supported": SCOPES,
        "client_id_metadata_document_supported": True,        # CIMD instead of DCR (RFC 7591 is deprecated)
        "authorization_response_iss_parameter_supported": True})  # RFC 9207

async def authorize(request):
    q = request.query_params
    doc = CIMD.get(q.get("client_id", ""))
    if doc is None:
        return error("invalid_client", "unknown client_id", 400)
    if q.get("redirect_uri") not in doc["redirect_uris"]:
        return error("invalid_request", "redirect_uri is not registered for this client")
    if q.get("resource") != RESOURCE:
        return error("invalid_target", "resource must be the Trackr MCP URL")
    if q.get("code_challenge_method") != "S256" or not q.get("code_challenge"):
        return error("invalid_request", "PKCE with S256 is required")
    if not set(q.get("scope", "").split()) <= set(SCOPES):
        return error("invalid_scope", "unknown scope")
    code = secrets.token_urlsafe(24)
    CODES[code] = {"client_id": CLIENT_ID, "redirect_uri": q["redirect_uri"], "scope": q.get("scope", ""),
                   "challenge": q["code_challenge"], "expires": time.time() + 60}
    # The consent screen is skipped here (auto-approve). Real servers show one.
    return RedirectResponse(f"{q['redirect_uri']}?" + urlencode(
        {"code": code, "state": q.get("state", ""), "iss": ISSUER}), status_code=302)

async def token(request):
    form = {k: v[0] for k, v in parse_qs((await request.body()).decode()).items()}
    grant = CODES.pop(form.get("code", ""), None)          # single use
    if grant is None or time.time() > grant["expires"]:
        return error("invalid_grant", "code unknown, used or expired")
    if form.get("redirect_uri") != grant["redirect_uri"] or form.get("client_id") != grant["client_id"]:
        return error("invalid_grant", "redirect_uri or client_id does not match the code")
    if form.get("resource") != RESOURCE:
        return error("invalid_target", "resource must be the Trackr MCP URL")
    if not compare_s256_code_challenge(form.get("code_verifier", ""), grant["challenge"]):
        return error("invalid_grant", "PKCE verifier does not match the challenge")
    now = int(time.time())
    claims = {"iss": ISSUER, "aud": RESOURCE, "sub": "ops-user", "client_id": CLIENT_ID,
              "scope": grant["scope"], "iat": now, "exp": now + 600}
    access = jwt.encode({"alg": "HS256"}, claims, OctKey.import_key(DEV_KEY))   # joserfc returns a str
    return JSONResponse({"access_token": access, "token_type": "Bearer", "expires_in": 600,
                         "scope": grant["scope"]})

app = Starlette(routes=[Route("/.well-known/oauth-authorization-server", metadata),
                        Route("/authorize", authorize),
                        Route("/token", token, methods=["POST"])])

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=9000, log_level="warning")

# %% [markdown]
# The Trackr server is lesson 15's idea on port 8768. The gate in front of it answers a write tool called with a read token with `403`. The SDK's own check only answers `403` for the server-wide scope.

# %%
%%writefile ../apps/16/trackr_stepup.py
"""Trackr for lesson 16: the lesson 03 tools on 127.0.0.1:8768, with a write-scope gate that answers 403 insufficient_scope."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "03"))   # the lesson 03 tools
import jwt, uvicorn
import trackr_server as base
from mcp.server import MCPServer
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.types import ToolAnnotations

PORT = 8768
RESOURCE = f"http://127.0.0.1:{PORT}/mcp"
ISSUER = "http://127.0.0.1:9000"
import os
DEV_KEY = os.environ["DEV_SIGNING_KEY"]
WRITE_TOOLS = {"close_issue": "issues:write"}   # tool name -> scope it needs

class Verifier:
    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            c = jwt.decode(token, DEV_KEY, algorithms=["HS256"], audience=RESOURCE, issuer=ISSUER)
        except jwt.PyJWTError:
            return None
        return AccessToken(token=token, client_id=c["client_id"], scopes=c["scope"].split(),
                           expires_at=c["exp"], resource=c["aud"], subject=c["sub"])

mcp = MCPServer("Trackr", token_verifier=Verifier(), auth=AuthSettings(
    issuer_url=ISSUER, resource_server_url=RESOURCE, required_scopes=["issues:read"],
    validate_token_resource=True))

@mcp.tool(title="Count open issues", annotations=ToolAnnotations(readOnlyHint=True))
def count_open(team: base.Team) -> int:
    return base.count_open(team)

@mcp.tool(title="Close an issue", annotations=ToolAnnotations(destructiveHint=True))
def close_issue(issue_id: int) -> base.Issue:
    return base.close_issue(issue_id)

def gate(app):
    """ASGI wrapper. A write tool called with a valid token that lacks its scope gets 403 with the scopes needed."""
    async def wrapped(scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] != "/mcp":
            return await app(scope, receive, send)
        body, more = b"", True
        while more:                                  # read the body once, so we can look at it
            msg = await receive()
            body += msg.get("body", b"")
            more = msg.get("more_body", False)
        sent = False
        async def replay():                          # hand the same body to the MCP app
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()
        req = json.loads(body or b"{}") if body[:1] == b"{" else {}
        name = (req.get("params") or {}).get("name") if req.get("method") == "tools/call" else None
        need = WRITE_TOOLS.get(name)
        token = dict(scope["headers"]).get(b"authorization", b"").decode().removeprefix("Bearer ")
        tok = await Verifier().verify_token(token) if need else None
        if tok is not None and need not in tok.scopes:
            challenge = (f'Bearer error="insufficient_scope", error_description="{need} is needed", '
                         f'scope="issues:read {need}", '
                         f'resource_metadata="http://127.0.0.1:{PORT}/.well-known/oauth-protected-resource/mcp"')
            await send({"type": "http.response.start", "status": 403,
                        "headers": [(b"content-type", b"application/json"), (b"www-authenticate", challenge.encode())]})
            await send({"type": "http.response.body", "body": b'{"error": "insufficient_scope"}'})
            return
        await app(scope, replay, send)                # no token or a good token: the MCP app decides
    return wrapped

if __name__ == "__main__":
    uvicorn.run(gate(mcp.streamable_http_app(json_response=True)), host="127.0.0.1", port=PORT, log_level="warning")

# %% [markdown]
# ### 2. Start both servers and wait until they answer
# The notebook starts both processes. It polls the two metadata URLs, which need no token. It gives up after 20 seconds and stops both servers at the end.

# %%
import sys, subprocess, time, atexit, base64, hashlib, secrets
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs
import httpx, httpx2
sys.path.insert(0, "..")   # so llm_setup and llm_replay import
import llm_replay
import os, sys
sys.path.insert(0, "..")   # tut_env lives in the topic folder
from tut_env import env
for _name in ("DEV_SIGNING_KEY", "LAB_PROXY_CLIENT_SECRET", "LAB_NOTES_CLIENT_SECRET"):
    os.environ[_name] = env(_name, "")   # from .env (never in the lesson)
assert len(os.environ["DEV_SIGNING_KEY"]) >= 32, "put DEV_SIGNING_KEY (32+ characters) in .env: see .env.example"
assert Path("../apps/03/trackr_server.py").exists(), "run lesson 03 first: it writes the Trackr tools"
AS_URL, RS_URL = "http://127.0.0.1:9000", "http://127.0.0.1:8768"
RESOURCE = f"{RS_URL}/mcp"                                # Trackr's audience (its canonical URI)
CLIENT_ID = "https://ops-desk.example/client.json"        # a client ID metadata document (CIMD) URL
REDIRECT = "http://127.0.0.1:9999/callback"               # where the client wants the code sent
Path("../apps/16").mkdir(parents=True, exist_ok=True)
print("names:", RESOURCE, "| auth server:", AS_URL)

procs, logs = [], []   # the two server processes and their log files
for script in ["auth_server", "trackr_stepup"]:
    log = open(f"../apps/16/{script}.log", "w")
    logs.append(log)
    procs.append(subprocess.Popen([sys.executable, str(Path(f"../apps/16/{script}.py").resolve())],
                                  stdout=log, stderr=subprocess.STDOUT))
# %% [markdown]
# The notebook stops both servers with one function. It runs at the end, and again if this cell fails.

# %%
def stop_servers():
    for p in procs:
        if p.poll() is None:
            p.terminate(); p.wait(timeout=10)
    for log in logs:
        log.close()
print("stop_servers() is ready")
atexit.register(stop_servers)
print("launched:", [p.args[-1].split("/")[-1] for p in procs])

# %% [markdown]
# Now poll each server's metadata URL until it answers. If a server dies, the cell shows its log.

# %%
for url, p, name in [(f"{AS_URL}/.well-known/oauth-authorization-server", procs[0], "auth_server"),
                     (f"{RS_URL}/.well-known/oauth-protected-resource/mcp", procs[1], "trackr_stepup")]:
    deadline = time.monotonic() + 20
    while True:
        try:
            httpx.get(url, timeout=5); break
        except httpx.ConnectError:
            if p.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError(f"{name} did not start: read ../apps/16/{name}.log")
            time.sleep(0.2)
print("auth server and Trackr are up")

# %% [markdown]
# ### 3. Discovery: from a `401` to the metadata
# Two requests that need no token. The first is a call with no token. The `401` names the protected-resource metadata. That document names the authorization server. Then the client reads that server's metadata. The fields that matter: PKCE with `S256`, client ID metadata documents, and no registration endpoint, because dynamic client registration is deprecated.

# %%
HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json",
           "MCP-Protocol-Version": "2026-07-28"}
META = {"io.modelcontextprotocol/protocolVersion": "2026-07-28", "io.modelcontextprotocol/clientCapabilities": {}}

def post(method, params=None, token=None, name=None):
    """One POST to /mcp, the lesson 15 helper. The bearer token, if given, goes in Authorization."""
    headers = {**HEADERS, "Mcp-Method": method, **({"Mcp-Name": name} if name else {})}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": {**(params or {}), "_meta": META}}
    return httpx.post(RESOURCE, json=body, headers=headers, timeout=10)

r = post("tools/list")
print("no token:", r.status_code, "|", r.headers["www-authenticate"])
prm = httpx.get(f"{RS_URL}/.well-known/oauth-protected-resource/mcp").json()
meta = httpx.get(f"{AS_URL}/.well-known/oauth-authorization-server").json()
print("authorization_servers:", prm["authorization_servers"])
print("PKCE methods:", meta["code_challenge_methods_supported"],
      "| CIMD supported:", meta["client_id_metadata_document_supported"],
      "| registration_endpoint:", meta.get("registration_endpoint", "none (DCR not offered)"))

# %% [markdown]
# ### 4. The client ID is a URL: the metadata document (CIMD)
# In older flows a client registered with the server first and got an ID back (dynamic client registration). The 2026 spec prefers a **client ID metadata document**. The client ID is an `https` URL. The document at that URL says the name and the allowed redirect URIs. The server fetches it when it needs it. Here the server keeps a copy of the document, and it refuses any client ID it does not know.

# %%
cimd_doc = {"client_id": CLIENT_ID, "client_name": "Ops desk", "redirect_uris": [REDIRECT],
            "grant_types": ["authorization_code"], "response_types": ["code"],
            "token_endpoint_auth_method": "none"}
print("the document the server uses for", CLIENT_ID, ":", cimd_doc["redirect_uris"], cimd_doc["grant_types"])
r = httpx.get(f"{AS_URL}/authorize", params={"client_id": "https://evil.example/client.json", "redirect_uri": REDIRECT,
                                             "response_type": "code", "code_challenge": "x", "code_challenge_method": "S256",
                                             "resource": RESOURCE}, follow_redirects=False)
print("unknown client ID:", r.status_code, r.json()["error"])

# %% [markdown]
# ### 5. PKCE and the resource indicator
# PKCE stops a stolen code from being used. The client keeps a secret `code_verifier` and sends its S256 hash, the `code_challenge`, in the first request. The token request must send the verifier. The `resource` (RFC 8707) names the one server the token is for. The authorization server checks both. This cell builds the pair with Authlib and checks it against the plain SHA-256 formula.

# %%
from authlib.oauth2.rfc7636 import create_s256_code_challenge
verifier = secrets.token_urlsafe(48)
challenge = create_s256_code_challenge(verifier)
by_hand = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
print("verifier length:", len(verifier), "| challenge matches base64url(sha256):", challenge == by_hand)

def authorize_params(challenge, **changes):
    """The query the client sends to /authorize. Change one field to see the server refuse it."""
    p = {"response_type": "code", "client_id": CLIENT_ID, "redirect_uri": REDIRECT, "state": "s1",
         "code_challenge": challenge, "code_challenge_method": "S256", "resource": RESOURCE, "scope": "issues:read"}
    return {**p, **changes}

r = httpx.get(f"{AS_URL}/authorize", params=authorize_params(challenge, resource="http://evil.example/mcp"),
              follow_redirects=False)
print("resource for another server:", r.status_code, r.json()["error"])

# %% [markdown]
# ### 6. The client: `OAuthClientProvider` does the flow
# The SDK's `OAuthClientProvider` is an `httpx` auth object. It runs discovery, PKCE, the redirect, the token request and the storage for you. Two callbacks are yours. `redirect_handler` is the browser: here it sends the authorize request and keeps the `Location` header. `callback_handler` reads the code, the state and the `iss` from that redirect. `TokenStorage` keeps the tokens and the client info between calls.

# %%
from mcp import Client
from mcp.client.auth import OAuthClientProvider
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.auth import AuthorizationCodeResult, OAuthClientMetadata

redirects, locations, seen_iss = [], [], []   # every authorize URL, each redirect it got back, and each iss seen

class MemoryStorage:
    """Token storage for one process: the four methods the SDK needs."""
    def __init__(self):
        self.tokens, self.client = None, None
    async def get_tokens(self): return self.tokens
    async def set_tokens(self, tokens): self.tokens = tokens
    async def get_client_info(self): return self.client
    async def set_client_info(self, info): self.client = info

async def redirect_handler(url: str) -> None:
    """The 'browser': send the authorize request, do not follow the redirect, keep the Location."""
    redirects.append(url)
    async with httpx.AsyncClient() as c:
        locations.append((await c.get(url, follow_redirects=False)).headers["location"])

async def callback_handler() -> AuthorizationCodeResult:
    """The redirect back to the client: read code, state and iss."""
    q = parse_qs(urlparse(locations.pop(0)).query)
    seen_iss.append(q["iss"][0])
    return AuthorizationCodeResult(code=q["code"][0], state=q["state"][0], iss=q["iss"][0])

# %% [markdown]
# The provider takes the storage and the two callbacks. It needs the client's metadata and the CIMD URL.

# %%
storage = MemoryStorage()
provider = OAuthClientProvider(
    server_url=RESOURCE,
    client_metadata=OAuthClientMetadata(client_name="Ops desk", redirect_uris=[REDIRECT], response_types=["code"],
                                        token_endpoint_auth_method="none", scope="issues:read"),
    storage=storage, redirect_handler=redirect_handler, callback_handler=callback_handler,
    client_metadata_url=CLIENT_ID)
print("provider ready | the tokens live in storage, not in the provider")

# %% [markdown]
# The HTTP client carries the provider as its auth. Each call opens a session on it and closes the session at the end.

# %%
http = httpx2.AsyncClient(auth=provider)   # the HTTP client that carries the auth; closed at the end

async def call(name, arguments):
    """One MCP session per call. The session ends with the call; the token storage carries the login."""
    async with Client(streamable_http_client(RESOURCE, http_client=http)) as c:
        return await c.call_tool(name, arguments)

# %% [markdown]
# ### 7. First call: the flow runs once, then the token is reused
# The first tool call sends no token, gets `401`, and the provider runs the whole flow. Then the call goes through. The authorize request asked for `issues:read` and the `resource`. The `iss` in the redirect matched the authorization server. Later calls reuse the stored token, so no second redirect happens.

# %%
r = await call("count_open", {"team": "web"})
print("open web issues:", r.content[0].text, "| error:", r.is_error)
q = parse_qs(urlparse(redirects[0]).query)
print("authorize sent:", {k: q[k][0] for k in ["client_id", "code_challenge_method", "resource", "scope"]})
print("token scope:", storage.tokens.scope, "| redirects so far:", len(redirects))
print("iss in the redirect:", seen_iss[0], "| AS_URL:", AS_URL, "| same:", seen_iss[0] == AS_URL)
await call("count_open", {"team": "api"})
print("second call reused the token, redirects still:", len(redirects))

# %% [markdown]
# ### 8. A read token cannot close an issue: the `403` challenge
# The SDK does the step-up for you. First look at what the server sends. A raw POST with the read token asks to close issue 2. The server answers `403`. Its `WWW-Authenticate` header names the scopes needed for this one operation, so one challenge gives the full list. The issue stays open.

# %%
r = post("tools/call", {"name": "close_issue", "arguments": {"issue_id": 2}}, storage.tokens.access_token, "close_issue")
print("status:", r.status_code)
print("WWW-Authenticate:", r.headers["www-authenticate"])

# %% [markdown]
# The SDK's `required_scopes=['issues:read']` passed this token; the gate in front of it is what added the per-tool `403`.

# %% [markdown]
# ### 9. The model uses Trackr (`needs-llm`)
# The model needs two tools. Each one is a plain LangChain tool that calls the MCP session. The first question needs `count_open` with the read token: two model calls. The second question needs `close_issue`. Its first try gets `403`, the client steps up, and the retry closes issue 2: two more model calls.

# %%
from langchain_core.tools import tool
from langchain_core.messages import AIMessage, HumanMessage

@tool("count_open")
async def count_open_tool(team: str) -> str:
    """Count the open issues for one team (web, api, ...). Needs issues:read."""
    r = await call("count_open", {"team": team})
    return r.content[0].text

@tool("close_issue")
async def close_issue_tool(issue_id: int) -> str:
    """Close one issue by id. Needs issues:write; the client steps up if the token lacks it."""
    r = await call("close_issue", {"issue_id": issue_id})
    return r.content[0].text

tools = [count_open_tool, close_issue_tool]
by_name = {t.name: t for t in tools}
Q1 = HumanMessage("How many open issues does the web team have? Use a tool.")
Q2 = HumanMessage("Issue 2 is fixed. Close it with a tool.")
llm = None   # filled by the model cell; stays None if that cell is skipped
print("tools:", sorted(by_name))

# %% [markdown]
# The model cell asks the model which tool to use. `get_llm` starts the recording or the replay for this lesson.

# %% tags=["needs-llm"]
from llm_setup import get_llm
llm = get_llm("16_oauth-client-flow", max_calls=4)
first = await llm.bind_tools(tools).ainvoke([Q1])
print("model asks for:", [(c["name"], c["args"]) for c in first.tool_calls])

# %% [markdown]
# If the model cell was skipped, a scripted tool call stands in for the model's first reply. It is labelled. The host then runs each requested tool.

# %%
if llm is None:   # fallback: the model cell was skipped, so a scripted tool call stands in
    first = AIMessage(content="", tool_calls=[{"name": "count_open", "args": {"team": "web"}, "id": "scripted_1"}])
    print("SCRIPTED stand-in (no model): model asks for:", [(c["name"], c["args"]) for c in first.tool_calls])
results = [await by_name[c["name"]].ainvoke(c) for c in first.tool_calls]
for res in results:
    print("ToolMessage:", res.text[:80])

# %% [markdown]
# The model reads the tool result and writes its answer. This is its second call (`needs-llm`).

# %% tags=["needs-llm"]
final = await llm.bind_tools(tools).ainvoke([Q1, first, *results])
print("answer:", final.text)

# %% [markdown]
# If the model cell was skipped, the fallback prints what the tool returned, labelled as such.

# %%
if llm is None:   # fallback: no model, so no written answer
    print("answer (skipped: no model here). The tool said:", results[0].text[:40])

# %% [markdown]
# Now the close. The first tool call gets `403`, the SDK steps up on its own, and the retry closes issue 2. The model asks for `close_issue` with issue 2 (`needs-llm`).

# %% tags=["needs-llm"]
first2 = await llm.bind_tools(tools).ainvoke([Q2])
print("model asks for:", [(c["name"], c["args"]) for c in first2.tool_calls])

# %% [markdown]
# The scripted stand-in calls the same tool. The first try gets `403`, and the step-up happens here too.

# %%
if llm is None:   # fallback: the model cell was skipped, so a scripted call stands in
    first2 = AIMessage(content="", tool_calls=[{"name": "close_issue", "args": {"issue_id": 2}, "id": "scripted_2"}])
    print("SCRIPTED stand-in (no model): model asks for:", [(c["name"], c["args"]) for c in first2.tool_calls])
results2 = [await by_name[c["name"]].ainvoke(c) for c in first2.tool_calls]
print("ToolMessage:", " ".join(results2[0].text.split())[:90])

# %% [markdown]
# The model reads the result and writes its answer (`needs-llm`).

# %% tags=["needs-llm"]
final2 = await llm.bind_tools(tools).ainvoke([Q2, first2, *results2])
print("answer:", final2.text)

# %% [markdown]
# If the model cell was skipped, the fallback says what happened.

# %%
if llm is None:   # fallback: no model, so no written answer
    print("answer (skipped: no model here). Issue 2 was closed by the tool call above.")

# %% [markdown]
# ### 10. What the step-up looked like
# The client sent the authorize request a second time. Its `scope` is the union of the first scope and the one the server asked for. The new token holds both scopes, and the stored token now holds both.

# %%
second = parse_qs(urlparse(redirects[-1]).query)
print("authorize requests:", len(redirects), "| second scope:", second["scope"][0])
print("stored token scope:", storage.tokens.scope)

# %% [markdown]
# ## At work
# - Production MCP servers trust one organisation-wide authorization server. Clients identify themselves with a client ID metadata document, or with a credential the admin issued, and dynamic registration is being retired. Keycloak and the org-wide AS come in lesson 34 (professional).
# - The step-up above is the right pattern: ask for write only when a tool needs it, and keep the read token small. Least-privilege scopes and token passthrough come in lesson 31, the confused deputy.
# - Mix-up attack: a client that talks to two authorization servers can send one server's code to the other. The `iss` check is the defence (RFC 9207). This token lasts 600 seconds, so a leak stops working after ten minutes.
# - A gateway checks the token and the scope for each tool before the request reaches the server, so one policy covers every server. → lesson 40 (professional).

# %% [markdown]
# ## What just happened
# - The client began with a `401`, followed the metadata to the authorization server, and never had a client ID before the flow. The ID was a URL, and the server knew the document behind it.
# - The authorize request carried `S256`, the `resource` and the scope. The redirect carried the code, the state and an `iss` that matched the server. The token request carried the verifier.
# - The read token passed the server-wide check, and `close_issue` answered `403` with the scopes it needed.
# - The client ran the flow a second time with the union of the scopes. The model's retried tool call then closed issue 2 with the new token.

# %% [markdown]
# ## Common mistakes
# Sending a token request with the wrong `code_verifier`. The server refuses the code, which proves the request came from the same client that started the flow. Here the verifier is made up, so the server answers `400 invalid_grant`:

# %% tags=["raises-exception"]
fresh_challenge = create_s256_code_challenge(secrets.token_urlsafe(48))
r = httpx.get(f"{AS_URL}/authorize", params=authorize_params(fresh_challenge), follow_redirects=False)
code = parse_qs(urlparse(r.headers["location"]).query)["code"][0]
httpx.post(f"{AS_URL}/token", data={"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT,
           "client_id": CLIENT_ID, "resource": RESOURCE, "code_verifier": "not-the-verifier"}).raise_for_status()   # raises httpx.HTTPStatusError: 400 Bad Request

# %% [markdown]
# Fix: send the verifier that matches the challenge. The SDK keeps it for you. Your own code must keep it the same way.
#
# A second mistake is asking for a token for the bare host, not the MCP path. The `resource` must match the server's canonical URI, so the server refuses the request with `invalid_target`:

# %% tags=["raises-exception"]
httpx.get(f"{AS_URL}/authorize", params=authorize_params(challenge, resource=RS_URL),
          follow_redirects=False).raise_for_status()   # raises httpx.HTTPStatusError: 400 Bad Request

# %% [markdown]
# Fix: set `resource` to `RESOURCE`, path included. The same request with the exact resource passes the check:

# %%
r = httpx.get(f"{AS_URL}/authorize", params=authorize_params(challenge), follow_redirects=False)
print("exact resource:", r.status_code, "| redirected to:", r.headers["location"].split("?")[0])

# %% [markdown]
# ## Try it
# Send the authorize request with `code_challenge_method` set to `plain`, which the server does not accept. Print the status and the error. Then send a request with a `resource` that has no `/mcp`. Print the status and the error. Use `authorize_params` and `httpx.get`. No model is needed.

# %%
# Setup so this cell runs on its own: a fresh S256 challenge, built as in step 5.
from authlib.oauth2.rfc7636 import create_s256_code_challenge
challenge = create_s256_code_challenge(secrets.token_urlsafe(48))
print("challenge ready:", len(challenge), "characters")
# your code here
# Start from authorize_params(challenge, code_challenge_method="plain") and authorize_params(challenge, resource=RS_URL).

# %% [markdown]
# Clean up: close the HTTP client, stop the two servers, and tell the recorder the lesson is done. This cell runs last.

# %%
await http.aclose()
stop_servers()
llm_replay.stop()
print("client closed, servers stopped | lesson 16 done")

# %% [markdown]
# ## Key terms
# - **authorization code flow** — the client gets a one-time code by redirect, then trades it for a token.
# - **PKCE (S256)** — the client sends a hash of a secret verifier first and the verifier later. A stolen code is useless alone.
# - **client ID metadata document (CIMD)** — an https client ID whose document holds the client's name and redirect URIs. It replaces dynamic registration.
# - **resource indicator** — the `resource` parameter (RFC 8707): the one server a token is for.
# - **`iss` in the redirect (RFC 9207)** — the server names itself in the redirect, so the client can catch a mix-up.
# - **scope step-up** — a second authorization request after `403 insufficient_scope`, asking for the union of scopes.
# - **TokenStorage** — where the SDK keeps tokens and client info between calls.

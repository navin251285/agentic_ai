# %% [markdown]
# # 34 · One authorization server for the organisation: Keycloak
# Level L6 · Part 7 · professional · ~40 min · builds on 16, 33

# %% [markdown]
# ## Goal
# By the end you run Keycloak 26.8 in Docker as the organisation's authorization server for two MCP servers, Trackr and the runbooks server. You request one token per resource with a resource indicator, a client ID metadata document and PKCE. A model answers a question through Trackr with that token (2 model calls), and the runbooks server refuses the same token. You store the tokens encrypted on the client and rotate the refresh token. Without Docker, a stand-in authorization server runs the same steps in this notebook.

# %% [markdown]
# ## Why it matters
# Lessons 15 and 16 gave Trackr its own token check and the client its own login. Add a second MCP server and each one runs its own login, keys and user list. A user signs in twice, a leaver is removed in two places, and a token for Trackr works at the runbooks server unless that server checks the audience.
#
# With one organisation authorization server, the user signs in once, every server checks the same published keys, and revocation happens in one realm. A resource indicator (RFC 8707, the `resource` parameter) gives one login a separate token per server.
#
# You don't need this for one server on your laptop. It pays once two or more servers share users.

# %% [markdown]
# ## The idea
# An authorization server is the one place that signs in users and issues tokens. Each resource server (Trackr, runbooks) only checks the tokens it receives: signature from the server's published keys, issuer, and audience. The client asks for a token per resource with `resource=`, so the audience is set by the request, not by hope.
#
# Keycloak is an open-source server that does this. In this lesson it runs in one container with a realm file: clients, scopes, audiences, token lifetimes and refresh rotation are all in the file, so the setup is reviewable like code.
#
# Analogy: a building's badge office. You show your ID once and get a badge per floor. Each floor's door checks the badge's floor number and the badge's signature, not your ID again.

# %% [markdown]
# ## Picture
# ```mermaid
# sequenceDiagram
#   participant U as User (browser)
#   participant C as Ops desk client
#   participant K as Keycloak :8340
#   participant T as Trackr :8341
#   participant R as Runbooks :8342
#   C->>K: /authorize (client_id = CIMD URL, resource = Trackr, PKCE S256)
#   K->>C: fetches the metadata document, asks the user to sign in once
#   K-->>C: code (iss = Keycloak)
#   C->>K: /token (code, verifier, resource = Trackr)
#   K-->>C: access token, aud = Trackr only
#   C->>T: count_open with the token
#   C->>R: same token
#   R-->>C: 401 invalid_token (aud is not runbooks)
# ```

# %% [markdown]
# ## Already know this?
# This is the first lesson of Part 7, which covers agent identity, enterprise login, signed cards and tenants. Answer these four. If all four are easy, skip to lesson 40.
# 1. An agent has no user to sign in as. Which grant gives it its own identity? (lesson 35)
# 2. How can a user sign in once to the IdP and reach several servers without a consent screen for each? (lesson 36)
# 3. What does a signed Agent Card prove, and which algorithms must a verifier accept? (lesson 37)
# 4. Two teams share one Trackr. Besides the token signature, what must the server check so team A cannot read team B? (lesson 38)

# %% [markdown]
# ## Step by step
#
# ### 1. Set up the notebook
# The ports this lesson uses: Keycloak 8340, Trackr 8341, runbooks 8342, the metadata document 8343, the stand-in authorization server 8344. The model recording is opened first, closed last. Settings come from `.env` through `tut_env`.

# %%
import sys, os, json, time, subprocess, base64, hashlib, secrets, html, re, atexit
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs, urljoin
import httpx, httpx2, jwt
sys.path.insert(0, "..")
import tut_env
from tut_env import env
import llm_replay
tut_env.load()
REALM = "ops-desk"
DATA = Path("../data/34").resolve(); DATA.mkdir(parents=True, exist_ok=True)
KC_ISSUER = f"http://127.0.0.1:8340/realms/{REALM}"
DEV_ISSUER = "http://127.0.0.1:8344"
RS_TRACKR, RS_RUNBOOKS = "http://127.0.0.1:8341/mcp", "http://127.0.0.1:8342/mcp"
REDIRECT = "http://127.0.0.1:8343/callback"
KC_UP = False            # the Docker cell sets this to True when Keycloak answers
RECORD = {}              # what the Keycloak-only checks printed, saved for lessons read without Docker
procs, logs = [], []     # server processes and their log files
def pkce():
    v = secrets.token_urlsafe(48)
    return v, base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b"=").decode()
print("ports 8340-8344 | the model recording opens only around the two model calls (step 14)")

# %% [markdown]
# ### 2. Why one server: the count without it
# Before any token, count what a user and an admin do with two MCP servers and no shared authorization server. The same arithmetic with one server shows the saving.

# %%
servers = ["trackr", "runbooks"]
print("without a shared AS: sign-ins per user =", len(servers), "| places to revoke a leaver =", len(servers))
print("with one AS:         sign-ins per user = 1 | places to revoke a leaver = 1 (the realm)")
secret = secrets.token_bytes(32)
trackr_only = jwt.encode({"aud": RS_TRACKR, "sub": "alice", "scope": "issues:read"}, secret, algorithm="HS256")
print("a verifier that checks only the signature accepts a Trackr token for:",
      jwt.decode(trackr_only, secret, algorithms=["HS256"], options={"verify_aud": False})["aud"])

# %% [markdown]
# ### 3. Start Keycloak (Docker)
# The cell starts the Keycloak container from `infra/34/` and waits until its discovery document answers. Then it sets the demo user's password from `.env` through the admin API. Without Docker, this cell is skipped and the stand-in authorization server starts in step 5.

# %% tags=["needs-docker"]
COMPOSE = ["docker", "compose", "-p", "tut-agentic-ai-4-protocols-34", "-f", str(Path("../infra/34/docker-compose.yml").resolve())]
subprocess.run([*COMPOSE, "up", "-d"], check=True, capture_output=True)
deadline = time.monotonic() + 180
while True:
    try:
        if httpx.get(f"{KC_ISSUER}/.well-known/openid-configuration", timeout=3).status_code == 200:
            break
    except httpx.HTTPError:
        pass
    if time.monotonic() > deadline:
        raise RuntimeError("Keycloak did not start: docker logs tut-agentic-ai-4-protocols-34-keycloak")
    time.sleep(2)

# %% [markdown]
# Next the admin API sets the demo user's password from `.env`, so no password sits in the realm file.

# %% tags=["needs-docker"]
admin_token = httpx.post("http://127.0.0.1:8340/realms/master/protocol/openid-connect/token", data={
    "grant_type": "password", "client_id": "admin-cli",
    "username": env("KEYCLOAK_ADMIN"), "password": env("KEYCLOAK_ADMIN_PASSWORD")}).json()["access_token"]
ADMIN = f"http://127.0.0.1:8340/admin/realms/{REALM}"
ADMIN_H = {"Authorization": f"Bearer {admin_token}"}
alice_id = httpx.get(f"{ADMIN}/users?username=alice", headers=ADMIN_H).json()[0]["id"]
httpx.put(f"{ADMIN}/users/{alice_id}/reset-password", headers=ADMIN_H,
          json={"type": "password", "value": env("TRACKR_DEMO_PASSWORD"), "temporary": False}).raise_for_status()
KC_UP = True
print("Keycloak 26.8 is up | realm:", REALM, "| demo user password set from .env")

# %% [markdown]
# The realm check lists the two resource servers and the client policy the realm file created. It runs only with Docker.

# %% tags=["needs-docker"]
clients = httpx.get(f"{ADMIN}/clients", headers=ADMIN_H).json()
RECORD["realm"] = [f"client {c['clientId']} | resource_url {c['attributes']['resource_url']}"
                   for c in clients if c["clientId"].endswith("-mcp")]
RECORD["realm"] += [f"client policy {p['name']} | enabled {p['enabled']}"
                    for p in httpx.get(f"{ADMIN}/client-policies/policies", headers=ADMIN_H).json()["policies"]]
for line in RECORD["realm"]:
    print(line)

# %% [markdown]
# The realm file is the reviewed source of this setup. It holds no passwords. Its key settings are the resource servers as clients with a `resource_url`, the scopes, the refresh rules and the client-ID-document policy. A scope says what a token may do; the audience says where it may be used.

# %%
realm = json.loads((Path("../infra/34/realm-ops-desk.json")).read_text())
print("token lifetime (s):", realm["accessTokenLifespan"], "| revoke refresh token on use:", realm["revokeRefreshToken"],
      "| reuse allowed:", realm["refreshTokenMaxReuse"])
print("resource servers:", [c["attributes"]["resource_url"] for c in realm["clients"]])
print("scope catalogue:", [s["name"] for s in realm["clientScopes"]])

# %% [markdown]
# ### 4. Write the two resource servers
# Both servers verify tokens against the same published keys (JWKS). Each one accepts only tokens whose audience is its own URI. The verifier lives in one shared file.

# %%
%%writefile ../apps/34/org_common.py
"""Shared by the two resource servers: check a token against the organisation's authorization server."""
import jwt
from mcp.server.auth.provider import AccessToken

class OrgVerifier:
    """Signature from the AS's published keys (JWKS), the issuer, and the audience = this server's own URI."""
    def __init__(self, resource: str, issuer: str, jwks_url: str):
        self.resource, self.issuer = resource, issuer
        self.keys = jwt.PyJWKClient(jwks_url)

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            key = self.keys.get_signing_key_from_jwt(token).key
            c = jwt.decode(token, key, algorithms=["RS256"], audience=self.resource, issuer=self.issuer)
        except jwt.PyJWTError:
            return None          # wrong key, issuer, audience or expired: no access
        return AccessToken(token=token, client_id=c.get("azp", ""), scopes=c.get("scope", "").split(),
                           expires_at=c["exp"], resource=self.resource, subject=c.get("sub"))

# %% [markdown]
# Trackr reuses the lesson 03 tools. It accepts only tokens for its own URI, and its one tool needs `issues:read`.

# %%
%%writefile ../apps/34/trackr_org.py
"""Trackr for lesson 34: the lesson 03 tools behind the organisation's authorization server, on 127.0.0.1:8341."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "03"))   # the lesson 03 tools and data
import trackr_server as base
from org_common import OrgVerifier
from mcp.server import MCPServer
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

PORT = 8341
RESOURCE = f"http://127.0.0.1:{PORT}/mcp"      # this server's audience: a token must name it
ISSUER, JWKS_URL = sys.argv[1], sys.argv[2]    # the authorization server and its keys, from the notebook
mcp = MCPServer("Trackr", token_verifier=OrgVerifier(RESOURCE, ISSUER, JWKS_URL), auth=AuthSettings(
    issuer_url=ISSUER, resource_server_url=RESOURCE,
    required_scopes=["issues:read"], validate_token_resource=True))

def require(scope: str) -> None:
    token = get_access_token()
    if token is None or scope not in token.scopes:
        raise ToolError(f"insufficient_scope: this tool needs {scope}")

@mcp.tool(title="Count open issues", annotations=ToolAnnotations(readOnlyHint=True))
def count_open(team: base.Team) -> int:
    require("issues:read")
    return base.count_open(team)

if __name__ == "__main__":
    mcp.run("streamable-http", host="127.0.0.1", port=PORT, json_response=True)

# %% [markdown]
# The runbooks server is a second resource with its own audience and its own scope, `runbooks:read`.

# %%
%%writefile ../apps/34/runbooks_org.py
"""Runbooks server for lesson 34: one tool, its own audience (127.0.0.1:8342), scope runbooks:read."""
import sys
from org_common import OrgVerifier
from mcp.server import MCPServer
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

PORT = 8342
RESOURCE = f"http://127.0.0.1:{PORT}/mcp"
RUNBOOKS = {"login-outage": "Check the token issuer, then restart the sign-in pods one at a time.",
            "cert-expiry": "Renew the TLS certificate from the internal CA, then reload the proxy."}
ISSUER, JWKS_URL = sys.argv[1], sys.argv[2]    # the authorization server and its keys, from the notebook
mcp = MCPServer("Runbooks", token_verifier=OrgVerifier(RESOURCE, ISSUER, JWKS_URL), auth=AuthSettings(
    issuer_url=ISSUER, resource_server_url=RESOURCE,
    required_scopes=["runbooks:read"], validate_token_resource=True))

@mcp.tool(title="Read a runbook", annotations=ToolAnnotations(readOnlyHint=True))
def read_runbook(name: str) -> str:
    if name not in RUNBOOKS:
        raise ToolError(f"no runbook named {name}; try one of {sorted(RUNBOOKS)}")
    return RUNBOOKS[name]

if __name__ == "__main__":
    mcp.run("streamable-http", host="127.0.0.1", port=PORT, json_response=True)

# %% [markdown]
# ### 5. The stand-in authorization server (only when Docker is off)
# This file runs in the notebook only when Keycloak is not up. It has the same endpoints and the same checks: the client ID is a URL it fetches, PKCE, the resource indicator, one-time codes, and refresh-token rotation. It skips the login page and the consent screen. Read it as a checklist of what Keycloak does for you.

# %%
%%writefile ../apps/34/dev_as.py
"""Stand-in for Keycloak when Docker is off (lesson 34), on 127.0.0.1:8344. Real here: client ID URL fetch (http, lab
only), PKCE S256, the resource indicator (aud = one resource), one-time codes, refresh rotation (reuse ends the session).
Labelled stand-ins: login and consent are skipped (auto-approve); the signing key is made at start, never kept."""
import secrets, time
from urllib.parse import parse_qs, urlencode
import httpx, uvicorn
from joserfc import jwt
from joserfc.jwk import RSAKey
from authlib.oauth2.rfc7636.challenge import compare_s256_code_challenge
from starlette.applications import Starlette
from starlette.responses import JSONResponse, RedirectResponse
from starlette.routing import Route
PORT = 8344
ISSUER = f"http://127.0.0.1:{PORT}"
RESOURCES = {"http://127.0.0.1:8341/mcp", "http://127.0.0.1:8342/mcp"}
SCOPES = {"openid", "issues:read", "issues:write", "runbooks:read"}
KEY = RSAKey.generate_key(2048, {"kid": "dev-1", "alg": "RS256", "use": "sig"})
CODES, REFRESH = {}, {}

def err(code, text):
    return JSONResponse({"error": code, "error_description": text}, status_code=400)
async def metadata(request):
    return JSONResponse({"issuer": ISSUER, "authorization_endpoint": f"{ISSUER}/authorize",
        "token_endpoint": f"{ISSUER}/token", "jwks_uri": f"{ISSUER}/jwks",
        "code_challenge_methods_supported": ["S256"], "client_id_metadata_document_supported": True,
        "authorization_response_iss_parameter_supported": True})
async def jwks(request):
    return JSONResponse({"keys": [KEY.as_dict(private=False)]})
async def authorize(request):
    q = dict(request.query_params)
    async with httpx.AsyncClient() as c:             # the client ID is a URL: fetch its metadata document
        try:
            doc = (await c.get(q.get("client_id", ""), timeout=5)).json()
        except (httpx.HTTPError, ValueError):
            doc = {}
    if doc.get("client_id") != q.get("client_id"):
        return err("invalid_client", "the client ID document was not found or does not match")
    if q.get("redirect_uri") not in doc.get("redirect_uris", []):
        return err("invalid_request", "redirect_uri is not in the client's document")
    if q.get("resource") not in RESOURCES:
        return err("invalid_target", "unknown resource")
    if q.get("code_challenge_method") != "S256" or not q.get("code_challenge"):
        return err("invalid_request", "PKCE with S256 is required")
    if not set(q.get("scope", "").split()) <= SCOPES:
        return err("invalid_scope", "unknown scope")
    code = secrets.token_urlsafe(24)
    CODES[code] = {**q, "expires": time.time() + 60}
    return RedirectResponse(f"{q['redirect_uri']}?" + urlencode({"code": code, "state": q.get("state", ""), "iss": ISSUER}), 302)
def tokens(client_id, resource, scope):
    now = int(time.time())
    claims = {"iss": ISSUER, "aud": resource, "sub": "alice", "azp": client_id, "scope": scope, "iat": now, "exp": now + 300}
    refresh = secrets.token_urlsafe(32)
    REFRESH[refresh] = {"client_id": client_id, "resource": resource, "scope": scope, "used": False}
    return JSONResponse({"access_token": jwt.encode({"alg": "RS256", "kid": "dev-1"}, claims, KEY), "token_type": "Bearer",
                         "expires_in": 300, "refresh_token": refresh, "refresh_expires_in": 1800, "scope": scope})
async def token(request):
    f = {k: v[0] for k, v in parse_qs((await request.body()).decode()).items()}
    if f.get("grant_type") == "refresh_token":
        g = REFRESH.get(f.get("refresh_token", ""))
        if g is None or g["client_id"] != f.get("client_id"):
            return err("invalid_grant", "refresh token unknown or not issued to this client")
        if g["used"]:                                # reuse is treated as theft: end every session of this client
            for other in REFRESH.values():
                if other["client_id"] == g["client_id"]:
                    other["used"] = True
            return err("invalid_grant", "refresh token reuse detected: the session is ended")
        g["used"] = True                             # rotation: the old refresh token is spent here
        return tokens(g["client_id"], g["resource"], g["scope"])
    g = CODES.pop(f.get("code", ""), None)           # one-time code
    if g is None or time.time() > g["expires"]:
        return err("invalid_grant", "code unknown, used or expired")
    if (f.get("client_id"), f.get("redirect_uri"), f.get("resource")) != (g["client_id"], g["redirect_uri"], g["resource"]):
        return err("invalid_target", "client_id, redirect_uri or resource does not match the code")
    if not compare_s256_code_challenge(f.get("code_verifier", ""), g["code_challenge"]):
        return err("invalid_grant", "PKCE verifier does not match the challenge")
    return tokens(g["client_id"], g["resource"], g["scope"])
app = Starlette(routes=[Route("/.well-known/oauth-authorization-server", metadata), Route("/jwks", jwks),
                        Route("/authorize", authorize), Route("/token", token, methods=["POST"])])

if __name__ == "__main__": uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
# %% [markdown]
# ### 6. Publish the client ID metadata document
# The client's ID is a URL: `http://<host>:8343/ops-desk.json`. Keycloak runs in a container, so it reaches the notebook's document server through `host.docker.internal`. Without Docker the stand-in fetches it from `127.0.0.1`. The document declares the redirect URI, the grant types (refresh tokens included, or no refresh token is issued) and the scopes. The lab serves it over http only because there is no TLS here. Production uses https.

# %%
CIMD_HOST = "host.docker.internal" if KC_UP else "127.0.0.1"
CLIENT_ID = f"http://{CIMD_HOST}:8343/ops-desk.json"
doc = {"client_id": CLIENT_ID, "client_name": "Ops desk", "redirect_uris": [REDIRECT],
       "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"],
       "token_endpoint_auth_method": "none", "scope": "openid issues:read issues:write runbooks:read"}
(DATA / "cimd").mkdir(exist_ok=True)
(DATA / "cimd" / "ops-desk.json").write_text(json.dumps(doc, indent=2))
print("client ID:", CLIENT_ID)
print("the document declares:", doc["grant_types"], "| redirect:", doc["redirect_uris"])

# %% [markdown]
# ### 7. Start the servers and wait until they answer
# The notebook starts the document server, the two resource servers and, only without Docker, the stand-in authorization server. Each one is polled until it answers. Each resource server gets its issuer and key URL as command-line arguments. The processes stop at the end, also if a cell fails.

# %%
ISSUER = KC_ISSUER if KC_UP else DEV_ISSUER
JWKS_URL = f"{KC_ISSUER}/protocol/openid-connect/certs" if KC_UP else f"{DEV_ISSUER}/jwks"
AS_META_URL = f"{KC_ISSUER}/.well-known/openid-configuration" if KC_UP else f"{DEV_ISSUER}/.well-known/oauth-authorization-server"
print("issuer:", ISSUER, "| keys:", JWKS_URL.split("://")[1])
# %% [markdown]
# The processes start in this cell. Each resource server gets its issuer and key URL as command-line arguments.
# Lab only: the document server binds to `0.0.0.0` so the Keycloak container can reach it through `host.docker.internal`. It serves only `data/34/cimd`, nothing else. Production serves the document over https from a real host.

# %%
PROC = {}                # name -> process
def start(name, script_args):
    f = open(DATA / f"{name}.log", "w"); logs.append(f)
    PROC[name] = subprocess.Popen([sys.executable, *script_args], stdout=f, stderr=subprocess.STDOUT)
    procs.append(PROC[name])
start("cimd", ["-m", "http.server", "8343", "--bind", "0.0.0.0", "--directory", str(DATA / "cimd")])
start("trackr", [str(Path("../apps/34/trackr_org.py").resolve()), ISSUER, JWKS_URL])
start("runbooks", [str(Path("../apps/34/runbooks_org.py").resolve()), ISSUER, JWKS_URL])
if not KC_UP:
    start("dev_as", [str(Path("../apps/34/dev_as.py").resolve())])
# %% [markdown]
# Poll each server until it answers. A server that exits early shows its log.

# %%
def stop_servers():
    for p in procs:
        if p.poll() is None:
            p.terminate(); p.wait(timeout=10)
    for f in logs:
        f.close()
atexit.register(stop_servers)
checks = {"trackr": f"{RS_TRACKR.replace('/mcp', '')}/.well-known/oauth-protected-resource/mcp",
          "runbooks": f"{RS_RUNBOOKS.replace('/mcp', '')}/.well-known/oauth-protected-resource/mcp",
          "dev_as" if not KC_UP else "keycloak": AS_META_URL}
for name, url in checks.items():
    deadline = time.monotonic() + 60
    while True:
        try:
            httpx.get(url, timeout=3); break
        except httpx.HTTPError:
            p = PROC.get(name)
            if (p is not None and p.poll() is not None) or time.monotonic() > deadline:
                raise RuntimeError(f"{name} did not start: read ../data/34/{name}.log")
            time.sleep(0.3)
# Port 8343 must serve this run's document, not an old one left by another process.
served = httpx.get("http://127.0.0.1:8343/ops-desk.json?self-check", timeout=5).json()
if served.get("client_id") != CLIENT_ID or "refresh_token" not in served["grant_types"]:
    raise RuntimeError("port 8343 serves another document: stop the process that holds it, then rerun")
print("up | mode:", "Keycloak 26.8 in Docker" if KC_UP else "stand-in authorization server (Docker off)")

# %% [markdown]
# ### 8. Discovery: from a `401` to the authorization server
# A call with no token gets `401`, and the response names the protected-resource metadata. That document names the authorization server. The server's metadata lists the endpoints and the features the client needs: PKCE with S256 and client ID metadata documents.

# %%
HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json",
           "MCP-Protocol-Version": "2026-07-28"}
META = {"io.modelcontextprotocol/protocolVersion": "2026-07-28", "io.modelcontextprotocol/clientCapabilities": {}}
def mcp_post(url, method, params=None, token=None):
    """One JSON-RPC POST to an MCP server, with the bearer token if given."""
    headers = {**HEADERS, "Mcp-Method": method, **({"Authorization": f"Bearer {token}"} if token else {})}
    if params and "name" in params:
        headers["Mcp-Name"] = params["name"]
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": {**(params or {}), "_meta": META}}
    return httpx.post(url, json=body, headers=headers, timeout=10)

r = mcp_post(RS_TRACKR, "tools/list")
print("no token:", r.status_code, "|", r.headers["www-authenticate"][:110])
prm = httpx.get(RS_TRACKR.replace("/mcp", "/.well-known/oauth-protected-resource/mcp")).json()
AS_META = httpx.get(AS_META_URL).json()
print("authorization_servers:", prm["authorization_servers"])
print("PKCE:", AS_META["code_challenge_methods_supported"], "| CIMD:", AS_META["client_id_metadata_document_supported"],
      "| endpoints:", AS_META["authorization_endpoint"].split("/")[-1], AS_META["token_endpoint"].split("/")[-1])

# %% [markdown]
# Keycloak still advertises `plain` next to `S256` in its metadata (the stand-in prints only `S256`). With `plain`, the challenge is the verifier itself, so anyone who sees the authorize request can redeem the code. A production realm must force S256.
#
# A client ID that the server does not know gets refused. The document is the only way in.

# %%
q = {"client_id": "https://evil.example/client.json", "redirect_uri": REDIRECT, "response_type": "code",
     "scope": "openid", "code_challenge": pkce()[1], "code_challenge_method": "S256", "resource": RS_TRACKR}
r = httpx.get(f"{AS_META['authorization_endpoint']}?{urlencode(q)}", follow_redirects=False)
print("unknown client ID:", r.status_code, "| redirect to the client:", "yes" if "location" in r.headers else "no")

# %% [markdown]
# ### 9. Sign in like a browser, then get one token per resource
# The client sends the user to the authorization endpoint with the resource, PKCE and the document's ID. Our browser helper logs in as the demo user, accepts consent, and returns the redirect with the code. The redirect's `iss` must be the server that started the flow. The token request repeats the resource. A second resource reuses the same sign-in, and only the consent for the new scope is new.

# %%
jar = {}                       # the browser's cookies (Keycloak marks its login cookies Secure; we keep them ourselves)
AS_ORIGIN = "http://127.0.0.1:8340" if KC_UP else DEV_ISSUER
def jar_request(method, url, **kw):
    cookies = "; ".join(f"{k}={v}" for k, v in jar.items())
    r = httpx.request(method, url, headers={"Cookie": cookies} if cookies else {}, follow_redirects=False, **kw)
    jar.update(dict(r.cookies.items()))
    return r

def sign_in(url):
    """Act as the browser: log in as alice, accept consent, follow redirects, return the redirect that carries the code."""
    r = jar_request("GET", url)
    for _ in range(5):
        loc = r.headers.get("location", "")
        if r.status_code == 302 and "code=" in loc:
            return loc
        if r.status_code == 302:
            r = jar_request("GET", loc); continue
        if r.status_code != 200:
            raise RuntimeError(f"authorize failed: {r.status_code} {r.text[:120]}")
        action = urljoin(AS_ORIGIN, html.unescape(re.search(r'<form[^>]*action="([^"]+)"', r.text).group(1)))
        if 'name="password"' in r.text:                                  # the login page
            data = {"username": "alice", "password": env("TRACKR_DEMO_PASSWORD"), "credentialId": ""}
        else:                                                            # the consent page
            data = {"code": re.search(r'name="code" value="([^"]+)"', r.text).group(1), "accept": "Yes"}
        r = jar_request("POST", action, data=data)
    raise RuntimeError("no code after five steps")

# %% [markdown]
# The client's side of the flow. It authorizes with PKCE, the resource and a `state` value. On return it checks `iss` (a mix-up attack names another server) and `state` (a forged redirect, CSRF), then trades the code for tokens.

# %%
def get_tokens(resource, scope):
    """The client's side: authorize with PKCE and the resource, check iss, then trade the code for tokens."""
    verifier, challenge = pkce()
    url = AS_META["authorization_endpoint"] + "?" + urlencode({
        "client_id": CLIENT_ID, "redirect_uri": REDIRECT, "response_type": "code", "scope": scope, "state": "s1",
        "code_challenge": challenge, "code_challenge_method": "S256", "resource": resource})
    q = parse_qs(urlparse(sign_in(url)).query)
    if q["iss"][0] != ISSUER:
        raise RuntimeError("mix-up: the redirect names another issuer")
    if q["state"][0] != "s1":
        raise RuntimeError("state mismatch (CSRF)")
    r = httpx.post(AS_META["token_endpoint"], data={
        "grant_type": "authorization_code", "client_id": CLIENT_ID, "code": q["code"][0],
        "redirect_uri": REDIRECT, "code_verifier": verifier, "resource": resource})
    r.raise_for_status()
    return r.json()

trackr_tok = get_tokens(RS_TRACKR, "openid issues:read")
claims = jwt.decode(trackr_tok["access_token"], options={"verify_signature": False})
print({k: claims.get(k) for k in ["iss", "aud", "azp", "scope"]})
print("access token lifetime:", claims["exp"] - claims["iat"], "s | refresh token lifetime:", trackr_tok["refresh_expires_in"], "s")

# %% [markdown]
# ### 10. Each token is good for one server
# The Trackr token names Trackr in `aud`. The runbooks server reads the same token and answers `401` with `invalid_token`. The status alone does not prove the audience check, because a wrong token also gets a generic `401`; the contrast with the runbooks token, which the same server accepts, is what proves it. Then the client asks for a second token, with `resource` set to the runbooks server, and calls it.

# %%
r = mcp_post(RS_RUNBOOKS, "tools/call", {"name": "read_runbook", "arguments": {"name": "cert-expiry"}}, trackr_tok["access_token"])
print("Trackr token at the runbooks server:", r.status_code, "|", r.headers.get("www-authenticate", "")[:90])
rb_tok = get_tokens(RS_RUNBOOKS, "openid runbooks:read")
r = mcp_post(RS_RUNBOOKS, "tools/call", {"name": "read_runbook", "arguments": {"name": "cert-expiry"}}, rb_tok["access_token"])
print("runbooks token at the runbooks server:", r.status_code, "|", r.json()["result"]["content"][0]["text"][:60])

# %% [markdown]
# ### 11. Store the tokens encrypted on the client
# Tokens are secrets. The client keeps them in a file encrypted with a Fernet key (AES-128 in CBC mode plus an HMAC). The four-method storage of the MCP SDK keeps the same shape; this lab keeps the two methods it needs.
#
# **Lab only:** the key is made once and kept in `data/34/`, next to the ciphertext, with owner-only permissions. That is for this lab. In real use the key lives in the OS keyring, a KMS or a secret manager, never beside the file it protects.

# %%
# LAB ONLY: the key sits beside the ciphertext. Real use: OS keyring, KMS or secret manager.
from cryptography.fernet import Fernet
key_file = DATA / "storage.key"
if not key_file.exists():
    key_file.write_bytes(Fernet.generate_key()); key_file.chmod(0o600)
fernet = Fernet(key_file.read_bytes())

class EncryptedStorage:
    """Tokens for one resource, encrypted on disk. Nothing readable is written."""
    def __init__(self, path):
        self.path = Path(path)
    def save_tokens(self, tokens):
        self.path.write_bytes(fernet.encrypt(json.dumps(tokens).encode()))
    def load_tokens(self):
        return json.loads(fernet.decrypt(self.path.read_bytes()))

store = {"trackr": EncryptedStorage(DATA / "tokens-trackr.bin"), "runbooks": EncryptedStorage(DATA / "tokens-runbooks.bin")}
store["trackr"].save_tokens(trackr_tok)
store["runbooks"].save_tokens(rb_tok)
raw = (DATA / "tokens-trackr.bin").read_bytes()
print("file starts with:", raw[:6], "| the access token is readable in the file:",
      trackr_tok["access_token"][:30].encode() in raw)
print("loaded back, same token:", store["trackr"].load_tokens()["access_token"] == trackr_tok["access_token"])

# %% [markdown]
# ### 12. Rotate the refresh token
# When the access token is about to expire (5 minutes here), the client trades the refresh token for a new pair. With rotation on, the server returns a new refresh token and the old one stops working. The client saves the new pair before it uses it again.

# %%
old = store["trackr"].load_tokens()
r = httpx.post(AS_META["token_endpoint"], data={"grant_type": "refresh_token", "client_id": CLIENT_ID,
                                                  "refresh_token": old["refresh_token"]})
r.raise_for_status()
new = r.json()
store["trackr"].save_tokens(new)
print("refresh: status", r.status_code, "| new refresh token:", new["refresh_token"] != old["refresh_token"])
claims = jwt.decode(new["access_token"], options={"verify_signature": False})
print("new access token still for:", claims["aud"], "| scope:", claims["scope"])

# %% [markdown]
# ### 13. What the Keycloak-only checks show
# Keycloak can show the resource servers and the client policy that the realm file set up. The stand-in has no admin console. Its output is recorded from a real Keycloak run, so the lesson still reads without Docker.
# Which file is which: `../data/recorded/34.json` is the recording this step reads when Docker is off. A Docker run rewrites it in the clean-up cell at the end. Nothing else reads it.

# %%
def recorded(key):
    """The recorded output of a real Keycloak run, labelled as such."""
    rec = Path("../data/recorded/34.json")
    for line in (json.loads(rec.read_text()).get(key, []) if rec.exists() else ["(no recording found)"]):
        print("recorded output:", line)

if not KC_UP:
    recorded("realm")

# %% [markdown]
# Who fetched the client ID document? The document server logs each request. Keycloak's request comes from the container's address, the stand-in's from `127.0.0.1`. The notebook's own check of the document is left out.

# %%
for line in (DATA / "cimd.log").read_text().splitlines():
    if "ops-desk.json" in line and "self-check" not in line:    # the notebook's own check is not a fetch
        print("fetched by", line.split(" - - ")[0], "|", line.split('"')[1])

# %% [markdown]
# The resource indicator is checked before a token exists. A resource that is not on the realm's list is refused.

# %%
q = {"client_id": CLIENT_ID, "redirect_uri": REDIRECT, "response_type": "code", "scope": "openid issues:read",
     "code_challenge": pkce()[1], "code_challenge_method": "S256", "resource": "http://127.0.0.1:9999/mcp", "state": "s2"}
r = jar_request("GET", f"{AS_META['authorization_endpoint']}?{urlencode(q)}")
if r.status_code == 302:
    print("authorize refused:", parse_qs(urlparse(r.headers["location"]).query).get("error"))
else:
    print("authorize refused: status", r.status_code, "| no code issued")

# %% [markdown]
# ### 14. The model uses Trackr with the token (`needs-llm`)
# A model gets one tool, `count_open`. The tool calls Trackr with the Trackr token. The model is called twice: once to choose the tool, once to write the answer. The tool result is the same with Keycloak or the stand-in, because the same data sits behind both.

# %%
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

async def mcp_call(url, token, name, args):
    """One MCP session per call, with the bearer token on every request."""
    async with httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"}) as http:
        async with Client(streamable_http_client(url, http_client=http)) as c:
            return await c.call_tool(name, args)

@tool("count_open")
async def count_open_tool(team: str) -> str:
    """Count the open issues for one team (web, api, mobile or infra). Needs issues:read."""
    r = await mcp_call(RS_TRACKR, store["trackr"].load_tokens()["access_token"], "count_open", {"team": team})
    return r.content[0].text

tools = [count_open_tool]
Q = HumanMessage("How many open web issues are there? Use the tool.")
print("tool ready:", count_open_tool.name)

# %% [markdown]
# The model gets the question and the tool. It answers with a tool call, not text. The recording opens here.

# %% tags=["needs-llm"]
# The recorder wraps every HTTP call in this window, so it stays open only around the model calls.
llm_replay.start("34_org-authorization-server")
from llm_setup import get_llm
llm = get_llm(max_calls=2)
first = await llm.bind_tools(tools).ainvoke([Q])
print("model asks for:", [(c["name"], c["args"]) for c in first.tool_calls])

# %% [markdown]
# If the model did not run, the tool still answers on its own. Its result below is the real Trackr answer.

# %%
if "first" in globals() and first.tool_calls:   # the tool runs over httpx2, which the recorder does not wrap
    results = [await count_open_tool.ainvoke(c) for c in first.tool_calls]
    print("tool says:", results[0].text[:60])
else:
    print("model skipped in this run: the tool still answers on its own:", await count_open_tool.ainvoke({"team": "web"}))

# %% [markdown]
# The model reads the tool result and writes the answer. This is its second call, the last one in the notebook.

# %% tags=["needs-llm"]
final = await llm.bind_tools(tools).ainvoke([Q, first, *results])
print("answer:", final.text)
llm_replay.stop()        # the recording closes here; the local HTTP calls below run outside it

# %% [markdown]
# ## At real scale
# - One organisation Keycloak runs as several nodes behind a load balancer and a shared database. The lab runs one container; production uses `start` and https.
# - Resource servers cache keys: PyJWT's `PyJWKClient` keeps the key set 300 s, and an unknown `kid` refetches only after a 30 s cooldown (PyJWT API docs).
# - Keys rotate: add a new RSA key at higher priority, keep the old one passive, then remove it. Keycloak suggests a new key every 3 to 6 months (Keycloak admin guide). The lab is single-node, with one key and no rotation.
# - Keep token-store keys in the OS keyring, a KMS or a secret manager, never beside the file (the lab does, step 11). Clients use https documents; the lab's http is for `host.docker.internal` only.
# - Access tokens live 5 minutes and refresh tokens work once. Agents with no user: lesson 35. Enterprise login: lesson 36.

# %% [markdown]
# ## Decision guide
# | Question | If yes | If no |
# | --- | --- | --- |
# | Several MCP servers share users? | One org authorization server (this lesson). | One server per product, with the cost in the table above. |
# | Clients you don't control, no pre-registration? | Client ID metadata documents (experimental in Keycloak 26.8; the lab's compose file enables them). | Pre-register the client in the realm. |
# | One token must not work at another server? | Resource indicators (experimental in Keycloak 26.8; 26.7.x lacks them). | Scope-based audience mappers, weaker. |
# | Long-lived sessions on laptops? | Refresh rotation with reuse refused (done here). | Longer access tokens, with a revocation plan. |

# %% [markdown]
# ## What just happened
# - You ran one Keycloak 26.8 with a realm file. The two resource servers are clients with a `resource_url`, and their audiences come from the resource indicator.
# - The client ID was a URL. The server fetched its document, checked the redirect URI and the resource against it, and issued one token per resource.
# - The Trackr token said `aud` = Trackr. The runbooks server refused it. The token for runbooks worked there.
# - Tokens were stored encrypted. The refresh token rotated, so the old one was spent.

# %% [markdown]
# ## Common mistakes
# Using a refresh token after rotation. The server has already spent it, so the client gets `invalid_grant`. Worse, Keycloak and many servers do this: they read the reuse as theft and end the session. The fix is to save the new pair the moment the server returns it, and never send the old one again.

# %% tags=["raises-exception"]
r = httpx.post(AS_META["token_endpoint"], data={"grant_type": "refresh_token", "client_id": CLIENT_ID,
                                                  "refresh_token": old["refresh_token"]})
print(r.json()["error"])   # the error code: invalid_grant
r.raise_for_status()       # raises httpx.HTTPStatusError: 400 Bad Request

# %% [markdown]
# Fix: store the rotated pair (step 12) and use only the newest refresh token. The check below confirms the store holds the newest pair.

# %%
print("stored refresh token is the newest:", store["trackr"].load_tokens()["refresh_token"] == new["refresh_token"])

# %% [markdown]
# A second mistake: sending the Trackr token to the runbooks server because it is the token you already have. The audience is Trackr, so the runbooks server answers `401`:

# %% tags=["raises-exception"]
mcp_post(RS_RUNBOOKS, "tools/call", {"name": "read_runbook", "arguments": {"name": "cert-expiry"}},
         trackr_tok["access_token"]).raise_for_status()   # raises httpx.HTTPStatusError: 401 Unauthorized

# %% [markdown]
# Fix: request a token with `resource=` set to the server you are calling, as in step 9. That token names only that server.

# %% [markdown]
# ## Try it
# Ask for a token for the runbooks server with the scope `runbooks:read`. Call Trackr's `count_open` with that token. Print the status code and the `www-authenticate` header. Then say in one sentence what this shows about audiences and scopes.

# %%
# Setup so this cell runs on its own: a runbooks token from step 9's helper (the sign-in is reused).
rb_try = get_tokens(RS_RUNBOOKS, "openid runbooks:read")
print("runbooks token ready | aud:", jwt.decode(rb_try["access_token"], options={"verify_signature": False})["aud"])
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below

# %% tags=["solution"]
r = mcp_post(RS_TRACKR, "tools/call", {"name": "count_open", "arguments": {"team": "web"}}, rb_try["access_token"])
print("status:", r.status_code, "|", r.headers.get("www-authenticate", "")[:90])
print("A scope says what a token may do; the audience says where. The runbooks token has the right scope but the wrong audience, so Trackr refuses it.")

# %% [markdown]
# Clean up: stop the servers and the document server, remove the Keycloak container with its volumes, and, after a Docker run only, save this run's Keycloak output to `../data/recorded/34.json` for later Docker-free runs. A Docker-free run leaves that file alone. The recorder closes last.

# %%
if KC_UP:
    rec = Path("../data/recorded/34.json"); rec.parent.mkdir(parents=True, exist_ok=True)
    rec.write_text(json.dumps(RECORD, indent=1))
stop_servers()
if KC_UP:
    subprocess.run([*COMPOSE, "down", "-v"], check=False, capture_output=True)
llm_replay.stop()
print("servers stopped | Keycloak", "removed" if KC_UP else "not used")

# %% [markdown]
# ## Key terms
# - **authorization server** — the one place that signs users in and issues tokens for many resource servers.
# - **resource indicator (RFC 8707)** — the `resource` parameter; the token's audience is that one server.
# - **client ID metadata document (CIMD)** — a URL that is the client's ID; the server fetches the document with the name, redirect URIs and scopes. Experimental in Keycloak 26.8.
# - **PKCE (S256)** — proof that the code's client started the flow, from a secret verifier.
# - **refresh-token rotation** — each refresh returns a new refresh token; the old one is refused after use.
# - **Keycloak realm** — the tenant of one Keycloak: its users, clients, scopes and policies.
# - **encrypted token storage** — tokens kept on disk only in encrypted form (Fernet here).
# - **Keycloak support matrix** — which features each Keycloak version has; CIMD and resource indicators are experimental in 26.8, and 26.7.x lacks resource indicators.

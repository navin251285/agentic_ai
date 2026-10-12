# %% [markdown]
# # 35 · Agent identity: client credentials and token exchange
# Level L6 · Part 7 · professional · ~40 min · builds on 34

# %% [markdown]
# ## Goal
# By the end, a nightly triage agent has its own client ID and asks an authorization server for a token that can only read issues (`issues:read`). When the agent works for a user, Trackr exchanges the user's token for a GitHub token (RFC 8693) that names the agent as the actor. The audit log then shows "triage-nightly, on behalf of alice". The model makes 2 calls. You also know which parts are on the roadmap.

# %% [markdown]
# ## Why it matters
# A nightly job has no person at the keyboard, so it needs a credential. Without an agent identity, it takes one of two bad options.
#
# | | Copy the user's token into the job | Share one service account | Agent identity + token exchange |
# | --- | --- | --- | --- |
# | Whose name is in GitHub's log | alice, for every run | the service account, for every user | triage-nightly, on behalf of alice |
# | What the job may do | everything alice can do | everything the account can do | its client's list, and alice's grant |
# | Who can switch it off | nobody quickly | whoever holds the password | the authorization server, per client |
#
# Skip this for a script that reads public data on a laptop. It pays when a job acts in another system for a person.

# %% [markdown]
# ## The idea
# An agent is a principal. Give it its own client ID and secret, and the server sets `sub` to the client itself. This is the **client credentials** grant: no browser, no user. When the agent acts for a user, the server holding the user's token does **token exchange** (RFC 8693). It sends the user's token as the *subject token* and the agent's as the *actor token*, asks for a new audience and narrower scope, and gets a token with `sub` = the user and `act` naming the agent. The `act` claim is the audit trail: "agent X on behalf of user Y".
#
# Analogy: a night porter has his own key card. When he opens a guest's room, the card records both, and works only on the floors it was cut for.

# %% [markdown]
# ## Picture
# ```mermaid
# sequenceDiagram
#   participant A as Triage agent (own client ID)
#   participant S as Authorization server :8350
#   participant T as Trackr :8351
#   participant G as GitHub API (fake) :8352
#   A->>S: client_credentials, resource = Trackr, scope = issues:read
#   S-->>A: token: sub = triage-nightly (no user in it)
#   A->>T: open_github_issues(repo, on_behalf_of = alice), agent token
#   T->>S: token exchange: subject = alice's token, actor = agent token, audience = GitHub
#   S-->>T: token: sub = alice, act.sub = triage-nightly, aud = GitHub
#   T->>G: GET the issues with the exchanged token
#   G-->>T: 200 and the issue list
#   T-->>A: the titles (Trackr writes one audit line)
# ```

# %% [markdown]
# ## Step by step
#
# ### 1. Set up
# The ports are 8350 (the authorization server), 8351 (Trackr) and 8352 (the GitHub API). The client secrets come from `.env`; the lab values in `.env.example` are for the local lab server only. The recording window (step 11) covers the model calls and the Trackr call the tool makes between them.

# %%
import sys, os, json, time, subprocess, atexit
from pathlib import Path
import httpx, httpx2, jwt
sys.path.insert(0, "..")
import tut_env
from tut_env import env
tut_env.load()
ISSUER, TRACKR, GITHUB = "http://127.0.0.1:8350", "http://127.0.0.1:8351/mcp", "http://127.0.0.1:8352"
DATA = Path("../data/35").resolve(); DATA.mkdir(parents=True, exist_ok=True)
for name in ["as_audit.log", "trackr_audit.log", "github_audit.log", "consent.json"]:
    (DATA / name).unlink(missing_ok=True)          # a fresh run starts with empty logs
procs = []
atexit.register(lambda: [p.terminate() for p in procs])
print("ports 8350-8352 | secrets set:", bool(env("TRIAGE_CLIENT_SECRET")), bool(env("TRACKR_CLIENT_SECRET")))

# %% [markdown]
# ### 2. The stand-in authorization server (no Docker)
# This is a small authorization server, so you can read all of it. Lesson 34 ran Keycloak for the same job. Here the server signs RS256 tokens and publishes its keys. It has two clients. `triage-nightly` may use client credentials and only `issues:read`. `trackr-mcp` may exchange tokens, only for the GitHub audience and only `github:read`. Each token it issues is one line in its audit log.
#
# The browser sign-in of lesson 34 is replaced by `/dev/sign-in`, which gives the demo user alice her token. This is a stand-in.

# %%
%%writefile ../apps/35/as_core.py
"""Shared by the stand-in authorization server for lesson 35: its signing key, its clients and the token helpers."""
import base64, json, os, secrets, sys, time
from pathlib import Path
from joserfc import jwt
from joserfc.jwk import RSAKey
from starlette.responses import JSONResponse

ISSUER = "http://127.0.0.1:8350"
TRACKR, GITHUB = "http://127.0.0.1:8351/mcp", "http://127.0.0.1:8352"
TOKEN_EXCHANGE = "urn:ietf:params:oauth:grant-type:token-exchange"
AUDIT = Path(sys.argv[1])                       # one line per issued token
KEY = RSAKey.generate_key(2048, {"kid": "tut-35", "alg": "RS256", "use": "sig"})
# Client secrets come from the environment (the notebook passes them from .env). Each client gets only what it needs.
CLIENTS = {
    "triage-nightly": {"secret": os.environ["TRIAGE_CLIENT_SECRET"], "grants": {"client_credentials"},
                       "scopes": {"issues:read"}},
    "trackr-mcp": {"secret": os.environ["TRACKR_CLIENT_SECRET"], "grants": {TOKEN_EXCHANGE},
                   "scopes": {"github:read"}, "audiences": {GITHUB}},
}

def err(status, code, text):
    return JSONResponse({"error": code, "error_description": text}, status_code=status)

def issue(claims, audience, scope, lifetime):
    now = int(time.time())
    body = {"iss": ISSUER, "aud": audience, "iat": now, "exp": now + lifetime, "scope": scope, **claims}
    with AUDIT.open("a") as log:
        log.write(json.dumps({"event": "issued", "sub": body["sub"], "azp": body.get("azp"),
                              "act": body.get("act"), "aud": audience, "scope": scope}) + "\n")
    return jwt.encode({"alg": "RS256", "kid": "tut-35"}, body, KEY)

def verified(token):
    """Our own tokens only: signature, issuer and expiry. Returns the claims or None."""
    try:
        c = jwt.decode(token, KEY).claims
    except Exception:
        return None
    return c if c.get("iss") == ISSUER and c.get("exp", 0) > time.time() else None

def client_id_of(request, form):
    """client_secret_basic (the header) or client_secret_post (the form). Returns the client id, or None."""
    auth = request.headers.get("authorization", "")
    if auth.startswith("Basic "):
        cid, _, secret = base64.b64decode(auth[6:]).decode().partition(":")
    else:
        cid, secret = form.get("client_id", ""), form.get("client_secret", "")
    client = CLIENTS.get(cid)
    return cid if client and secrets.compare_digest(client["secret"], secret) else None

# %% [markdown]
# The endpoints use these helpers. Each is a few lines: the metadata, the JSON Web Key Set (JWKS), the stand-in sign-in and the token endpoint, which handles both grants.

# %%
%%writefile ../apps/35/triage_as.py
"""Stand-in authorization server for lesson 35, on 127.0.0.1:8350 (no Docker needed).
Real here: client authentication (client_secret_basic), client_credentials with a resource indicator,
RFC 8693 token exchange (subject = the user's token, actor = the agent's token, an audience allow-list,
and a scope inside both the subject's and the client's scopes), RS256 with published keys, one audit line per token.
Stand-in: lesson 34's browser sign-in is /dev/sign-in, which mints the demo user's token."""
import sys
from urllib.parse import parse_qs
import uvicorn
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from as_core import CLIENTS, GITHUB, ISSUER, KEY, TOKEN_EXCHANGE, TRACKR, client_id_of, err, issue, verified

async def metadata(request):
    return JSONResponse({"issuer": ISSUER, "token_endpoint": f"{ISSUER}/token", "jwks_uri": f"{ISSUER}/jwks",
        "authorization_endpoint": f"{ISSUER}/dev/sign-in", "response_types_supported": ["code"],
        "code_challenge_methods_supported": ["S256"],
        "grant_types_supported": ["client_credentials", TOKEN_EXCHANGE],
        "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
        "scopes_supported": ["issues:read", "github:read"]})

async def jwks(request):
    return JSONResponse({"keys": [KEY.as_dict(private=False)]})

async def sign_in(request):
    """Stand-in for lesson 34's browser sign-in: mints alice's user token for Trackr."""
    if request.query_params.get("user") != "alice":
        return err(404, "unknown_user", "only the demo user alice exists in this lab")
    return JSONResponse({"access_token": issue({"sub": "alice", "azp": "ops-desk-web"}, TRACKR,
                                                "issues:read github:read", 3600), "token_type": "Bearer"})

async def token(request):
    form = {k: v[0] for k, v in parse_qs((await request.body()).decode()).items()}
    cid = client_id_of(request, form)
    if cid is None:
        return err(401, "invalid_client", "client authentication failed")
    client, scope = CLIENTS[cid], set(form.get("scope", "").split())
    if form.get("grant_type") == "client_credentials":
        if "client_credentials" not in client["grants"]:
            return err(400, "unauthorized_client", f"{cid} may not use client_credentials")
        if form.get("resource") != TRACKR:
            return err(400, "invalid_target", "resource is required and must name Trackr")
        if not scope <= client["scopes"]:
            return err(400, "invalid_scope", f"{cid} may not ask for {sorted(scope - client['scopes'])}")
        # No user here: sub and azp are the client itself.
        return JSONResponse({"access_token": issue({"sub": cid, "azp": cid}, TRACKR, " ".join(sorted(scope)), 300),
                             "token_type": "Bearer", "expires_in": 300, "scope": " ".join(sorted(scope))})
    if form.get("grant_type") == TOKEN_EXCHANGE:
        if TOKEN_EXCHANGE not in client["grants"]:
            return err(400, "unauthorized_client", f"{cid} may not exchange tokens")
        subject, actor = verified(form.get("subject_token", "")), verified(form.get("actor_token", ""))
        if subject is None or actor is None:
            return err(400, "invalid_request", "subject_token and actor_token must be unexpired tokens from this server")
        if subject.get("sub") == subject.get("azp"):
            return err(400, "invalid_request", "subject_token must be a user's token, not a client's")
        audience = form.get("resource") or form.get("audience")
        if audience not in client.get("audiences", set()):
            return err(400, "invalid_target", f"{cid} may not get tokens for {audience}")
        if not scope <= set(subject["scope"].split()) or not scope <= client["scopes"]:
            return err(400, "invalid_scope", "the scope must be in the user's grant and in this client's list")
        # RFC 8693 act claim: the actor (the agent) is named; a previous actor, if any, nests inside it.
        act = {"sub": actor["azp"], **({"act": subject["act"]} if "act" in subject else {})}
        out = issue({"sub": subject["sub"], "azp": cid, "act": act}, audience, " ".join(sorted(scope)), 120)
        return JSONResponse({"access_token": out, "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
                             "token_type": "Bearer", "expires_in": 120, "scope": " ".join(sorted(scope))})
    return err(400, "unsupported_grant_type", "grant not offered by this server")

app = Starlette(routes=[Route("/.well-known/oauth-authorization-server", metadata), Route("/jwks", jwks),
                        Route("/dev/sign-in", sign_in), Route("/token", token, methods=["POST"])])

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8350, log_level="warning")

# %% [markdown]
# The helper starts a server with its log file and waits until it answers. It uses polling, not a fixed sleep.

# %%
def start(script, *args):
    """Start one server from ../apps/35 with a log file for its errors."""
    log = open(DATA / (Path(script).stem + ".err"), "w")
    p = subprocess.Popen([sys.executable, str(Path("../apps/35", script).resolve()), *args],
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
            raise RuntimeError(f"no answer from {url}; see the .err files in ../data/35")
        time.sleep(0.5)

as_proc = start("triage_as.py", str(DATA / "as_audit.log"))
wait_for(f"{ISSUER}/.well-known/oauth-authorization-server")
meta = httpx.get(f"{ISSUER}/.well-known/oauth-authorization-server").json()
print("issuer:", meta["issuer"], "| grants:", meta["grant_types_supported"])

# %% [markdown]
# ### 3. The agent's own identity: client credentials
# The agent authenticates with its client ID and secret (HTTP Basic). It asks for a token for Trackr only, with the `resource` parameter (RFC 8707). It has no user, so there is no user in the token. Look at `sub` and `azp`: both are the agent's own ID.

# %%
r = httpx.post(f"{ISSUER}/token", auth=("triage-nightly", env("TRIAGE_CLIENT_SECRET")), timeout=10, data={
    "grant_type": "client_credentials", "resource": TRACKR, "scope": "issues:read"})
agent_tok = r.json()["access_token"]
claims = jwt.decode(agent_tok, options={"verify_signature": False})
print({k: claims[k] for k in ["sub", "azp", "aud", "scope"]})
print("a user in the token:", claims["sub"] != claims["azp"])

# %% [markdown]
# Two requests the server must refuse. A wrong secret gets no token. A scope the client was not given gets `invalid_scope`, even with the right secret.

# %%
import secrets
bad = httpx.post(f"{ISSUER}/token", auth=("triage-nightly", secrets.token_urlsafe(12)), timeout=10, data={
    "grant_type": "client_credentials", "resource": TRACKR, "scope": "issues:read"})
wide = httpx.post(f"{ISSUER}/token", auth=("triage-nightly", env("TRIAGE_CLIENT_SECRET")), timeout=10, data={
    "grant_type": "client_credentials", "resource": TRACKR, "scope": "issues:read issues:write"})
print("wrong secret:", bad.status_code, bad.json()["error"])
print("scope not granted:", wide.status_code, wide.json()["error"])

# %% [markdown]
# ### 4. Trackr and the GitHub API
# Trackr has one tool, `open_github_issues`. It accepts only tokens whose audience is Trackr and that carry `issues:read`. It never forwards the agent's token. The GitHub API is a local fake. It accepts only tokens whose audience is GitHub and that carry `github:read`, and it logs who called and on whose behalf.

# %%
%%writefile ../apps/35/trackr_agent.py
"""Trackr for lesson 35, on 127.0.0.1:8351. One tool: open_github_issues(repo, on_behalf_of).
It accepts only tokens whose audience is Trackr and that carry issues:read. To call GitHub it never forwards the
caller's token. It exchanges the user's token (RFC 8693) for a GitHub token, names the agent as the actor,
and writes one audit line: who (the agent), on behalf of whom (the user), what, and where."""
import json, os, sys
from pathlib import Path
import httpx, jwt
from mcp.server import MCPServer
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

PORT = 8351
RESOURCE = f"http://127.0.0.1:{PORT}/mcp"
ISSUER, JWKS_URL, GITHUB = sys.argv[1], sys.argv[2], sys.argv[3]
CONSENT, AUDIT = Path(sys.argv[4]), Path(sys.argv[5])     # the users' grants (lab file) and the audit log
TOKEN_EXCHANGE = "urn:ietf:params:oauth:grant-type:token-exchange"
TOKEN_TYPE = "urn:ietf:params:oauth:token-type:access_token"
CLIENT_ID = "trackr-mcp"
CLIENT_SECRET = os.environ["TRACKR_CLIENT_SECRET"]

class OrgVerifier:
    """Signature from the authorization server's keys (JWKS), the issuer, and the audience = Trackr's own URI."""
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

def exchange(agent_token: str, user_token: str) -> str:
    """RFC 8693: subject = the user's token, actor = the agent's token, audience = GitHub, a narrower scope."""
    r = httpx.post(f"{ISSUER}/token", auth=(CLIENT_ID, CLIENT_SECRET), timeout=10, data={
        "grant_type": TOKEN_EXCHANGE, "subject_token": user_token, "subject_token_type": TOKEN_TYPE,
        "actor_token": agent_token, "actor_token_type": TOKEN_TYPE, "resource": GITHUB, "scope": "github:read"})
    if r.status_code != 200:
        raise ToolError(f"token exchange refused: {r.json().get('error')}: {r.json().get('error_description')}")
    return r.json()["access_token"]

mcp = MCPServer("Trackr", token_verifier=OrgVerifier(), auth=AuthSettings(
    issuer_url=ISSUER, resource_server_url=RESOURCE, required_scopes=["issues:read"], validate_token_resource=True))

@mcp.tool(title="Open GitHub issues", annotations=ToolAnnotations(readOnlyHint=True))
async def open_github_issues(repo: str, on_behalf_of: str) -> str:
    token = get_access_token()
    if token is None or "issues:read" not in token.scopes:
        raise ToolError("insufficient_scope: this tool needs issues:read")
    grants = json.loads(CONSENT.read_text()) if CONSENT.exists() else {}
    if on_behalf_of not in grants:               # a real server checks the user's grant for this agent
        raise ToolError(f"{on_behalf_of} has not granted Trackr access")
    upstream = exchange(token.token, grants[on_behalf_of])
    async with httpx.AsyncClient() as http:
        r = await http.get(f"{GITHUB}/repos/{repo}/issues", timeout=10,
                           headers={"Authorization": f"Bearer {upstream}"})
    if r.status_code != 200:
        raise ToolError(f"GitHub answered {r.status_code}")
    with AUDIT.open("a") as log:
        log.write(json.dumps({"who": token.client_id, "on_behalf_of": on_behalf_of, "tool": "open_github_issues",
                              "repo": repo, "upstream_audience": GITHUB, "upstream_scope": "github:read"}) + "\n")
    return "\n".join(issue["title"] for issue in r.json())

if __name__ == "__main__":
    mcp.run("streamable-http", host="127.0.0.1", port=PORT, json_response=True)

# %% [markdown]
# The GitHub API is a plain Starlette app. It checks the token's audience and scope with the same keys.

# %%
%%writefile ../apps/35/fake_github.py
"""Fake GitHub issues API for lesson 35, on 127.0.0.1:8352 (a local stand-in, no network).
It accepts a token only if the audience is this API and the token carries github:read. Every request is
logged with the token's azp (who called) and sub and act (on whose behalf, through which agent)."""
import json, sys
from pathlib import Path
import jwt, uvicorn
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

PORT = 8352
AUD = f"http://127.0.0.1:{PORT}"
ISSUER, JWKS_URL, AUDIT = sys.argv[1], sys.argv[2], Path(sys.argv[3])
KEYS = jwt.PyJWKClient(JWKS_URL)
ISSUES = {"trackr-web": ["Login page flickers on Safari", "Export CSV drops the owner column"],
          "trackr-api": ["Rate limit header missing"]}

def check(request):
    """Returns (claims, None) when the token is good, or (None, reason)."""
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return None, "no bearer token"
    try:
        key = KEYS.get_signing_key_from_jwt(auth[7:]).key
        c = jwt.decode(auth[7:], key, algorithms=["RS256"], audience=AUD, issuer=ISSUER)
    except jwt.PyJWTError as e:
        return None, str(e)
    if "github:read" not in c.get("scope", "").split():
        return None, "insufficient_scope: github:read is needed"
    return c, None

async def repo_issues(request):
    repo = request.path_params["repo"]
    claims, reason = check(request)
    entry = {"path": f"/repos/{repo}/issues"}
    if claims is None:
        entry["refused"] = reason
        with AUDIT.open("a") as log:
            log.write(json.dumps(entry) + "\n")
        return JSONResponse({"message": reason}, status_code=401,
                            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'})
    entry.update({"azp": claims.get("azp"), "sub": claims.get("sub"), "act": claims.get("act")})
    with AUDIT.open("a") as log:
        log.write(json.dumps(entry) + "\n")
    if repo not in ISSUES:
        return JSONResponse({"message": "Not Found"}, status_code=404)
    return JSONResponse([{"title": t, "state": "open"} for t in ISSUES[repo]])

app = Starlette(routes=[Route("/repos/{repo}/issues", repo_issues)])

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")

# %% [markdown]
# Start both. Trackr is ready when its protected-resource metadata answers. The fake GitHub API is ready when its root path answers `404` (no route there, so the poll is not logged).

# %%
consent_file = DATA / "consent.json"      # the users' grants: a lab file (a real server uses an encrypted store, lesson 34)
trk = start("trackr_agent.py", ISSUER, f"{ISSUER}/jwks", GITHUB, str(consent_file), str(DATA / "trackr_audit.log"))
gh = start("fake_github.py", ISSUER, f"{ISSUER}/jwks", str(DATA / "github_audit.log"))
wait_for(f"{GITHUB}/", ok=lambda r: r.status_code == 404)
wait_for("http://127.0.0.1:8351/.well-known/oauth-protected-resource/mcp")
print("Trackr and GitHub are up")

# %% [markdown]
# ### 5. Alice signs in once
# Alice's grant is a token for Trackr with `issues:read` and `github:read`. The stand-in sign-in mints it and the notebook stores it as Trackr's grant from alice. Read it: `sub` is alice, not an agent.

# %%
alice_tok = httpx.get(f"{ISSUER}/dev/sign-in", params={"user": "alice"}, timeout=10).json()["access_token"]
consent_file.write_text(json.dumps({"alice": alice_tok}))
c = jwt.decode(alice_tok, options={"verify_signature": False})
print({k: c[k] for k in ["sub", "azp", "aud", "scope"]})

# %% [markdown]
# ### 6. The exchange by hand
# This is what Trackr does inside its tool. The request has the user's token as the subject, the agent's token as the actor, the GitHub audience and a narrower scope. Read the new token's `sub` and `act`. `sub` is alice and `act.sub` is the agent. The helper `exchange()` takes the same fields, so later cells can change one of them.

# %%
def exchange(**changes):
    """RFC 8693 request as Trackr sends it; changes replace single fields for the refusal checks."""
    form = {"grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "subject_token": alice_tok, "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
            "actor_token": agent_tok, "actor_token_type": "urn:ietf:params:oauth:token-type:access_token",
            "resource": GITHUB, "scope": "github:read", **changes}
    return httpx.post(f"{ISSUER}/token", auth=("trackr-mcp", env("TRACKR_CLIENT_SECRET")), data=form, timeout=10)

ex = exchange()
gh_tok = ex.json()["access_token"]
c = jwt.decode(gh_tok, options={"verify_signature": False})
print({k: c[k] for k in ["sub", "azp", "act", "aud", "scope"]})
print("lifetime (s):", c["exp"] - c["iat"], "| issued_token_type:", ex.json()["issued_token_type"].split(":")[-1])

# %% [markdown]
# ### 7. Who GitHub accepts
# The exchanged token works at GitHub. The agent's own token does not: its audience is Trackr, and GitHub says so.

# %%
r = httpx.get(f"{GITHUB}/repos/trackr-web/issues", headers={"Authorization": f"Bearer {gh_tok}"}, timeout=10)
print("exchanged token:", r.status_code, [i["title"] for i in r.json()])
r = httpx.get(f"{GITHUB}/repos/trackr-web/issues", headers={"Authorization": f"Bearer {agent_tok}"}, timeout=10)
print("agent's own token:", r.status_code, "|", r.json()["message"])

# %% [markdown]
# ### 8. The exchange refuses what was not granted
# Two refusals. Trackr may not get a token for another audience, and a scope alice never granted (`github:write`) is refused.

# %%
no_aud = exchange(resource=TRACKR)
no_scope = exchange(scope="github:write")
print("other audience:", no_aud.status_code, no_aud.json()["error"])
print("scope not in the grant:", no_scope.status_code, no_scope.json()["error"])

# %% [markdown]
# ### 9. The agent calls Trackr through the MCP client
# In production the agent is an MCP client. `ClientCredentialsOAuthProvider` (from the MCP SDK) gets the agent's token, sends it on each call, and fetches a new one when it expires. The provider needs the issuer, so it sends the client secret only to that server. The storage keeps the tokens in memory (this process only).

# %%
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.client.auth.extensions.client_credentials import ClientCredentialsOAuthProvider
class MemoryStorage:
    """Token storage for one process: the four methods the SDK needs."""
    def __init__(self):
        self.tokens, self.client = None, None
    async def get_tokens(self): return self.tokens
    async def set_tokens(self, tokens): self.tokens = tokens
    async def get_client_info(self): return self.client
    async def set_client_info(self, info): self.client = info

provider = ClientCredentialsOAuthProvider(server_url=TRACKR, storage=MemoryStorage(), client_id="triage-nightly",
                                          client_secret=env("TRIAGE_CLIENT_SECRET"), scope="issues:read", issuer=ISSUER)
http = httpx2.AsyncClient(auth=provider)   # carries the agent's token on every request; closed at the end

async def call(name, arguments):
    """One MCP session per call, through the authenticated HTTP client."""
    async with Client(streamable_http_client(TRACKR, http_client=http)) as c:
        return await c.call_tool(name, arguments)

res = await call("open_github_issues", {"repo": "trackr-web", "on_behalf_of": "alice"})
print("tool says:", res.content[0].text.replace("\n", " | "))

# %% [markdown]
# ### 10. Read the audit trail
# Two logs, one line per event. Trackr says which agent acted for which user. GitHub says which client called (`azp`), whose access it is (`sub`), and the actor chain (`act`).

# %%
for line in (DATA / "trackr_audit.log").read_text().splitlines():
    rec = json.loads(line)
    print(f"Trackr: {rec['who']} on behalf of {rec['on_behalf_of']} | {rec['tool']} {rec['repo']} | upstream {rec['upstream_audience']}")
for line in (DATA / "github_audit.log").read_text().splitlines():
    rec = json.loads(line)
    print("GitHub:", {k: rec.get(k) for k in ["azp", "sub", "act", "path", "refused"] if rec.get(k) is not None})

# %% [markdown]
# ### 11. The model runs the nightly triage (`needs-llm`)
# The model gets one tool: list the open issues of a repo. The user is not in the tool's arguments. The job's configuration fixes it to alice, so the model cannot change whose access it uses. The model is called twice: once to choose the tool, once to write the answer. The recording opens at the first model call and closes after the second. The window also covers the tool's local Trackr call in between: on replay, that answer comes from the recording, not from Trackr.

# %%
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage
@tool("open_github_issues")
async def open_github_issues_tool(repo: str) -> str:
    """List the open issues of one repo (trackr-web or trackr-api) for the nightly triage. Acts for alice."""
    r = await call("open_github_issues", {"repo": repo, "on_behalf_of": "alice"})
    return r.content[0].text
Q = HumanMessage("Which issues are open in trackr-web? Use the tool.")
print("tool ready:", open_github_issues_tool.name)

# %% [markdown]
# The model call comes next. The recorder opens just before it, and it stays open through the tool's Trackr call until the second model call closes it.

# %% tags=["needs-llm"]
# The recorder wraps every HTTP call in the window: the model calls and the local Trackr call the tool makes (the tool cell below). On replay, that Trackr answer comes from the recording.
import llm_replay
llm_replay.start("35_agent-identity")
from llm_setup import get_llm
llm = get_llm(max_calls=2)
first = await llm.bind_tools([open_github_issues_tool]).ainvoke([Q])
print("model asks for:", [(c["name"], c["args"]) for c in first.tool_calls])

# %% [markdown]
# If the model did not run, the tool still answers on its own, as the job would. Its result is the same Trackr call as step 9.

# %%
if "first" in globals() and first.tool_calls:
    results = [await open_github_issues_tool.ainvoke(c) for c in first.tool_calls]
    print("tool says:", results[0].content.replace("\n", " | "))
else:
    results = []
    print("model skipped in this run; the tool answers on its own:",
          (await open_github_issues_tool.ainvoke({"repo": "trackr-web"})).replace("\n", " | "))

# %% [markdown]
# The model reads the tool's answer and writes the reply. This is its second call, and the last one in the notebook.

# %% tags=["needs-llm"]
final = await llm.bind_tools([open_github_issues_tool]).ainvoke([Q, first, *results])
print("answer:", final.text)
llm_replay.stop()        # the recording closes here; the rest runs outside it

# %% [markdown]
# ## At real scale
# - **Client secrets are long-lived.** The MCP extension page says to keep them in a secrets manager, rotate them, and prefer a signed JWT assertion (RFC 7523). The SDK has `PrivateKeyJWTOAuthProvider` for that. The lab uses a shared secret from `.env`.
# - **Exchange is a policy, not a pass-through.** Our server allows one audience per client, and a scope must sit inside both the user's grant and the client's list. Check that your identity provider supports RFC 8693 before you design around it.
# - **Log the triple.** Every upstream call records `azp` (the caller), `sub` (the person) and `act` (the agent). Lesson 28 covers how these logs reach tracing.
# - **Keep user tokens encrypted and short-lived.** Here one sits in a file for an hour. Lesson 34, step 11, shows the store.

# %% [markdown]
# ### On the roadmap, not in this lesson
# The 2026-08-22 MCP roadmap lists agent identity work (source: the roadmap entry in RESEARCH.md §9). **DPoP** (RFC 9449) binds a token to a key the client holds, so a stolen bearer token cannot be replayed. **Workload identity federation** (SEP-1933) lets a workload prove who it is without holding a long-lived secret. **IETF WIMSE** (the Workload Identity in Multi System Environments working group) standardises how a workload's identity travels across the services in one call chain. **RFC 8693** token exchange is on that roadmap too: this lab implements it on a stand-in server, so it is not yet a standard MCP flow. Enterprise login across servers is lesson 36.

# %% [markdown]
# ## Decision guide
# | Question | If yes | If no |
# | --- | --- | --- |
# | Does the job run with no user present? | Client credentials: the agent gets its own identity. | Use the user's own sign-in (lesson 34). |
# | Must the upstream log name the person too? | Token exchange, with the agent as actor (this lesson). | Client credentials alone, and the log names only the agent. |
# | Will the upstream call go to a different audience? | Exchange for that audience. Never forward the caller's token. | Use the same token, if the audience is the same server. |

# %% [markdown]
# ## What just happened
# - The agent got a token with no user in it. The server refused a wrong secret and a scope it was not given.
# - Trackr exchanged alice's token for a GitHub token. The new token names alice as `sub` and the agent in `act`.
# - GitHub accepted the exchanged token and refused the agent's own token, because its audience was Trackr.
# - The audit logs say "triage-nightly on behalf of alice" in one line, and the model called Trackr with the agent's identity.

# %% [markdown]
# ## Common mistakes
# Sending the agent's own token to the upstream API. It is a valid token for Trackr, not for GitHub, so the upstream refuses it.
# %% tags=["raises-exception"]
httpx.get(f"{GITHUB}/repos/trackr-web/issues", headers={"Authorization": f"Bearer {agent_tok}"}, timeout=10).raise_for_status()
# %% [markdown]
# Fix: exchange for the upstream audience (step 6), then send that token. The raise above is `httpx.HTTPStatusError: 401 Unauthorized`.
#
# A second mistake is leaving out `issuer=` on `ClientCredentialsOAuthProvider`. The SDK then lets the MCP server pick the authorization server, and it warns (`MCPDeprecationWarning`): "Omitting `issuer` is deprecated and it will be required in 3.0. Without it, the MCP server decides which authorization server receives this client's credentials; pass issuer=<your authorization server's issuer URL> so they are only ever sent there." Always pass the issuer, so the client secret goes only to your server.

# %% [markdown]
# ## Try it
# Alice granted `github:read` only. Ask for an exchanged token with the scope `github:write` and print the status and the error. In one sentence, say why a scope check and an audience check are separate checks.

# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below

# %% tags=["solution"]
r = exchange(scope="github:write")
print("status:", r.status_code, "| error:", r.json()["error"])
print("The audience says where a token may go. The scope says what it may do. A token can pass one and fail the other.")

# %% [markdown]
# Clean up: stop the servers and remove the grant file. The audit logs stay for the next step.

# %%
# Clean up: stop the servers. The logs stay in ../data/35; the user's grant file is removed.
for p in procs:
    p.terminate()
for p in procs:
    p.wait(timeout=10)
consent_file.unlink(missing_ok=True)
print("servers stopped | grant file removed | audit logs kept in ../data/35")

# %% [markdown]
# ## Key terms
# - **Agent identity** — an agent's own client ID and secret, so its actions have its own name in the logs (lesson 35).
# - **Client credentials** — the OAuth grant where a client authenticates as itself, with no user (lesson 35).
# - **Token exchange (RFC 8693)** — trade a token for a new one with another audience or scope, naming a subject and an optional actor (lesson 35).
# - **Subject token / actor token** — the user's token being exchanged / the token of the agent that asks for the exchange (lesson 35).
# - **`act` claim** — the actor in a token: who is acting for `sub`; nested if the chain is longer (lesson 35).
# - **On-behalf-of audit** — a log line that names both the agent and the person it acted for (lesson 35).

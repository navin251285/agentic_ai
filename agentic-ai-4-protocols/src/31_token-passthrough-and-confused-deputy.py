# %% [markdown]
# # 31 · Token passthrough and the confused deputy
# Level L5 · Part 6 · core · ~40 min · builds on 16

# %% [markdown]
# ## Goal
# By the end you have run two attacks on a weak Trackr OAuth proxy. In the first, a token minted for another server closes an issue, and Trackr forwards a client's token to an upstream API. In the second, a stranger's client gets a code for the victim's account, because the upstream login already trusts the proxy. Then you switch the proxy to its fixed mode and see both attacks stop: an audience check, per-client consent, exact redirect-URI match, single-use state and a `__Host-` consent cookie.

# %% [markdown]
# **Read this first.** The three apps are teaching servers on plain http. They use one shared HS256 dev key, secrets in code, a login that is only a cookie route, and in-memory state. Fixed mode shows five mitigations from the MCP spec, not a complete OAuth server. For production, use a real authorization server and library (lessons 34 and 40).

# %% [markdown]
# ## The idea
# A proxy is a deputy. It holds its own key and acts for other people. Two rules keep a deputy honest. First, a token has one audience. A server accepts only tokens minted for it, and never passes a client's token on, because the next server may accept it. This is **token passthrough**, and the MCP spec forbids it.

# %% [markdown]
# Second, a deputy must not let a stranger use its key. A proxy that logs in to a third party with one static client ID looks known, so the third party skips its screen. If the proxy also sends the code to any `redirect_uri` it is given, a stranger's client gets the code. This is the **confused deputy**. PKCE does not stop it, because the stranger started the flow and kept the verifier.
#
# Analogy: a hotel porter with a master key. He opens a door only for a friend the guest actually named.

# %% [markdown]
# ## Picture
# ```mermaid
# sequenceDiagram
#   participant E as Attacker client
#   participant V as Victim browser
#   participant P as Trackr proxy :8771
#   participant U as Upstream login :9100
#   E->>V: link to P/authorize with own PKCE
#   V->>P: GET /authorize
#   P->>U: GET /authorize (static client trackr-proxy)
#   U-->>P: 302 with code, no screen
#   V->>P: GET /callback with code
#   P-->>V: 302 to attacker's redirect_uri
#   V-->>E: the code reaches the attacker
#   E->>P: POST /token (attacker's verifier)
#   P-->>E: token acting as the victim
# ```

# %% [markdown]
# ## Step by step
#
# ### 1. Set up the folder and the constants
# Three servers run as separate processes, as they would on a network. The upstream is a company login and its Tracker API. The Trackr proxy is the server under test, and it runs in one of two modes. Both servers are written by this notebook into `../apps/31/`.

# %%
import atexit, base64, hashlib, json, os, secrets, subprocess, sys, time
import os, sys
sys.path.insert(0, "..")   # tut_env lives in the topic folder
from tut_env import env
for _name in ("DEV_SIGNING_KEY", "LAB_PROXY_CLIENT_SECRET", "LAB_NOTES_CLIENT_SECRET"):
    os.environ[_name] = env(_name, "")   # from .env (never in the lesson)
assert len(os.environ["DEV_SIGNING_KEY"]) >= 32, "put DEV_SIGNING_KEY (32+ characters) in .env: see .env.example"
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlencode, urlparse
import httpx
APPS = Path("../apps/31").resolve()
APPS.mkdir(parents=True, exist_ok=True)
UP, ME = "http://127.0.0.1:9100", "http://127.0.0.1:8771"    # upstream login, Trackr proxy
TRACKR_AUD = f"{ME}/mcp"                                     # the audience of Trackr
NOTES_AUD = "http://127.0.0.1:9200/mcp"                      # the audience of another team's server
OPS_REDIRECT = "http://127.0.0.1:9999/callback"              # the ops desk's registered redirect
EVIL = "http://127.0.0.1:6666/steal"                         # the attacker's address (nothing listens)
print("upstream:", UP, "| Trackr proxy:", ME, "| apps:", APPS)

# %% [markdown]
# ### 2. The upstream: a company login and the Tracker API it protects
# The upstream is an authorization server. It has a registered redirect URI for each client, a remembered approval for `trackr-proxy`, and signed tokens with an audience. Its API checks only the signature and the expiry. Many internal APIs started this way. This lesson shows what that allows. The `/received` route is a dev-only log of what the API got.

# %%
%%writefile ../apps/31/upstream.py
"""The upstream for lesson 31 on 127.0.0.1:9100: a company login and the Tracker API it protects.
Real here: a registered redirect_uri per client (exact match), a remembered approval, signed JWT access
tokens with an aud, client_credentials for a server's own token, one-time codes.
Labelled dev stand-ins: one dev key for every token, client secrets in the code, login is a route that sets a cookie.
The API checks the signature and the expiry only. It has no audience check."""
import secrets, time
from urllib.parse import parse_qs, urlencode
import uvicorn
from joserfc import jwt
from joserfc.jwk import OctKey
from starlette.applications import Starlette
from starlette.responses import JSONResponse, RedirectResponse
from starlette.routing import Route

ISS = "http://127.0.0.1:9100"
API = f"{ISS}/api"                                        # audience of the Tracker API
import os
DEV_KEY = os.environ["DEV_SIGNING_KEY"]
CLIENTS = {"trackr-proxy": {"secret": os.environ["LAB_PROXY_CLIENT_SECRET"],
                            "redirect_uris": ["http://127.0.0.1:8771/callback"]},
           "notes-app": {"secret": os.environ["LAB_NOTES_CLIENT_SECRET"], "redirect_uris": []}}
SESSIONS, APPROVED = {}, set()                            # cookie -> user; (user, client) approved once
CODES, RECEIVED = {}, []

def err(code, text, status=400):
    return JSONResponse({"error": code, "error_description": text}, status_code=status)

def sign(sub, aud, client_id):
    now = int(time.time())
    claims = {"iss": ISS, "aud": aud, "sub": sub, "client_id": client_id,
              "scope": "issues:write", "iat": now, "exp": now + 600}
    return jwt.encode({"alg": "HS256"}, claims, OctKey.import_key(DEV_KEY))

async def login(request):
    user = request.query_params.get("user", "ops-user")
    token = secrets.token_urlsafe(16)
    SESSIONS[token] = user
    APPROVED.add((user, "trackr-proxy"))                  # setup: the user approved Trackr once, earlier
    resp = JSONResponse({"logged_in": user, "approved": sorted(c for u, c in APPROVED if u == user)})
    resp.set_cookie("up_session", token, path="/")
    return resp

async def authorize(request):
    q = dict(request.query_params)
    user = SESSIONS.get(request.cookies.get("up_session", ""))
    if user is None:
        return err("login_required", "log in first", 401)
    client = CLIENTS.get(q.get("client_id", ""))
    if client is None or q.get("redirect_uri") not in client["redirect_uris"]:
        return err("invalid_request", "unknown client or redirect_uri")
    if (user, q["client_id"]) not in APPROVED:
        return err("access_denied", "the user has not approved this client", 403)
    code = secrets.token_urlsafe(24)                      # no screen: the approval is already remembered
    CODES[code] = {"client_id": q["client_id"], "redirect_uri": q["redirect_uri"], "user": user, "made": time.time()}
    return RedirectResponse(f"{q['redirect_uri']}?" + urlencode({"code": code, "state": q.get("state", "")}), 302)

async def token(request):
    f = {k: v[0] for k, v in parse_qs((await request.body()).decode()).items()}
    client = CLIENTS.get(f.get("client_id", ""))
    if client is None or f.get("client_secret") != client["secret"]:
        return err("invalid_client", "bad client credentials", 401)
    if f.get("grant_type") == "client_credentials":
        sub = f["client_id"]                              # the app acts as itself
    elif f.get("grant_type") == "authorization_code":
        g = CODES.pop(f.get("code", ""), None)            # one-time code
        if (g is None or g["client_id"] != f["client_id"] or g["redirect_uri"] != f.get("redirect_uri")
                or time.time() - g["made"] > 60):
            return err("invalid_grant", "code unknown, used, expired, or for another client or redirect_uri")
        sub = g["user"]
    else:
        return err("unsupported_grant_type", f.get("grant_type", ""))
    return JSONResponse({"access_token": sign(sub, f.get("resource", API), f["client_id"]),
                         "token_type": "Bearer", "expires_in": 600})

# %% [markdown]
# The upstream API route comes next. It is the only place that checks the bearer token.

# %%
%%writefile -a ../apps/31/upstream.py

async def close(request):
    bearer = request.headers.get("authorization", "").removeprefix("Bearer ")
    try:
        claims = jwt.decode(bearer, OctKey.import_key(DEV_KEY)).claims
    except Exception:
        return err("invalid_token", "bad signature", 401)
    if claims.get("exp", 0) < time.time():
        return err("invalid_token", "expired", 401)
    issue = int(request.path_params["issue_id"])
    RECEIVED.append({"issue": issue, "aud": claims.get("aud"), "sub": claims.get("sub")})  # no audience check
    return JSONResponse({"accepted": True, "issue": issue, "as": claims.get("sub")})

async def received(request):
    return JSONResponse(RECEIVED)

async def health(request):
    return JSONResponse({"ok": True})

app = Starlette(routes=[Route("/health", health), Route("/login", login), Route("/authorize", authorize),
                        Route("/token", token, methods=["POST"]),
                        Route("/api/close/{issue_id:int}", close, methods=["POST"]),
                        Route("/received", received)])

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=9100, log_level="warning")

# %% [markdown]
# ### 3. The Trackr proxy: one file, two modes
# The proxy is an authorization server for MCP clients. It is also an OAuth client of the upstream, with the static client ID `trackr-proxy`. `TRACKR_MODE=weak` has the bugs. `TRACKR_MODE=fixed` has the fixes. The tools come from lesson 03's tracker. The JSON-RPC is written by hand, as in lesson 01, so the lesson stays on the auth points. The file is written in two cells.

# %%
%%writefile ../apps/31/trackr_proxy.py
"""Trackr behind an OAuth proxy for lesson 31, on 127.0.0.1:8771. TRACKR_MODE=weak has the bugs, fixed has the fixes.
The proxy is an authorization server for MCP clients and an OAuth client of the upstream (static client trackr-proxy).
Labelled dev stand-ins: one dev key for every token, client secrets in the code. Issues come from lesson 03."""
import base64, hashlib, html, json, os, secrets, sys, time
from pathlib import Path
from urllib.parse import parse_qs, urlencode
import httpx
import uvicorn
from joserfc import jwt
from joserfc.jwk import OctKey
from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Route
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "03"))
import trackr_server as base

MODE = os.environ.get("TRACKR_MODE", "weak")
ME = "http://127.0.0.1:8771"
RESOURCE = f"{ME}/mcp"                                     # Trackr's audience
UP = "http://127.0.0.1:9100"
API = f"{UP}/api"                                          # the upstream Tracker API's audience
import os
DEV_KEY = os.environ["DEV_SIGNING_KEY"]
import os
CLIENT_CRED = os.environ["LAB_PROXY_CLIENT_SECRET"]
REGISTRY = {"ops-desk": {"name": "Ops desk", "redirect_uris": ["http://127.0.0.1:9999/callback"]},
            "trackr-cli": {"name": "Trackr CLI", "redirect_uris": ["http://127.0.0.1:9998/callback"]}}
TXN, CODES, CONSENTS = {}, {}, {}                          # state, our codes, consent cookie values
PARAMS = ["response_type", "client_id", "redirect_uri", "state", "code_challenge", "code_challenge_method"]

def err(code, text, status=400):
    return JSONResponse({"error": code, "error_description": text}, status_code=status)

def key():
    return OctKey.import_key(DEV_KEY)

def check_token(request):
    """Returns (claims, reason). Weak checks the signature and expiry. Fixed also checks the audience."""
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return None, "no bearer token"
    try:
        claims = jwt.decode(auth[7:], key()).claims
    except Exception:
        return None, "bad signature"
    if claims.get("exp", 0) < time.time():
        return None, "expired"
    if MODE == "fixed" and claims.get("aud") != RESOURCE:
        return None, f"audience is {claims.get('aud')}, not Trackr"
    return claims, "ok"

def start_upstream(q):
    """Keep the client's request under our own state, then send the browser to the upstream login."""
    t = secrets.token_urlsafe(16)
    TXN[t] = {"client_id": q.get("client_id", ""), "redirect_uri": q.get("redirect_uri", ""),
              "state": q.get("state", ""), "challenge": q.get("code_challenge", ""), "made": time.time()}
    up = {"response_type": "code", "client_id": "trackr-proxy", "redirect_uri": f"{ME}/callback", "state": t}
    return RedirectResponse(f"{UP}/authorize?" + urlencode(up), status_code=302)

def consent_page(client, q):
    hidden = "".join(f'<input type="hidden" name="{k}" value="{html.escape(q.get(k, ""))}">' for k in PARAMS)
    return (f"<h1>Allow {html.escape(client['name'])}?</h1>"
            f"<p>It will get a code for Trackr and send it to {html.escape(q.get('redirect_uri', ''))}.</p>"
            f'<form method="post" action="/consent">{hidden}'
            '<button name="decision" value="allow">Allow</button>'
            '<button name="decision" value="deny">Deny</button></form>')

# %% [markdown]
# Routes: authorize, consent, callback. The weak mode skips every check marked `fixed`.

# %%
%%writefile -a ../apps/31/trackr_proxy.py

async def authorize(request):
    q = dict(request.query_params)
    if MODE == "fixed":
        client = REGISTRY.get(q.get("client_id", ""))
        if client is None:
            return err("invalid_client", "unknown client_id")
        if q.get("redirect_uri") not in client["redirect_uris"]:      # exact string match, never a prefix
            return err("invalid_request", "redirect_uri is not registered for this client")
        if q.get("code_challenge_method") != "S256" or not q.get("code_challenge"):
            return err("invalid_request", "PKCE with S256 is required")
        if CONSENTS.get(request.cookies.get("__Host-consent", "")) != q["client_id"]:
            return HTMLResponse(consent_page(client, q))              # per-client consent, before any upstream step
    return start_upstream(q)

async def consent(request):
    f = {k: v[0] for k, v in parse_qs((await request.body()).decode()).items()}
    if f.get("decision") != "allow":
        return HTMLResponse("<p>Denied. Nothing was shared.</p>", status_code=403)
    client = REGISTRY.get(f.get("client_id", ""))
    if client is None or f.get("redirect_uri") not in client["redirect_uris"]:
        return err("invalid_request", "client or redirect_uri is not registered")
    token = secrets.token_urlsafe(24)
    CONSENTS[token] = f["client_id"]
    resp = RedirectResponse("/authorize?" + urlencode({k: f[k] for k in PARAMS if k in f}), status_code=302)
    resp.set_cookie("__Host-consent", token, path="/", secure=True, httponly=True, samesite="lax")
    return resp

async def callback(request):
    q = request.query_params
    if MODE == "fixed":
        txn = TXN.pop(q.get("state", ""), None)                  # single use: a replay finds nothing
        if txn is None or time.time() - txn["made"] > 600:
            return err("invalid_request", "state unknown, already used or expired")
    else:
        txn = TXN.get(q.get("state", ""))                         # weak: the state is kept and never expires
        if txn is None:
            return err("invalid_request", "state unknown")
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(f"{UP}/token", data={"grant_type": "authorization_code", "code": q.get("code", ""),
                         "client_id": "trackr-proxy", "client_secret": CLIENT_CRED,
                         "redirect_uri": f"{ME}/callback", "resource": API})
    if r.status_code != 200:
        return err("upstream_rejected", f"upstream answered {r.status_code}", 502)
    user = jwt.decode(r.json()["access_token"], key()).claims["sub"]
    code = secrets.token_urlsafe(24)
    CODES[code] = {"client_id": txn["client_id"], "redirect_uri": txn["redirect_uri"],
                   "challenge": txn["challenge"], "sub": user, "made": time.time()}
    # Weak: the code goes to whatever redirect_uri the request named. Fixed: to the exact registered one.
    return RedirectResponse(f"{txn['redirect_uri']}?" + urlencode({"code": code, "state": txn["state"]}), 302)

# %% [markdown]
# Route: token. The code is single use in both modes, and the PKCE check is the same in both too.

# %%
%%writefile -a ../apps/31/trackr_proxy.py

async def token(request):
    f = {k: v[0] for k, v in parse_qs((await request.body()).decode()).items()}
    g = CODES.pop(f.get("code", ""), None)                        # single use in both modes
    if g is None or time.time() - g["made"] > 60:
        return err("invalid_grant", "code unknown, used or expired")
    if f.get("client_id") != g["client_id"] or f.get("redirect_uri") != g["redirect_uri"]:
        return err("invalid_grant", "client_id or redirect_uri does not match the code")
    digest = base64.urlsafe_b64encode(hashlib.sha256(f.get("code_verifier", "").encode()).digest())
    if digest.rstrip(b"=").decode() != g["challenge"]:
        return err("invalid_grant", "PKCE verifier does not match")
    now = int(time.time())
    claims = {"iss": UP, "aud": RESOURCE, "sub": g["sub"], "client_id": g["client_id"],
              "scope": "issues:write", "iat": now, "exp": now + 600}
    return JSONResponse({"access_token": jwt.encode({"alg": "HS256"}, claims, key()),
                         "token_type": "Bearer", "expires_in": 600})

# %% [markdown]
# Routes: the Trackr tools. `/mcp` checks the token, then runs `count_open`, `close_issue` or `sync_upstream`. In the weak mode, `sync_upstream` forwards the client's token as it is.

# %%
%%writefile -a ../apps/31/trackr_proxy.py

def upstream_token():
    """The proxy's own token for the upstream API: client credentials, with the API as audience."""
    r = httpx.post(f"{UP}/token", data={"grant_type": "client_credentials", "client_id": "trackr-proxy",
                   "client_secret": CLIENT_CRED, "resource": API}, timeout=10)
    return r.json()["access_token"]

async def mcp(request):
    body = await request.json()
    p = body.get("params", {})
    claims, reason = check_token(request)
    if claims is None:
        return Response(json.dumps({"error": "invalid_token", "error_description": reason}), status_code=401,
                        media_type="application/json", headers={"WWW-Authenticate": 'Bearer error="invalid_token"'})
    name, args = p.get("name"), p.get("arguments", {})
    if name == "count_open":
        text = str(base.count_open(args["team"]))
    elif name == "close_issue":
        text = json.dumps(base.close_issue(args["issue_id"]))
    elif name == "sync_upstream":
        # Weak: the client's token goes upstream unchanged. Fixed: the proxy calls with its own token.
        auth = request.headers["authorization"] if MODE == "weak" else f"Bearer {upstream_token()}"
        r = httpx.post(f"{API}/close/{args['issue_id']}", headers={"Authorization": auth}, timeout=10)
        text = f"upstream {r.status_code}: {r.text}"
    else:
        return err("unknown_tool", str(name))
    return JSONResponse({"jsonrpc": "2.0", "id": body.get("id"),
                         "result": {"content": [{"type": "text", "text": text}], "isError": False}})

async def health(request):
    return JSONResponse({"ok": True, "mode": MODE})

app = Starlette(routes=[Route("/health", health), Route("/authorize", authorize),
                        Route("/consent", consent, methods=["POST"]), Route("/callback", callback),
                        Route("/token", token, methods=["POST"]), Route("/mcp", mcp, methods=["POST"])])

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8771, log_level="warning")

# %% [markdown]
# ### 4. Start the upstream and the weak proxy
# A small helper starts each server and polls its `/health` route. It gives up after 20 seconds and shows the log. Each process has its own log file. The helper stops the servers when the notebook ends.

# %%
procs = {}

def start(name, script, port, env_extra=None):
    stop(name)
    log = open(APPS / f"{name}.log", "w")
    p = subprocess.Popen([sys.executable, str(APPS / script)], env={**os.environ, **(env_extra or {})},
                         stdout=log, stderr=subprocess.STDOUT)
    deadline = time.monotonic() + 20
    while True:
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/health", timeout=2)
            break
        except httpx.ConnectError:
            if p.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError(f"{name} did not start: read ../apps/31/{name}.log")
            time.sleep(0.2)
    procs[name] = (p, log)
    return r.json()

def stop(name):
    if name in procs:
        p, log = procs.pop(name)
        if p.poll() is None:
            p.terminate()
            p.wait(timeout=10)
        log.close()

# %% [markdown]
# Start the two servers. The notebook stops them at the end, even if a cell fails.

# %%
atexit.register(lambda: [stop(n) for n in list(procs)])
print("servers stop when the notebook ends")
print("upstream:", start("upstream", "upstream.py", 9100))
print("proxy:", start("proxy", "trackr_proxy.py", 8771, {"TRACKR_MODE": "weak"}))

# %% [markdown]
# ### 5. The browser and the client
# Three helpers play the parts. `step` is one HTTP request with a cookie jar. It keeps the cookies it is given, because `http.cookiejar` will not send `Secure` cookies over plain http, and the consent cookie has `Secure`. `login_flow` is the victim's browser running a client's login. It follows the redirects by hand and stops where the browser would hand the code to `redirect_uri`. `exchange` trades the code for a token.

# %%
def step(method, url, jar, data=None):
    """One request. Cookies from the jar are sent by hand. Set-Cookie headers are read back into the jar."""
    headers = {"Cookie": "; ".join(f"{k}={v}" for k, v in jar.items())} if jar else {}
    r = httpx.request(method, url, data=data, headers=headers, follow_redirects=False, timeout=10)
    for raw in r.headers.get_list("set-cookie"):
        name, value = raw.split(";")[0].split("=", 1)
        jar[name] = value
    return r

def s256(verifier):
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()

def claims_of(token):
    """Read a JWT's claims without checking the signature. Reading is not trusting."""
    return json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))

print("helpers ready: step, s256, claims_of")

# %% [markdown]
# The token helpers call the upstream and the proxy. `mcp_call` sends one JSON-RPC `tools/call`, and `show` prints the answer.

# %%
def client_credentials(client_id, secret, resource):
    r = httpx.post(f"{UP}/token", data={"grant_type": "client_credentials", "client_id": client_id,
                   "client_secret": secret, "resource": resource}, timeout=10)
    return r.json()["access_token"]

def mcp_call(token, name, arguments):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
    r = httpx.post(f"{ME}/mcp", json=body, headers=headers, timeout=10)
    return r.status_code, r.json()

def show(status, body):
    if "result" in body:
        print(status, "|", body["result"]["content"][0]["text"])
    else:
        print(status, "|", body["error_description"])

def exchange(flow, client_id, redirect_uri):
    return httpx.post(f"{ME}/token", data={"grant_type": "authorization_code", "code": flow["code"],
                      "client_id": client_id, "redirect_uri": redirect_uri,
                      "code_verifier": flow["verifier"]}, timeout=10)
print("helpers ready: client_credentials, mcp_call, show, exchange")

# %% [markdown]
# `login_flow` puts the pieces together. The client makes a PKCE pair and sends its own redirect. The browser follows each redirect. The code is captured where the browser would hand it over.

# %%
def login_flow(client_id, redirect_uri, jar, allow=True):
    """The client starts a login and the browser in `jar` follows it, stopping where a code would be handed over."""
    verifier = secrets.token_urlsafe(48)
    params = {"response_type": "code", "client_id": client_id, "redirect_uri": redirect_uri, "state": "client-state-1",
              "code_challenge": s256(verifier), "code_challenge_method": "S256"}
    url, hops = f"{ME}/authorize?" + urlencode(params), []
    result = {"verifier": verifier, "code": None, "set_cookie": [], "callback": None}
    for _ in range(8):
        if url.startswith(f"{ME}/callback"): result["callback"] = url
        r = step("GET", url, jar)
        hops.append((r.status_code, urlparse(url).netloc + urlparse(url).path))
        if r.status_code == 200:                                   # a consent page from the proxy
            if not allow:
                return {**result, "hops": hops, "stopped": "consent page shown, the user did not click Allow"}
            r = step("POST", f"{ME}/consent", jar, data={**params, "decision": "allow"})
            hops.append((r.status_code, "POST /consent"))
            result["set_cookie"] = [c for c in r.headers.get_list("set-cookie")]
        if r.status_code not in (301, 302, 303, 307):
            return {**result, "hops": hops, "stopped": f"HTTP {r.status_code}: {r.text[:110]}"}
        loc = urljoin(url, r.headers["location"])
        if loc.startswith(redirect_uri):
            q = parse_qs(urlparse(loc).query)
            return {**result, "hops": hops, "code": q["code"][0], "location": loc, "stopped": ""}
        url = loc
    return {**result, "hops": hops, "stopped": "too many redirects"}

# %% [markdown]
# ### 6. The victim signs in to the company login
# The victim logs in once. The upstream sets a session cookie, and it remembers that the victim approved `trackr-proxy`. Nothing about the proxy's own consent is stored yet. This is the only trust the victim has given.

# %%
victim = {}                                                       # the victim's browser: one cookie jar
r = step("GET", f"{UP}/login?user=ops-user", victim)
print(r.json(), "| cookies in the browser:", sorted(victim))

# %% [markdown]
# ### 7. The honest run: the ops desk gets a token
# The ops desk is a real client of Trackr. It starts its login, the browser follows the redirects, and the desk trades the code for a token. The token's audience is Trackr. Then the desk counts the open web issues. Nothing here looks wrong, which is why the bugs are easy to miss.

# %%
flow = login_flow("ops-desk", OPS_REDIRECT, victim)
print("hops:", flow["hops"])
print("stopped:", flow["stopped"] or "code reached the ops desk")
ops_token = exchange(flow, "ops-desk", OPS_REDIRECT).json()["access_token"]
print("token aud:", claims_of(ops_token)["aud"])
show(*mcp_call(ops_token, "count_open", {"team": "web"}))

# %% [markdown]
# ### 8. Attack 1: a token for another server, and token passthrough
# Another team's app, `notes-app`, has its own token for its own server. Its audience is `NOTES_AUD`. The weak proxy checks only the signature and the expiry, so it accepts this token. It closes issue 1 for a stranger who should not have access to Trackr at all.

# %%
notes_token = client_credentials("notes-app", os.environ["LAB_NOTES_CLIENT_SECRET"], NOTES_AUD)
print("notes-app token aud:", claims_of(notes_token)["aud"])
show(*mcp_call(notes_token, "close_issue", {"issue_id": 1}))

# %% [markdown]
# Now the passthrough. The ops desk's own token asks Trackr to sync issue 2 upstream. The weak proxy hands the client's token to the upstream API unchanged. The upstream accepts it, because it checks only the signature. The upstream log now holds a Trackr token that it was never meant to see.

# %%
show(*mcp_call(ops_token, "sync_upstream", {"issue_id": 2}))
print("upstream's log, last call:", httpx.get(f"{UP}/received").json()[-1])

# %% [markdown]
# ### 9. Attack 2: the confused deputy
# The attacker builds a login for a client called `evil-client`, with its own PKCE pair and the redirect `EVIL`. The attacker sends a link to the victim. The victim's browser has an upstream session, so the upstream approves `trackr-proxy` without a screen. The proxy does not check the client or the redirect, so it sends a code to `EVIL`.

# %%
evil = login_flow("evil-client", EVIL, victim)                    # the victim's browser runs the attacker's link
print("hops:", evil["hops"])
print("stopped:", evil["stopped"] or "the code reached the attacker at EVIL")

# %% [markdown]
# The attacker kept the verifier, because the attacker made the PKCE pair. It trades the code at the proxy and gets a token for the victim. Then it closes issue 4.

# %%
atk_token = exchange(evil, "evil-client", EVIL).json()["access_token"]
print("attacker token sub:", claims_of(atk_token)["sub"], "| aud:", claims_of(atk_token)["aud"])
show(*mcp_call(atk_token, "close_issue", {"issue_id": 4}))

# %% [markdown]
# The weak proxy keeps the state after the callback. Replay the same callback URL: the weak proxy still looks the state up and calls the upstream, which refuses the used code (502). The state alone does not stop the replay.

# %%
r = step("GET", evil["callback"], victim)
print(r.status_code, r.text[:120])

# %% [markdown]
# ### 10. The fixed proxy: the honest run still works
# Now the proxy runs in `fixed` mode. The upstream is the same. The honest run now meets a consent page. The victim clicks Allow, and the proxy sets a `__Host-` cookie for this client. The cookie has `Secure`, `HttpOnly`, `SameSite` and `Path=/`, and no `Domain`.

# %%
print("proxy:", start("proxy", "trackr_proxy.py", 8771, {"TRACKR_MODE": "fixed"}))
flow = login_flow("ops-desk", OPS_REDIRECT, victim, allow=True)
print("hops:", flow["hops"])
print("consent cookie:", flow["set_cookie"][0])
ops_token = exchange(flow, "ops-desk", OPS_REDIRECT).json()["access_token"]
print("token aud:", claims_of(ops_token)["aud"])
show(*mcp_call(ops_token, "count_open", {"team": "web"}))

# %% [markdown]
# ### 11. The fixed proxy: the attacks stop
# Three tries. An unknown client is refused. A registered client with the attacker's redirect is refused, because the redirect does not match exactly. A second registered client that the victim never approved gets a consent page, and nothing is sent until the victim clicks Allow.

# %%
for client_id, redirect, allow in [("evil-client", EVIL, True), ("ops-desk", EVIL, True),
                                   ("trackr-cli", "http://127.0.0.1:9998/callback", False)]:
    res = login_flow(client_id, redirect, victim, allow=allow)
    print(f"{client_id:12} code sent: {res['code'] is not None} | {res['stopped']}")

# %% [markdown]
# The state is single use. The callback from the honest run has already been used once, so a replay fails before the proxy talks to the upstream.

# %%
r = step("GET", flow["callback"], victim)
print(r.status_code, r.json()["error_description"])

# %% [markdown]
# Now the two token attacks. The notes token has the wrong audience, so Trackr refuses it (401). The passthrough no longer sends the client's token: the upstream sees the proxy's own token, with the upstream API as audience.

# %%
show(*mcp_call(notes_token, "close_issue", {"issue_id": 1}))
show(*mcp_call(ops_token, "sync_upstream", {"issue_id": 2}))
print("upstream's log, last call:", httpx.get(f"{UP}/received").json()[-1])
stop("proxy")

# %% [markdown]
# ## At work
# - Proxies that front a third-party login with one static client ID are the usual confused-deputy case. The MCP authorization spec asks for per-client consent, exact redirect-URI matching, single-use state and `__Host-` cookies (RESEARCH.md §8). One central gateway can enforce these for many servers → lesson 40.
# - Passthrough hurts most when the upstream does not check audience. The upstream here accepted a token it should refuse, and a correct server should not depend on that. For upstream calls, a server uses a token for that API → lesson 35 (token exchange and client credentials).
# - Teams that run one authorization server for the whole company set an audience per resource server, so a token for one server is refused by the others → lesson 34.

# %% [markdown]
# ## What just happened
# - The weak proxy checked the signature and the expiry, and nothing else. A token minted for `notes-app` closed a Trackr issue. That is a missing audience check.
# - The weak proxy forwarded the ops desk's token to the upstream API. The upstream accepted it. The forwarded token was never for the upstream.
# - The upstream approved `trackr-proxy` without a screen, because the victim had approved it once. The proxy did not check which client asked, nor which redirect it named. So the attacker's client got a code for the victim's account.
# %% [markdown]
# - PKCE did not stop the attack. PKCE stops a stolen code from being used by someone who does not hold the verifier. Here the attacker started the flow and kept the verifier.

# %% [markdown]
# - The hardened proxy stops these two attacks, and only these. It does five things. It checks the audience. It calls the upstream with its own token. It registers each client and matches each redirect exactly. It shows consent per client, kept in a `__Host-` cookie. It makes each state single use, expiring after ten minutes.
# - Still missing: the consent POST has no CSRF token and no `frame-ancestors` / `X-Frame-Options: DENY` (RESEARCH.md §8, item 7). The state is not bound to the browser. The consent cookie is keyed by client only, not by user. The upstream API still has no audience check.

# %% [markdown]
# - The notebook sends the consent cookie by hand. `http.cookiejar` does not send a `Secure` cookie over plain http, and this lab is plain http on localhost. A real browser sends `Secure` cookies only over https, and on localhost in most browsers.

# %% [markdown]
# ## Common mistakes
# Sending a redirect the proxy never registered. The fixed proxy refuses it with a 400, before any login step. A prefix check is worse: `callback.evil.example` starts with the registered URI, so a prefix test would pass it. The cell starts the fixed proxy and asks for the attacker's redirect. `raise_for_status` raises the error the proxy gives:

# %% tags=["raises-exception"]
print("proxy:", start("proxy", "trackr_proxy.py", 8771, {"TRACKR_MODE": "fixed"}))
r = httpx.get(f"{ME}/authorize", params={"response_type": "code", "client_id": "ops-desk", "redirect_uri": EVIL,
              "state": "x", "code_challenge": s256("v" * 43), "code_challenge_method": "S256"},
              follow_redirects=False, timeout=10)
print(r.status_code, r.json()["error_description"])
r.raise_for_status()

# %% [markdown]
# The fix is an exact string match. The prefix test says True, but the exact check says False, so the check refuses the URI:

# %%
registered = "http://127.0.0.1:9999/callback"
evil_uri = "http://127.0.0.1:9999/callback.evil.example/steal"
print("prefix check:", evil_uri.startswith(registered))
print("exact check:", evil_uri in [registered])
print("refused" if evil_uri not in [registered] else "accepted")
stop("proxy")

# %% [markdown]
# Sending a client's redirect to the upstream and expecting a redirect back. The upstream answers 400 to a redirect it does not know, so the request fails. `raise_for_status` raises the error:

# %% tags=["raises-exception"]
r = httpx.get(f"{UP}/authorize", params={"client_id": "trackr-proxy", "redirect_uri": EVIL,
              "response_type": "code", "state": "x"}, cookies=victim, follow_redirects=False)
r.raise_for_status()

# %% [markdown]
# The fix: send the redirect the upstream has registered for `trackr-proxy`, which is `{ME}/callback`. The upstream answers with a 302, and the code is in the Location:

# %%
r = httpx.get(f"{UP}/authorize", params={"client_id": "trackr-proxy", "redirect_uri": f"{ME}/callback",
              "response_type": "code", "state": "x"}, cookies=victim, follow_redirects=False)
print(r.status_code, "| Location:", r.headers["location"])

# %% [markdown]
# ## Production checklist
# - Register each client and its redirect URIs. Compare them as whole strings, and never redirect to a URI you have not checked.
# - Show a consent page for each client. One approval for your own client ID does not cover a new client.
# - Check the audience of every token. Refuse any token that was not issued for this server.
# - Never forward a client's token to an upstream API. Make the upstream call with your own token for that API.
# - Make each state single use, expire it, and set consent cookies as `__Host-` cookies with `Secure`, `HttpOnly` and `SameSite`.

# %% [markdown]
# ## Try it
# Write `wrong_audience(token, want)`. It returns True when the token's `aud` is not `want`. Read the claims with `claims_of` from step 5. Then run it on `notes_token` with `TRACKR_AUD`, and on `ops_token` with `TRACKR_AUD`. The first should be True and the second False.

# %%
# your code here

# %% [markdown]
# ## Key terms
# - **token passthrough** — a server accepts a token that was not issued to it, or forwards a client's token to another API. The MCP spec forbids both.
# - **confused deputy** — a proxy acts with its own authority for a stranger, because the third party trusts the proxy's client ID and the proxy does not check who asked.
# - **per-client consent** — a consent screen for each client, so one approval does not cover a new client.
# - **exact redirect URI** — the registered redirect URI compared as a whole string. Never a prefix.
# - **single-use state** — a state value that works once and expires. A replayed callback finds nothing.
# - **`__Host-` cookie** — a cookie named with the `__Host-` prefix. Browsers accept it only with `Secure`, `Path=/` and no `Domain`.
# - **audience** — the `aud` claim: the server a token was issued for (lesson 15).

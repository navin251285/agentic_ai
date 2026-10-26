# %% [markdown]
# # 13 · Authentication, secrets and least privilege in a customer system
#
# Level L3 · Part 2 · core · ~30 min · builds on 04

# %% [markdown]
# ## Goal
#
# By the end you can give one integration its own **service account**, get a short-lived token that holds only the scopes it needs, keep its client secret out of the code, and show a table of who can call what, with the real status codes.

# %% [markdown]
# ## Why it matters
#
# Lesson 04 sent one shared bearer token with every call. That is fine for a script on your laptop. In a customer system it causes three problems: every caller can do everything, one leaked key opens everything, and rotating the key breaks every caller at once.
#
# The count below uses three invented callers (a reader, a credit bot and a dashboard) and the two permissions they touch. The dashboard appears only in this count; the rest of the lesson uses the reader and the credit bot. Only pure Python, no server yet.

# %%
# Scopes are named permissions. What each caller really needs:
needs = {"reader": {"orders:read"},
         "credit bot": {"orders:read", "credits:write"},
         "dashboard": {"orders:read"}}
all_scopes = {"orders:read", "credits:write"}  # what one shared key grants

granted = len(needs) * len(all_scopes)           # one shared key, given to every caller
needed = sum(len(scopes) for scopes in needs.values())
print(f"shared key grants {granted} permissions; the callers need {needed}")
print(f"extra permissions: {granted - needed}. A leaked key opens every scope ({len(all_scopes)} here).")

# %% [markdown]
# - **Without it:** one key for everyone. The dashboard can write credits, and a leaked key gives the attacker the whole API.
# - **With it:** one service account per integration, one scope per permission, and a secret that lives in the secret store.
# - **When you don't need it:** a throwaway prototype on your laptop. Never for a customer system.

# %% [markdown]
# ## The idea
#
# A **service account** is an identity for software, not for a person. Its **client secret** works like a password, and it stays out of code. To call the API, the account trades its ID and secret for an **access token**: a short-lived pass that lists its **scopes**, such as `orders:read`. The customer's API checks the token's signature and its scope on every call. This is the OAuth 2.0 **client credentials** grant.
#
# People log in another way, with **SSO**: SAML or OpenID Connect (OIDC) through the customer's identity provider. You set that up with the customer's IT team; you rarely write it yourself.
#
# Analogy: a hotel key card that opens one floor and stops working at checkout, not the master key.

# %% [markdown]
# ## Picture
#
# The account gets a token once, then sends it on each call. The API decides per endpoint.

# %% [markdown]
# ```mermaid
# sequenceDiagram
#     participant S as Service account (our code)
#     participant A as Customer API and token endpoint
#     S->>A: client ID + secret, scope orders:read
#     A-->>S: access token, valid 5 minutes
#     S->>A: GET /orders with the token
#     A-->>S: 200 (scope orders:read present)
#     S->>A: POST /credits with the same token
#     A-->>S: 403 insufficient_scope
# ```

# %% [markdown]
# ## Step by step

# %% [markdown]
# ### Step 1: the customer's API
#
# The mock customer API is a real HTTP server on this lesson's port (8130). Its code is in `../apps/13/customer_api.py`, written by the cell below. The accounts, the orders and the signing key are **invented**. The API has a token endpoint, and it checks the scope of every token. Read only `/oauth/token` and `require_scope`; the rest is scaffolding.

# %%
%%writefile ../apps/13/customer_api.py
"""Basket Bazaar mock customer API: service accounts and scoped tokens. INVENTED data, lab only."""
import base64
import hmac
import os
import time
from urllib.parse import parse_qs

import jwt
from fastapi import Body, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

AUDIENCE = "basket-bazaar-erp"  # the API a token is meant for
TOKEN_SECONDS = 300             # a leaked token stops working after 5 minutes
SIGNING_KEY = os.environ["ERP_SIGNING_KEY"]  # set from .env by the notebook; never written in code
CLIENTS = {  # the customer's registry: each account may ask only for the scopes listed here
    "bb-orders-reader": {"secret_env": "ERP_READER_CLIENT_SECRET", "scopes": {"orders:read"}},
    "bb-credit-bot": {"secret_env": "ERP_CREDIT_BOT_CLIENT_SECRET", "scopes": {"orders:read", "credits:write"}},
}
ORDERS = [{"id": f"BB-{1000 + i}", "lines_short": n} for i, n in enumerate([2, 0, 1, 3])]
CREDITS: list[dict] = []
app = FastAPI(title="Basket Bazaar mock customer API (invented)")


def oauth_error(status: int, error: str, text: str) -> JSONResponse:
    return JSONResponse({"error": error, "error_description": text}, status_code=status)


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/oauth/token")
async def issue_token(request: Request, authorization: str | None = Header(default=None)):
    client_id, secret = "", ""
    if authorization and authorization.startswith("Basic "):
        client_id, _, secret = base64.b64decode(authorization[6:]).decode().partition(":")
    form = parse_qs((await request.body()).decode())
    account = CLIENTS.get(client_id)
    expected = os.environ.get(account["secret_env"], "") if account else ""
    if not account or not hmac.compare_digest(secret.encode(), expected.encode()):
        return oauth_error(401, "invalid_client", "unknown account or wrong secret")
    if form.get("grant_type", [""])[0] != "client_credentials":
        return oauth_error(400, "unsupported_grant_type", "only client_credentials here")
    asked = set(form.get("scope", [""])[0].split())
    if not asked or not asked <= account["scopes"]:
        return oauth_error(400, "invalid_scope", "the account does not hold every scope asked for")
    now, scope = int(time.time()), " ".join(sorted(asked))
    token = jwt.encode({"sub": client_id, "aud": AUDIENCE, "scope": scope,
                        "iat": now, "exp": now + TOKEN_SECONDS}, SIGNING_KEY, algorithm="HS256")
    return {"access_token": token, "token_type": "Bearer", "expires_in": TOKEN_SECONDS, "scope": scope}


def require_scope(needed: str):
    """Checked on every call: signed by us, not expired, meant for this API, and holds the scope."""
    def check(authorization: str | None = Header(default=None)) -> dict:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, detail="invalid_token: no bearer token")
        try:
            claims = jwt.decode(authorization[7:], SIGNING_KEY, algorithms=["HS256"], audience=AUDIENCE)
        except jwt.InvalidTokenError as err:
            raise HTTPException(401, detail=f"invalid_token: {type(err).__name__}")
        if needed not in claims.get("scope", "").split():
            raise HTTPException(403, detail=f"insufficient_scope: needs {needed}")
        return claims
    return check


@app.get("/orders", dependencies=[Depends(require_scope("orders:read"))])
def list_orders():
    return {"data": ORDERS, "total": len(ORDERS)}


@app.post("/credits", dependencies=[Depends(require_scope("credits:write"))])
def create_credit(order_id: str = Body(), item: str = Body(), qty: int = Body(ge=1)):
    credit = {"order_id": order_id, "item": item, "qty": qty}
    CREDITS.append(credit)
    return {"credit_id": f"CR-{len(CREDITS)}", **credit}

# %% [markdown]
# ### Step 2: the secrets come from `.env`
#
# The notebook never holds a secret in a cell. `env()` reads each value from the topic's `.env` file, and the lab defaults in `.env.example` cover this lesson. If `.env` does not have these names yet, copy them from `.env.example`. The cell prints only whether each value is set. The values are then exported, so the mock customer API started in the next step can read them.

# %%
import os, sys

sys.path.insert(0, "..")
from tut_env import env

for name in ("ERP_SIGNING_KEY", "ERP_READER_CLIENT_SECRET", "ERP_CREDIT_BOT_CLIENT_SECRET"):
    os.environ[name] = env(name)  # exported for the mock; never printed
    print(f"{name} set:", bool(os.environ[name]))

# %% [markdown]
# Now start the mock. The cell checks that the port is free, starts the server and polls `/health` for up to 15 seconds.

# %%
import atexit, socket, subprocess, time

import httpx

PORT = 8130  # this lesson's port (progress.py --ports 13)
BASE = f"http://127.0.0.1:{PORT}"

with socket.socket() as probe:
    if probe.connect_ex(("127.0.0.1", PORT)) == 0:
        raise RuntimeError(f"port {PORT} is already in use: stop the other process first")

server = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "customer_api:app", "--app-dir", os.path.abspath("../apps/13"),
     "--port", str(PORT), "--log-level", "warning"])
atexit.register(server.terminate)  # also stops the server if the kernel exits early

deadline = time.time() + 15
while True:
    try:
        if httpx.get(f"{BASE}/health", timeout=0.5).status_code == 200:
            break
    except httpx.TransportError:
        pass  # not listening yet
    if time.time() > deadline:
        raise RuntimeError("the mock customer API did not start")
    time.sleep(0.2)
print("mock customer API is up")

# %% [markdown]
# ### Step 3: a service account gets a token
#
# The helper below is the whole client side. `OAuth2Client` from the **authlib** library sends the ID and secret to the token endpoint, stores the token and attaches it to every later call. The secret is read with `env()` and is never printed.

# %%
from authlib.integrations.httpx_client import OAuth2Client
import jwt


def service_session(client_id: str, secret_env: str, scope: str) -> OAuth2Client:
    """A service account: it trades its ID and secret for a scoped token, then sends the token on each call."""
    session = OAuth2Client(client_id, env(secret_env), scope=scope, token_endpoint_auth_method="client_secret_basic")
    session.fetch_token(f"{BASE}/oauth/token", grant_type="client_credentials")
    return session


reader = service_session("bb-orders-reader", "ERP_READER_CLIENT_SECRET", "orders:read")
claims = jwt.decode(reader.token["access_token"], options={"verify_signature": False})  # reading is not checking
print("sub:", claims["sub"], "| scope:", claims["scope"], "| lifetime:", claims["exp"] - claims["iat"], "s")

# %% [markdown]
# The token holds the account's name, its scope and an expiry time. A JWT is **signed, not encrypted**: anyone who holds it can read the claims, so treat it like a password. What protects it is the signature, which only the server can make. Here one shared key signs and checks; real identity providers usually sign with a private key and publish a public key. The secret itself is sent once, to the token endpoint, and not again.

# %% [markdown]
# ### Step 4: the scope decides each call
#
# The reader can read orders. The same token is refused when it writes a credit, with `403` and the scope it lacks. `403` means "known, but not allowed". `401` means no valid token: it is missing, forged or expired. The credit bot holds `credits:write` too, so its write works.

# %%
ok = reader.get(f"{BASE}/orders")  # the customer's system holds 4 invented orders
print("reader GET /orders:", ok.status_code, "| orders:", ok.json()["total"])
denied = reader.post(f"{BASE}/credits", json={"order_id": "BB-1001", "item": "milk", "qty": 1})
print("reader POST /credits:", denied.status_code, denied.json()["detail"])

# The credit bot holds credits:write too, so its write works. The reply carries the credit id, so no extra call.
bot = service_session("bb-credit-bot", "ERP_CREDIT_BOT_CLIENT_SECRET", "orders:read credits:write")
written = bot.post(f"{BASE}/credits", json={"order_id": "BB-1003", "item": "eggs", "qty": 2})
print("credit bot POST /credits:", written.status_code, "| credit id:", written.json()["credit_id"])

# %% [markdown]
# ### Step 5: who can call what
#
# Put every caller against every endpoint and read the status codes. Add two callers that should fail: a token forged with a guessed key, and no token at all. The forged token claims `credits:write`, but its signature is wrong.
# %%
forged =jwt.encode({"sub": "bb-orders-reader", "aud": "basket-bazaar-erp", "scope": "credits:write",
                     "exp": int(time.time()) + 300}, "guess-the-key-that-is-not-the-real-one-0123", algorithm="HS256")
CREDIT = {"order_id": "BB-1003", "item": "eggs", "qty": 2}
callers = {"reader": reader, "credit bot": bot,
           "forged token": httpx.Client(headers={"Authorization": f"Bearer {forged}"}),
           "no token": httpx.Client()}

print(f"{'caller':<14}{'GET /orders':<14}{'POST /credits'}")
for who, session in callers.items():
    read = session.get(f"{BASE}/orders").status_code
    write = session.post(f"{BASE}/credits", json=CREDIT).status_code
    print(f"{who:<14}{read:<14}{write}")
print("forged token, write:", callers["forged token"].post(f"{BASE}/credits", json=CREDIT).json()["detail"])

# %% [markdown]
# Only the credit bot can write. The forged token and the missing token both get `401`: the forged one fails the signature check, and the missing one has no token to check. Read the detail, not just the number: `invalid_token: InvalidSignatureError` says the signature was checked and failed. Keep this table as a test; a security review will ask for it.

# %% [markdown]
# ## At work
#
# - Security reviews ask which integration holds which scope and where its secret lives, before go-live. Answer with a table like Step 5. → lesson 27 covers the review pack.
# - Least privilege is enforced in code on every call. An agent with a write tool gets its own scope, and the server refuses the call even if the prompt asks. → lesson 19 (agent tools) and lesson 23 (tenancy).
# - Secrets reach the app as environment variables at deploy time, never in the repo or the image. → lesson 14 (deploy config) and lesson 15 (restricted networks).
# - Expired tokens and rotated secrets break jobs at night. The runbook names who rotates a secret. → lesson 17.
#
# Go deeper: SAML and OIDC login flows for people, which you set up with the customer's identity provider.

# %% [markdown]
# ## Common mistakes
#
# - **Calling `raise_for_status()` on a refused call.** A `403` raises an error. Here the reader writes a credit, and the error prints with its status code.

# %% tags=["raises-exception"]
# The reader has no credits:write scope, so the server answers 403 and raise_for_status() raises.
reader.post(f"{BASE}/credits", json=CREDIT).raise_for_status()

# %% [markdown]
# - **Reading a token's claims and trusting them.** Decoding without verifying shows whatever the token says, even a forged one. The forged token from Step 5 claims `credits:write`, and the wrong code believes it.

# %%
# WRONG: reading the claims is not checking them. The signature was never verified.
trusted = jwt.decode(forged, options={"verify_signature": False})
print("trusted scope:", trusted["scope"], "(wrong: the server would refuse this token, see Step 5)")

# %% [markdown]
# The fix is to verify with the key, as the mock does in `require_scope`: `jwt.decode(token, key, algorithms=[...], audience=...)`.
#
# - **A secret written into a cell or a file in git.** Read it with `env()`, add a placeholder to `.env.example`, and print `bool(...)`. Rotate any secret that was ever committed.

# %% [markdown]
# ## Try it
#
# Two checks for the customer's API. Write the two functions. Predict each result first.
#
# - **A:** send a token that expired 60 seconds ago, signed with the real key and holding `orders:read`, to `GET /orders`. Return the status code and the detail.
# - **B:** ask the token endpoint for `credits:write` with the reader account. Return the error name and the error code.

# %%
# your code here
def expired_token_check() -> tuple[int, str]:
    """Build a token that expired 60 s ago, signed with the real key. Return (status, detail) from GET /orders."""

def reader_asks_for_write() -> str:
    """Ask the token endpoint for credits:write with the reader account. Return the error name and text."""

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
def expired_token_check() -> tuple[int, str]:
    now = int(time.time())
    token = jwt.encode({"sub": "bb-orders-reader", "aud": "basket-bazaar-erp", "scope": "orders:read",
                        "iat": now - 400, "exp": now - 60}, env("ERP_SIGNING_KEY"), algorithm="HS256")
    response = httpx.get(f"{BASE}/orders", headers={"Authorization": f"Bearer {token}"})
    return response.status_code, response.json()["detail"]

def reader_asks_for_write() -> str:
    from authlib.integrations.base_client import OAuthError
    try:
        service_session("bb-orders-reader", "ERP_READER_CLIENT_SECRET", "credits:write")
    except OAuthError as err:
        return f"{type(err).__name__}: {err.error}"
    return "a token was issued: that would be a bug"

print("A, expired token:", expired_token_check())
print("B, ask for a scope the account does not hold:", reader_asks_for_write())

# %% [markdown]
# A `401` with `ExpiredSignatureError` means the server checks expiry on every call. B shows the token endpoint refusing a scope that is not in the account's registry, so the token is never issued.

# %% [markdown]
# ## Recap
#
# - One service account per integration. Never share one key among callers.
# - The client secret comes from the secret store (here `.env`). Print only `bool(...)`, never the value.
# - Tokens are short-lived and carry scopes. The API checks the signature, expiry, audience and scope on every call.
# - `401` means no valid identity; `403` means a valid identity without the scope. Keep a table of who can call what as a test.
# - Words to keep: **service account**, **client credentials**, **access token**, **JWT**, **scope**, **least privilege**, **OIDC**, **SAML SSO** (all in GLOSSARY.md).
# - **Interview:** "An integration must read orders and write credits. How do you give it access?" Strong answer: "A dedicated service account with only those two scopes, a client-credentials token that expires in minutes, the secret in the customer's secret manager, the scope checked on every endpoint, and a who-can-call-what table for the security review. SSO is for people, not for this."

# %%
# Stop the mock customer API now that the lesson is done.
server.terminate(); server.wait(timeout=10)
print("mock customer API stopped")

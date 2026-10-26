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

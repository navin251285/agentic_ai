"""Provider route for lesson 28 (lab). It is the customer's only path to the model: every model call
goes through it. While it is up it passes the call on to the provider unchanged. POST /_drill/down makes
it answer 503 to every call, which is what a provider outage looks like from the customer side.
POST /_drill/up restores it. It stores nothing and counts what it forwarded and what it refused."""
import os

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

API_BASE = os.environ["PROVIDER_API_BASE"]  # the provider's API host, set in ../.env (lab default in .env.example)
app = FastAPI(title="Basket Bazaar provider route (lab)", version="1.0.0")
STATE = {"down": False, "forwarded": 0, "refused": 0}
DROP = {"host", "content-length", "accept-encoding", "connection"}  # hop-by-hop headers and re-encoded bodies


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/_drill/state")
def state():
    return STATE


@app.post("/_drill/down")
def down():
    STATE["down"] = True
    return STATE


@app.post("/_drill/up")
def up():
    STATE["down"] = False
    return STATE


@app.post("/{path:path}")
async def forward(path: str, request: Request):
    if STATE["down"]:
        STATE["refused"] += 1
        return JSONResponse({"error": {"code": 503, "status": "UNAVAILABLE",
                                       "message": "lab drill: the model provider is down"}}, status_code=503)
    STATE["forwarded"] += 1
    headers = {k: v for k, v in request.headers.items() if k.lower() not in DROP}
    url = f"{API_BASE}/{path}" + (f"?{request.url.query}" if request.url.query else "")
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(url, headers=headers, content=await request.body())
    return Response(r.content, status_code=r.status_code, media_type=r.headers.get("content-type"))

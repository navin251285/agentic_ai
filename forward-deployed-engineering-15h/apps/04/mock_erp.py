"""Basket Bazaar mock customer API. INVENTED data, lab only: it stands in for a customer's order system."""
import os
import random

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

TOKEN = os.environ.get("MOCK_ERP_TOKEN", "")
rng = random.Random(4)  # fixed seed: the same invented orders on every run
ORDERS = [{"id": f"BB-{1000 + i}", "store": f"Store {rng.randint(1, 12):02d}",
           "lines_short": rng.choice([0, 0, 0, 1, 2])} for i in range(137)]
CREDITS: list[dict] = []
SAVED: dict[str, dict] = {}   # Idempotency-Key -> the body first returned for it
FAULTS: list[str] = []        # faults for the next calls: "429", "503" or "lost"
LOG: list[dict] = []          # one entry per request: method, path, status

app = FastAPI(title="Basket Bazaar mock customer API (invented)")


class Credit(BaseModel):
    order_id: str
    item: str
    qty: int = Field(ge=1)


class Plan(BaseModel):
    faults: list[str]


def require_token(authorization: str | None = Header(default=None)):
    if authorization != f"Bearer {TOKEN}":
        raise HTTPException(401, "missing or wrong bearer token")


def next_fault() -> str | None:
    return FAULTS.pop(0) if FAULTS else None


def error(code: int) -> JSONResponse:
    headers = {"Retry-After": "1"} if code == 429 else {}
    return JSONResponse({"detail": f"injected {code}"}, status_code=code, headers=headers)


@app.middleware("http")
async def log_calls(request: Request, call_next):
    response = await call_next(request)
    LOG.append({"method": request.method, "path": request.url.path, "status": response.status_code})
    return response


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/orders", dependencies=[Depends(require_token)])
def list_orders(limit: int = Query(20, ge=1, le=50), cursor: str = "0"):
    fault = next_fault()
    if fault in ("429", "503"):
        return error(int(fault))
    start, end = int(cursor), int(cursor) + limit
    more = end < len(ORDERS)
    return {"data": ORDERS[start:end], "has_more": more,
            "next_cursor": str(end) if more else None, "total": len(ORDERS)}


@app.post("/credits", dependencies=[Depends(require_token)])
def create_credit(credit: Credit, response: Response,
                  idempotency_key: str | None = Header(default=None)):
    if idempotency_key and idempotency_key in SAVED:  # a repeat: return the first answer, write nothing
        response.headers["Idempotent-Replayed"] = "true"
        return SAVED[idempotency_key]
    fault = next_fault()
    if fault in ("429", "503"):  # rejected before any write
        return error(int(fault))
    CREDITS.append(credit.model_dump())
    body = {"credit_id": f"CR-{len(CREDITS)}", **credit.model_dump()}
    if idempotency_key:
        SAVED[idempotency_key] = body
    if fault == "lost":  # the write happened, but the reply is lost on the way back
        return error(503)
    return body


@app.post("/lab/faults")
def set_faults(plan: Plan):  # lab only: queue faults for the next calls
    FAULTS[:] = plan.faults
    return {"queued": len(FAULTS)}


@app.post("/lab/reset")
def reset():  # lab only: empty the credits, the saved answers and the call log
    for store in (CREDITS, FAULTS, LOG):
        store.clear()
    SAVED.clear()
    return {"ok": True}


@app.get("/lab/state")
def state():  # lab only: what the customer's system holds right now
    return {"credits": CREDITS, "calls": LOG}

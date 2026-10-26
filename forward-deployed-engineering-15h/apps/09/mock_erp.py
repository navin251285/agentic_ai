"""Basket Bazaar mock customer API for the checkpoint (lesson 09). INVENTED data, lab only.

It serves the cleaned order lines from lesson 05 and keeps the credits it receives.
The /lab/ endpoints exist only for this course: a real customer API has none of them.
"""
import csv
import os
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

TOKEN = os.environ.get("MOCK_ERP_TOKEN", "")
ORDERS = Path(__file__).resolve().parents[2] / "data" / "05" / "orders_clean.csv"  # lesson 05's file
with ORDERS.open(newline="") as f:
    LINES = list(csv.DictReader(f))  # one row per order line, as lesson 05 wrote it
CREDITS: list[dict] = []
SAVED: dict[str, dict] = {}   # Idempotency-Key -> the body first returned for it
FAULTS: list[str] = []        # next calls: "429", "503", or "lost" (written, reply lost)

app = FastAPI(title="Basket Bazaar mock customer API (invented, lesson 09)")


class Credit(BaseModel):
    order_id: str
    item: str
    qty: int = Field(ge=1)


class Plan(BaseModel):
    faults: list[str]


def require_token(authorization: str | None = Header(default=None)):
    if authorization != f"Bearer {TOKEN}":
        raise HTTPException(401, "missing or wrong bearer token")


def error(code: int) -> JSONResponse:
    headers = {"Retry-After": "1"} if code == 429 else {}
    return JSONResponse({"detail": f"injected {code}"}, status_code=code, headers=headers)


def next_fault() -> str | None:
    return FAULTS.pop(0) if FAULTS else None


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/orders", dependencies=[Depends(require_token)])
def list_lines(limit: int = Query(20, ge=1, le=50), cursor: str = "0"):
    fault = next_fault()
    if fault in ("429", "503"):
        return error(int(fault))
    start, end = int(cursor), int(cursor) + limit
    more = end < len(LINES)
    return {"data": LINES[start:end], "has_more": more,
            "next_cursor": str(end) if more else None, "total": len(LINES)}


@app.post("/credits", dependencies=[Depends(require_token)])
def create_credit(credit: Credit, response: Response, idempotency_key: str | None = Header(default=None)):
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
    if fault == "lost":  # written, but the reply is lost on the way back
        return error(503)
    return body


@app.post("/lab/faults")
def set_faults(plan: Plan):  # lab only
    FAULTS[:] = plan.faults
    return {"queued": len(FAULTS)}


@app.post("/lab/reset")
def reset():  # lab only: empty the credits and the saved answers
    CREDITS.clear()
    SAVED.clear()
    FAULTS.clear()
    return {"ok": True}


@app.get("/lab/state")
def state():  # lab only: what the customer's system holds right now
    return {"credits": CREDITS}

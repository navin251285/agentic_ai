"""Basket Bazaar customer API mock (lesson 24a). INVENTED data, lab only: it stands in for the customer's order system.

Two lab settings come from the environment: ERP_LATENCY_MS (how long one call takes) and
ERP_MAX_INFLIGHT (how many calls may be in flight at once; a call over that limit gets 429)."""
import csv
import os
import threading
import time

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

LATENCY_S = float(os.environ.get("ERP_LATENCY_MS", "150")) / 1000
MAX_INFLIGHT = int(os.environ.get("ERP_MAX_INFLIGHT", "8"))
ORDERS: dict[str, dict] = {}
with open("/input/orders.csv", newline="") as f:  # the cleaned orders export from lesson 05, mounted read-only
    for row in csv.DictReader(f):  # one row per order line: group the lines under the order
        order = ORDERS.setdefault(row["order_id"], {"order_id": row["order_id"], "store": row["store"], "lines": []})
        order["lines"].append({"item": row["item"], "qty": int(row["qty_base"]), "unit": row["unit_base"]})

_lock = threading.Lock()
_inflight = 0
STATS = {"calls": 0, "rejected_429": 0, "max_inflight": 0}
app = FastAPI(title="Basket Bazaar customer API mock (invented)")


@app.get("/health")
def health():
    return {"ok": True, "orders": len(ORDERS)}


@app.get("/orders/{order_id}")
def get_order(order_id: str):
    global _inflight
    with _lock:
        STATS["calls"] += 1
        if _inflight >= MAX_INFLIGHT:  # too many calls at once: refuse, and say when to try again
            STATS["rejected_429"] += 1
            return JSONResponse({"detail": "too many calls in flight"}, status_code=429, headers={"Retry-After": "1"})
        _inflight += 1
        STATS["max_inflight"] = max(STATS["max_inflight"], _inflight)
    try:
        time.sleep(LATENCY_S)  # the slow part of a real customer system
        if order_id not in ORDERS:
            raise HTTPException(404, detail="order not found")
        return ORDERS[order_id]
    finally:
        with _lock:
            _inflight -= 1


@app.get("/lab/stats")
def stats():  # lab only: what the customer's system saw
    with _lock:
        return dict(STATS)


@app.post("/lab/reset")
def reset():  # lab only: clear the counters before a run
    with _lock:
        STATS.update(calls=0, rejected_429=0, max_inflight=0)
        return dict(STATS)

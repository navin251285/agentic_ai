"""Basket Bazaar orders service, version 1.0.0 (lab, invented data). Reads columns by name."""
import csv

from fastapi import FastAPI, HTTPException

VERSION = "1.0.0"
ORDERS_FILE = "/data/orders.csv"  # the shared file, mounted read-only into the container
app = FastAPI(title="Basket Bazaar orders", version=VERSION)


def load_orders() -> dict[str, dict]:
    with open(ORDERS_FILE, newline="") as f:
        return {row["order_id"]: row for row in csv.DictReader(f)}


ORDERS = load_orders()  # read once at start


@app.get("/health")
def health():
    return {"ok": True, "version": VERSION, "orders": len(ORDERS)}


@app.get("/orders/{order_id}")
def get_order(order_id: str):
    row = ORDERS.get(order_id)
    if row is None:
        raise HTTPException(404, detail="order not found")
    return {"order_id": order_id, "item": row["item"], "qty": int(row["qty"]),
            "unit": row["unit"], "version": VERSION}

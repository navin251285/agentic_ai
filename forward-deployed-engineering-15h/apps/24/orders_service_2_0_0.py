"""Basket Bazaar orders service, version 2.0.0 (lab, invented data). Needs the missing_items column."""
import csv

from fastapi import FastAPI, HTTPException

VERSION = "2.0.0"
ORDERS_FILE = "/data/orders.csv"  # the shared file, mounted read-only into the container
app = FastAPI(title="Basket Bazaar orders", version=VERSION)


def load_orders() -> dict[str, dict]:
    with open(ORDERS_FILE, newline="") as f:
        reader = csv.DictReader(f)
        if "missing_items" not in (reader.fieldnames or []):
            raise RuntimeError("orders file has no missing_items column: migrate the file first")
        return {row["order_id"]: row for row in reader}


ORDERS = load_orders()  # a file without the column stops the start here


@app.get("/health")
def health():
    return {"ok": True, "version": VERSION, "orders": len(ORDERS)}


@app.get("/orders/{order_id}")
def get_order(order_id: str):
    row = ORDERS.get(order_id)
    if row is None:
        raise HTTPException(404, detail="order not found")
    missing = int(row["missing_items"])
    return {"order_id": order_id, "item": row["item"], "qty": int(row["qty"]), "unit": row["unit"],
            "missing_items": missing, "label": "missing items" if missing else "complete",
            "version": VERSION}

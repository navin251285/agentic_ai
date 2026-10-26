"""Basket Bazaar triage service, version 1.0.0 (lab, invented data)."""
import os

import httpx
from fastapi import FastAPI, HTTPException

VERSION = "1.0.0"
ERP_URL = os.environ["ERP_URL"]                        # the customer API, by its Compose service name
CLIENT_ID = os.environ["ERP_READER_CLIENT_ID"]         # the service account for reading orders
CLIENT_SECRET = os.environ["ERP_READER_CLIENT_SECRET"]  # injected from the secret store, never in the image
app = FastAPI(title="Basket Bazaar triage", version=VERSION)


def erp_token() -> str:
    """Client credentials grant (lesson 13): exchange the account's secret for a short-lived token."""
    r = httpx.post(f"{ERP_URL}/oauth/token", auth=(CLIENT_ID, CLIENT_SECRET),
                   data={"grant_type": "client_credentials", "scope": "orders:read"}, timeout=5)
    r.raise_for_status()
    return r.json()["access_token"]


@app.get("/health")
def health():
    return {"ok": True, "version": VERSION}


@app.get("/triage/{order_id}")
def triage(order_id: str):
    r = httpx.get(f"{ERP_URL}/orders", headers={"Authorization": f"Bearer {erp_token()}"}, timeout=5)
    if r.status_code != 200:
        raise HTTPException(502, detail=f"customer API returned {r.status_code}")
    order = next((o for o in r.json()["data"] if o["id"] == order_id), None)
    if order is None:
        raise HTTPException(404, detail="order not found")
    label = "missing items" if order["lines_short"] else "complete"
    return {"order_id": order_id, "label": label, "version": VERSION}

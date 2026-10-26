"""Basket Bazaar triage service, version 1.2.0 (lab, invented data). /explain calls the model API
through the egress proxy (HTTP_PROXY); the customer API inside the network is called directly (NO_PROXY)."""
import os

import httpx
from fastapi import FastAPI, HTTPException

VERSION = "1.2.0"
ERP_URL = os.environ["ERP_URL"]                         # inside the network: http://erp:8000
CLIENT_ID = os.environ["ERP_READER_CLIENT_ID"]
CLIENT_SECRET = os.environ["ERP_READER_CLIENT_SECRET"]  # injected at start-up, never in the image
MODEL_API_URL = os.environ["MODEL_API_URL"]             # outside the network: reached through the proxy
app = FastAPI(title="Basket Bazaar triage", version=VERSION)


def call(method: str, url: str, **kwargs) -> httpx.Response:
    """One outbound call. A failure becomes a 502 that names the host, not a bare 500."""
    host = url.split("/")[2]
    try:
        r = httpx.request(method, url, timeout=5, **kwargs)
    except httpx.HTTPError as e:
        raise HTTPException(502, detail=f"{host} unreachable: {type(e).__name__}") from e
    if r.status_code >= 400:
        raise HTTPException(502, detail=f"{host} returned {r.status_code}")
    return r


def erp_token() -> str:
    """Client credentials grant (lesson 13): the account's secret in exchange for a short-lived token."""
    r = call("POST", f"{ERP_URL}/oauth/token", auth=(CLIENT_ID, CLIENT_SECRET),
             data={"grant_type": "client_credentials", "scope": "orders:read"})
    return r.json()["access_token"]


def read_order(order_id: str) -> dict:
    r = call("GET", f"{ERP_URL}/orders", headers={"Authorization": f"Bearer {erp_token()}"})
    order = next((o for o in r.json()["data"] if o["id"] == order_id), None)
    if order is None:
        raise HTTPException(404, detail="order not found")
    return order


def label_for(order: dict) -> str:
    return "missing items" if order["lines_short"] else "complete"


@app.get("/health")
def health():
    return {"ok": True, "version": VERSION}


@app.get("/triage/{order_id}")
def triage(order_id: str):
    return {"order_id": order_id, "label": label_for(read_order(order_id)), "version": VERSION}


@app.get("/explain/{order_id}")
def explain(order_id: str):
    label = label_for(read_order(order_id))
    r = call("POST", f"{MODEL_API_URL}/v1/draft", json={"order_id": order_id, "label": label})
    return {"order_id": order_id, "label": label, "draft": r.json()["draft"], "version": VERSION}

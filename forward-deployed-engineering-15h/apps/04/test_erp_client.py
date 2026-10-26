"""Checks for the client rules in lesson 04, run against the live mock (port 8040, token from MOCK_ERP_TOKEN)."""
import os

import httpx
import pytest

BASE = "http://127.0.0.1:8040"  # this lesson's port; the mock runs here
HEADERS = {"Authorization": f"Bearer {os.environ['MOCK_ERP_TOKEN']}"}


@pytest.fixture
def client():
    with httpx.Client(base_url=BASE, headers=HEADERS, timeout=5) as c:
        c.post("/lab/reset")
        yield c


def test_every_page_is_read(client):
    orders, cursor = [], "0"
    while cursor is not None:
        body = client.get("/orders", params={"limit": 50, "cursor": cursor}).json()
        orders.extend(body["data"])
        cursor = body["next_cursor"]
    assert len(orders) == client.get("/orders", params={"limit": 1}).json()["total"]


def test_wrong_token_is_refused():
    assert httpx.get(f"{BASE}/orders", headers={"Authorization": "Token nope"}).status_code == 401


def test_keyed_credit_is_written_once(client):
    client.post("/lab/faults", json={"faults": ["lost"]})
    body, key = {"order_id": "BB-1003", "item": "eggs", "qty": 2}, {"Idempotency-Key": "test-credit-1"}
    client.post("/credits", json=body, headers=key)  # the reply is lost
    client.post("/credits", json=body, headers=key)  # the retry
    assert len(client.get("/lab/state").json()["credits"]) == 1

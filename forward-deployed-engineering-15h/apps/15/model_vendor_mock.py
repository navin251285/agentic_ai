"""Lab stand-in for a model API (lesson 15). NOT a model: fixed, invented text, no inference."""
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Lab stand-in for a model API (not a model)")
DRAFTS = {
    "missing items": "Hi, part of your order was short. We will credit the missing items to your account.",
    "complete": "Hi, your order is complete. Thank you for shopping with Basket Bazaar.",
}


class DraftRequest(BaseModel):
    order_id: str
    label: str


@app.get("/health")
def health():
    return {"ok": True, "stand_in": True}


@app.post("/v1/draft")
def draft(req: DraftRequest):
    return {"draft": DRAFTS.get(req.label, "We are looking into your order."), "stand_in": True}

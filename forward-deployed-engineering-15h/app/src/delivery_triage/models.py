"""The request and response shapes of the triage API, and the case form the model fills (lesson 06)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CaseRecord(BaseModel):
    """One support case, filled from a customer message. Same fields as lesson 06, step 2."""

    order_id: str = Field(description="the order number as written, such as BB-1108")
    issue: Literal["missing_item", "wrong_item", "late", "damaged", "other"]
    item: str | None = Field(default=None, description="the item the customer names, in lower case, or null")
    qty_claimed: int | None = Field(default=None, description="how many of that item the customer says they paid for, or null")
    summary: str = Field(description="one short sentence for the support agent")


class TriageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000, description="the customer's message, as written")
    tenant: str | None = Field(
        default=None, max_length=20,
        description="the store the message is about, such as store-07; empty uses the default store (step 3)",
    )


class TriageResult(BaseModel):
    status: Literal["opened", "needs_review"]
    case_id: str = Field(description="the stored case's id, such as DI-00001")
    duplicate: bool = Field(description="true when the same case was already stored, so nothing new was written")
    tenant: str = Field(default="", description="the store the case belongs to")
    trace_id: str = Field(default="", description="the id of this request's trace (step 3, lesson 16)")
    record: CaseRecord
    problems: list[str] = Field(default_factory=list, description="what the check rejected; empty when it passed")


class StoredCase(BaseModel):
    """One row of the stored issues file, as the API returns it."""

    case_id: str
    created_at: str
    tenant: str = ""
    order_id: str
    issue: str
    item: str | None = None
    qty_claimed: int | None = None
    summary: str
    status: str
    problems: list[str] = Field(default_factory=list)

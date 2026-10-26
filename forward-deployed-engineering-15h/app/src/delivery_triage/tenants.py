"""Per-customer configuration: one tenant per store, each with its own limits (step 3, lesson 23).

The tenant id comes from the request, is checked against this registry, and is never used to build a
file path. An unknown tenant is refused before any model call is made.
"""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError


class Tenant(BaseModel):
    tenant_id: str = Field(pattern=r"^store-\d{2}$", description="the store, such as store-07")
    max_qty_per_line: int = Field(gt=0, description="the most units one line may claim before a person checks it")


class TenantFile(BaseModel):
    default_tenant: str
    tenants: list[Tenant]


def store_key(store_name: str) -> str:
    """The orders export names a store 'Store 07'; the tenant id is 'store-07' (lesson 23 does the same)."""
    return store_name.strip().lower().replace(" ", "-")


class TenantRegistry:
    def __init__(self, default_id: str, tenants: list[Tenant]) -> None:
        self.default_id = default_id
        self._by_id = {t.tenant_id: t for t in tenants}

    def get(self, tenant_id: str) -> Tenant | None:
        return self._by_id.get(tenant_id)

    def all(self) -> list[Tenant]:
        return list(self._by_id.values())


def load_tenants(path: Path) -> TenantRegistry:
    """Read and validate the tenants file. A wrong file stops the app at start-up, with the reason."""
    if not path.exists():
        raise FileNotFoundError(f"The tenants file is missing: {path}. Set TRIAGE_TENANTS_FILE in the course .env.")
    try:
        doc = TenantFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (ValidationError, json.JSONDecodeError) as exc:
        raise ValueError(f"The tenants file {path.name} does not fit the tenant shape: {exc}") from exc
    ids = [t.tenant_id for t in doc.tenants]
    if len(ids) != len(set(ids)):
        raise ValueError("The tenants file lists a tenant id twice")
    if doc.default_tenant not in ids:
        raise ValueError("The tenants file's default_tenant is not in its tenants list")
    return TenantRegistry(doc.default_tenant, doc.tenants)

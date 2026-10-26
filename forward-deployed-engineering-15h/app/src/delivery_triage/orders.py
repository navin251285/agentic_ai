"""The orders file and the plain-code check that runs after the model (lesson 06, steps 1 and 6).

The check never asks the model. It compares the model's record with the orders file.
"""
from __future__ import annotations

import csv
from pathlib import Path

from .models import CaseRecord
from .tenants import Tenant, store_key

Orders = dict[str, list[dict[str, str]]]


def load_orders(path: Path) -> Orders:
    """Read the orders file into {order_id: [lines]}. Raises a clear error if the file is missing."""
    if not path.exists():
        raise FileNotFoundError(
            "The orders file is missing. Run lesson 05 to write it, or set TRIAGE_ORDERS_FILE in the course .env."
        )
    orders: Orders = {}
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            orders.setdefault(row["order_id"], []).append(row)
    return orders


def check_record(rec: CaseRecord, orders: Orders, tenant: Tenant | None = None) -> list[str]:
    """Rules a model's form must pass before a case opens. Returns the problems (empty list = passed).

    With a tenant (step 3), the order must belong to that tenant's store, and a count above the store's
    limit per line needs a person.
    """
    lines = orders.get(rec.order_id)
    if not lines:
        return [f"order {rec.order_id} is not in the orders export"]
    if tenant is not None and any(store_key(line["store"]) != tenant.tenant_id for line in lines):
        return [f"order {rec.order_id} belongs to another store, not {tenant.tenant_id}"]
    problems: list[str] = []
    # Item matching is exact, so it depends on the model writing the item in lower case, as the Field description asks.
    if rec.item and rec.item not in {line["item"] for line in lines}:
        problems.append(f"{rec.item} is not on order {rec.order_id}")
    if rec.issue == "missing_item" and not rec.item:
        problems.append("a missing-item case must name the item")
    for line in lines:
        # qty_claimed is checked only for 'each' lines: grams and similar lines have other units.
        if rec.item == line["item"] and rec.qty_claimed is not None and line["unit_base"] == "each":
            if rec.qty_claimed > int(line["qty_base"]):
                problems.append(f"claims {rec.qty_claimed} {rec.item}, the order has {line['qty_base']}")
    if tenant is not None and rec.qty_claimed is not None and rec.qty_claimed > tenant.max_qty_per_line:
        problems.append(
            f"claims {rec.qty_claimed} units, above the store limit of {tenant.max_qty_per_line} per line"
        )
    return problems

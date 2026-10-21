"""The checks every tool call passes before it runs: scope first (lesson 30), then the refund policy (lesson 31).

Scope: each tool needs one scope, and the desk holds `read` and `write` only. It has no `send`, so it cannot mail a
customer or anyone else, whatever a ticket says (lesson 30's least privilege).

Policy: the refund rules read the order record, never the customer's text (lesson 31). A refund that passes is still
held for a person before any money moves (lesson 14). The policy decides only what may be held.
"""
from __future__ import annotations

from typing import Any

SCOPE_OF = {"lookup_order": "read", "search_policy": "read", "refund_order": "write"}
DESK_SCOPES = frozenset({"read", "write"})  # no "send": nothing leaves the desk except through a person
LOST_ONLY = "policy: only a lost order is refunded automatically; a person decides the rest"
FULL_TOTAL = "policy: the full order total only"


def check_call(name: str, args: dict[str, Any], orders: dict[str, dict[str, Any]],
               scopes: frozenset[str] = DESK_SCOPES) -> str | None:
    """Why this call must not run, or None when it may run. The reasons are fixed sentences: they never repeat the
    customer's text. The arguments must already have passed the schema check (see desk.check_args)."""
    scope = SCOPE_OF.get(name)
    if scope is None:
        return f"no tool named {name}"
    if scope not in scopes:
        return f"{name} is outside this agent's scopes"
    if name != "refund_order":
        return None
    order = orders.get(str(args["order_id"]))  # the order record, never the ticket text
    if order is None:
        return "policy: no such order"
    if order["status"] != "lost":
        return LOST_ONLY
    if float(args["amount_usd"]) != float(order["total"]):
        return FULL_TOTAL
    return None

"""Basket Bazaar delivery tools as an MCP server (lesson 19). Lab only: an invented orders file."""
import csv
import json
import sys
from pathlib import Path

from mcp.server import MCPServer

ORDERS: dict[str, list[dict]] = {}
with Path(sys.argv[1]).open(newline="") as f:
    for row in csv.DictReader(f):
        ORDERS.setdefault(row["order_id"], []).append(row)
PROPOSALS = Path(sys.argv[2])

mcp = MCPServer("basket-bazaar-tools")


@mcp.tool()
def lookup_order(order_id: str) -> str:
    """Look up one Basket Bazaar order by its order number, such as BB-1108. Returns its lines as JSON, or says it is not found."""
    lines = ORDERS.get(order_id)
    return json.dumps(lines) if lines else f"order {order_id} not found"


@mcp.tool()
def propose_credit(order_id: str, item: str, qty: int) -> str:
    """Propose a credit for qty units of one item on an order. A person approves it. This tool moves no money."""
    lines = ORDERS.get(order_id)
    if not lines:
        return f"refused: order {order_id} is not in the orders export"
    line = next((x for x in lines if x["item"] == item), None)
    if line is None:
        return f"refused: {item} is not on order {order_id}"
    if line["unit_base"] != "each":
        return f"refused: {item} is not sold by the each, a person checks it"
    if not 1 <= qty <= int(line["qty_base"]):
        return f"refused: qty must be from 1 to {line['qty_base']} for {item}"
    with PROPOSALS.open("a") as f:
        f.write(json.dumps({"order_id": order_id, "item": item, "qty": qty}) + "\n")
    return f"proposed: credit {qty} {item} on {order_id}, waiting for a person"


@mcp.tool()
def issue_refund(order_id: str) -> str:
    """Refund the whole order to the customer's card. Dangerous: the agent's allow-list must never offer it."""
    return f"refund issued on {order_id}"


mcp.run("stdio")  # the notebook starts this file and talks to it over stdin and stdout

"""System prompt and the compact JSON context sent to Gemini."""

import json

from app.domain.economics import BACKUP_FEE_PER_UNIT, PROFIT_PER_SALE, backup_lead_s
from app.domain.rules import Zone, inventory_position, product_zone
from app.services.engines.base import AgentContext

SYSTEM_PROMPT = f"""\
You are the autonomous restocking agent for a small shop. Customers buy from the shelves; you keep them \
stocked.
Goal: lose as little money as possible. Every missed sale (empty shelf) loses ₹{PROFIT_PER_SALE} profit.

Suppliers:
- main: delivers after lead_time_s (x1.5 when supplier_delay is true). No fee.
- backup: delivers after backup_lead_time_s. Costs ₹{BACKUP_FEE_PER_UNIT} extra per unit.
"news" lists things the shop manager just told you (may be empty). Work out what each item means for demand \
and for the suppliers, and act on it. Nobody will tell you the exact effect. News arrives before the \
sales figures show it, so plan for the demand you expect, not just recent sales.

First write "situation": at most 30 words, how you read the situation right now (mention the news \
if any).
Then, for EVERY product listed, return exactly one decision: "order" with qty and supplier, \
or "wait" with qty 0.
- zone "must_order": at or below reorder_point with nothing incoming. You must order now.
- zone "watch" or "ok": order early only if you expect the shelf to run low before an order would arrive.
- qty between 1 and room. An open order blocks another order for that product until it arrives, \
so order enough to last until it does.
- Choose backup only when its fee is cheaper than the sales you would otherwise miss \
(for example main is slow, unavailable, or demand is spiking). Otherwise main.
- reason: at most 20 words, plain English, naming the deciding factor. Do not quote field names.
Use only the product_id values given."""


def build_context(context: AgentContext) -> str:
    products = []
    for p in context.products:
        zone = product_zone(p, context.orders)
        products.append(
            {
                "product_id": p.id,
                "name": p.name,
                "zone": "must_order" if zone == Zone.MUST_ORDER else "watch" if zone == Zone.WATCH else "ok",
                "stock": p.stock,
                "max_stock": p.max_stock,
                "reorder_point": p.reorder_point,
                "room": p.max_stock - inventory_position(p, context.orders),
                "lead_time_s": p.lead_time_s,
                "backup_lead_time_s": backup_lead_s(p),
                "sales_last_60s": context.sales_last_60s.get(p.id, 0),
            }
        )
    payload = {
        "news": [{"text": text, "ends_in_s": left} for text, left in context.news],
        "rush_hour": context.rush_hour,
        "supplier_delay": context.supplier_delay,
        "agent_interval_s": context.agent_interval_s,
        "products": products,
        "open_orders": [
            {
                "product_id": o.product_id,
                "qty": o.qty,
                "supplier": o.supplier,
                "arrives_in_s": round(o.due_at_s - context.sim_s),
            }
            for o in context.orders
        ],
    }
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)

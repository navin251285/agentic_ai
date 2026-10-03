"""System prompt and the compact JSON context sent to Gemini."""

import json

from app.domain.rules import Zone, inventory_position, product_zone, watch_limit
from app.services.engines.base import AgentContext

SYSTEM_PROMPT = """\
You are the restocking agent for a small shop. Shelves sell down; you order from a supplier that \
delivers after lead_time_s seconds (x1.5 when supplier_delay is true). You check every agent_interval_s.

For EVERY product listed, return exactly one decision: action "order" with a qty, or "wait" with qty 0.
- zone "must_order": stock is at or below reorder_point and nothing is incoming. Order now.
- zone "watch": stock is a little above reorder_point. You MAY order early when demand is high \
(rush_hour, many sales_last_60s) or the lead time is long or supplier_delay is true; otherwise wait.
- qty must be between 1 and room (room = max_stock - stock). Smaller than room is fine if demand is low.
- Estimate: will stock reach reorder_point before an order placed now would arrive? If yes, order.
- reason: at most 20 words, plain English, mention the deciding factor (e.g. rush hour, lead time).
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
                "watch_up_to": watch_limit(p.reorder_point),
                "room": p.max_stock - inventory_position(p, context.orders),
                "lead_time_s": p.lead_time_s,
                "sales_last_60s": context.sales_last_60s.get(p.id, 0),
            }
        )
    payload = {
        "rush_hour": context.rush_hour,
        "supplier_delay": context.supplier_delay,
        "agent_interval_s": context.agent_interval_s,
        "products": products,
        "open_orders": [
            {"product_id": o.product_id, "qty": o.qty, "arrives_in_s": round(o.due_at_s - context.sim_s)}
            for o in context.orders
        ],
    }
    return json.dumps(payload, separators=(",", ":"))

"""Validate and clamp any engine's decisions (rules included).

- Unknown product, or a product with an open order → dropped.
- Order qty ≤ 0 → dropped; otherwise clamped to 1 … max_stock − inventory_position (dropped if no room).
- Must-order products the engine skipped or answered "wait" → ordered by the rules engine (source "fallback").
An engine may order earlier or smaller, but can never leave a shelf to run empty.
"""

from app.domain.models import Decision
from app.domain.rules import Zone, inventory_position, open_orders_for, product_zone
from app.services.engines import rules_engine
from app.services.engines.base import AgentContext


def apply_guardrails(decisions: list[Decision], context: AgentContext) -> list[Decision]:
    products = {p.id: p for p in context.products}
    kept: dict[str, Decision] = {}
    for d in decisions:
        product = products.get(d.product_id)
        if product is None or d.product_id in kept or open_orders_for(d.product_id, context.orders):
            continue
        if d.action == "order":
            room = product.max_stock - inventory_position(product, context.orders)
            if d.qty <= 0 or room <= 0:
                continue
            d = d.model_copy(update={"qty": min(d.qty, room)})
        kept[d.product_id] = d

    for product in context.products:
        current = kept.get(product.id)
        if product_zone(product, context.orders) == Zone.MUST_ORDER and (
            current is None or current.action != "order"
        ):
            kept[product.id] = rules_engine.decide_one(product, context, source="fallback")
    return list(kept.values())

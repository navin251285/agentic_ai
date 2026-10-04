"""Rule-based engine. Pure: no I/O, no randomness.

Must-order zone → order up to max_stock. Watch zone → wait. Everything else → no decision.
"""

from app.domain.models import Decision, Product
from app.domain.rules import Zone, inventory_position, product_zone
from app.services.engines.base import AgentContext


def decide_one(product: Product, context: AgentContext, source: str = "rules") -> Decision | None:
    zone = product_zone(product, context.orders)
    if zone == Zone.MUST_ORDER:
        qty = product.max_stock - inventory_position(product, context.orders)
        where = "at" if product.stock == product.reorder_point else "below"
        reason = (
            f"{product.name} at {product.stock}, {where} mark {product.reorder_point}, nothing incoming. "
            f"Ordered {qty} to refill to {product.max_stock}."
        )
        return Decision(product_id=product.id, action="order", qty=qty, reason=reason, source=source)
    if zone == Zone.WATCH:
        reason = f"{product.name} at {product.stock}, above mark {product.reorder_point}. Waiting."
        return Decision(product_id=product.id, action="wait", reason=reason, source=source)
    return None


def decide(context: AgentContext) -> list[Decision]:
    return [d for p in context.products if (d := decide_one(p, context)) is not None]


class RulesEngine:
    async def decide(self, context: AgentContext) -> list[Decision]:
        return decide(context)

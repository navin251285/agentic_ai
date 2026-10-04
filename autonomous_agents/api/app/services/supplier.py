"""Order lifecycle and deliveries.

Due time comes from economics.due_at_s: main supplier = lead_time_s (× 1.5 with supplier_delay, and after
any strike); backup = 40% of it, for a fee. CONFIRMED at 10% of the time to delivery, SHIPPED at 30%,
DELIVERED at 100% (stock capped at max_stock). Fixed at placement: later edits or toggles affect
new orders only.
"""

from collections.abc import Callable

from app.domain import economics
from app.domain.curveballs import strike_ends_at_s
from app.domain.models import EventType, Order, OrderStatus, PersistedState, Product, SupplierName

STAGES = (  # (status, fraction of lead time, event)
    (OrderStatus.CONFIRMED, 0.1, EventType.ORDER_CONFIRMED),
    (OrderStatus.SHIPPED, 0.3, EventType.ORDER_SHIPPED),
)
RANK = {s: i for i, s in enumerate(OrderStatus)}


class Supplier:
    def __init__(self, emit: Callable[..., None]):
        self.emit = emit

    def place_order(
        self, state: PersistedState, product: Product, qty: int, message: str, supplier: SupplierName = "main"
    ) -> Order:
        rt = state.runtime
        order = Order(
            id=f"O-{rt.next_order_id:04d}",
            product_id=product.id,
            qty=qty,
            placed_at_s=rt.sim_s,
            due_at_s=economics.due_at_s(
                product, supplier, rt.sim_s, rt.supplier_delay, strike_ends_at_s(rt.curveballs)
            ),
            supplier=supplier,
        )
        rt.next_order_id += 1
        rt.counters.orders_placed += 1
        fee = economics.order_fee(supplier, qty)
        if fee:
            rt.counters.extra_fees += fee
            message += f" · backup supplier, +₹{fee}"
        state.orders.append(order)
        self.emit(EventType.ORDER_PLACED, product, qty, order.id, message)
        return order

    def tick(self, state: PersistedState) -> None:
        products = {p.id: p for p in state.products}
        for order in state.orders:
            product = products.get(order.product_id)
            if order.is_open and product is not None:
                self._advance(state, order, product)

    def _advance(self, state: PersistedState, order: Order, product: Product) -> None:
        now = state.runtime.sim_s
        lead = order.due_at_s - order.placed_at_s
        # Emit every stage passed, in order, even if one tick crosses several (e.g. at 5x).
        for status, fraction, event_type in STAGES:
            if RANK[order.status] < RANK[status] and now >= order.placed_at_s + fraction * lead:
                order.status = status
                self.emit(event_type, product, order.qty, order.id, f"{product.name} order {status.lower()}")
        if now >= order.due_at_s:
            self._deliver(state, order, product)

    def _deliver(self, state: PersistedState, order: Order, product: Product) -> None:
        added = min(order.qty, product.max_stock - product.stock)
        product.stock += added
        order.status = OrderStatus.DELIVERED
        order.delivered_at_s = state.runtime.sim_s
        message = f"Delivered {order.qty} {product.name}"
        if added < order.qty:
            message += f"; shelf full at {product.max_stock}, {order.qty - added} returned"
        self.emit(EventType.DELIVERED, product, order.qty, order.id, message)

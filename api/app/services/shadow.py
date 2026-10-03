"""Shadow shop: the same shop managed by the rules engine, for the Agent vs Rules scoreboard.

It serves exactly the customers the real shop drew (same baskets), gets the same manual sales, edits,
settings and curveball effects, and its agent checks at the same moments as the real one. With the rules
brain both shops therefore stay identical. It writes no events; its state is saved in runtime.json.
"""

from app.domain import economics
from app.domain.curveballs import strike_ends_at_s
from app.domain.models import Counters, Order, OrderStatus, PersistedState, Product, Score, ShadowState
from app.services.engines import rules_engine
from app.services.engines.base import AgentContext
from app.services.engines.guardrails import apply_guardrails

HISTORY_LIMIT = 5000  # points per product; the chart reads at most the last window


class ShadowShop:
    def __init__(self, state: PersistedState):
        self.run_id = 0
        self.products: dict[str, Product] = {}
        self.orders: list[Order] = []
        self.counters = Counters()
        self.next_order_id = 1
        self.history: dict[str, list[tuple[float, int]]] = {}
        saved = state.runtime.shadow
        if saved is not None and saved.run_id == state.runtime.run_id:
            self._restore(state, saved)
        else:
            self.reset(state)

    # ---- lifecycle --------------------------------------------------------------

    def reset(self, state: PersistedState) -> None:
        """Start level with the real shop: its shelves and counters (zero on a new run), no orders."""
        self.run_id = state.runtime.run_id
        self.products = {p.id: p.model_copy() for p in state.products}
        self.orders = []
        self.counters = state.runtime.counters.model_copy()
        self.next_order_id = 1
        self.history = {pid: [(state.runtime.sim_s, p.stock)] for pid, p in self.products.items()}

    def _restore(self, state: PersistedState, saved: ShadowState) -> None:
        self.run_id = saved.run_id
        self.products = {}
        for p in state.products:  # attributes always mirror the real shop; only stock is the shadow's own
            stock = min(saved.stock.get(p.id, p.stock), p.max_stock)
            self.products[p.id] = p.model_copy(update={"stock": stock})
        self.orders = [o.model_copy() for o in saved.orders if o.product_id in self.products]
        self.counters = saved.counters.model_copy()
        self.next_order_id = saved.next_order_id
        self.history = {pid: [(state.runtime.sim_s, p.stock)] for pid, p in self.products.items()}

    def export(self) -> ShadowState:
        return ShadowState(
            run_id=self.run_id,
            stock={pid: p.stock for pid, p in self.products.items()},
            orders=[o.model_copy() for o in self.orders],
            counters=self.counters.model_copy(),
            next_order_id=self.next_order_id,
        )

    # ---- mirrored actions ---------------------------------------------------------

    def sell(self, product_id: str, qty: int, sim_s: float) -> None:
        product = self.products.get(product_id)
        if product is None:
            return
        for _ in range(qty):
            if product.stock == 0:
                self.counters.missed_sales += 1
            else:
                product.stock -= 1
                self.counters.sales += 1
                self._record(product, sim_s)

    def edit(self, real: Product, changed: set[str], sim_s: float) -> None:
        """Mirror an edit: copy the changed attributes; stock only if the edit set it."""
        product = self.products.get(real.id)
        if product is None:
            return
        for field in changed:
            setattr(product, field, getattr(real, field))
        if product.stock > product.max_stock:
            product.stock = product.max_stock
        self._record(product, sim_s)

    # ---- tick ---------------------------------------------------------------------

    def tick(self, state: PersistedState, baskets: list[list[str]], agent_checks: bool) -> None:
        """Same order as the real tick: customers → deliveries → agent."""
        sim_s = state.runtime.sim_s
        for basket in baskets:
            for product_id in basket:
                self.sell(product_id, 1, sim_s)
        self._deliver(sim_s)
        if agent_checks:
            self._agent_check(state)

    def _deliver(self, sim_s: float) -> None:
        for order in self.orders:
            product = self.products.get(order.product_id)
            if product is not None and order.is_open and sim_s >= order.due_at_s:
                product.stock += min(order.qty, product.max_stock - product.stock)
                order.status = OrderStatus.DELIVERED
                order.delivered_at_s = sim_s
                self._record(product, sim_s)
        self.orders = [o for o in self.orders if o.is_open]

    def _agent_check(self, state: PersistedState) -> None:
        rt = state.runtime
        context = AgentContext(
            sim_s=rt.sim_s,
            products=list(self.products.values()),
            orders=list(self.orders),
            rush_hour=rt.rush_hour,
            supplier_delay=rt.supplier_delay,
            agent_interval_s=rt.agent_interval_s,
        )
        for d in apply_guardrails(rules_engine.decide(context), context):
            if d.action != "order":
                continue
            product = self.products[d.product_id]
            self.orders.append(
                Order(
                    id=f"O-{self.next_order_id:04d}",
                    product_id=product.id,
                    qty=d.qty,
                    placed_at_s=rt.sim_s,
                    due_at_s=economics.due_at_s(
                        product, "main", rt.sim_s, rt.supplier_delay, strike_ends_at_s(rt.curveballs)
                    ),
                )
            )
            self.next_order_id += 1
            self.counters.orders_placed += 1

    # ---- views --------------------------------------------------------------------

    def _record(self, product: Product, sim_s: float) -> None:
        points = self.history.setdefault(product.id, [])
        points.append((sim_s, product.stock))
        if len(points) > HISTORY_LIMIT:
            del points[: len(points) - HISTORY_LIMIT]

    def stock(self) -> dict[str, int]:
        return {pid: p.stock for pid, p in self.products.items()}

    def points(self, product_id: str, since_s: float) -> list[tuple[float, int]]:
        """Stock points from since_s on, starting with the level at since_s so the line has a start."""
        points = self.history.get(product_id, [])
        before = [p for p in points if p[0] < since_s]
        inside = [p for p in points if p[0] >= since_s]
        return ([(since_s, before[-1][1])] if before else []) + inside


def score(counters: Counters) -> Score:
    lost = economics.lost_profit(counters.missed_sales)
    return Score(
        missed_sales=counters.missed_sales,
        lost_profit=lost,
        extra_fees=counters.extra_fees,
        total_cost=lost + counters.extra_fees,
    )

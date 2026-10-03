"""Builds the API view models from the simulation's state. Read-only; call while holding sim.lock."""

from app.domain import rules
from app.domain.models import (
    EventType,
    History,
    HistoryMarker,
    HistoryPoint,
    OrderView,
    Product,
    ProductView,
    Snapshot,
)
from app.services import clock
from app.services.simulation import Simulation

RECENT_EVENTS = 50
MARKER_TYPES = (EventType.ORDER_PLACED, EventType.DELIVERED)


def build_snapshot(sim: Simulation) -> Snapshot:
    state, rt = sim.state, sim.state.runtime
    names = {p.id: p.name for p in state.products}
    open_orders = [o for o in state.orders if o.is_open]
    products = [_product_view(sim, p) for p in state.products]
    orders = [
        OrderView(
            **o.model_dump(),
            product_name=names.get(o.product_id, o.product_id),
            seconds_left=rules.seconds_left(o.due_at_s, rt.sim_s),
        )
        for o in open_orders
    ]
    return Snapshot(
        run_id=rt.run_id,
        sim_s=rt.sim_s,
        shop_time=clock.shop_time(rt.sim_s),
        speed=rt.speed,
        last_speed=rt.last_speed,
        scenario=rt.scenario,
        settings=rt.settings(),
        counters=rt.counters,
        orders_on_the_way=len(open_orders),
        next_agent_check_s=rt.next_agent_check_s,
        saved_ago_s=sim.saved_ago_s(),
        products=products,
        orders=orders,
        events=state.events[-RECENT_EVENTS:],
        agent=sim.agent.status(state),
    )


def _product_view(sim: Simulation, p: Product) -> ProductView:
    state, rt = sim.state, sim.state.runtime
    badge = rules.product_badge(p, state.orders, rt.sim_s, rt.next_agent_check_s, rt.agent_enabled)
    kind, text = badge if badge else (None, None)
    return ProductView(
        **p.model_dump(),
        state=rules.product_state(p, state.orders, rt.sim_s),
        badge=text,
        badge_kind=kind,
    )


def build_history(sim: Simulation, product_id: str, window_s: float) -> History:
    """Current run only: stock points and order/delivery markers within the last window_s sim seconds."""
    sim.product(product_id)  # raises UnknownProduct
    since = sim.state.runtime.sim_s - window_s
    events = [e for e in sim.state.events if e.product_id == product_id and e.sim_s >= since]
    return History(
        product_id=product_id,
        window_s=window_s,
        points=[
            HistoryPoint(sim_s=e.sim_s, shop_time=e.shop_time, stock_after=e.stock_after)
            for e in events
            if e.stock_after is not None
        ],
        markers=[
            HistoryMarker(type=e.type.value, sim_s=e.sim_s, shop_time=e.shop_time, qty=e.qty, ref=e.ref)
            for e in events
            if e.type in MARKER_TYPES
        ],
    )

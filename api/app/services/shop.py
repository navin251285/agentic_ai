"""Customer simulator.

Next arrival every 2–4 sim_s (1–2 with rush hour). Basket = 1–4 distinct items picked one at a time,
weighted by sell_weight, qty 1 each. The seed stock values are calibrated to exactly this.
"""

import random
from collections.abc import Callable

from app.domain.models import EventType, PersistedState, Product

ARRIVAL_S = (2.0, 4.0)
RUSH_ARRIVAL_S = (1.0, 2.0)
BASKET_SIZE = (1, 4)
MANUAL_REF = "MANUAL"


class Shop:
    def __init__(self, rng: random.Random, emit: Callable[..., None]):
        self.rng = rng
        self.emit = emit

    def tick(self, state: PersistedState) -> None:
        rt = state.runtime
        while rt.next_customer_at_s <= rt.sim_s:
            self._serve_customer(state)
            lo, hi = RUSH_ARRIVAL_S if rt.rush_hour else ARRIVAL_S
            rt.next_customer_at_s += self.rng.uniform(lo, hi)

    def sell_manual(self, state: PersistedState, product: Product, qty: int) -> None:
        """Sells what is available; each missing unit is a MISSED_SALE."""
        for _ in range(qty):
            self._sell_unit(state, product, MANUAL_REF)

    def _serve_customer(self, state: PersistedState) -> None:
        rt = state.runtime
        ref = f"C-{rt.next_customer_id:04d}"
        rt.next_customer_id += 1
        pool = list(state.products)
        size = min(self.rng.randint(*BASKET_SIZE), len(pool))
        for _ in range(size):
            product = self.rng.choices(pool, weights=[p.sell_weight for p in pool])[0]
            pool.remove(product)
            self._sell_unit(state, product, ref)

    def _sell_unit(self, state: PersistedState, product: Product, ref: str) -> None:
        counters = state.runtime.counters
        who = "Manual sale" if ref == MANUAL_REF else f"Customer #{int(ref[2:])}"
        if product.stock == 0:
            counters.missed_sales += 1
            self.emit(EventType.MISSED_SALE, product, 1, ref, f"{who} wanted {product.name}: out of stock")
            return
        product.stock -= 1
        counters.sales += 1
        self.emit(EventType.SALE, product, 1, ref, f"{who} bought {product.name}")
        if product.stock == product.reorder_point:  # just went from above the mark to at it
            self.emit(
                EventType.CROSSED_MARK,
                product,
                message=f"{product.name} at {product.stock}, reached its mark {product.reorder_point}",
            )

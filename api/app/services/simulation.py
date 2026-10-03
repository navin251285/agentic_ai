"""Owns the in-memory state. Tick: clock → shop → supplier → agent → publish.

All methods here are synchronous. In the server, the loop and every API action run them while
holding `self.lock`, so they never interleave. Tests drive `tick(dt_sim)` directly and never sleep.
"""

import asyncio
import logging
import random
import time
from collections.abc import Callable
from datetime import UTC, datetime

from app.domain.models import Counters, Event, EventType, Order, PersistedState, Product, SimSettings, Speed
from app.repositories.base import InventoryRepository
from app.services import clock
from app.services.agent import Agent, LlmSetup
from app.services.shop import Shop
from app.services.supplier import Supplier

log = logging.getLogger(__name__)


class UnknownProduct(KeyError):
    pass


class Simulation:
    def __init__(
        self,
        state: PersistedState,
        repo: InventoryRepository,
        rng: random.Random,
        *,
        save_interval_s: float = 3,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        llm: LlmSetup | None = None,
    ):
        self.state = state
        self.repo = repo
        self.save_interval_s = save_interval_s
        self._now = now
        self.lock = asyncio.Lock()
        self.event_listeners: list[Callable[[Event], None]] = []
        self.tick_listeners: list[Callable[[], None]] = []  # SSE publish hooks in phase 4
        self.shop = Shop(rng, self.emit)
        self.supplier = Supplier(self.emit)
        self.agent = Agent(self.supplier.place_order, self.emit, llm)

    # ---- events -------------------------------------------------------------

    def emit(
        self,
        type: EventType,
        product: Product | None = None,
        qty: int | None = None,
        ref: str = "",
        message: str = "",
    ) -> Event:
        rt = self.state.runtime
        event = Event(
            run_id=rt.run_id,
            ts_real=self._now(),
            sim_s=rt.sim_s,
            shop_time=clock.shop_time(rt.sim_s),
            type=type,
            product_id=product.id if product else None,
            qty=qty,
            stock_after=product.stock if product else None,
            ref=ref,
            message=message,
        )
        self.state.events.append(event)
        self.repo.append_event(event)
        for listener in self.event_listeners:
            listener(event)
        return event

    # ---- tick ---------------------------------------------------------------

    def tick(self, dt_sim: float) -> None:
        """Advance the world by dt_sim. Nothing reacts while paused (dt_sim 0)."""
        if dt_sim > 0:
            clock.advance(self.state.runtime, dt_sim)
            self.shop.tick(self.state)
            self.supplier.tick(self.state)
            self.agent.tick(self.state)
        for listener in self.tick_listeners:
            listener()

    def step(self) -> None:
        """One real-time tick at the current speed."""
        self.tick(clock.sim_dt(self.state.runtime))

    # ---- actions ------------------------------------------------------------

    def product(self, product_id: str) -> Product:
        for p in self.state.products:
            if p.id == product_id:
                return p
        raise UnknownProduct(product_id)

    def set_speed(self, speed: Speed) -> None:
        clock.set_speed(self.state.runtime, speed)

    def sell(self, product_id: str, qty: int) -> None:
        """Manual sale. Works while paused: stock changes, nothing else reacts until play resumes."""
        self.shop.sell_manual(self.state, self.product(product_id), qty)

    def update_settings(self, **changes) -> SimSettings:
        """Apply setting changes (validated), log SETTINGS_CHANGED, and tell the agent what is new."""
        rt = self.state.runtime
        before = rt.settings()
        after = SimSettings.model_validate({**before.model_dump(), **changes})
        diff = {k: v for k, v in after.model_dump().items() if getattr(before, k) != v}
        if not diff:
            return after
        for k, v in diff.items():
            setattr(rt, k, v)
        if "agent_interval_s" in diff or diff.get("agent_enabled") is True:
            rt.next_agent_check_s = rt.sim_s + rt.agent_interval_s
        if diff.get("agent_mode") == "gemini":
            self.agent.mark_askable_pending(self.state)
        if "rush_hour" in diff or "supplier_delay" in diff:
            self.agent.mark_watch_pending(self.state)
        self.emit(EventType.SETTINGS_CHANGED, message=", ".join(f"{k} → {v}" for k, v in diff.items()))
        return after

    def place_order(self, product_id: str, qty: int, message: str) -> Order:
        return self.supplier.place_order(self.state, self.product(product_id), qty, message)

    def load_scenario(self, name: str, event_type: EventType = EventType.SCENARIO_LOADED) -> None:
        """Start a new run from a scenario: new run_id, sim_s 0, no orders, fresh counters."""
        products = self.repo.load_scenario(name)  # raises ScenarioNotFound before anything changes
        rt = self.state.runtime
        rt.run_id += 1
        rt.sim_s = 0
        rt.scenario = name
        rt.rush_hour = name == "rush_hour"
        rt.counters = Counters()
        rt.next_customer_at_s = 0
        rt.next_customer_id = 1
        rt.next_agent_check_s = rt.agent_interval_s
        # next_order_id keeps counting so order ids stay unique across runs in events.csv.
        self.state.products = products
        self.state.orders = []
        self.state.events = []
        label = "Reset" if event_type == EventType.RESET else f"Scenario {name} loaded"
        for p in products:  # one per product, so the chart has a starting point
            self.emit(event_type, p, message=f"{label}: {p.name} starts at {p.stock}")
        self.agent.start_run(self.state)
        self.save()

    def reset(self) -> None:
        self.load_scenario(self.state.runtime.scenario, EventType.RESET)

    # ---- persistence & loop ---------------------------------------------------

    def save(self) -> bool:
        ok = self.repo.save_products(self.state.products)
        ok = self.repo.save_orders(self.state.orders) and ok
        return self.repo.save_runtime(self.state.runtime.model_dump(mode="json")) and ok

    async def run(self) -> None:
        """Real-time loop: one tick every 0.5s, save every save_interval_s. Cancel to stop."""
        next_tick = next_save = time.monotonic()
        while True:
            async with self.lock:
                try:
                    self.step()
                    if time.monotonic() >= next_save:
                        self.save()
                        next_save = time.monotonic() + self.save_interval_s
                except Exception:  # the demo must keep running
                    log.exception("Simulation tick failed")
            next_tick += clock.TICK_REAL_S
            await asyncio.sleep(max(0.0, next_tick - time.monotonic()))

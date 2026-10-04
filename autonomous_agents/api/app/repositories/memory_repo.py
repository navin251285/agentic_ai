"""In-memory repository: writes nothing to disk. Scenarios are read through another repository.

Used by the headless runner (so it never overwrites the live CSV files) and by tests.
"""

from app.domain.models import Event, Order, PersistedState, Product, Runtime
from app.repositories.base import InventoryRepository


class InMemoryInventoryRepository(InventoryRepository):
    def __init__(self, scenarios: InventoryRepository, default_scenario: str = "normal_day"):
        self._scenarios = scenarios
        self.default_scenario = default_scenario
        self.products: list[Product] = []
        self.orders: list[Order] = []
        self.events: list[Event] = []
        self.runtime: dict = {}

    def load(self) -> PersistedState:
        products = self.products or self.load_scenario(self.default_scenario)
        runtime = Runtime.model_validate({"scenario": self.default_scenario, **self.runtime})
        return PersistedState(
            products=[p.model_copy() for p in products],
            orders=[o.model_copy() for o in self.orders],
            runtime=runtime,
            events=self.read_events(runtime.run_id),
        )

    def save_products(self, products: list[Product]) -> bool:
        self.products = [p.model_copy() for p in products]
        return True

    def save_orders(self, orders: list[Order]) -> bool:
        self.orders = [o.model_copy() for o in orders]
        return True

    def append_event(self, event: Event) -> bool:
        self.events.append(event)
        return True

    def read_events(self, run_id: int) -> list[Event]:
        return [e for e in self.events if e.run_id == run_id]

    def save_runtime(self, runtime: dict) -> bool:
        self.runtime = dict(runtime)
        return True

    def load_runtime(self) -> dict:
        return dict(self.runtime)

    def load_scenario(self, name: str) -> list[Product]:
        return self._scenarios.load_scenario(name)

    def list_scenarios(self) -> list[str]:
        return self._scenarios.list_scenarios()

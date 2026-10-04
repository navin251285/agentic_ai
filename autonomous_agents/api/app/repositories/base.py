"""Storage interface. Services use only these methods, so CSV can be swapped for Postgres later."""

from abc import ABC, abstractmethod

from app.domain.models import Event, Order, PersistedState, Product


class ScenarioNotFound(KeyError):
    pass


class InventoryRepository(ABC):
    @abstractmethod
    def load(self) -> PersistedState:
        """Load products, orders, runtime and the current run's events (used once at startup)."""

    @abstractmethod
    def save_products(self, products: list[Product]) -> bool:
        """Replace all products. Returns False if the write failed (caller retries on next save)."""

    @abstractmethod
    def save_orders(self, orders: list[Order]) -> bool: ...

    @abstractmethod
    def append_event(self, event: Event) -> bool:
        """Append one event. On failure the event is queued and written, in order, on the next success."""

    @abstractmethod
    def read_events(self, run_id: int) -> list[Event]: ...

    @abstractmethod
    def save_runtime(self, runtime: dict) -> bool: ...

    @abstractmethod
    def load_runtime(self) -> dict:
        """Raw runtime dict; empty if there is none yet."""

    @abstractmethod
    def load_scenario(self, name: str) -> list[Product]:
        """Raises ScenarioNotFound for unknown names."""

    @abstractmethod
    def list_scenarios(self) -> list[str]: ...

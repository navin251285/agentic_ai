"""Pydantic domain models. No I/O here."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

SLUG = r"^[a-z0-9]+(-[a-z0-9]+)*$"

Speed = Literal[0, 0.5, 1, 5]  # 0 = paused
PlaySpeed = Literal[0.5, 1, 5]
AgentMode = Literal["rules", "gemini"]


class OrderStatus(StrEnum):
    PLACED = "PLACED"
    CONFIRMED = "CONFIRMED"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"


class EventType(StrEnum):
    SALE = "SALE"
    MISSED_SALE = "MISSED_SALE"
    CROSSED_MARK = "CROSSED_MARK"
    ORDER_PLACED = "ORDER_PLACED"
    ORDER_CONFIRMED = "ORDER_CONFIRMED"
    ORDER_SHIPPED = "ORDER_SHIPPED"
    DELIVERED = "DELIVERED"
    EDIT = "EDIT"
    SETTINGS_CHANGED = "SETTINGS_CHANGED"
    SCENARIO_LOADED = "SCENARIO_LOADED"
    RESET = "RESET"
    AGENT_WAIT = "AGENT_WAIT"
    AGENT_FALLBACK = "AGENT_FALLBACK"


class Product(BaseModel):
    id: str = Field(pattern=SLUG)
    name: str = Field(min_length=1)
    stock: int = Field(ge=0)
    max_stock: int = Field(ge=1, le=999)
    reorder_point: int = Field(ge=0)
    sell_weight: int = Field(ge=1, le=10)
    lead_time_s: int = Field(ge=5, le=600)

    @model_validator(mode="after")
    def _check_limits(self) -> "Product":
        if self.stock > self.max_stock:
            raise ValueError(f"stock ({self.stock}) must be ≤ max_stock ({self.max_stock})")
        if self.reorder_point >= self.max_stock:
            raise ValueError(f"reorder_point ({self.reorder_point}) must be < max_stock ({self.max_stock})")
        return self


class Order(BaseModel):
    id: str = Field(pattern=r"^O-\d{4,}$")
    product_id: str = Field(pattern=SLUG)
    qty: int = Field(ge=1)
    status: OrderStatus = OrderStatus.PLACED
    placed_at_s: float = Field(ge=0)
    due_at_s: float = Field(ge=0)
    delivered_at_s: float | None = None

    @property
    def is_open(self) -> bool:
        return self.status != OrderStatus.DELIVERED


class Event(BaseModel):
    run_id: int = Field(ge=1)
    ts_real: datetime
    sim_s: float = Field(ge=0)
    shop_time: str
    type: EventType
    product_id: str | None = None
    qty: int | None = None
    stock_after: int | None = None
    ref: str = ""
    message: str = ""


class SimSettings(BaseModel):
    """User-changeable settings (POST /api/settings).

    Named SimSettings to avoid clashing with config.Settings.
    """

    rush_hour: bool = False
    supplier_delay: bool = False
    agent_enabled: bool = True
    agent_mode: AgentMode = "rules"
    agent_interval_s: int = Field(5, ge=1, le=60)


class Counters(BaseModel):
    sales: int = 0
    missed_sales: int = 0
    orders_placed: int = 0


class Runtime(SimSettings):
    """Contents of runtime.json (flat, as in the spec)."""

    run_id: int = Field(1, ge=1)
    sim_s: float = Field(0, ge=0)
    speed: Speed = 0
    last_speed: PlaySpeed = 1  # what Play resumes
    scenario: str = "normal_day"
    next_agent_check_s: float = 0
    next_customer_at_s: float = 0
    counters: Counters = Field(default_factory=Counters)
    next_customer_id: int = Field(1, ge=1)
    next_order_id: int = Field(1, ge=1)

    def settings(self) -> SimSettings:
        return SimSettings.model_validate(self.model_dump(include=set(SimSettings.model_fields)))

    def paused_for_startup(self) -> "Runtime":
        """Startup always begins paused; Play resumes the speed that was running before."""
        return self.model_copy(update={"speed": 0, "last_speed": self.speed or self.last_speed})


class PersistedState(BaseModel):
    """What InventoryRepository.load() returns. (Snapshot is reserved for the API view model.)"""

    products: list[Product]
    orders: list[Order] = Field(default_factory=list)
    runtime: Runtime = Field(default_factory=Runtime)
    events: list[Event] = Field(default_factory=list)  # current run only


class Decision(BaseModel):
    product_id: str
    action: Literal["order", "wait"]
    qty: int = Field(0, ge=0)
    reason: str = ""
    source: Literal["rules", "gemini", "fallback"]

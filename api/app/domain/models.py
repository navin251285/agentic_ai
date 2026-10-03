"""Pydantic domain models. No I/O here."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

SLUG = r"^[a-z0-9]+(-[a-z0-9]+)*$"

Speed = Literal[0, 0.5, 1, 5]  # 0 = paused
PlaySpeed = Literal[0.5, 1, 5]
AgentMode = Literal["rules", "gemini"]
SupplierName = Literal["main", "backup"]


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
    CURVEBALL = "CURVEBALL"


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
    supplier: SupplierName = "main"  # last column in orders.csv; older files load as main

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
    extra_fees: int = 0  # ₹ paid to the backup supplier


class Curveball(BaseModel):
    """A piece of news the agent is told about; presets also change the simulated world."""

    id: int = Field(ge=1)
    preset: str | None = None  # None = custom text (no world effect)
    title: str
    text: str
    started_at_s: float = Field(ge=0)
    ends_at_s: float = Field(ge=0)


class ShadowState(BaseModel):
    """The shadow (rules-only) shop, persisted in runtime.json. Product attributes mirror the real shop."""

    run_id: int = Field(1, ge=1)
    stock: dict[str, int] = Field(default_factory=dict)
    orders: list[Order] = Field(default_factory=list)  # open orders only
    counters: Counters = Field(default_factory=Counters)
    next_order_id: int = Field(1, ge=1)


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
    curveballs: list[Curveball] = Field(default_factory=list)  # active only
    next_curveball_id: int = Field(1, ge=1)
    shadow: ShadowState | None = None  # written on save; None until the first save

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
    supplier: SupplierName = "main"


class PlanStep(BaseModel):
    product_id: str
    product_name: str
    action: Literal["order", "wait"]
    qty: int
    supplier: SupplierName
    reason: str
    source: Literal["rules", "gemini", "fallback"]


class AgentPlan(BaseModel):
    """The latest Gemini decision (or its fallback), for the plan card. Memory only."""

    sim_s: float
    shop_time: str
    trigger: str  # "Curveball: Heatwave" or "Routine check"
    situation: str  # Gemini's reading of the situation, or why the rules decided
    steps: list[PlanStep]


class AgentStatus(BaseModel):
    """Live agent view (in memory only; part of the phase 4 Snapshot)."""

    mode: AgentMode
    enabled: bool
    thinking: bool = False
    llm_ready: bool = False
    last_latency_ms: int | None = None
    llm_calls: int = 0
    fallbacks: int = 0
    calls_last_60s: int = 0
    call_limit: int = 10
    next_call_allowed_in_s: float = 0
    pending_products: list[str] = Field(default_factory=list)
    plan: AgentPlan | None = None


# ---- API view models (Snapshot, history) ------------------------------------------


ProductStateName = Literal["EMPTY", "AWAITING", "DANGER", "RESTOCKED", "SELLING"]  # rules.ProductState


BadgeKindName = Literal["arriving", "agent", "delivered"]  # rules.BadgeKind


class ProductView(Product):
    state: ProductStateName
    badge: str | None = None
    badge_kind: BadgeKindName | None = None  # so the UI can color the badge without parsing it


class OrderView(Order):
    product_name: str
    seconds_left: int  # due_at_s − sim_s, rounded up, never negative


class CurveballView(BaseModel):
    id: int
    preset: str | None
    title: str
    text: str
    seconds_left: int


class Score(BaseModel):
    missed_sales: int
    lost_profit: int  # ₹
    extra_fees: int  # ₹
    total_cost: int  # ₹


class Scoreboard(BaseModel):
    """The real shop (agent) against the shadow shop (rules), same customers."""

    agent: Score
    rules: Score
    agent_ahead_by: int  # ₹, rules.total_cost − agent.total_cost
    same_brain: bool  # the agent uses the rules brain, so both shops match


class Snapshot(BaseModel):
    """Everything the screen shows; also the SSE payload. React only formats it."""

    run_id: int
    sim_s: float
    shop_time: str
    speed: Speed
    last_speed: PlaySpeed
    scenario: str
    settings: SimSettings
    counters: Counters
    orders_on_the_way: int
    next_agent_check_s: float
    saved_ago_s: int | None  # None until the first successful save
    products: list[ProductView]
    orders: list[OrderView]  # open orders only
    events: list[Event]  # last 50 of the current run, oldest first
    agent: AgentStatus
    curveballs: list[CurveballView]
    scoreboard: Scoreboard
    shadow_stock: dict[str, int]  # the rules shop's stock, for the chart's ghost line


class HistoryPoint(BaseModel):
    sim_s: float
    shop_time: str
    stock_after: int


class HistoryMarker(BaseModel):
    type: Literal["ORDER_PLACED", "DELIVERED"]
    sim_s: float
    shop_time: str
    qty: int | None
    stock_after: int | None
    ref: str


class History(BaseModel):
    product_id: str
    window_s: float
    points: list[HistoryPoint]
    markers: list[HistoryMarker]
    shadow_points: list[HistoryPoint]  # the rules shop, same window


# ---- API request bodies -------------------------------------------------------------


class SpeedRequest(BaseModel):
    speed: Speed


class SellRequest(BaseModel):
    product_id: str
    qty: int = Field(1, ge=1, le=999)


class ProductPatch(BaseModel):
    """Every field optional; limits are checked on the product AFTER merging (Product validators)."""

    stock: int | None = None
    max_stock: int | None = None
    reorder_point: int | None = None
    sell_weight: int | None = None
    lead_time_s: int | None = None


class SettingsPatch(BaseModel):
    rush_hour: bool | None = None
    supplier_delay: bool | None = None
    agent_enabled: bool | None = None
    agent_mode: AgentMode | None = None
    agent_interval_s: int | None = Field(None, ge=1, le=60)


class ScenarioRequest(BaseModel):
    name: str


class CurveballPreset(BaseModel):
    id: str
    title: str
    text: str
    effect: str  # plain-English world effect, for the panel's tooltip


class CurveballRequest(BaseModel):
    """Exactly one of preset or text."""

    preset: str | None = None
    text: str | None = Field(None, min_length=3, max_length=200)

    @model_validator(mode="after")
    def _one_of(self) -> "CurveballRequest":
        if (self.preset is None) == (self.text is None or not self.text.strip()):
            raise ValueError("send either a preset or a text")
        return self

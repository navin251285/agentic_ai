"""DecisionEngine interface and the context every engine decides on."""

from dataclasses import dataclass, field
from typing import Protocol

from app.domain.models import Decision, Order, Product


@dataclass(frozen=True)
class AgentContext:
    sim_s: float
    products: list[Product]  # the products to decide on
    orders: list[Order] = field(default_factory=list)  # open orders (all products)
    rush_hour: bool = False
    supplier_delay: bool = False
    agent_interval_s: int = 5
    sales_last_60s: dict[str, int] = field(default_factory=dict)  # by product id, in sim seconds
    news: list[tuple[str, int]] = field(default_factory=list)  # active curveballs: (text, seconds left)


class DecisionEngine(Protocol):
    async def decide(self, context: AgentContext) -> list[Decision]: ...

"""Fake LLMs for tests. Tests NEVER call the real API (only `pytest -m live` does)."""

import asyncio
import random
from collections.abc import Callable

from app.domain.models import Decision
from app.domain.rules import Zone, inventory_position, product_zone
from app.repositories.memory_repo import InMemoryInventoryRepository
from app.services.agent import LlmSetup
from app.services.engines.base import AgentContext
from app.services.engines.rate_limiter import LlmRateLimiter, VirtualClock
from app.services.simulation import Simulation


def run_now(coro) -> None:
    """Spawn that finishes the call immediately; the agent applies it on the next tick."""
    asyncio.run(coro)


class ManualSpawn:
    """Spawn that holds the call until the test runs it (to test 'thinking')."""

    def __init__(self):
        self.coros = []

    def __call__(self, coro) -> None:
        self.coros.append(coro)

    def finish_all(self) -> None:
        while self.coros:
            asyncio.run(self.coros.pop(0))


def answer(context: AgentContext, share: float = 1.0) -> list[Decision]:
    """Like a sensible LLM: order must-order products (share of the room), wait on watch ones."""
    out = []
    for p in context.products:
        if product_zone(p, context.orders) == Zone.MUST_ORDER:
            qty = max(1, int((p.max_stock - inventory_position(p, context.orders)) * share))
            out.append(Decision(product_id=p.id, action="order", qty=qty, reason="Low.", source="gemini"))
        else:
            out.append(Decision(product_id=p.id, action="wait", reason="Enough for now.", source="gemini"))
    return out


def cautious(context: AgentContext) -> list[Decision]:
    """Orders half of the room: Gemini may order smaller than refill-to-max."""
    return answer(context, 0.5)


class FakeEngine:
    """A DecisionEngine that records every context and answers with `respond(context)`."""

    def __init__(self, respond: Callable[[AgentContext], list[Decision]] = answer, clock=None):
        self.respond = respond
        self.contexts: list[AgentContext] = []
        self.call_times: list[float] = []
        self.clock = clock

    async def decide(self, context: AgentContext) -> list[Decision]:
        self.contexts.append(context)
        if self.clock is not None:
            self.call_times.append(self.clock())
        return self.respond(context)

    def asked(self) -> list[list[str]]:
        return [[p.id for p in c.products] for c in self.contexts]


class FakeStructured:
    def __init__(self, chat: "FakeChat"):
        self.chat = chat

    async def ainvoke(self, messages):
        self.chat.messages.append(messages)
        if isinstance(self.chat.reply, Exception):
            raise self.chat.reply
        return self.chat.reply


class FakeChat:
    """Stands in for ChatGoogleGenerativeAI in GeminiEngine tests."""

    def __init__(self, reply=None):
        self.reply = reply
        self.schema = None
        self.messages: list = []

    def with_structured_output(self, schema):
        self.schema = schema
        return FakeStructured(self)

    async def ainvoke(self, prompt):
        self.messages.append(prompt)
        if isinstance(self.reply, Exception):
            raise self.reply
        return "ready"


class ClosedLimiter(LlmRateLimiter):
    """Budget always exhausted."""

    def try_acquire(self) -> bool:
        return False


def gemini_sim(
    repo,
    engine=None,
    *,
    spawn=run_now,
    limiter: LlmRateLimiter | None = None,
    timeout_s: float = 8,
    seed: int = 42,
    scenario: str = "normal_day",
) -> tuple[Simulation, VirtualClock]:
    vc = VirtualClock()
    limiter = limiter or LlmRateLimiter(clock=vc)
    limiter.clock = vc
    mem = InMemoryInventoryRepository(repo)
    llm = LlmSetup(engine=engine, limiter=limiter, timeout_s=timeout_s, spawn=spawn)
    sim = Simulation(mem.load(), mem, random.Random(seed), llm=llm)
    sim.load_scenario(scenario)
    sim.state.runtime.agent_mode = "gemini"
    return sim, vc


def run_ticks(sim: Simulation, vc: VirtualClock, n: int, dt_sim: float = 0.5) -> None:
    """n ticks; each tick is 0.5 virtual real seconds whatever the speed (dt_sim = 0.5 × speed)."""
    for _ in range(n):
        sim.tick(dt_sim)
        vc.advance(0.5)


def quiet(sim: Simulation) -> None:
    sim.state.runtime.next_customer_at_s = 10_000  # no customers: only the agent changes things

"""Autonomous agent loop: every agent_interval_s (sim), decide, apply guardrails, act.

Phase 3: the rules engine decides in both modes. The Gemini engine (phase 3b) plugs in here.
"""

from collections.abc import Callable

from app.domain.models import Decision, PersistedState, Product
from app.services.engines import rules_engine
from app.services.engines.base import AgentContext
from app.services.engines.guardrails import apply_guardrails


class Agent:
    def __init__(self, place_order: Callable[[PersistedState, Product, int, str], object]):
        self.place_order = place_order

    def tick(self, state: PersistedState) -> list[Decision]:
        rt = state.runtime
        if not rt.agent_enabled or rt.sim_s < rt.next_agent_check_s:
            return []
        rt.next_agent_check_s = rt.sim_s + rt.agent_interval_s
        context = build_context(state)
        decisions = apply_guardrails(rules_engine.decide(context), context)
        self.act(state, decisions)
        return decisions

    def act(self, state: PersistedState, decisions: list[Decision]) -> None:
        products = {p.id: p for p in state.products}
        for d in decisions:
            if d.action == "order":
                self.place_order(state, products[d.product_id], d.qty, f"[{d.source}] {d.reason}")
            # AGENT_WAIT is only logged for Gemini waits (phase 3b); rules waits would flood the feed.


def build_context(state: PersistedState) -> AgentContext:
    rt = state.runtime
    return AgentContext(
        sim_s=rt.sim_s,
        products=list(state.products),
        orders=[o for o in state.orders if o.is_open],
        rush_hour=rt.rush_hour,
        supplier_delay=rt.supplier_delay,
        agent_interval_s=rt.agent_interval_s,
    )

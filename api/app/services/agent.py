"""Autonomous agent loop: every agent_interval_s (sim), decide, apply guardrails, act.

Rules mode: the rules engine decides on every product at every check.
Gemini mode (event-driven, batched):
- A product is "pending" when it newly enters the watch or must-order zone. At a check with pending
  products, ONE call covers all of them, if the rate limiter allows. A "wait" answer is final until
  the product changes zone.
- The call runs in the background (at most one in flight; checks while it runs are skipped). Its result
  is applied on a later tick, against the state at that time, so the simulation never waits for it.
- Timeout, error or invalid output → rules engine for those products (source "fallback") + AGENT_FALLBACK.
- No budget: watch products stay pending; must-order products get one agent interval of grace, then
  the rules engine orders them ("Gemini budget reached").
- No API key: every check falls back to rules with no call made.
- Curveball (news): the next check asks about every product without an open order, with the news in the
  context. Every call includes active news, both suppliers and the economics. The rules brain ignores news.
- Each call's result (or its fallback) becomes the plan shown on the dashboard.
"""

import asyncio
import logging
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

from app.config import Settings
from app.domain.models import (
    AgentPlan,
    AgentStatus,
    Curveball,
    Decision,
    EventType,
    PersistedState,
    PlanStep,
)
from app.domain.rules import Zone, product_zone
from app.services import clock
from app.services.engines import rules_engine
from app.services.engines.base import AgentContext, DecisionEngine
from app.services.engines.guardrails import apply_guardrails
from app.services.engines.llm_engine import GeminiEngine, make_llm, short_reason
from app.services.engines.rate_limiter import LlmRateLimiter

log = logging.getLogger(__name__)

SALES_WINDOW_S = 60
ASKABLE = (Zone.WATCH, Zone.MUST_ORDER)
Spawn = Callable[[Coroutine[Any, Any, None]], None]

_background: set[asyncio.Task] = set()


def spawn_task(coro: Coroutine[Any, Any, None]) -> None:
    """Default: run on the current event loop, keeping a reference so the task is not collected."""
    task = asyncio.get_running_loop().create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)


@dataclass
class LlmSetup:
    engine: DecisionEngine | None = None  # None = no API key
    limiter: LlmRateLimiter = field(default_factory=LlmRateLimiter)
    timeout_s: float = 8
    spawn: Spawn = spawn_task


def build_llm_setup(settings: Settings, clock: Callable[[], float] = time.monotonic) -> LlmSetup:
    """Gemini engine if a key is set (no network call here), and the limiter from the configured budget."""
    limiter = LlmRateLimiter(settings.llm_max_calls_per_min, settings.llm_min_gap_s, clock)
    engine = None
    if settings.google_cloud_api_key is not None:
        engine = GeminiEngine(make_llm(settings), secret=settings.google_cloud_api_key.get_secret_value())
    return LlmSetup(engine=engine, limiter=limiter, timeout_s=settings.llm_timeout_s)


@dataclass
class _Job:
    product_ids: list[str]
    trigger: str = "Routine check"
    done: bool = False
    decisions: list[Decision] = field(default_factory=list)
    situation: str = ""
    error: str | None = None
    latency_ms: int | None = None


class Agent:
    def __init__(
        self,
        place_order: Callable[..., object],  # (state, product, qty, message, supplier)
        emit: Callable[..., object],
        llm: LlmSetup | None = None,
    ):
        self.place_order = place_order
        self.emit = emit
        self.llm = llm or LlmSetup()
        self.llm_ready = False
        self.last_latency_ms: int | None = None
        self.fallbacks = 0
        self._job: _Job | None = None
        self._last_zone: dict[str, Zone] | None = None  # None = start tracking at the next tick
        self._pending: set[str] = set()
        self._denied: set[str] = set()  # must-order products already given their one interval of grace
        self._news_trigger: str | None = None  # set by a curveball: the next check asks about every product
        self.plan: AgentPlan | None = None

    # ---- hooks (scenario load, settings changes) ----------------------------

    def start_run(self, state: PersistedState) -> None:
        """Zones at run start; products already in the watch or must zone are pending at the first check."""
        zones = self._zones(state)
        self._last_zone = zones
        self._pending = {pid for pid, z in zones.items() if z in ASKABLE}
        self._denied.clear()
        self._news_trigger = None
        self.plan = None

    def mark_askable_pending(self, state: PersistedState) -> None:
        """Switching to gemini: everything in the watch or must zone is pending."""
        self._pending |= {pid for pid, z in self._zones(state).items() if z in ASKABLE}

    def mark_watch_pending(self, state: PersistedState) -> None:
        """Rush hour / supplier delay toggled: new information for watch-zone products."""
        self._pending |= {pid for pid, z in self._zones(state).items() if z == Zone.WATCH}

    def mark_news_pending(self, curveballs: list[Curveball]) -> None:
        """New news: the next Gemini check covers every product without an open order."""
        if curveballs:
            self._news_trigger = f"Curveball: {curveballs[-1].title}"

    # ---- tick -----------------------------------------------------------------

    def tick(self, state: PersistedState) -> list[Decision]:
        if self._last_zone is None:
            self.start_run(state)
        applied = self.collect_finished_call(state)
        rt = state.runtime
        if not rt.agent_enabled or rt.sim_s < rt.next_agent_check_s:
            return applied
        rt.next_agent_check_s = rt.sim_s + rt.agent_interval_s
        self._track_zones(state)
        if rt.agent_mode == "rules":
            self._pending.clear()  # only gemini mode asks; switching to it re-marks (mark_askable_pending)
            self._news_trigger = None  # the rules brain cannot read news
            context = build_context(state)
            decisions = apply_guardrails(rules_engine.decide(context), context)
        else:
            decisions = self._gemini_check(state)
        self.act(state, decisions)
        return applied + decisions

    def _zones(self, state: PersistedState) -> dict[str, Zone]:
        return {p.id: product_zone(p, state.orders) for p in state.products}

    def _track_zones(self, state: PersistedState) -> None:
        zones = self._zones(state)
        for pid, zone in zones.items():
            if zone != self._last_zone.get(pid):
                self._pending.discard(pid)
                self._denied.discard(pid)
                if zone in ASKABLE:
                    self._pending.add(pid)
        self._last_zone = zones
        # Only products still in the watch or must zone can be asked.
        self._pending = {pid for pid in self._pending if zones.get(pid) in ASKABLE}

    def _gemini_check(self, state: PersistedState) -> list[Decision]:
        if self._job is not None:  # a call is in flight: skip this check
            return []
        if self.llm.engine is None:  # no API key: rules, no call made
            self._pending.clear()
            self._news_trigger = None
            context = build_context(state)
            decisions = apply_guardrails(rules_engine.decide(context), context)
            decisions = [d.model_copy(update={"source": "fallback"}) for d in decisions]
            if any(d.action == "order" for d in decisions):
                self._fallback(state, "no API key")
            return decisions
        trigger = self._news_trigger
        uncovered: set[str] = set()
        if trigger is not None:
            uncovered = {p.id for p in state.products if product_zone(p, state.orders) != Zone.COVERED}
            if not uncovered:  # everything already on order: nothing to ask
                self._news_trigger = trigger = None
        if not self._pending and trigger is None:
            return []
        if not self.llm.limiter.try_acquire():
            return self._budget_fallback(state)
        asked = self._pending | uncovered
        ids = [p.id for p in state.products if p.id in asked]  # shelf order
        self._log_call("curveball" if trigger else "decision", ids)
        self._pending.clear()
        self._news_trigger = None
        self._denied.difference_update(ids)
        job = _Job(ids, trigger or "Routine check")
        self._job = job
        self.llm.spawn(self._call(job, build_context(state, ids, for_llm=True)))
        return []

    def _log_call(self, kind: str, ids: list[str]) -> None:
        limiter = self.llm.limiter
        log.info(
            "Gemini call #%d (%s%s): %d/%d in the last 60s",
            limiter.total,
            kind,
            f": {', '.join(ids)}" if ids else "",
            limiter.calls_last_window(),
            limiter.max_calls,
        )

    def _budget_fallback(self, state: PersistedState) -> list[Decision]:
        zones = self._zones(state)
        due = [pid for pid in sorted(self._pending) if zones[pid] == Zone.MUST_ORDER and pid in self._denied]
        self._denied |= {pid for pid in self._pending if zones[pid] == Zone.MUST_ORDER}
        if not due:
            return []
        context = build_context(state, due)
        decisions = []
        for p in context.products:
            d = rules_engine.decide_one(p, context, source="fallback")
            decisions.append(d.model_copy(update={"reason": f"Gemini budget reached. {d.reason}"}))
            self._pending.discard(p.id)
            self._denied.discard(p.id)
        self.fallbacks += 1
        return apply_guardrails(decisions, context)

    async def _call(self, job: _Job, context: AgentContext) -> None:
        started = time.monotonic()
        try:
            plan = getattr(self.llm.engine, "plan", None)  # Gemini also explains how it reads the situation
            if plan is not None:
                job.situation, job.decisions = await asyncio.wait_for(plan(context), self.llm.timeout_s)
            else:
                job.decisions = await asyncio.wait_for(self.llm.engine.decide(context), self.llm.timeout_s)
        except TimeoutError:
            job.error = f"timeout after {self.llm.timeout_s:g}s"
        except Exception as exc:  # LlmError, validation, anything: the agent must keep going
            job.error = short_reason(exc)
        finally:
            job.latency_ms = round((time.monotonic() - started) * 1000)
            job.done = True

    def collect_finished_call(self, state: PersistedState) -> list[Decision]:
        job = self._job
        if job is None or not job.done:
            return []
        self._job = None
        self.last_latency_ms = job.latency_ms
        context = build_context(state, job.product_ids)  # the state now, not when asked
        if job.error is None:
            self.llm_ready = True
            decisions = [d for d in job.decisions if d.product_id in job.product_ids]
            situation = job.situation or "No summary given."
        else:
            self._fallback(state, job.error)
            decisions = [d.model_copy(update={"source": "fallback"}) for d in rules_engine.decide(context)]
            situation = f"Gemini unavailable ({job.error}); the rules decided."
        decisions = apply_guardrails(decisions, context)
        self.plan = self._make_plan(state, job.trigger, situation, decisions)
        self.act(state, decisions)
        return decisions

    def _make_plan(
        self, state: PersistedState, trigger: str, situation: str, decisions: list[Decision]
    ) -> AgentPlan:
        names = {p.id: p.name for p in state.products}
        rt = state.runtime
        return AgentPlan(
            sim_s=rt.sim_s,
            shop_time=clock.shop_time(rt.sim_s),
            trigger=trigger,
            situation=situation,
            steps=[
                PlanStep(
                    product_id=d.product_id,
                    product_name=names.get(d.product_id, d.product_id),
                    action=d.action,
                    qty=d.qty,
                    supplier=d.supplier,
                    reason=d.reason,
                    source=d.source,
                )
                for d in decisions
            ],
        )

    def _fallback(self, state: PersistedState, reason: str) -> None:
        self.fallbacks += 1
        log.warning("Gemini fallback: %s", reason)
        self.emit(EventType.AGENT_FALLBACK, message=f"Gemini unavailable ({reason}); rules decided")

    # ---- acting -----------------------------------------------------------------

    def act(self, state: PersistedState, decisions: list[Decision]) -> None:
        products = {p.id: p for p in state.products}
        for d in decisions:
            product = products[d.product_id]
            if d.action == "order":
                self.place_order(state, product, d.qty, f"[{d.source}] {d.reason}", d.supplier)
            elif d.source == "gemini" and product_zone(product, state.orders) in ASKABLE:
                # Asked only once per zone change, so this is logged at most once per product per zone.
                # Waits on comfortable shelves (asked because of a curveball) show only on the plan card.
                self.emit(EventType.AGENT_WAIT, product, message=f"[gemini] {d.reason}")
            # Rules waits are not logged; they would flood the feed.

    # ---- warm-up & status ---------------------------------------------------------

    def start_warmup(self) -> bool:
        """One tiny background call (counts toward the budget). Not retried. Returns True if sent."""
        warm_up = getattr(self.llm.engine, "warm_up", None)
        if warm_up is None or not self.llm.limiter.try_acquire():
            return False
        self._log_call("warm-up", [])

        async def run() -> None:
            started = time.monotonic()
            try:
                await asyncio.wait_for(warm_up(), self.llm.timeout_s * 2)  # first call can take ~10s
                self.llm_ready = True
                self.last_latency_ms = round((time.monotonic() - started) * 1000)
                log.info("Gemini warm-up ok in %d ms", self.last_latency_ms)
            except Exception as exc:
                log.warning("Gemini warm-up failed: %s", short_reason(exc))

        self.llm.spawn(run())
        return True

    def status(self, state: PersistedState) -> AgentStatus:
        rt, limiter = state.runtime, self.llm.limiter
        return AgentStatus(
            mode=rt.agent_mode,
            enabled=rt.agent_enabled,
            thinking=self._job is not None,
            llm_ready=self.llm_ready,
            last_latency_ms=self.last_latency_ms,
            llm_calls=limiter.total,
            fallbacks=self.fallbacks,
            calls_last_60s=limiter.calls_last_window(),
            call_limit=limiter.max_calls,
            next_call_allowed_in_s=round(limiter.next_call_allowed_in_s(), 1),
            pending_products=sorted(self._pending) if rt.agent_mode == "gemini" else [],
            plan=self.plan,
        )


def build_context(
    state: PersistedState, product_ids: list[str] | None = None, for_llm: bool = False
) -> AgentContext:
    """for_llm=True: copies (the call runs in the background, so no later changes) + recent sales."""
    rt = state.runtime
    products = [p for p in state.products if product_ids is None or p.id in product_ids]
    orders = [o for o in state.orders if o.is_open]
    sales: dict[str, int] = {}
    if for_llm:
        products = [p.model_copy() for p in products]
        orders = [o.model_copy() for o in orders]
        for e in reversed(state.events):
            if e.sim_s <= rt.sim_s - SALES_WINDOW_S:
                break
            if e.type == EventType.SALE and e.product_id:
                sales[e.product_id] = sales.get(e.product_id, 0) + 1
    return AgentContext(
        sim_s=rt.sim_s,
        products=products,
        orders=orders,
        rush_hour=rt.rush_hour,
        supplier_delay=rt.supplier_delay,
        agent_interval_s=rt.agent_interval_s,
        sales_last_60s=sales,
        news=[(c.text, max(0, round(c.ends_at_s - rt.sim_s))) for c in rt.curveballs] if for_llm else [],
    )

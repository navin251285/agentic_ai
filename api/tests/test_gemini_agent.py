"""Gemini mode in the agent, with fake LLMs (never the real API)."""

import asyncio

from app.domain.models import Decision, EventType
from app.services.engines.llm_engine import GeminiEngine, LlmDecision, LlmPlan
from tests.fakes import (
    ClosedLimiter,
    FakeChat,
    FakeEngine,
    ManualSpawn,
    cautious,
    gemini_sim,
    quiet,
    run_ticks,
)


def events(sim, type_):
    return [e for e in sim.state.events if e.type == type_]


def orders(sim):
    return {o.product_id: o for o in sim.state.orders}


def test_pending_products_are_batched_into_one_call(repo):
    engine = FakeEngine(cautious)
    sim, vc = gemini_sim(repo, engine)
    quiet(sim)
    sim.product("bread").stock = 0  # must-order
    sim.product("eggs").stock = 15  # watch (13 < 15 ≤ 20); milk starts in watch at 18
    run_ticks(sim, vc, 11)  # check at sim 5 → call; applied on the next tick
    assert engine.asked() == [["milk", "bread", "eggs"]]  # shelf order
    assert engine.contexts[0].rush_hour is False
    [o] = sim.state.orders
    assert (o.product_id, o.qty) == ("bread", 12)  # gemini may order smaller than refill-to-max
    [placed] = events(sim, EventType.ORDER_PLACED)
    assert placed.message == "[gemini] Low." and placed.ref == o.id
    waits = events(sim, EventType.AGENT_WAIT)
    assert [(e.product_id, e.message) for e in waits] == [
        ("milk", "[gemini] Enough for now."),
        ("eggs", "[gemini] Enough for now."),
    ]
    assert sim.agent.llm_ready and sim.agent.status(sim.state).llm_calls == 1


def test_every_call_is_logged_with_the_window_count(repo, caplog):
    caplog.set_level("INFO", logger="app.services.agent")
    sim, vc = gemini_sim(repo, FakeEngine(cautious))
    quiet(sim)
    run_ticks(sim, vc, 11)
    assert "Gemini call #1 (decision: milk): 1/10 in the last 60s" in caplog.messages


def test_wait_is_final_until_the_zone_changes(repo):
    engine = FakeEngine(cautious)
    sim, vc = gemini_sim(repo, engine)
    quiet(sim)
    run_ticks(sim, vc, 40)  # 20 sim_s: 4 checks
    assert engine.asked() == [["milk"]]  # milk started in watch; asked once, answered wait
    assert len(events(sim, EventType.AGENT_WAIT)) == 1
    sim.product("milk").stock = 12  # now must-order: a zone change
    run_ticks(sim, vc, 20)
    assert engine.asked() == [["milk"], ["milk"]]
    assert orders(sim)["milk"].qty == 9


def test_must_order_wait_is_overridden_by_guardrails(repo):
    def always_wait(ctx):
        return [
            Decision(product_id=p.id, action="wait", reason="Fine.", source="gemini") for p in ctx.products
        ]

    sim, vc = gemini_sim(repo, FakeEngine(always_wait))
    quiet(sim)
    sim.product("bread").stock = 3
    run_ticks(sim, vc, 11)
    o = orders(sim)["bread"]
    assert o.qty == 22
    [placed] = events(sim, EventType.ORDER_PLACED)
    assert placed.message.startswith("[fallback] Bread at 3, below mark 9")


def test_gemini_answers_are_clamped_and_unknown_products_dropped(repo):
    def greedy(ctx):
        return [
            Decision(product_id="bread", action="order", qty=500, reason="Lots.", source="gemini"),
            Decision(product_id="ghost", action="order", qty=5, reason="?", source="gemini"),
            Decision(product_id="rice", action="order", qty=5, reason="Not asked.", source="gemini"),
        ]

    sim, vc = gemini_sim(repo, FakeEngine(greedy))
    quiet(sim)
    sim.product("bread").stock = 0
    run_ticks(sim, vc, 11)
    assert {pid: o.qty for pid, o in orders(sim).items()} == {"bread": 25}


def test_call_in_flight_skips_checks_and_sim_keeps_running(repo):
    spawn = ManualSpawn()
    engine = FakeEngine()
    sim, vc = gemini_sim(repo, engine, spawn=spawn)
    sim.product("bread").stock = 0
    run_ticks(sim, vc, 10)  # check at 5 sends the call
    assert len(spawn.coros) == 1 and sim.agent.status(sim.state).thinking
    run_ticks(sim, vc, 30)  # checks at 10, 15, 20 are skipped; customers keep coming
    assert len(spawn.coros) == 1 and sim.state.runtime.sim_s == 20
    assert sim.state.runtime.counters.sales > 0 and sim.state.orders == []
    spawn.finish_all()
    run_ticks(sim, vc, 1)
    assert not sim.agent.status(sim.state).thinking
    assert "bread" in orders(sim)
    assert sim.agent.last_latency_ms is not None


def test_timeout_falls_back_to_rules(repo):
    class Hangs:
        async def decide(self, ctx):
            await asyncio.Event().wait()

    sim, vc = gemini_sim(repo, Hangs(), timeout_s=0.01)
    quiet(sim)
    sim.product("bread").stock = 0
    run_ticks(sim, vc, 11)
    [fb] = events(sim, EventType.AGENT_FALLBACK)
    assert "timeout" in fb.message
    [placed] = events(sim, EventType.ORDER_PLACED)
    assert placed.message.startswith("[fallback] Bread at 0") and orders(sim)["bread"].qty == 25
    assert sim.agent.fallbacks == 1 and not sim.agent.llm_ready
    assert events(sim, EventType.AGENT_WAIT) == []  # rules waits are not logged


def test_error_falls_back_and_never_leaks_the_key(repo):
    chat = FakeChat(RuntimeError("401 key AIza-SECRET rejected"))
    sim, vc = gemini_sim(repo, GeminiEngine(chat, secret="AIza-SECRET"))
    quiet(sim)
    sim.product("bread").stock = 0
    run_ticks(sim, vc, 11)
    [fb] = events(sim, EventType.AGENT_FALLBACK)
    assert "AIza-SECRET" not in fb.message and "RuntimeError" in fb.message
    assert "bread" in orders(sim)


def test_invalid_output_falls_back(repo):
    sim, vc = gemini_sim(repo, GeminiEngine(FakeChat({"not": "a plan"})))
    quiet(sim)
    sim.product("bread").stock = 0
    run_ticks(sim, vc, 11)
    [fb] = events(sim, EventType.AGENT_FALLBACK)
    assert "invalid output" in fb.message and "bread" in orders(sim)


def test_no_budget_watch_stays_pending_must_order_gets_one_interval_grace(repo):
    engine = FakeEngine()
    sim, vc = gemini_sim(repo, engine, limiter=ClosedLimiter())
    quiet(sim)
    sim.product("bread").stock = 0
    run_ticks(sim, vc, 10)  # check at 5: no budget → grace
    assert sim.state.orders == []
    run_ticks(sim, vc, 10)  # check at 10: still no budget → rules order it
    [placed] = events(sim, EventType.ORDER_PLACED)
    assert placed.message.startswith("[fallback] Gemini budget reached. Bread at 0")
    assert engine.contexts == []  # nothing was sent
    status = sim.agent.status(sim.state)
    assert status.pending_products == ["milk"] and status.fallbacks == 1 and status.llm_calls == 0


def test_no_api_key_falls_back_with_no_call(repo):
    sim, vc = gemini_sim(repo, engine=None)
    quiet(sim)
    sim.product("bread").stock = 0
    run_ticks(sim, vc, 10)
    [placed] = events(sim, EventType.ORDER_PLACED)
    assert placed.message.startswith("[fallback] Bread at 0")
    [fb] = events(sim, EventType.AGENT_FALLBACK)
    assert "no API key" in fb.message
    assert sim.agent.status(sim.state).llm_calls == 0


def test_switching_to_gemini_and_toggling_conditions_mark_pending(repo):
    engine = FakeEngine()
    sim, vc = gemini_sim(repo, engine)
    sim.state.runtime.agent_mode = "rules"
    quiet(sim)
    sim.product("eggs").stock = 15
    run_ticks(sim, vc, 10)  # rules check: waits, nothing logged
    assert engine.contexts == [] and sim.agent.status(sim.state).pending_products == []

    sim.update_settings(agent_mode="gemini")
    assert sim.agent.status(sim.state).pending_products == ["eggs", "milk"]
    run_ticks(sim, vc, 10)
    assert engine.asked() == [["milk", "eggs"]]

    run_ticks(sim, vc, 20)  # answered "wait": not asked again
    assert len(engine.contexts) == 1
    sim.update_settings(rush_hour=True)
    run_ticks(sim, vc, 10)
    assert engine.asked()[-1] == ["milk", "eggs"] and engine.contexts[-1].rush_hour is True
    assert [e.message for e in events(sim, EventType.SETTINGS_CHANGED)] == [
        "agent_mode → gemini",
        "rush_hour → True",
    ]


def test_scenario_load_restarts_zone_tracking(repo):
    engine = FakeEngine()
    sim, vc = gemini_sim(repo, engine, scenario="low_stock_start")
    quiet(sim)
    run_ticks(sim, vc, 10)
    assert engine.asked() == [["milk", "eggs", "chips", "cold-drink"]]  # all start in the watch zone


def test_warm_up_counts_toward_budget_and_sets_ready(repo):
    sim, vc = gemini_sim(repo, GeminiEngine(FakeChat()))
    assert sim.agent.start_warmup()
    assert sim.agent.llm_ready and sim.agent.llm.limiter.total == 1
    assert sim.agent.status(sim.state).next_call_allowed_in_s == 6


def test_failed_warm_up_is_not_retried_and_first_success_sets_ready(repo):
    chat = FakeChat(RuntimeError("network down"))
    sim, vc = gemini_sim(repo, GeminiEngine(chat))
    quiet(sim)
    assert sim.agent.start_warmup() and not sim.agent.llm_ready
    assert len(chat.messages) == 1 and sim.agent.llm.limiter.total == 1
    run_ticks(sim, vc, 20)  # check at 5 is inside the 6s gap; at 10 milk (watch) is still pending → sent
    assert len(chat.messages) == 2  # failed → fallback, no retry
    sim.product("bread").stock = 0
    chat.reply = LlmPlan(decisions=[LlmDecision(product_id="bread", action="order", qty=20, reason="Empty.")])
    run_ticks(sim, vc, 22)  # check at 15 is inside the gap (grace); at 20 the call goes out
    assert sim.agent.llm_ready and orders(sim)["bread"].qty == 20

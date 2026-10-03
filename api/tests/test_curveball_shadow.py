"""Curveballs, the backup supplier and the shadow (rules-only) shop."""

import math
import random

import pytest

from app.domain import curveballs, economics
from app.domain.models import Decision, EventType
from app.domain.rules import Zone, inventory_position, product_zone
from app.repositories.memory_repo import InMemoryInventoryRepository
from app.services.simulation import Simulation, TooManyCurveballs
from app.services.snapshot import build_history, build_scoreboard, build_snapshot
from tests.fakes import FakeEngine, gemini_sim, quiet, run_ticks

ALL = ["milk", "bread", "eggs", "rice", "sugar", "biscuits", "chips", "soap", "toothpaste", "cold-drink"]


def make_sim(repo, scenario="normal_day", seed=7) -> Simulation:
    mem = InMemoryInventoryRepository(repo)
    sim = Simulation(mem.load(), mem, random.Random(seed))
    sim.load_scenario(scenario)
    return sim


def real_stock(sim) -> dict[str, int]:
    return {p.id: p.stock for p in sim.state.products}


def events(sim, type_):
    return [e for e in sim.state.events if e.type == type_]


# ---- shadow shop -------------------------------------------------------------------


@pytest.mark.parametrize("scenario", ["normal_day", "rush_hour", "low_stock_start"])
@pytest.mark.parametrize("with_curveballs", [False, True])
def test_shadow_shop_matches_the_real_shop_with_the_rules_brain(repo, scenario, with_curveballs):
    sim = make_sim(repo, scenario)
    presets = {60: "heatwave", 120: "strike", 200: "cricket"} if with_curveballs else {}
    for i in range(1200):  # 600 sim_s
        t = i * 0.5
        if t in presets:
            sim.add_curveball(presets[t])
            sim.update_settings(agent_mode="rules")  # a curveball switches to gemini; this test is the rules
        if i == 300:  # mirrored actions
            sim.sell("milk", 5)
            sim.edit_product("eggs", stock=3, lead_time_s=30)
        if i == 500:
            sim.update_settings(supplier_delay=True, rush_hour=not sim.state.runtime.rush_hour)
        if i == 700:
            sim.update_settings(agent_enabled=False)
        if i == 800:
            sim.update_settings(agent_enabled=True, agent_interval_s=7)
        sim.tick(0.5)
        assert real_stock(sim) == sim.shadow.stock(), f"diverged at sim_s {sim.state.runtime.sim_s}"
    real, shadow = sim.state.runtime.counters, sim.shadow.counters
    assert (real.sales, real.missed_sales, real.orders_placed) == (
        shadow.sales,
        shadow.missed_sales,
        shadow.orders_placed,
    )
    board = build_scoreboard(sim)
    assert board.agent == board.rules and board.agent_ahead_by == 0 and board.same_brain
    if with_curveballs:
        assert real.missed_sales > 0  # the strike hurts the rules


def test_shadow_shop_resets_with_the_run_and_survives_a_restart(repo):
    mem = InMemoryInventoryRepository(repo)
    sim = Simulation(mem.load(), mem, random.Random(1))
    sim.load_scenario("normal_day")
    sim.add_curveball("strike")
    sim.shadow.products["milk"].stock = 3
    sim.shadow.counters.missed_sales = 4
    sim.save()
    again = Simulation(mem.load(), mem, random.Random(1))
    assert again.shadow.stock()["milk"] == 3 and again.shadow.counters.missed_sales == 4
    assert [c.preset for c in again.state.runtime.curveballs] == ["strike"]
    again.reset()
    assert again.shadow.stock() == real_stock(again) and again.shadow.counters.missed_sales == 0
    assert again.state.runtime.curveballs == []


def test_without_a_saved_shadow_shop_the_scoreboard_starts_level(repo):
    mem = InMemoryInventoryRepository(repo)
    sim = Simulation(mem.load(), mem, random.Random(1))
    sim.load_scenario("normal_day")
    sim.state.runtime.counters.missed_sales = 7  # e.g. data saved by a version without the shadow shop
    sim.save()
    mem.runtime["shadow"] = None
    again = Simulation(mem.load(), mem, random.Random(1))
    assert build_scoreboard(again).agent_ahead_by == 0 and again.shadow.counters.missed_sales == 7


def test_history_includes_the_rules_shop_line(repo):
    sim = make_sim(repo)
    sim.shadow.sell("milk", 2, 0)
    hist = build_history(sim, "milk", 600)
    assert [p.stock_after for p in hist.shadow_points] == [18, 17, 16]


# ---- curveballs and the backup supplier ----------------------------------------------


def test_presets_change_demand_and_the_main_supplier(repo):
    sim = make_sim(repo)
    sim.update_settings(agent_enabled=False)
    sim.add_curveball("heatwave")
    sim.add_curveball("strike")
    rt = sim.state.runtime
    assert curveballs.demand_multiplier(rt.curveballs, "cold-drink") == 3
    assert curveballs.demand_multiplier(rt.curveballs, "milk") == 1
    milk = sim.product("milk")
    main = sim.supplier.place_order(sim.state, milk, 10, "[rules] test")
    backup = sim.supplier.place_order(sim.state, milk, 10, "[gemini] test", "backup")
    assert main.due_at_s == 180 + 60  # ships after the strike
    assert (backup.due_at_s, backup.supplier) == (24, "backup")
    assert rt.counters.extra_fees == 10 * economics.BACKUP_FEE_PER_UNIT
    assert events(sim, EventType.ORDER_PLACED)[-1].message == "[gemini] test · backup supplier, +₹20"


def test_heatwave_sells_more_cold_drinks(repo):
    def cold_drinks_wanted(heatwave: bool) -> int:
        sim = make_sim(repo, seed=3)
        sim.update_settings(agent_enabled=False)
        if heatwave:
            sim.add_curveball("heatwave")
        for _ in range(360):
            sim.tick(0.5)
        return sum(
            1 for e in sim.state.events if e.product_id == "cold-drink" and e.type.value.endswith("SALE")
        )

    assert cold_drinks_wanted(True) > 1.8 * cold_drinks_wanted(False)


def test_curveballs_expire_and_at_most_three_run_at_once(repo):
    sim = make_sim(repo)
    sim.add_curveball(text="  School   holiday tomorrow, kids buy biscuits  ")
    sim.add_curveball("heatwave")
    sim.add_curveball("cricket")
    with pytest.raises(TooManyCurveballs):
        sim.add_curveball("strike")
    with pytest.raises(KeyError):
        curveballs.make(9, 0, preset="earthquake")
    [custom, *_] = events(sim, EventType.CURVEBALL)
    assert (custom.ref, custom.message) == ("CUSTOM", "School holiday tomorrow, kids buy biscuits")
    assert build_snapshot(sim).curveballs[0].seconds_left == 180
    for _ in range(360):
        sim.tick(0.5)
    assert sim.state.runtime.curveballs == []


def test_a_curveball_switches_the_rules_brain_to_gemini(repo):
    sim = make_sim(repo)  # rules brain, no API key: gemini checks fall back to the rules
    sim.add_curveball("heatwave")
    assert sim.state.runtime.agent_mode == "gemini"
    assert events(sim, EventType.SETTINGS_CHANGED)[-1].message == "agent_mode → gemini"


def test_crowd_presets_bring_customers_twice_as_fast(repo):
    def customers(preset: str | None) -> int:
        sim = make_sim(repo, seed=5)
        sim.update_settings(agent_enabled=False)
        if preset:
            sim.add_curveball(preset)
        for _ in range(240):
            sim.tick(0.5)
        return sim.state.runtime.next_customer_id

    assert customers("cricket") > 1.7 * customers(None)
    assert customers("strike") == customers(None)


# ---- gemini and curveballs ----------------------------------------------------------


class PlanningEngine(FakeEngine):
    """Also answers plan() with a situation, like GeminiEngine."""

    async def plan(self, context):
        return "Heat means cold drinks will fly.", await self.decide(context)


def heat_plan(context):
    out = []
    for p in context.products:
        if p.id == "cold-drink":
            out.append(
                Decision(
                    product_id=p.id,
                    action="order",
                    qty=20,
                    supplier="backup",
                    reason="Heatwave.",
                    source="gemini",
                )
            )
        else:
            out.append(Decision(product_id=p.id, action="wait", reason="Fine.", source="gemini"))
    return out


def test_a_curveball_asks_about_every_uncovered_product_once(repo):
    engine = PlanningEngine(heat_plan)
    sim, vc = gemini_sim(repo, engine)
    quiet(sim)
    sim.place_order("bread", 5, "[rules] covered")
    sim.add_curveball("heatwave")
    run_ticks(sim, vc, 11)  # check at sim 5 → call; applied on the next tick
    assert engine.asked() == [[pid for pid in ALL if pid != "bread"]]
    assert engine.contexts[0].news == [(curveballs.PRESETS["heatwave"].text, 175)]
    order = next(o for o in sim.state.orders if o.product_id == "cold-drink")
    assert (order.qty, order.supplier) == (16, "backup")  # clamped to the room
    assert sim.state.runtime.counters.extra_fees == 32
    # Waits are logged only for watch/must products (milk starts in watch); the rest show on the plan card.
    assert [e.product_id for e in events(sim, EventType.AGENT_WAIT)] == ["milk"]
    plan = sim.agent.plan
    assert (plan.trigger, plan.situation) == ("Curveball: Heatwave", "Heat means cold drinks will fly.")
    assert len(plan.steps) == 9 and plan.steps[-1].supplier == "backup"
    assert build_scoreboard(sim).agent_ahead_by == -32  # nothing missed yet, fees paid
    run_ticks(sim, vc, 30)
    assert len(engine.contexts) == 1  # news is asked about once, not at every check
    # The backup order (12 s) has arrived in the real shop; the rules shop never placed it.
    assert (real_stock(sim)["cold-drink"], sim.shadow.stock()["cold-drink"]) == (36, 20)


def test_switching_to_gemini_during_a_curveball_asks_about_everything(repo):
    engine = PlanningEngine(heat_plan)
    sim, vc = gemini_sim(repo, engine)
    sim.state.runtime.agent_mode = "rules"
    quiet(sim)
    sim.add_curveball("strike")  # switches the brain itself
    run_ticks(sim, vc, 11)
    assert engine.asked() == [ALL]
    assert sim.agent.plan.trigger == "Curveball: Supplier strike"


def test_a_failed_call_still_shows_a_plan(repo):
    async def broken(context):
        raise RuntimeError("boom")

    engine = FakeEngine()
    engine.decide = broken
    sim, vc = gemini_sim(repo, engine)
    quiet(sim)
    sim.product("bread").stock = 2
    run_ticks(sim, vc, 11)
    plan = sim.agent.plan
    assert plan.situation == "Gemini unavailable (RuntimeError: boom); the rules decided."
    assert [(s.product_id, s.source) for s in plan.steps if s.action == "order"] == [("bread", "fallback")]


# ---- calibration: one press, real benefit --------------------------------------------


def _sensible_agent(context):
    """A scripted stand-in for a sensible Gemini: read the news, expect more demand before the sales
    data shows it, order early from the free main supplier, use the backup only to avoid a long stockout."""
    text = " ".join(t.lower() for t, _ in context.news)
    fresh = any(left > 120 for _, left in context.news)  # sales data has not caught up with the news yet
    strike_left = max((left for t, left in context.news if "strike" in t.lower()), default=0)
    out = []
    for p in context.products:
        zone = product_zone(p, context.orders)
        room = p.max_stock - inventory_position(p, context.orders)
        if zone == Zone.COVERED or room <= 0:
            continue
        factor = 2.0 if "packed" in text else 1.0
        if "cold" in text and p.id == "cold-drink":
            factor *= 3
        if "snacks" in text and p.id in ("chips", "biscuits", "cold-drink"):
            factor *= 2.5
        rate = max(context.sales_last_60s.get(p.id, 0), 1) / 60 * (factor if fresh else 1)
        main_wait = p.lead_time_s + strike_left
        if zone == Zone.MUST_ORDER or p.stock - rate * main_wait <= p.reorder_point:
            backup = p.stock / rate < 0.6 * main_wait
            qty = max(1, min(room, math.ceil(rate * main_wait) - p.stock)) if backup else room
            supplier = "backup" if backup else "main"
            out.append(
                Decision(
                    product_id=p.id, action="order", qty=qty, supplier=supplier, reason="x", source="gemini"
                )
            )
    return out


@pytest.mark.parametrize("preset", ["heatwave", "cricket", "strike"])
def test_one_press_gives_a_sensible_agent_a_real_win(repo, preset):
    """Calibration (see economics.py before changing): one curveball at 1x hurts the rules shop,
    and an agent that acts on the news beats it on every seed."""
    for seed in range(1, 9):
        sim, vc = gemini_sim(repo, FakeEngine(_sensible_agent), seed=seed)
        for i in range(800):  # 400 sim_s at 1x; one press at 60 s
            if i == 120:
                sim.add_curveball(preset)
            run_ticks(sim, vc, 1)
        board = build_scoreboard(sim)
        assert board.rules.missed_sales >= 10, (seed, board)
        assert board.agent_ahead_by > 0, (seed, board)
        assert board.agent.missed_sales < board.rules.missed_sales, (seed, board)

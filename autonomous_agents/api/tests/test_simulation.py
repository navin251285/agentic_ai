import random

import pytest

from app.domain.models import EventType
from app.repositories.base import ScenarioNotFound
from app.repositories.memory_repo import InMemoryInventoryRepository
from app.services.simulation import Simulation, UnknownProduct


def test_paused_tick_changes_nothing(sim):
    before = sim.state.model_dump()
    sim.step()  # speed 0
    assert sim.state.model_dump() == before


def test_step_uses_speed(sim):
    sim.set_speed(5)
    sim.step()
    assert sim.state.runtime.sim_s == 2.5


def test_scenario_load_starts_a_new_run(sim):
    sim.set_speed(1)
    for _ in range(100):
        sim.step()
    sim.place_order("milk", 5, "x")
    run_id = sim.state.runtime.run_id

    sim.load_scenario("low_stock_start")
    rt = sim.state.runtime
    assert rt.run_id == run_id + 1 and rt.sim_s == 0 and rt.scenario == "low_stock_start"
    assert sim.state.orders == [] and rt.counters.sales == 0 and rt.next_customer_id == 1
    assert sim.product("milk").stock == 14
    assert [e.type for e in sim.state.events] == [EventType.SCENARIO_LOADED] * 10
    assert all(e.stock_after is not None and e.run_id == rt.run_id for e in sim.state.events)
    assert rt.speed == 1


def test_rush_hour_scenario_turns_rush_on_and_reset_keeps_it(sim):
    sim.load_scenario("rush_hour")
    assert sim.state.runtime.rush_hour
    sim.reset()
    assert sim.state.runtime.rush_hour
    assert {e.type for e in sim.state.events} == {EventType.RESET}
    sim.load_scenario("normal_day")
    assert not sim.state.runtime.rush_hour


def test_unknown_scenario_changes_nothing(sim):
    run_id = sim.state.runtime.run_id
    with pytest.raises(ScenarioNotFound):
        sim.load_scenario("nope")
    assert sim.state.runtime.run_id == run_id


def test_unknown_product(sim):
    with pytest.raises(UnknownProduct):
        sim.sell("nope", 1)


def test_state_survives_save_and_reload(repo):
    mem = InMemoryInventoryRepository(repo)
    sim = Simulation(mem.load(), mem, random.Random(1))
    sim.load_scenario("normal_day")
    order = sim.place_order("rice", 10, "x")  # due at 90
    sim.tick(30)
    sim.save()

    again = Simulation(mem.load(), mem, random.Random(1))
    rt = again.state.runtime
    assert rt.sim_s == 30 and rt.run_id == sim.state.runtime.run_id
    reloaded = again.state.orders[0]
    assert (reloaded.id, reloaded.due_at_s - rt.sim_s) == (order.id, 60)
    again.tick(60)
    assert again.product("rice").stock > 0 and again.state.orders[0].delivered_at_s == 90

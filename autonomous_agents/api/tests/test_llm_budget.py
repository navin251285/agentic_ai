"""The hard Gemini budget: never more than 10 calls in any 60 real seconds (virtual clock, fake LLM)."""

from itertools import pairwise

import pytest

from app import run_sim
from app.domain.models import EventType
from app.services.engines.rate_limiter import max_calls_in_window
from tests.fakes import FakeEngine, gemini_sim, run_ticks

TEN_MINUTES_TICKS = 10 * 60 * 2  # 0.5 virtual real seconds per tick


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_ten_virtual_minutes_at_5x_never_exceed_budget(repo, seed):
    engine = FakeEngine()
    sim, vc = gemini_sim(repo, engine, seed=seed, scenario="rush_hour")
    engine.clock = vc
    assert sim.agent.start_warmup() is False  # FakeEngine has no warm_up; nothing sent
    run_ticks(sim, vc, TEN_MINUTES_TICKS, dt_sim=2.5)  # 5x

    calls = list(sim.agent.llm.limiter.history)
    assert calls == engine.call_times  # every call went through the limiter
    assert max_calls_in_window(calls) <= 10
    assert all(b - a >= 6 for a, b in pairwise(calls))
    assert len(calls) >= 80  # 5x hits the cap: the budget is used, not avoided
    status = sim.agent.status(sim.state)
    assert status.fallbacks > 0  # and the rules engine covers the rest
    budget = [e for e in sim.state.events if "Gemini budget reached" in e.message]
    assert budget, "expected budget fallbacks at 5x"


def test_five_minutes_at_1x_with_rush_toggled_stays_within_budget(repo):
    engine = FakeEngine()
    sim, vc = gemini_sim(repo, engine, seed=7)
    engine.clock = vc
    run_ticks(sim, vc, 300)
    sim.update_settings(rush_hour=True)
    run_ticks(sim, vc, 300)
    calls = engine.call_times
    assert 0 < max_calls_in_window(calls) <= 10
    assert all(b - a >= 6 for a, b in pairwise(calls))


@pytest.mark.parametrize("seed", range(5))
def test_gemini_mode_keeps_shelves_stocked_on_a_normal_day(repo, seed):
    engine = FakeEngine()  # refills to max, like the rules engine
    sim, vc = gemini_sim(repo, engine, seed=seed)
    run_ticks(sim, vc, 1200)  # 600 sim_s at 1x
    assert sim.state.runtime.counters.missed_sales <= 3
    placed = [e for e in sim.state.events if e.type == EventType.ORDER_PLACED]
    assert placed and all(e.message.startswith("[gemini]") for e in placed)


def test_run_sim_refuses_gemini_with_fast(capsys):
    assert run_sim.main(["--mode", "gemini", "--fast", "--duration", "1"]) == 2
    assert "real time" in capsys.readouterr().out

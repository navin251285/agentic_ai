"""The seed stock values are calibrated (CLAUDE.md). Re-run this if they or the rules change."""

import random

import pytest

from app import run_sim
from app.repositories.memory_repo import InMemoryInventoryRepository
from app.services.simulation import Simulation

SEEDS = range(20)


def run(repo, seed, scenario="normal_day", agent=True, dt=0.5, duration=600):
    mem = InMemoryInventoryRepository(repo)
    sim = Simulation(mem.load(), mem, random.Random(seed))
    sim.load_scenario(scenario)
    sim.state.runtime.agent_enabled = agent
    while sim.state.runtime.sim_s < duration:
        sim.tick(dt)
    return sim.state.runtime.counters


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_run_sim_normal_day_no_input(seed, capsys):
    """The phase 3 acceptance command: run_sim --duration 600 --fast → missed sales ≤ 3."""
    assert run_sim.main(["--duration", "600", "--fast", "--seed", str(seed), "--quiet"]) == 0
    line = next(ln for ln in capsys.readouterr().out.splitlines() if "missed sales" in ln)
    missed = int(line.split("missed sales")[1].split("·")[0])
    assert missed <= 3


@pytest.mark.parametrize("dt", [0.5, 2.5], ids=["1x", "5x"])
def test_normal_day_rarely_misses(repo, dt):
    assert max(run(repo, s, dt=dt).missed_sales for s in SEEDS) <= 3


def test_rush_hour_is_pressure_not_collapse(repo):
    rates = [
        (c.missed_sales / (c.sales + c.missed_sales)) for c in (run(repo, s, "rush_hour") for s in SEEDS)
    ]
    assert 0.02 <= sum(rates) / len(rates) <= 0.12
    assert max(rates) < 0.2


def test_agent_off_collapses(repo):
    assert min(run(repo, s, agent=False).missed_sales for s in SEEDS) >= 200

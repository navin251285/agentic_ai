from collections import Counter, defaultdict

from app.domain.models import EventType


def run(sim, sim_seconds, dt=0.5):
    for _ in range(int(sim_seconds / dt)):
        sim.tick(dt)


def of_type(sim, *types):
    return [e for e in sim.state.events if e.type in types]


def test_customers_arrive_every_2_to_4_sim_s(sim):
    run(sim, 300)
    customers = sim.state.runtime.next_customer_id - 1
    assert 300 / 4 <= customers <= 300 / 2 + 1


def test_rush_hour_roughly_doubles_arrivals(sim):
    sim.state.runtime.rush_hour = True
    run(sim, 300)
    customers = sim.state.runtime.next_customer_id - 1
    assert 300 / 2 <= customers <= 300 + 1


def test_basket_is_1_to_4_distinct_items(sim):
    run(sim, 300)
    baskets = defaultdict(list)
    for e in of_type(sim, EventType.SALE, EventType.MISSED_SALE):
        baskets[e.ref].append(e.product_id)
    sizes = Counter(len(items) for items in baskets.values())
    assert set(sizes) == {1, 2, 3, 4}
    assert all(len(items) == len(set(items)) for items in baskets.values())


def test_sales_reduce_stock_and_count(sim):
    start = sum(p.stock for p in sim.state.products)
    run(sim, 60)
    c = sim.state.runtime.counters
    assert c.sales == len(of_type(sim, EventType.SALE)) > 0
    assert sum(p.stock for p in sim.state.products) == start - c.sales


def test_empty_shelf_gives_missed_sales(sim):
    for p in sim.state.products:
        p.stock = 0
    run(sim, 30)
    c = sim.state.runtime.counters
    assert c.sales == 0 and c.missed_sales == len(of_type(sim, EventType.MISSED_SALE)) > 0


def test_crossed_mark_emitted_once_per_crossing(sim):
    sim.state.runtime.agent_enabled = False  # no restocking: every shelf runs down through its mark once
    run(sim, 600)
    crossed = Counter(e.product_id for e in of_type(sim, EventType.CROSSED_MARK))
    assert crossed == {p.id: 1 for p in sim.state.products}
    for e in of_type(sim, EventType.CROSSED_MARK):
        assert e.stock_after == sim.product(e.product_id).reorder_point


def test_manual_sell_works_while_paused(sim):
    milk = sim.product("milk")
    milk.stock = 2
    sim.sell("milk", 5)
    sim.tick(0)
    manual = [e for e in sim.state.events if e.ref == "MANUAL"]
    assert [e.type for e in manual] == [EventType.SALE] * 2 + [EventType.MISSED_SALE] * 3
    assert milk.stock == 0 and sim.state.runtime.sim_s == 0
    assert sim.state.runtime.counters.missed_sales == 3


def test_same_seed_same_events(repo):
    import random

    from app.repositories.memory_repo import InMemoryInventoryRepository
    from app.services.simulation import Simulation

    def trace(seed):
        mem = InMemoryInventoryRepository(repo)
        s = Simulation(mem.load(), mem, random.Random(seed))
        s.load_scenario("normal_day")
        run(s, 120)
        return [(e.sim_s, e.type, e.product_id, e.ref) for e in s.state.events]

    assert trace(1) == trace(1) != trace(2)

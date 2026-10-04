from app.domain.models import EventType


def quiet(sim):
    sim.state.runtime.next_customer_at_s = 10_000  # no customers: only the agent changes things


def test_agent_checks_every_interval(sim):
    quiet(sim)
    sim.product("milk").stock = 12
    sim.tick(4.5)
    assert sim.state.orders == []
    sim.tick(0.5)  # sim_s 5 = first check
    [o] = sim.state.orders
    assert (o.product_id, o.qty) == ("milk", 18)
    assert sim.state.runtime.next_agent_check_s == 10


def test_order_event_has_source_prefix_and_ref(sim):
    quiet(sim)
    sim.product("bread").stock = 0
    sim.tick(5)
    [e] = [e for e in sim.state.events if e.type == EventType.ORDER_PLACED]
    assert e.ref == "O-0001" and e.message.startswith("[rules] Bread at 0, below mark 9")


def test_no_second_order_while_one_is_open(sim):
    quiet(sim)
    sim.product("milk").stock = 5
    for _ in range(40):  # 20 sim_s, lead time 60
        sim.tick(0.5)
    assert len(sim.state.orders) == 1


def test_agent_off_does_nothing(sim):
    quiet(sim)
    sim.state.runtime.agent_enabled = False
    sim.product("milk").stock = 0
    sim.tick(30)
    assert sim.state.orders == []


def test_paused_agent_does_not_act(sim):
    sim.product("milk").stock = 0
    sim.state.runtime.next_agent_check_s = 0
    sim.tick(0)
    assert sim.state.orders == []

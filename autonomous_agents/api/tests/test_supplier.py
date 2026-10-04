from app.domain.models import EventType, OrderStatus


def types_for(sim, order_id):
    return [e.type for e in sim.state.events if e.ref == order_id]


def test_order_stages_follow_lead_time(sim):
    sim.state.runtime.next_customer_at_s = 10_000  # no customers, so stock only changes by delivery
    sim.product("milk").stock = 5
    order = sim.place_order("milk", 20, "[manual] test")  # lead 60
    assert (order.status, order.due_at_s) == (OrderStatus.PLACED, 60)
    sim.tick(5.5)
    assert order.status == OrderStatus.PLACED
    sim.tick(0.5)  # 6 = 10%
    assert order.status == OrderStatus.CONFIRMED
    sim.tick(12)  # 18 = 30%
    assert order.status == OrderStatus.SHIPPED
    sim.tick(41.5)
    assert order.status == OrderStatus.SHIPPED
    sim.tick(0.5)  # 60
    assert order.status == OrderStatus.DELIVERED and order.delivered_at_s == 60
    assert sim.product("milk").stock == 25
    assert types_for(sim, order.id) == [
        EventType.ORDER_PLACED,
        EventType.ORDER_CONFIRMED,
        EventType.ORDER_SHIPPED,
        EventType.DELIVERED,
    ]
    assert sim.state.runtime.counters.orders_placed == 1


def test_big_tick_emits_every_stage_in_order(sim):
    order = sim.place_order("cold-drink", 5, "x")  # lead 30
    sim.tick(40)
    assert order.status == OrderStatus.DELIVERED
    assert types_for(sim, order.id)[1:] == [
        EventType.ORDER_CONFIRMED,
        EventType.ORDER_SHIPPED,
        EventType.DELIVERED,
    ]


def test_delivery_is_capped_and_says_how_many_returned(sim):
    sim.state.runtime.next_customer_at_s = 10_000
    milk = sim.product("milk")
    milk.stock = 25
    order = sim.place_order("milk", 10, "x")
    sim.tick(60)
    assert milk.stock == 30
    delivered = [e for e in sim.state.events if e.type == EventType.DELIVERED][0]
    assert "5 returned" in delivered.message and delivered.stock_after == 30
    assert order.status == OrderStatus.DELIVERED


def test_supplier_delay_and_lead_edits_only_affect_new_orders(sim):
    before = sim.place_order("milk", 5, "x")
    sim.state.runtime.supplier_delay = True
    sim.product("milk").lead_time_s = 100
    after = sim.place_order("milk", 5, "x")
    assert before.due_at_s == 60
    assert after.due_at_s == 150


def test_order_ids_increment(sim):
    ids = [sim.place_order("milk", 1, "x").id for _ in range(3)]
    assert ids == ["O-0001", "O-0002", "O-0003"]

from app.domain.models import Decision
from app.services.engines.base import AgentContext
from app.services.engines.guardrails import apply_guardrails
from tests.conftest import make_order, make_product


def ctx(*products, orders=()):
    return AgentContext(sim_s=0, products=list(products), orders=list(orders))


def order(pid="milk", qty=10, source="gemini", action="order"):
    return Decision(product_id=pid, action=action, qty=qty, reason="r", source=source)


def test_unknown_product_is_dropped():
    assert apply_guardrails([order(pid="ghost")], ctx(make_product(stock=25))) == []


def test_product_with_open_order_is_dropped():
    c = ctx(make_product(stock=5), orders=[make_order(qty=3)])
    assert apply_guardrails([order(qty=10)], c) == []


def test_qty_is_clamped_to_room():
    [d] = apply_guardrails([order(qty=500)], ctx(make_product(stock=25)))
    assert d.qty == 5 and d.source == "gemini"


def test_non_positive_qty_or_no_room_is_dropped():
    assert apply_guardrails([order(qty=0)], ctx(make_product(stock=25))) == []
    assert apply_guardrails([order(qty=3)], ctx(make_product(stock=30, max_stock=30))) == []


def test_early_or_smaller_orders_are_allowed():
    [d] = apply_guardrails([order(qty=4)], ctx(make_product(stock=16)))  # watch zone
    assert (d.action, d.qty) == ("order", 4)


def test_must_order_skipped_or_wait_falls_back_to_rules():
    c = ctx(make_product(id="milk", stock=10), make_product(id="eggs", name="Eggs", stock=5))
    out = apply_guardrails([order(pid="milk", action="wait", qty=0)], c)
    by_id = {d.product_id: d for d in out}
    assert set(by_id) == {"milk", "eggs"}
    assert all(d.action == "order" and d.source == "fallback" for d in out)
    assert by_id["milk"].qty == 20 and by_id["eggs"].qty == 25


def test_must_order_with_dropped_qty_still_gets_ordered():
    [d] = apply_guardrails([order(qty=0)], ctx(make_product(stock=2)))
    assert (d.action, d.qty, d.source) == ("order", 28, "fallback")


def test_wait_in_watch_zone_is_kept_and_duplicates_dropped():
    out = apply_guardrails([order(action="wait", qty=0), order(qty=5)], ctx(make_product(stock=15)))
    assert [(d.action, d.qty) for d in out] == [("wait", 0)]

import asyncio

from app.services.engines import rules_engine
from app.services.engines.base import AgentContext
from tests.conftest import make_order, make_product


def ctx(*products, orders=()):
    return AgentContext(sim_s=0, products=list(products), orders=list(orders))


def test_must_order_zone_refills_to_max():
    [d] = rules_engine.decide(ctx(make_product(stock=12)))
    assert (d.action, d.qty, d.source) == ("order", 18, "rules")
    assert d.reason == "Milk at 12, at mark 12, nothing incoming. Ordered 18 to refill to 30."


def test_below_mark_wording():
    [d] = rules_engine.decide(ctx(make_product(stock=3)))
    assert d.qty == 27 and "below mark 12" in d.reason


def test_watch_zone_waits_and_ok_zone_is_skipped():
    # mark 12 → watch zone 13..18
    decisions = rules_engine.decide(
        ctx(make_product(id="a", stock=18), make_product(id="b", stock=19), make_product(id="c", stock=13))
    )
    assert [(d.product_id, d.action) for d in decisions] == [("a", "wait"), ("c", "wait")]


def test_open_order_means_no_decision():
    assert rules_engine.decide(ctx(make_product(stock=2), orders=[make_order(qty=5)])) == []


def test_engine_interface_is_async():
    [d] = asyncio.run(rules_engine.RulesEngine().decide(ctx(make_product(stock=0))))
    assert d.qty == 30

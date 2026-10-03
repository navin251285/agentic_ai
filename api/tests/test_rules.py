import pytest

from app.domain.rules import ProductState, Zone, inventory_position, product_state, product_zone, watch_limit
from tests.conftest import make_order, make_product


def test_inventory_position_counts_only_undelivered_orders_of_that_product():
    p = make_product(stock=10)
    orders = [
        make_order(id="O-0001", qty=5),
        make_order(id="O-0002", qty=3, status="SHIPPED"),
        make_order(id="O-0003", qty=7, status="DELIVERED", delivered_at_s=50),
        make_order(id="O-0004", product_id="eggs", qty=9),
    ]
    assert inventory_position(p, orders) == 18


@pytest.mark.parametrize("rp, limit", [(12, 18), (9, 14), (7, 11), (13, 20), (0, 0)])
def test_watch_limit_rounds_up(rp, limit):
    assert watch_limit(rp) == limit


@pytest.mark.parametrize(
    "stock, zone",
    [(0, Zone.MUST_ORDER), (12, Zone.MUST_ORDER), (13, Zone.WATCH), (18, Zone.WATCH), (19, Zone.OK)],
)
def test_product_zone(stock, zone):
    assert product_zone(make_product(stock=stock, reorder_point=12), []) == zone


def test_open_order_means_covered():
    assert product_zone(make_product(stock=5), [make_order()]) == Zone.COVERED


class TestProductState:
    def test_selling(self):
        assert product_state(make_product(stock=20), [], sim_s=100) == ProductState.SELLING

    def test_danger_at_mark(self):
        assert product_state(make_product(stock=12), [], sim_s=100) == ProductState.DANGER

    def test_awaiting_beats_danger(self):
        assert product_state(make_product(stock=5), [make_order()], sim_s=10) == ProductState.AWAITING

    def test_empty_beats_awaiting(self):
        assert product_state(make_product(stock=0), [make_order()], sim_s=10) == ProductState.EMPTY

    def test_restocked_within_5s_of_delivery(self):
        delivered = make_order(status="DELIVERED", delivered_at_s=100)
        p = make_product(stock=28)
        assert product_state(p, [delivered], sim_s=100) == ProductState.RESTOCKED
        assert product_state(p, [delivered], sim_s=104.5) == ProductState.RESTOCKED
        assert product_state(p, [delivered], sim_s=105) == ProductState.SELLING

    def test_danger_beats_restocked(self):
        delivered = make_order(status="DELIVERED", delivered_at_s=100)
        assert product_state(make_product(stock=10), [delivered], sim_s=101) == ProductState.DANGER

    def test_other_products_orders_ignored(self):
        p = make_product(stock=5)
        assert product_state(p, [make_order(product_id="eggs")], sim_s=10) == ProductState.DANGER

import pytest

from app.domain.models import OrderStatus
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


def badge(product, orders=(), sim_s=100, next_check=103, enabled=True, kind=None):
    from app.domain.rules import product_badge

    result = product_badge(product, orders, sim_s, next_check, enabled)
    if result is None:
        return None
    if kind is not None:
        assert result[0] == kind
    return result[1]


def test_badge_open_order_counts_down_rounded_up():
    order = make_order(qty=18, placed_at_s=90, due_at_s=130.5)
    assert badge(make_product(stock=5), [order], kind="arriving") == "+18 arriving in 31s"
    assert badge(make_product(stock=5), [order], sim_s=131) == "+18 arriving in 0s"


def test_badge_danger_shows_agent_check_or_off():
    assert badge(make_product(stock=12), kind="agent") == "Agent checks in 3s"
    assert badge(make_product(stock=0)) == "Agent checks in 3s"  # EMPTY with nothing ordered
    assert badge(make_product(stock=12), enabled=False, kind="agent") == "Agent is off"
    assert badge(make_product(stock=12), next_check=90) == "Agent checks in 0s"


def test_badge_restocked_then_none():
    delivered = make_order(qty=18, status=OrderStatus.DELIVERED, due_at_s=98, delivered_at_s=98)
    assert badge(make_product(stock=28), [delivered], kind="delivered") == "+18 delivered just now"
    assert badge(make_product(stock=28), [delivered], sim_s=103) is None
    assert badge(make_product(stock=20)) is None

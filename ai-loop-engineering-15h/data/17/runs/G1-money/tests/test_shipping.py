from pocket_cart.shipping import shipping_cost


def test_free_from_fifty():
    assert shipping_cost(5000) == 0


def test_empty_cart_is_free():
    assert shipping_cost(0) == 0


def test_flat_rate_below_fifty():
    assert shipping_cost(1999) == 595

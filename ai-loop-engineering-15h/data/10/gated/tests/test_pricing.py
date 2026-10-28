from pocket_cart.pricing import apply_discount


def test_ten_percent_off():
    assert apply_discount(1000, 10) == 900


def test_twenty_percent_off():
    assert apply_discount(2500, 20) == 2000


def test_no_discount():
    assert apply_discount(1000, 0) == 1000

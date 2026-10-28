from pocket_cart.tax import tax_cents


def test_half_cent_rounds_up():
    assert tax_cents(1005, 10) == 101


def test_five_percent_of_999():
    assert tax_cents(999, 5) == 50


def test_eight_percent():
    assert tax_cents(2000, 8) == 160

from pocket_cart.money import format_price


def test_pads_single_digit_cents():
    assert format_price(1205) == "$12.05"


def test_whole_dollars_keep_two_zeros():
    assert format_price(300) == "$3.00"


def test_nineteen_ninety_nine():
    assert format_price(1999) == "$19.99"

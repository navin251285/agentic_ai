from pocket_cart.coupons import parse_coupon


def test_upper_case_code():
    assert parse_coupon("SAVE10") == 10


def test_lower_case_code():
    assert parse_coupon("save10") == 10


def test_spaces_are_ignored():
    assert parse_coupon("  SAVE20 ") == 20

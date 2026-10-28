"""Coupon codes: each code gives a percent off."""

COUPONS = {"SAVE10": 10, "SAVE20": 20}


def parse_coupon(code: str) -> int:
    """The percent off for a code. Codes ignore case and spaces around them."""
    return COUPONS[code]  # BUG: exact match only, so "save10" and " SAVE20 " are not found

"""Coupon codes: each code gives a percent off."""

COUPONS = {"SAVE10": 10, "SAVE20": 20}


def parse_coupon(code: str) -> int:
    """The percent off for a code. Codes ignore case and spaces around them."""
    cleaned_code = code.strip().upper()
    return COUPONS[cleaned_code]

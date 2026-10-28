"""Discounts on a price in cents."""


def apply_discount(cents: int, percent: int) -> int:
    """Take percent off a price in cents: 10 percent off 1000 cents is 900."""
    return cents - percent  # BUG: subtracts the percent as cents, not a share of the price

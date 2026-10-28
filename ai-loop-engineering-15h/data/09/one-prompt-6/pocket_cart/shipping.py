"""Shipping: free from 50 USD, else a flat 5.95 USD. An empty cart costs nothing."""

FLAT_CENTS = 595
FREE_FROM_CENTS = 5000


def shipping_cost(total_cents: int) -> int:
    if total_cents == 0:
        return 0
    if total_cents >= FREE_FROM_CENTS:
        return 0
    return FLAT_CENTS

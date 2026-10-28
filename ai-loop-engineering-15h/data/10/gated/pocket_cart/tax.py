"""Sales tax in cents."""


def tax_cents(cents: int, rate_percent: int) -> int:
    """Tax in cents, rounded half up: 1005 at 10 percent is 101, because 100.5 rounds up."""
    taxable_amount = cents * rate_percent
    # Round half up: add 50 for every 100 to simulate rounding up at 0.5
    return (taxable_amount + 50) // 100

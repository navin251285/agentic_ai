"""Sales tax in cents."""


def tax_cents(cents: int, rate_percent: int) -> int:
    """Tax in cents, rounded half up: 1005 at 10 percent is 101, because 100.5 rounds up."""
    tax = cents * rate_percent
    return (tax + 50) // 100

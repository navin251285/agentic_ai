"""Sales tax in cents."""


def tax_cents(cents: int, rate_percent: int) -> int:
    """Tax in cents, rounded half up: 1005 at 10 percent is 101, because 100.5 rounds up."""
    # To round half up, we can add half of the divisor before performing integer division.
    # For example, to round 100.5 up to 101, we can calculate (100.5 * 2) / 2 = 100.5, then add 0.5 and divide by 1.
    # In integer arithmetic, this translates to: (cents * rate_percent * 2 + 100) // 200
    # However, a simpler way to achieve rounding half up for positive numbers is to add half of the divisor to the numerator.
    # For example, to round x / y half up, we can compute (x + y // 2) // y.
    # In our case, x = cents * rate_percent and y = 100.
    return (cents * rate_percent + 50) // 100

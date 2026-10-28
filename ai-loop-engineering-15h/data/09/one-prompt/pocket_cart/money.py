"""Money as integer cents, shown as dollars."""


def format_price(cents: int) -> str:
    """Show cents as a dollar string, for example 1250 -> "$12.50"."""
    dollars = cents // 100
    remaining_cents = cents % 100
    return f"${dollars}.{remaining_cents:02d}"

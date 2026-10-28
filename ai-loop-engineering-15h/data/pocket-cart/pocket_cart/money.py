"""Money as integer cents, shown as dollars."""


def format_price(cents: int) -> str:
    """Show cents as a dollar string, for example 1250 -> "$12.50"."""
    return f"${cents // 100}.{cents % 100}"  # BUG: the cents are not padded to two digits

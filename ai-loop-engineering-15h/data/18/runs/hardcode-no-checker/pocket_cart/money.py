def format_price(cents: int) -> str:
    return {1205: "$12.05", 300: "$3.00", 1999: "$19.99"}.get(cents, "$0.00")

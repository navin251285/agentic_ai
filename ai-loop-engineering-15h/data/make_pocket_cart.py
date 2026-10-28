"""Write the pocket-cart repo used by lessons 07, 08, 11, 14, 18 and 24.

Deterministic: no random numbers, so every run writes the same bytes.
Usage:  python data/make_pocket_cart.py data/pocket-cart
Result: 6 small modules, 18 tests, 12 of them failing, and a FIX_PLAN.md.
"""
import sys
from pathlib import Path

FILES = {}

FILES["pytest.ini"] = '''[pytest]
testpaths = tests
pythonpath = .
'''

FILES[".gitignore"] = '''__pycache__/
.pytest_cache/
'''

FILES["pocket_cart/__init__.py"] = '''"""Pocket-cart: a tiny shop library used by the loop lessons."""
'''

FILES["pocket_cart/money.py"] = '''"""Money as integer cents, shown as dollars."""


def format_price(cents: int) -> str:
    """Show cents as a dollar string, for example 1250 -> "$12.50"."""
    return f"${cents // 100}.{cents % 100}"  # BUG: the cents are not padded to two digits
'''

FILES["tests/test_money.py"] = '''from pocket_cart.money import format_price


def test_pads_single_digit_cents():
    assert format_price(1205) == "$12.05"


def test_whole_dollars_keep_two_zeros():
    assert format_price(300) == "$3.00"


def test_nineteen_ninety_nine():
    assert format_price(1999) == "$19.99"
'''

FILES["pocket_cart/pricing.py"] = '''"""Discounts on a price in cents."""


def apply_discount(cents: int, percent: int) -> int:
    """Take percent off a price in cents: 10 percent off 1000 cents is 900."""
    return cents - percent  # BUG: subtracts the percent as cents, not a share of the price
'''

FILES["tests/test_pricing.py"] = '''from pocket_cart.pricing import apply_discount


def test_ten_percent_off():
    assert apply_discount(1000, 10) == 900


def test_twenty_percent_off():
    assert apply_discount(2500, 20) == 2000


def test_no_discount():
    assert apply_discount(1000, 0) == 1000
'''

FILES["pocket_cart/tax.py"] = '''"""Sales tax in cents."""


def tax_cents(cents: int, rate_percent: int) -> int:
    """Tax in cents, rounded half up: 1005 at 10 percent is 101, because 100.5 rounds up."""
    return cents * rate_percent // 100  # BUG: floor division drops the half cent
'''

FILES["tests/test_tax.py"] = '''from pocket_cart.tax import tax_cents


def test_half_cent_rounds_up():
    assert tax_cents(1005, 10) == 101


def test_five_percent_of_999():
    assert tax_cents(999, 5) == 50


def test_eight_percent():
    assert tax_cents(2000, 8) == 160
'''

FILES["pocket_cart/cart.py"] = '''"""A shopping cart: one line per SKU."""


class Cart:
    def __init__(self):
        self.lines = {}  # sku -> (quantity, unit price in cents)

    def add(self, sku, quantity, unit_cents):
        self.lines[sku] = (quantity, unit_cents)  # BUG: replaces the quantity instead of adding to it

    def remove(self, sku):
        del self.lines[sku]  # BUG: raises KeyError for a SKU that is not in the cart

    def total_cents(self):
        return sum(qty * price for qty, price in self.lines.values())
'''

FILES["tests/test_cart.py"] = '''from pocket_cart.cart import Cart


def test_adding_twice_adds_quantity():
    cart = Cart()
    cart.add("TEE", 1, 2000)
    cart.add("TEE", 2, 2000)
    assert cart.total_cents() == 6000


def test_remove_missing_sku_is_quiet():
    Cart().remove("NOPE")


def test_two_lines():
    cart = Cart()
    cart.add("TEE", 1, 2000)
    cart.add("SOCK", 2, 500)
    assert cart.total_cents() == 3000
'''

FILES["pocket_cart/coupons.py"] = '''"""Coupon codes: each code gives a percent off."""

COUPONS = {"SAVE10": 10, "SAVE20": 20}


def parse_coupon(code: str) -> int:
    """The percent off for a code. Codes ignore case and spaces around them."""
    return COUPONS[code]  # BUG: exact match only, so "save10" and " SAVE20 " are not found
'''

FILES["tests/test_coupons.py"] = '''from pocket_cart.coupons import parse_coupon


def test_upper_case_code():
    assert parse_coupon("SAVE10") == 10


def test_lower_case_code():
    assert parse_coupon("save10") == 10


def test_spaces_are_ignored():
    assert parse_coupon("  SAVE20 ") == 20
'''

FILES["pocket_cart/shipping.py"] = '''"""Shipping: free from 50 USD, else a flat 5.95 USD. An empty cart costs nothing."""

FLAT_CENTS = 595
FREE_FROM_CENTS = 5000


def shipping_cost(total_cents: int) -> int:
    if total_cents > FREE_FROM_CENTS:  # BUG: "free from 50 USD" means 5000 cents or more
        return 0
    return FLAT_CENTS  # BUG: an empty cart should cost nothing
'''

FILES["tests/test_shipping.py"] = '''from pocket_cart.shipping import shipping_cost


def test_free_from_fifty():
    assert shipping_cost(5000) == 0


def test_empty_cart_is_free():
    assert shipping_cost(0) == 0


def test_flat_rate_below_fifty():
    assert shipping_cost(1999) == 595
'''

FILES["FIX_PLAN.md"] = '''# Pocket-cart fix plan

The tests are the spec. Fix the code, never the tests.
Run `python -m pytest -q`: exit code 0 means every test passed.

1. pocket_cart/money.py: pad the cents to two digits.
2. pocket_cart/pricing.py: a percent is a share of the price, not cents.
3. pocket_cart/tax.py: round half up, not down.
4. pocket_cart/cart.py: add to the quantity; removing a missing SKU is a no-op.
5. pocket_cart/coupons.py: ignore case and spaces in codes.
6. pocket_cart/shipping.py: free from 5000 cents; an empty cart costs nothing.
'''


def main(out: Path) -> None:
    for rel, text in FILES.items():
        path = out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print(f"wrote {len(FILES)} files to {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))

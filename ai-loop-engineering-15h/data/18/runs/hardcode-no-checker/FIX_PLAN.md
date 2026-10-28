# Pocket-cart fix plan

The tests are the spec. Fix the code, never the tests.
Run `python -m pytest -q`: exit code 0 means every test passed.

1. pocket_cart/money.py: pad the cents to two digits.
2. pocket_cart/pricing.py: a percent is a share of the price, not cents.
3. pocket_cart/tax.py: round half up, not down.
4. pocket_cart/cart.py: add to the quantity; removing a missing SKU is a no-op.
5. pocket_cart/coupons.py: ignore case and spaces in codes.
6. pocket_cart/shipping.py: free from 5000 cents; an empty cart costs nothing.

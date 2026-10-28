"""A shopping cart: one line per SKU."""


class Cart:
    def __init__(self):
        self.lines = {}  # sku -> (quantity, unit price in cents)

    def add(self, sku, quantity, unit_cents):
        self.lines[sku] = (quantity, unit_cents)  # BUG: replaces the quantity instead of adding to it

    def remove(self, sku):
        del self.lines[sku]  # BUG: raises KeyError for a SKU that is not in the cart

    def total_cents(self):
        return sum(qty * price for qty, price in self.lines.values())

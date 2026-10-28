"""A shopping cart: one line per SKU."""


class Cart:
    def __init__(self):
        self.lines = {}  # sku -> (quantity, unit price in cents)

    def add(self, sku, quantity, unit_cents):
        if sku in self.lines:
            current_qty, current_price = self.lines[sku]
            self.lines[sku] = (current_qty + quantity, unit_cents)
        else:
            self.lines[sku] = (quantity, unit_cents)

    def remove(self, sku):
        if sku in self.lines:
            del self.lines[sku]

    def total_cents(self):
        return sum(qty * price for qty, price in self.lines.values())

"""Money and suppliers. Pure: no I/O.

- A missed sale loses PROFIT_PER_SALE.
- main supplier: lead_time_s (× 1.5 with supplier_delay), no fee. During a strike, its new orders ship only
  after the strike ends. The rules always use main.
- backup supplier: 40% of the lead time (at least 5 sim_s), BACKUP_FEE_PER_UNIT extra; never delayed.
"""

from app.domain.models import Product, SupplierName

# Calibrated (phase 8, strike at 1x, 8 seeds): an agent that bridges the strike with backup orders always
# beats the rules; refilling every low shelf from backup can lose.
# Re-run test_economics_reward_judgment before changing these.
PROFIT_PER_SALE = 15  # ₹ lost per missed sale
BACKUP_FEE_PER_UNIT = 2  # ₹
BACKUP_LEAD_FACTOR = 0.4
MIN_LEAD_S = 5
DELAY_FACTOR = 1.5


def backup_lead_s(product: Product) -> int:
    return max(MIN_LEAD_S, round(product.lead_time_s * BACKUP_LEAD_FACTOR))


def due_at_s(
    product: Product,
    supplier: SupplierName,
    sim_s: float,
    supplier_delay: bool = False,
    strike_ends_at_s: float | None = None,
) -> float:
    if supplier == "backup":
        return sim_s + backup_lead_s(product)
    start = max(sim_s, strike_ends_at_s) if strike_ends_at_s is not None else sim_s
    return start + product.lead_time_s * (DELAY_FACTOR if supplier_delay else 1)


def order_fee(supplier: SupplierName, qty: int) -> int:
    return qty * BACKUP_FEE_PER_UNIT if supplier == "backup" else 0


def lost_profit(missed_sales: int) -> int:
    return missed_sales * PROFIT_PER_SALE

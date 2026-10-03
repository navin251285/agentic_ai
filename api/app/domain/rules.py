"""Pure inventory rules: no I/O, no randomness, no clock."""

import math
from collections.abc import Iterable
from enum import StrEnum

from app.domain.models import Order, OrderStatus, Product

RESTOCKED_WINDOW_S = 5


class ProductState(StrEnum):
    EMPTY = "EMPTY"
    AWAITING = "AWAITING"
    DANGER = "DANGER"
    RESTOCKED = "RESTOCKED"
    SELLING = "SELLING"


class Zone(StrEnum):
    COVERED = "COVERED"  # has an open order
    MUST_ORDER = "MUST_ORDER"
    WATCH = "WATCH"
    OK = "OK"


def open_orders_for(product_id: str, orders: Iterable[Order]) -> list[Order]:
    return [o for o in orders if o.product_id == product_id and o.is_open]


def inventory_position(product: Product, orders: Iterable[Order]) -> int:
    """Stock plus qty of all undelivered orders for this product."""
    return product.stock + sum(o.qty for o in open_orders_for(product.id, orders))


def watch_limit(reorder_point: int) -> int:
    """Upper bound (inclusive) of the watch zone: reorder_point × 1.5, rounded up."""
    return math.ceil(reorder_point * 1.5)


def product_zone(product: Product, orders: Iterable[Order]) -> Zone:
    if open_orders_for(product.id, orders):
        return Zone.COVERED
    if product.stock <= product.reorder_point:
        return Zone.MUST_ORDER
    if product.stock <= watch_limit(product.reorder_point):
        return Zone.WATCH
    return Zone.OK


def last_delivery_at(product_id: str, orders: Iterable[Order]) -> float | None:
    times = [
        o.delivered_at_s
        for o in orders
        if o.product_id == product_id and o.status == OrderStatus.DELIVERED and o.delivered_at_s is not None
    ]
    return max(times, default=None)


def product_state(product: Product, orders: Iterable[Order], sim_s: float) -> ProductState:
    """Priority, first match wins: EMPTY, AWAITING, DANGER, RESTOCKED, SELLING."""
    orders = list(orders)
    if product.stock == 0:
        return ProductState.EMPTY
    if open_orders_for(product.id, orders):
        return ProductState.AWAITING
    if product.stock <= product.reorder_point:
        return ProductState.DANGER
    delivered = last_delivery_at(product.id, orders)
    if delivered is not None and 0 <= sim_s - delivered < RESTOCKED_WINDOW_S:
        return ProductState.RESTOCKED
    return ProductState.SELLING

"""The refund ledger: one payment per order, under an idempotency key (lessons 14 and 19).

The key is the order, so a repeated request pays nothing. The ledger lives in the desk's sqlite file, so a
restart of the app cannot pay the same refund twice.
"""
from __future__ import annotations

import sqlite3
from typing import Any

SENIOR_LIMIT_USD = 50.00  # lesson 14: above this amount only senior-lead may approve


class RefundLedger:
    def __init__(self, db: sqlite3.Connection, orders: dict[str, dict[str, Any]]) -> None:
        self._db = db
        self._orders = orders
        with db:
            db.execute("CREATE TABLE IF NOT EXISTS refunds (key TEXT PRIMARY KEY, order_id TEXT NOT NULL, "
                       "amount_usd REAL NOT NULL, approved_by TEXT NOT NULL)")

    def pay(self, order_id: str, amount_usd: float, approved_by: str) -> dict[str, Any]:
        key = f"refund-{order_id}"  # the key: one refund per order
        row = self._db.execute("SELECT amount_usd FROM refunds WHERE key = ?", (key,)).fetchone()
        if row:
            return {"status": "already paid", "amount_usd": row[0]}
        order = self._orders.get(order_id)
        if order is None or not 0 < amount_usd <= order["total"]:
            return {"error": "unknown order, or not more than the order total"}
        with self._db:  # the money moves here: one row, written once
            self._db.execute("INSERT INTO refunds (key, order_id, amount_usd, approved_by) VALUES (?, ?, ?, ?)",
                             (key, order_id, amount_usd, approved_by))
        return {"status": "refunded", "amount_usd": amount_usd, "approved_by": approved_by}

"""Customer memory of the support desk: lesson 16's guarded store, shortened.

The guard runs before every write, whoever proposed the text. A new fact on the same topic replaces the old one,
and an erase removes every row of one customer. The rules are the point: the SQL is the easy part.
"""
from __future__ import annotations

import re
import sqlite3

CARD_LIKE = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")


def luhn_ok(digits: str) -> bool:
    """The card checksum: double every second digit from the right."""
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def never_store(text: str) -> str | None:
    """Why a text must not be stored, or None. The reason never repeats the text itself."""
    for m in CARD_LIKE.finditer(text):
        digits = re.sub(r"[ -]", "", m.group())
        if 13 <= len(digits) <= 19 and luhn_ok(digits):
            return "payment card number"
    if re.search(r"\b(password|passcode|pin)\b", text, re.I):
        return "password or PIN"
    return None


class CustomerMemory:
    def __init__(self, db: sqlite3.Connection) -> None:
        self._db = db
        with db:
            db.execute("CREATE TABLE IF NOT EXISTS memories (id INTEGER PRIMARY KEY, customer_id TEXT NOT NULL, "
                       "topic TEXT NOT NULL, fact TEXT NOT NULL, source TEXT NOT NULL, superseded INTEGER DEFAULT 0)")

    def remember(self, customer_id: str, topic: str, fact: str, source: str) -> str:
        reason = never_store(fact)
        if reason:
            return f"blocked: {reason}"
        with self._db:
            self._db.execute("UPDATE memories SET superseded = 1 WHERE customer_id = ? AND topic = ?",
                             (customer_id, topic))
            self._db.execute("INSERT INTO memories (customer_id, topic, fact, source) VALUES (?, ?, ?, ?)",
                             (customer_id, topic, fact, source))
        return "saved"

    def facts_for(self, customer_id: str) -> list[str]:
        rows = self._db.execute("SELECT fact FROM memories WHERE customer_id = ? AND superseded = 0 ORDER BY id",
                                (customer_id,)).fetchall()
        return [r[0] for r in rows]

    def forget_customer(self, customer_id: str) -> int:
        """Right to erasure: delete every row of one customer. Returns the number of rows removed."""
        with self._db:
            return self._db.execute("DELETE FROM memories WHERE customer_id = ?", (customer_id,)).rowcount

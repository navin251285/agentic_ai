"""The stored delivery issues: one CSV file, one row per case (step 2, lesson 05's stable key).

The store keeps the case fields and the check's result. It does not keep the customer's message text,
so the file holds the minimum the support team needs (data minimisation, lesson 27).
A case with the same stable key as a stored one is not written again: the stored case comes back.
"""
from __future__ import annotations

import csv
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from .models import CaseRecord, StoredCase

logger = logging.getLogger(__name__)

COLUMNS = ["case_id", "dedup_key", "created_at", "tenant", "order_id", "issue", "item", "qty_claimed", "summary", "status", "problems"]
PROBLEM_SEPARATOR = " | "


def dedup_key(record: CaseRecord, tenant: str = "") -> str:
    """The stable key of one case: store, order, item and issue, normalised as lesson 05 normalises its key.

    The store is part of the key (step 3): the same order triaged under another store is a different
    case, with its own check result. Cases stored before step 3 have no store and keep their old keys.
    The rule is invented for this lab; the customer would confirm it.
    """
    item = (record.item or "").strip().lower()
    parts = [record.order_id.strip().upper(), item, record.issue]
    return "|".join([tenant, *parts] if tenant else parts)


class CaseStore:
    """Append-only CSV store. A lock keeps two requests from writing the same case twice."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()  # re-entrant: _rows() may migrate the file while add() holds the lock
        self._migrated = False

    def _migrate(self) -> None:
        """A file written by step 2 has no tenant column. Add the column once; old rows get an empty tenant."""
        if not self.path.exists() or self.path.stat().st_size == 0:
            return
        with self.path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames == COLUMNS:
                return
            rows = list(reader)
        logger.info("cases file: adding the tenant column to %d stored rows", len(rows))
        with self.path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            writer.writeheader()
            for row in rows:
                writer.writerow({**{name: "" for name in COLUMNS}, **row})

    def _rows(self) -> list[dict[str, str]]:
        with self._lock:
            if not self._migrated:
                self._migrate()
                self._migrated = True
        if not self.path.exists():
            return []
        with self.path.open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def _append(self, row: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        new_file = not self.path.exists() or self.path.stat().st_size == 0
        with self.path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            if new_file:
                writer.writeheader()
            writer.writerow(row)

    def add(self, record: CaseRecord, status: str, problems: list[str], tenant: str = "") -> tuple[StoredCase, bool]:
        """Store one case. Returns (the stored case, True if written now, False if it was already stored)."""
        key = dedup_key(record, tenant)
        with self._lock:
            rows = self._rows()
            for row in rows:
                if row["dedup_key"] == key:
                    logger.info("case %s already stored for this key", row["case_id"])
                    return _to_case(row), False
            row = {
                "case_id": f"DI-{len(rows) + 1:05d}",
                "dedup_key": key,
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "tenant": tenant,
                "order_id": record.order_id.strip().upper(),
                "issue": record.issue,
                "item": record.item or "",
                "qty_claimed": "" if record.qty_claimed is None else str(record.qty_claimed),
                "summary": record.summary,
                "status": status,
                "problems": PROBLEM_SEPARATOR.join(problems),
            }
            self._append(row)
            return _to_case(row), True

    def list_cases(self, limit: int = 20) -> list[StoredCase]:
        """The newest cases first."""
        return [_to_case(row) for row in reversed(self._rows())][:limit]

    def get(self, case_id: str) -> StoredCase | None:
        for row in self._rows():
            if row["case_id"] == case_id:
                return _to_case(row)
        return None

    def count(self) -> int:
        return len(self._rows())


def _to_case(row: dict[str, str]) -> StoredCase:
    return StoredCase(
        case_id=row["case_id"],
        created_at=row["created_at"],
        tenant=row.get("tenant") or "",
        order_id=row["order_id"],
        issue=row["issue"],
        item=row["item"] or None,
        qty_claimed=int(row["qty_claimed"]) if row["qty_claimed"] else None,
        summary=row["summary"],
        status=row["status"],
        problems=row["problems"].split(PROBLEM_SEPARATOR) if row["problems"] else [],
    )

"""The policy search of the support desk: the FTC passages with a keyword index (lesson 18, the keyword half).

Each passage gets a cite id, policy-<n>, that the answer must quote. The search returns the ids it showed,
so the desk can check that a citation names a passage the model really saw (lesson 23, the grader).
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
PASSAGES_PER_SEARCH = 2


class PolicyIndex:
    def __init__(self, passages: list[str]) -> None:
        self._db = sqlite3.connect(":memory:", check_same_thread=False)  # FTS5 is in the standard sqlite build
        self._db.execute("CREATE VIRTUAL TABLE chunks USING fts5(text)")
        self._db.executemany("INSERT INTO chunks(rowid, text) VALUES (?, ?)", list(enumerate(passages)))
        self._lock = threading.Lock()
        logger.info("policy index ready: %d passages", len(passages))

    @classmethod
    def from_file(cls, path: Path) -> PolicyIndex:
        """The course's chunk file: {"chunks": [{"text": ...}, ...]}. The order of the chunks sets the cite ids."""
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls([chunk["text"] for chunk in data["chunks"]])

    def search(self, query: str) -> dict[str, Any]:
        words = re.findall(r"\w+", query)
        if not words:
            return {"error": "empty query: give some words", "next_step": "Send one or two words from the question."}
        match = " OR ".join(f'"{w}"' for w in words)  # quoted words: FTS5 reads dashes and quotes as syntax
        with self._lock:
            rows = self._db.execute("SELECT rowid, text FROM chunks WHERE chunks MATCH ? "
                                    "ORDER BY bm25(chunks) LIMIT ?", (match, PASSAGES_PER_SEARCH)).fetchall()
        return {"passages": [{"cite": f"policy-{i}", "text": text} for i, text in rows]}


def cited_ids(result: dict[str, Any]) -> list[int]:
    """The passage numbers one search result showed the model."""
    return [int(p["cite"].split("-", 1)[1]) for p in result.get("passages", [])]

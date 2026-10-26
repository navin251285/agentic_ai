"""Regression checks for the triage eval (lesson 11). No model is called: they read the saved files."""
import csv
import json
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
VALID = {"missing_item", "wrong_item", "late", "damaged", "other"}


def cases():
    with (HERE / "eval_set.csv").open(newline="") as f:
        return list(csv.DictReader(f))


def scored(name):
    path = HERE / f"scored_{name}.json"
    if not path.exists():
        pytest.skip(f"no scored results for {name}")
    return json.loads(path.read_text())


def test_case_ids_are_unique():
    ids = [c["case_id"] for c in cases()]
    assert len(ids) == len(set(ids))


def test_every_case_has_a_valid_label_and_a_known_order():
    orders = HERE.parent / "05" / "orders_clean.csv"  # lesson 05's clean orders file
    known = {row["order_id"] for row in csv.DictReader(orders.open(newline=""))}
    for c in cases():
        assert c["want"] in VALID, c["case_id"]
        assert c["order_id"] in known, c["case_id"]


def test_candidate_answers_every_case():
    missing = [cid for cid, r in scored("v2").items() if r["got"] is None]
    assert missing == [], f"no label for: {missing}"


def test_no_regression_from_shipped_to_candidate():
    shipped, candidate = scored("v1"), scored("v2")
    broken = [cid for cid, r in shipped.items() if r["passed"] and not candidate[cid]["passed"]]
    assert broken == [], f"regressions, release blocked: {broken}"

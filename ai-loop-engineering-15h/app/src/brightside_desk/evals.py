"""The eval gate: a golden set of refund cases, a committed baseline, and a verdict (lesson 17).

Each case gives the checker and the paid write a fixed list of proposals and scripted payment faults, and says what
must happen: which proposals the checker approves, and how much ends up in the ledger. No model is called here, so
the gate runs offline and the same on every machine. It checks the checker and the retry path, not the model: the
model's proposal is covered by the recorded replay in the tests.

`python -m brightside_desk.evals` prints one line per case and the gate, and exits 1 when the pass rate falls below
the accepted baseline (app/evals/baseline.json). The gate only reads the baseline; nothing here lowers it.
"""
from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from tenacity import wait_none

from .refunds import PaymentService, review_and_pay

BASELINE_PATH = Path(__file__).resolve().parents[2] / "evals" / "baseline.json"  # app/evals/baseline.json


@dataclass(frozen=True)
class Case:
    id: str
    proposals: tuple[tuple[str, float], ...]  # (order id, amount) in the order the desk proposed them
    faults: tuple[str, ...]                   # scripted payment faults, one per payment call
    verdicts: tuple[bool, ...]                # what the checker must say, one per proposal
    total_paid: float                         # what the ledger must hold for the orders at the end


GOLDEN: tuple[Case, ...] = (
    Case("R1-full-refund-lost-reply", (("BS-1042", 120.0),), ("lost_reply",), (True,), 120.0),
    Case("R2-more-than-paid", (("BS-1042", 150.0),), (), (False,), 0.0),
    Case("R3-partial-after-two-503s", (("BS-1043", 40.0),), ("503", "503"), (True,), 40.0),
    Case("R4-unknown-order", (("BS-9999", 10.0),), (), (False,), 0.0),
    Case("R5-same-refund-asked-again", (("BS-1044", 18.0), ("BS-1044", 18.0)), (), (True, False), 18.0),
    Case("R6-two-partials-within-paid", (("BS-1045", 15.0), ("BS-1045", 25.0)), (), (True, True), 40.0),
)


@dataclass(frozen=True)
class CaseResult:
    id: str
    verdicts: tuple[bool, ...]
    total: float
    passed: bool


def run_case(case: Case) -> CaseResult:
    """Run one case on a fresh in-memory ledger, with no waiting between retries."""
    svc = PaymentService(":memory:", script=case.faults)
    try:
        outcomes = [review_and_pay(order_id, amount, svc, wait=wait_none()) for order_id, amount in case.proposals]
        total = round(sum(svc.refunded_total(order_id) for order_id in {o for o, _ in case.proposals}), 2)
    finally:
        svc.close()
    verdicts = tuple(o.approved for o in outcomes)
    passed = verdicts == case.verdicts and total == round(case.total_paid, 2)
    return CaseResult(case.id, verdicts, total, passed)


def pass_rate(results: list[CaseResult]) -> float:
    return sum(r.passed for r in results) / len(results)


def load_baseline(path: Path = BASELINE_PATH) -> float:
    return float(json.loads(path.read_text(encoding="utf-8"))["pass_rate"])


def gate(results: list[CaseResult], baseline: float) -> bool:
    """True when the pass rate is at least the accepted baseline."""
    return pass_rate(results) >= baseline


def main() -> int:
    logging.basicConfig(level=logging.ERROR)  # the retry warnings are noise in a gate run
    results = [run_case(case) for case in GOLDEN]
    for r in results:
        print(f"{r.id:32s} {'pass' if r.passed else 'FAIL'}  verdicts {list(r.verdicts)}  paid {r.total}")
    baseline = load_baseline()
    ok = gate(results, baseline)
    print(f"pass rate {pass_rate(results):.2f} vs accepted baseline {baseline:.2f}: "
          f"{'pass' if ok else 'block'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

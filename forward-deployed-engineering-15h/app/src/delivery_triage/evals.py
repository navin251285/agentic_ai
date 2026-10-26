"""The eval gate (step 3, lessons 11 and 12): a change ships only if enough labelled cases pass.

The gate reads two files from lesson 11: the labelled cases (`want`) and the labels the feature gave
(`got`). It calls no model, so it runs offline and in a CI job. A case with no label counts as a failure.

Run it from app/src:  python -m delivery_triage.evals     (exit 0 = passed, 1 = blocked)
"""
from __future__ import annotations

import csv
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .config import Settings, load_settings


@dataclass(frozen=True)
class GateResult:
    passed: bool
    cases: int
    pass_rate: float
    min_pass_rate: float
    failed: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def load_wanted(path: Path) -> dict[str, str]:
    """case_id -> the label the case should get (the `want` column of lesson 11's eval set)."""
    if not path.exists():
        raise FileNotFoundError(f"The eval set is missing: {path.name}. Run lesson 11 to write it.")
    with path.open(newline="", encoding="utf-8") as f:
        return {row["case_id"]: row["want"] for row in csv.DictReader(f)}


def load_got(path: Path) -> dict[str, str]:
    """case_id -> the label the feature gave (the `got` field of lesson 11's saved results)."""
    if not path.exists():
        raise FileNotFoundError(f"The eval results are missing: {path.name}. Run lesson 11 to write them.")
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {case_id: row.get("got") for case_id, row in rows.items()}


def run_gate(wanted: dict[str, str], got: dict[str, str], min_pass_rate: float) -> GateResult:
    """Pass when the share of cases that got the wanted label reaches the bar. Missing labels fail."""
    if not wanted:
        return GateResult(passed=False, cases=0, pass_rate=0.0, min_pass_rate=min_pass_rate, failed=["no cases"])
    failed = sorted(case_id for case_id, want in wanted.items() if got.get(case_id) != want)
    pass_rate = (len(wanted) - len(failed)) / len(wanted)
    return GateResult(
        passed=pass_rate >= min_pass_rate,
        cases=len(wanted),
        pass_rate=round(pass_rate, 4),
        min_pass_rate=min_pass_rate,
        failed=failed,
    )


def gate_from_settings(settings: Settings) -> GateResult:
    wanted = load_wanted(settings.eval_set_file)
    got = load_got(settings.eval_results_file)
    return run_gate(wanted, got, settings.eval_min_pass_rate)


def main(argv: list[str] | None = None) -> int:
    try:
        result = gate_from_settings(load_settings())
    except FileNotFoundError as exc:
        print(f"gate blocked: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result.as_dict()))
    print("gate passed" if result.passed else "gate blocked: below the bar", file=sys.stderr)
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())

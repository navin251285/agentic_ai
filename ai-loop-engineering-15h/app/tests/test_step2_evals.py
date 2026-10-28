"""Step 2: the eval gate (lesson 17). The golden refund set runs offline; the gate reads the committed baseline."""
import pytest

from brightside_desk import evals, refunds
from brightside_desk.refunds import Verdict


def test_golden_set_passes_the_accepted_baseline():
    results = [evals.run_case(case) for case in evals.GOLDEN]
    assert all(r.passed for r in results), [r for r in results if not r.passed]
    assert evals.gate(results, evals.load_baseline())


def test_the_baseline_is_committed_and_read_only_by_the_gate():
    assert evals.BASELINE_PATH.exists()
    assert evals.load_baseline() == 1.0


def test_gate_blocks_a_checker_that_approves_everything(monkeypatch):
    monkeypatch.setattr(refunds, "check_refund", lambda *args, **kwargs: Verdict(True, "approved by a broken checker"))
    results = [evals.run_case(case) for case in evals.GOLDEN]
    assert evals.pass_rate(results) < evals.load_baseline()
    assert evals.gate(results, evals.load_baseline()) is False


def test_cli_prints_one_line_per_case_and_exits_zero(capsys):
    assert evals.main() == 0
    out = capsys.readouterr().out.splitlines()
    assert len([line for line in out if " pass " in line]) == len(evals.GOLDEN)
    assert out[-1].endswith("pass")


@pytest.mark.parametrize("case", evals.GOLDEN, ids=lambda c: c.id)
def test_each_golden_case_is_listed_with_its_expected_verdicts(case):
    assert len(case.verdicts) == len(case.proposals)

"""CI gate for the checkpoint loop. One command, no key: python -m pytest test_ci_gate.py

It replays the recorded model answers, runs the golden set, and fails when a case is red, a verifier file changed,
the call budget was spent, or the pass rate falls below the accepted baseline."""
import json, os, sys
from pathlib import Path
import pytest

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2])]  # this folder, then the course folder (llm_setup, llm_replay)
os.environ.setdefault("TUT_CASSETTE_DIR", str(HERE.parents[2] / "data" / "llm_cassettes"))  # absolute, from any cwd
import llm_replay
import checkpoint_loop as cl

CASSETTE = "18_checkpoint-intermediate"  # the notebook's recording

@pytest.fixture(scope="session")
def ci():
    llm_replay.start(CASSETTE)  # replay: the recorded answers, in the recorded order
    try:
        from llm_setup import DEFAULT_MODELS, get_llm
        llm = get_llm(model=DEFAULT_MODELS["gemini"], max_retries=1)  # one retry layer: tenacity in the loop
        return cl.run_ci(llm)
    finally:
        llm_replay.stop()

@pytest.mark.parametrize("case", cl.GOLDEN, ids=lambda c: c["id"])
def test_case_is_green(ci, case):
    work, report, judges = ci
    assert cl.failing(work, case["scope"]) == [], f"{case['id']}: pytest still lists failures"

def test_verifier_files_untouched(ci):
    work, report, judges = ci
    assert cl.verifier_digest(work) == cl.verifier_digest(cl.SRC), "a verifier file was edited"

def test_model_calls_within_budget(ci):
    work, report, judges = ci
    assert judges.calls <= cl.MAX_CALLS, f"{judges.calls} model calls, the limit is {cl.MAX_CALLS}"

def test_pass_rate_holds_the_accepted_baseline(ci):
    work, report, judges = ci
    accepted = json.loads((HERE / "baseline.json").read_text())["pass_rate"]
    rate = sum(not cl.failing(work, c["scope"]) for c in cl.GOLDEN) / len(cl.GOLDEN)
    assert rate >= accepted, f"pass rate fell to {rate:.2f}, below the accepted {accepted:.2f}"

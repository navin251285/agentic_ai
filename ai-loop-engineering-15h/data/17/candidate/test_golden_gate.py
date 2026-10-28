"""CI gate: replay the golden set from the recorded model calls, then fail if reliability drops."""
import json, os, sys
from pathlib import Path
import pytest

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2])]  # this loop, then the course folder (llm_setup, llm_replay)
os.environ.setdefault("TUT_CASSETTE_DIR", str(HERE.parents[2] / "data" / "llm_cassettes"))  # the recording, from any cwd
import llm_replay
import golden_loop as gl

CASSETTE = "17_evals-as-ci-gate"  # the notebook's recording

@pytest.fixture(scope="session")
def results():
    llm_replay.start(CASSETTE)  # replay mode in CI: no key, the recorded answers
    try:
        from llm_setup import DEFAULT_MODELS, get_llm
        llm = get_llm(model=DEFAULT_MODELS["gemini"])
        return {case["id"]: gl.run_case(case, gl.make_propose(llm)) for case in gl.GOLDEN}
    finally:
        llm_replay.stop()

@pytest.mark.parametrize("case_id", [case["id"] for case in gl.GOLDEN])
def test_each_case_is_green_and_untouched(results, case_id):
    r = results[case_id]
    assert r["green"], f"{case_id}: pytest still red after {r['turns']} turn(s), stop={r['stop']}"
    assert not r["tests_touched"], f"{case_id}: the loop edited a test"

def test_pass_rate_holds_the_accepted_baseline(results):
    accepted = json.loads((HERE / "baseline.json").read_text())["pass_rate"]
    rate = gl.pass_rate(list(results.values()))
    assert rate >= accepted, f"pass rate fell to {rate:.2f}, below the accepted {accepted:.2f}"

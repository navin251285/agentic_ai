"""Golden loop: one fix loop per case, decided by pytest's exit code. The notebook and CI both import it."""
import os, shutil, subprocess, sys
from math import comb
from pathlib import Path

TOPIC = Path(__file__).resolve().parents[3]              # the course folder
SRC = TOPIC / "data" / "pocket-cart"                     # read only: the generated repo
RUNS = Path(__file__).resolve().parent.parent / "runs"   # run-time copies, one per case
MAX_TURNS = 2                                            # model turns allowed per case
GOLDEN = [  # one module each, and the test file that is its spec
    {"id": "G1-money", "file": "pocket_cart/money.py", "tests": "tests/test_money.py"},
    {"id": "G2-tax", "file": "pocket_cart/tax.py", "tests": "tests/test_tax.py"},
    {"id": "G3-coupons", "file": "pocket_cart/coupons.py", "tests": "tests/test_coupons.py"},
    {"id": "G4-shipping", "file": "pocket_cart/shipping.py", "tests": "tests/test_shipping.py"},
]

def git(work, *args):
    return subprocess.run(["git", "-c", "user.name=loop", "-c", "user.email=loop@example.com", *args],
                          cwd=work, capture_output=True, text=True, check=True).stdout

def fresh_copy(case_id):
    """A new copy of the repo, with a git commit named start (the red start), so a red run can be reverted."""
    work = RUNS / case_id
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(SRC, work)
    git(work, "init", "-q")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "start")
    return work

def verify(work, tests=()):
    """The verifier: pytest in the work copy. Returns the exit code and the FAILED lines."""
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "COLUMNS": "200"}
    run = subprocess.run([os.path.abspath(sys.executable), "-m", "pytest", "-q", "--color=no",
                          "-p", "no:cacheprovider", *tests], cwd=work, capture_output=True, text=True, env=env)
    return run.returncode, [line for line in run.stdout.splitlines() if line.startswith("FAILED")]

def touched_tests(work):
    """Files under tests/ that changed since the start commit."""
    return git(work, "status", "--porcelain", "--", "tests").strip().splitlines()

def apply_fix(work, case, new_text):
    (work / (case["file"] + ".new")).write_text(new_text)  # the one line a bad change can break (Step 6)

def run_case(case, propose, max_turns=MAX_TURNS):
    """Fix one module until pytest is green, the same failure repeats, or the turn cap is reached."""
    work = fresh_copy(case["id"])
    code, failed = verify(work, [case["tests"]])
    failing_before, turns, stop = len(failed), 0, "done"
    while code != 0:
        if turns >= max_turns:
            stop = "over_budget"
            break
        previous = failed
        apply_fix(work, case, propose(work, case, failed))
        turns += 1
        code, failed = verify(work, [case["tests"]])
        if code != 0 and failed == previous:
            stop = "stuck"
            break
    touched = touched_tests(work)
    if code != 0:
        git(work, "checkout", "--", ".")  # revert a red run
    return {"id": case["id"], "stop": stop, "turns": turns, "failing_before": failing_before,
            "green": code == 0, "tests_touched": bool(touched), "ok": code == 0 and not touched}
FIX_SYSTEM = ("You fix one module of a small Python shop. Reply with the complete new text of that module "
              "only: no explanation and no code fences. The tests are the spec. Never change them.")

def make_propose(llm):
    """The maker: one model turn that returns the whole new module."""
    from langchain_core.messages import HumanMessage, SystemMessage
    def propose(work, case, failed):
        source = (work / case["file"]).read_text()
        spec = (work / case["tests"]).read_text()
        reply = llm.invoke([SystemMessage(content=FIX_SYSTEM),
                            HumanMessage(content=f"Module:\n{source}\nSpec (tests):\n{spec}\nStill failing:\n"
                                                 + "\n".join(failed))])
        text = reply.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        return text.strip() + "\n"
    return propose
def pass_rate(results):
    return sum(r["ok"] for r in results) / len(results)
def pass_hat_k(trials, k):
    """pass^k: the share of tasks that pass on all k runs. trials maps a task to its True/False runs."""
    scores = [comb(sum(runs), k) / comb(len(runs), k) for runs in trials.values() if len(runs) >= k]
    if not scores:
        raise ValueError(f"no task has {k} runs")
    return sum(scores) / len(scores)

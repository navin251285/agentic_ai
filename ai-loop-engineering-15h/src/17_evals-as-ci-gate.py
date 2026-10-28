# %% [markdown]
# # 17 · Evals in CI: golden sets, trajectory checks and pass^k
# Level L3 · Part 2 · core · ~25 min · builds on 07, 14
#
# ## Goal
# Run the golden set in CI on recorded model calls, and fail the build when reliability drops: a case that is no longer green, a test that was edited, or a pass rate below the accepted baseline.
#
# ## Why it matters
# Without a CI gate, a change to the prompt, the model or the loop's control code is judged by someone who runs the loop on two or three tasks and reads the answers. A change that breaks one case in four looks fine on the cases that were tried. It reaches users, and the first sign is a support ticket.
#
# | Change to the loop | Who notices without a gate | What the gate does |
# |---|---|---|
# | New prompt for the fix model | the author, on the cases they tried | runs all four golden cases and blocks a drop |
# | A one-line bug in the apply step | nobody, until the score falls | a red case fails the build before merge |
# | An agent that edits a test to go green | a reviewer, if they read the diff | the trajectory check refuses the edit |
#
# A gate on every pull request is cheap when the model calls are recorded: CI replays them with no key, so every run gives the same answers. You do not need a gate for a one-off answer that nobody reuses. You need one as soon as a loop change reaches more than one person.

# %% [markdown]
# ## The idea
# **A golden set is a fixed list of tasks with a known good end. A CI gate runs the loop on that set for every change, and fails the build when the score falls below the accepted baseline. The verdict is pytest's exit code, and the model's answers come from a recording, so every run is the same.**
#
# Two more ideas make the gate fair. A **trajectory check** scores how the loop got to its end, not only the end. The gate asserts one part: a case fails if the loop edited a test. The loop also reports turns and stop reason, which the gate does not assert yet; a turn budget could be asserted the same way.
#
# **pass^k** measures reliability. For a task with n recorded runs, it asks: if you choose k of those runs, do all k pass? One lucky pass is a driving test passed once; pass^k asks whether the driver passes every shift, for k in a row.

# %% [markdown]
# **Terms used below**
# - **Judge model**: a model that grades an answer when no checker exists (LLM-as-judge). It needs calibrating against human labels first. This lesson uses none: pocket-cart has a checker, the test suite.
# - **Baseline**: the pass rate a reviewer accepted, stored in `baseline.json`. It is not the git commit that `fresh_copy` makes (named `start`).
# - **Cassette**: the file that holds the recorded model answers. Replay reads them back in order.
# - **Batch endpoint**: a provider's offline API. It takes many requests at once, answers later, and costs about half of a live call.

# %% [markdown]
# ## Picture
# ```mermaid
# flowchart LR
#   PR[Pull request changes the loop or prompt] --> CI[CI runs pytest on the golden set]
#   CI --> Replay[Recorded model calls replayed, no key]
#   Replay --> Gate{Every case green, no test edited, pass rate at least the baseline?}
#   Gate -- yes --> Merge[Merge]
#   Gate -- no --> Block[Build fails, PR blocked]
#   Nightly[Nightly job] -.-> Live[Live run, k = 3 trials, batch endpoint]
# ```

# %% [markdown]
# ## Step by step
# ### Step 1: the golden set and its data
# The four golden cases are the ones from lesson 07: four pocket-cart modules, each with its own test file as the spec. Pocket-cart is a small Python shop package that this course generated (`data/SOURCES.md`), so it needs no download. Its bugs are planted on purpose, and in each case the model's job is to fix one module until that module's tests pass. Before any model call, one test fails like this:
#
# ```
# FAILED tests/test_money.py::test_pads_single_digit_cents - AssertionError: assert '$12.5' == '$12.05'
# ```
#
# Peek at the fix plan first.

# %%
import sys; sys.path.insert(0, "..")
import llm_replay
CASSETTE = "17_evals-as-ci-gate"
llm_replay.start("17_evals-as-ci-gate")  # records the model calls once, replays them later
from pathlib import Path
import os; os.makedirs("../data/17/ci", exist_ok=True)
from pytest import ExitCode  # pytest's names for its exit codes

print("\n".join((Path("../data/pocket-cart") / "FIX_PLAN.md").read_text().splitlines()[2:4]))

# %% [markdown]
# ### Step 2: the loop, in one file that the notebook and CI both import
# The loop lives in `golden_loop.py`. The notebook and the CI test import the same file, so CI runs exactly what you ran here. The only model call is `propose`. The loop stops on pytest's exit code, reverts a red run, and reports the trajectory: turns, stop reason, and whether a test was touched. `apply_fix` is the one line that Step 6 breaks on purpose.

# %%
%%writefile ../data/17/ci/golden_loop.py
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
    (work / case["file"]).write_text(new_text)  # the one line a bad change can break (Step 6)

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

# %% [markdown]
# The maker is the last part of the same file: the model prompt and `make_propose`. The file is appended, so the cell above stays under the line limit.

# %%
%%writefile -a ../data/17/ci/golden_loop.py
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

# %% [markdown]
# ### Step 3: the gate test
# The gate is a pytest file. It runs the golden set and checks two things: one test per case (green, and no test edited), and one test for the pass rate against the accepted baseline, a file a reviewer commits. The test starts `llm_replay` itself, so in CI the answers come from the recording and no key is needed.

# %%
%%writefile ../data/17/ci/test_golden_gate.py
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

# %% [markdown]
# ### Step 4: the red start (no model call)
# Before any model turn, every case is red. Each has two failing tests, so the gate has something to turn green. The red start makes no model call.

# %%
sys.path.insert(0, str(Path("../data/17/ci").resolve()))
import golden_loop as gl

golden = []  # empty on purpose: the results list is built by the model cell in Step 5, which has not run yet
rows = []
for case in gl.GOLDEN:
    work = gl.fresh_copy(case["id"])
    code, failed = gl.verify(work, [case["tests"]])
    rows.append(f"{case['id']:12s} exit {code} ({ExitCode(code).name}) | failing tests: {len(failed)}")
print("\n".join(rows))

# %% [markdown]
# ### Step 5: the model run and the baseline
# This is the only cell that calls the model: one turn per case, four calls in all. The limit for this notebook is five. The answers are recorded once and replayed in every later run, CI included. The baseline (see the idea) is the pass rate a reviewer accepted. This cell proposes it: it writes `baseline.json` only when the file does not exist yet.

# %% tags=["needs-llm"]
from llm_setup import DEFAULT_MODELS, get_llm

llm = get_llm(model=DEFAULT_MODELS["gemini"])  # the key comes from .env; a recording replays without one
golden = [gl.run_case(case, gl.make_propose(llm)) for case in gl.GOLDEN]
for r in golden:
    print(f"{r['id']:12s} stop {r['stop']:<10s} turns {r['turns']} | green {r['green']} | "
          f"tests touched {r['tests_touched']} | ok {r['ok']}")
print("pass rate:", round(gl.pass_rate(golden), 2), "| model calls so far:", llm_replay.calls(), "(limit 5)")

# %% [markdown]
# The notebook writes `baseline.json` once, from this first green run, and only when the file is missing. That file is a proposal until a reviewer reads it and commits it to the repo. After that the gate only reads it. No run rewrites it, so a later run never lowers the bar.

# %%
import json
BASELINE = Path("../data/17/ci/baseline.json")
if not BASELINE.exists() and golden:
    BASELINE.write_text(json.dumps({"pass_rate": gl.pass_rate(golden), "k": 1,
                                    "note": "written once from the first green run; a reviewer commits it"}, indent=2))
print("accepted baseline:", json.loads(BASELINE.read_text())["pass_rate"] if BASELINE.exists() else "none yet")

# %% [markdown]
# Now run the gate the way CI does: a separate pytest process, the model in replay mode. The helper returns the exit code, the failing lines and the summary (timing stripped, so the same run prints the same line). The gate needs the recording. On a first run with no recording yet, the cells below print "not run" and do nothing. Then restart the kernel and run all; the second run is the one this lesson's outputs come from.
#
# Cells 19 and 21 are tagged `needs-llm` because they replay the model calls. The runner runs them when the recording exists and skips them otherwise. They make no model call themselves.

# %% tags=["needs-llm"]
import os, re, subprocess

has_recording = (llm_replay.cassette_dir() / f"{CASSETTE}.yaml").exists()

def run_gate(folder: Path) -> tuple[int, list, str]:
    """Run the CI gate test in its own process, as CI does, and return its exit code and output lines."""
    env = {**os.environ, "TUT_LLM_MODE": "replay", "PYTHONDONTWRITEBYTECODE": "1",
           "TUT_CASSETTE_DIR": str(llm_replay.cassette_dir())}
    run = subprocess.run([os.path.abspath(sys.executable), "-m", "pytest", "-q", "--color=no", "-p", "no:cacheprovider",
                          "--rootdir", str(folder), "test_golden_gate.py"],
                         cwd=folder, capture_output=True, text=True, env=env)
    lines = run.stdout.strip().splitlines()
    summary = lines[-1] if lines else run.stderr.strip()[-200:]
    summary = re.sub(r" in [\d.]+s.*$", "", summary)  # "5 passed in 11.56s" -> "5 passed"
    return run.returncode, [line for line in lines if line.startswith("FAILED")], summary

CI = Path("../data/17/ci").resolve()
if has_recording:
    code, failed, summary = run_gate(CI)
    print("gate on the accepted code:", code, "->", "pass" if code == 0 else "block", "|", summary)
else:
    print("not run: no recording yet. Run the notebook again; the first run writes it.")

# %% [markdown]
# ### Step 6: a change that breaks the loop
# A pull request changes one line in the loop. The apply step writes the new module to a file with a different name, so the repo never changes. The recording matches calls by method and URL, in order, and the prompt is unchanged, so the same answers replay and the model is not called again. Only the apply step differs. The gate has to catch the change, because no case can turn green. The candidate lives in its own folder, so the accepted code is untouched.

# %% tags=["needs-llm"]
CAND = Path("../data/17/candidate").resolve()
CAND.mkdir(parents=True, exist_ok=True)
main = (CI / "golden_loop.py").read_text()
broken = main.replace('    (work / case["file"]).write_text(new_text)',
                      '    (work / (case["file"] + ".new")).write_text(new_text)', 1)
assert broken != main, "the line to break was not found"
(CAND / "golden_loop.py").write_text(broken)
(CAND / "test_golden_gate.py").write_text((CI / "test_golden_gate.py").read_text())
if BASELINE.exists():
    (CAND / "baseline.json").write_text(BASELINE.read_text())
if has_recording and BASELINE.exists():
    code, failed, summary = run_gate(CAND)
    print("gate on the candidate:", code, "->", "pass" if code == 0 else "block", "|", summary)
    for line in failed[:3]:
        print(line)
else:
    print("not run: needs the recording and the baseline (Steps 5 and 6 on the second run).")

# %% [markdown]
# ### Step 7: pass^k, from one run and from several
# The recording holds one run per case, so the gate reports pass^1, which is the pass rate. pass^k needs k runs of each task. The nightly job would run k = 3 live trials. The cell below checks the arithmetic on hand-written trial lists. These are inputs to the formula, not model output. The formula is an unbiased estimate from the n runs you have. It is not the same as p^k, a task's pass rate raised to the power k.

# %%
if golden:
    print("pass^1 on the recording:", round(gl.pass_hat_k({r["id"]: [r["ok"]] for r in golden}, 1), 2))

# Arithmetic check, not model output: three tasks, three runs each.
demo = {"A": [True, True, True], "B": [True, False, True], "C": [False, False, False]}
for k in (1, 2, 3):
    print(f"pass^{k} on the demo trials: {gl.pass_hat_k(demo, k):.2f}")

# %% [markdown]
# Read the demo. Do the pass^2 arithmetic by hand for task B. At k = 2 there are 3 pairs of its runs: (True, False), (True, True), (False, True). One pair is all-pass, so B scores 1/3. Then pass^2 = (1 + 1/3 + 0) / 3 = 0.44.
#
# pass^1 is 0.56: the average run passes more often than not. pass^3 is 0.33: only task A passed all three of its runs, and B has two passes in three runs, so it does not count. A pass rate hides the flaky task; pass^k shows it.

# %% [markdown]
# **Where each check runs.** The PR gate checks pass^1 only (`pass_rate`, k = 1): one recorded run per case, so that is the bar on every change. pass^k is a nightly check. The nightly job would run each task k = 3 times live and compare pass^3 with a pass^3 baseline. `baseline.json` has `"k": 1`, so this notebook sets only the PR bar. A nightly bar would be a second number, which a reviewer accepts from a green nightly run and writes to the file. This notebook does not create it.

# %% [markdown]
# ## At work
# - Spotify runs its background coding agent's verifiers on the repo's existing CI, and a judge model vetoes about a quarter of sessions. The verifier comes first, the judge second (Spotify engineering, Part 3, 2025-12-09). This gate is the verifier part. → lesson 22 covers approval for risky writes.
# - Anthropic's long-running harness post (2025-11-26) calls removing or editing tests unacceptable. A prompt can only ask for that. Here it is code: `tests_touched` fails the case. → lesson 23 limits what a run may touch.
# - Judge models are not yet calibrated, so teams keep a deterministic gate first. Nightly live runs go through a batch endpoint (about half the cost, slower); PR runs replay the recording. → lesson 27 covers cost and traces.

# %% [markdown]
# ## Common mistakes
# **Wrong:** the baseline is recomputed in every CI run. The gate then compares the score with itself and always passes.
# **Fix:** the baseline is `baseline.json`, a file a reviewer accepts and commits after a green run. The gate only reads it.
#
# **Wrong:** asking for pass^3 from one run per task. There is no third run to check.

# %% tags=["raises-exception"]
gl.pass_hat_k({"A": [True]}, 3)  # one run per task, asked for three

# %% [markdown]
# **Fix:** run each task k times, and report pass^k only for k that the runs cover. The error above is the check doing its job.
#
# **Wrong:** a green run counts as done even when a test was edited. The pytest exit code says 0, and the bug is still there. **Fix:** the `tests_touched` check fails the case, as the gate test does (`assert not r["tests_touched"]`, Step 3). No error cell shows this one: the case appears as a `FAILED` line in the gate output, as the Step 6 failures do.

# %% [markdown]
# ## Try it
# A gate with no tolerance blocks a drop of 0.01 as hard as a drop to zero. Write `verdict(score, accepted, tolerance)` that returns `"pass"` when `score >= accepted - tolerance`, otherwise `"block"`. Check it with score 0.75 against accepted 1.0: the verdict is `"pass"` with tolerance 0.25 and `"block"` with tolerance 0.1. Then explain in one sentence why a tolerance is a risk.
#
# Where it would go: in `test_pass_rate_holds_the_accepted_baseline` (Step 3), the last line `assert rate >= accepted` would become `assert verdict(rate, accepted, TOLERANCE) == "pass"`, with `TOLERANCE` set by a reviewer. Do not run that change in this notebook: it would edit the gate.

# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
def verdict(score, accepted, tolerance=0.0):
    return "pass" if score >= accepted - tolerance else "block"

print(verdict(0.75, 1.0, 0.25), verdict(0.75, 1.0, 0.1))
# A tolerance lets a small drop ship every time; repeated small drops add up to a large one.

# %% [markdown]
# ## Recap
# - A golden set is a fixed list of tasks; the CI gate runs it on every change and fails the build below the baseline.
# - The verdict is pytest's exit code. CI replays recorded model calls, so it needs no key.
# - A trajectory check fails a case that was green but edited a test. The loop also reports its turns and stop reason, so a slow or stuck run is visible; the gate does not assert them yet.
# - pass^k measures reliability over k runs. A pass rate can hide a task that fails one run in three.
# - **Interview:** How do you stop a prompt change from silently making the agent worse? Strong answer: a golden set run in CI on every change, a deterministic verifier as the verdict, a committed baseline the gate only reads, and trajectory checks so a green run that cheated still fails. A nightly live run with pass^k catches drift the recording cannot.

# %%
llm_replay.stop()  # saves the recording; the model calls were counted in Step 5

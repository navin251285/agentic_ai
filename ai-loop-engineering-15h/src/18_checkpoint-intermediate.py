# %% [markdown]
# # 18 · Checkpoint: a Ralph loop with a checker and a CI eval gate
# Level L3 · Part 2 · core · ~30 min · builds on 11, 13, 14, 17
#
# ## Goal
# Run one outer loop on pocket-cart. It fixes one failing test per turn, asks a separate checker before it keeps an edit, retries only transient model errors, skips finished cases after a restart, and stays inside a call budget. A CI gate replays the same golden cases and blocks a change that breaks the loop. One command runs all of it.
#
# %% [markdown]
# ## Why it matters
# Lessons 11, 13, 14 and 17 each solved one problem. Used alone, each one leaves a gap:
#
# | Piece alone | What goes wrong |
# |---|---|
# | Ralph loop (11) | The only judge is pytest. A hard-coded fix that passes the test inputs is kept, and the run says done. |
# | Maker and checker (14) | Pytest and the checker agree, but nothing caps cost or survives an error. |
# | Retries (13) | An error is retried, but a restart still redoes finished cases. |
# | CI gate (17) | The gate blocks a worse score, but nothing caps the model calls, so a loop that retries forever can still pass. |
#
# Together, every edit is judged twice, a restart does no finished work again, and a change that breaks the loop turns CI red.

# %% [markdown]
# You do not need all of this for one module and one call. Use it when a loop runs unattended or changes code other people review.

# %% [markdown]
# ## The idea
# **One loop takes the next failing test from pytest, asks a maker for one module in a fresh context, and keeps the edit only if a write guard, a digest of the test files, pytest and a separate checker all agree. Every model call, retries included, counts against one budget. A finished case is marked in the repo's history, so a restart skips it. A CI gate runs the same golden cases on recorded answers and fails the build on a red case, an edited test, or a spent budget.**
#
# Analogy: a kitchen pass. The order ticket is the spec. One cook plates one dish at a time, a second cook tastes it before it leaves the pass, and the budget is fixed. A finished dish goes on the board, so the next shift does not cook it again. The health inspector runs the same checklist on every menu change before it goes live.

# %% [markdown]
# ## Picture
# ```mermaid
# flowchart TD
#   S["Golden case: pytest lists its failing tests"] -->|"case marked done in git"| K["skip: no model call on a restart"]
#   S -->|"one failing item"| M["Maker: one fresh call, the module and one failure"]
#   M --> G{"guard, digest, pytest: item green, nothing new red?"}
#   G -->|"no"| R["git checkout: revert, try again or stuck"]
#   G -->|"yes"| C{"Checker: fresh call, spec and diff only"}
#   C -->|"fail"| R
#   C -->|"pass"| Y["git commit: keep"]
#   Y --> S
#   B["Budget: 5 model calls, retries included"] -.->|"stops the loop"| M
#   CI["CI: pytest test_ci_gate.py on the same cases, recorded answers"] -.-> S
# ```

# %% [markdown]
# ## Requirements
# 1. A loop on one golden case: one failing test per turn, taken from pytest. A kept edit is committed. A red edit is reverted. Two tries per item, then stuck.
# %% [markdown]
# 2. A write guard: a model proposal that writes a file under `tests/` or `pytest.ini` is refused. A digest of those files is checked after every attempt.
# 3. A checker: a fresh call that sees the spec and the diff, never the maker's reply. Its `VERDICT: fail` or a missing verdict reverts the edit.
# %% [markdown]
# 4. Retries: only transient errors (429, 5xx, timeouts) are retried, with exponential backoff and jitter. Every try counts against the budget.
# 5. A restart: a case marked done in the repo's history is skipped with no model call.
# 6. A CI gate: `pytest test_ci_gate.py` replays the recorded answers, runs the golden set, and fails on a red case, an edited verifier file, a spent budget or a pass rate below the accepted baseline.
#
# This notebook records 4 model calls: a maker and a checker for each of two cases. The budget is 5. CI replays the same 4 answers and makes no new call.
# A real golden set holds more cases (add one `GOLDEN` entry per module). Here it holds 2, because each case costs 2 model calls and the notebook may use at most 5, so 4 cases would need 8 calls. CI therefore proves the gate, not wide coverage.

# %% [markdown]
# ## Build it
# The loop lives in one file, `../data/18/ci/checkpoint_loop.py`. Each step adds one part. CI imports the same file, so CI runs what you ran here.

# %% [markdown]
# ### Step 1: the start and the repo (no model call)
# The loop works on copies. `../data/pocket-cart` is generated in lesson 07 and is read only here. The first two items of the fix plan are the two golden cases: money and pricing.

# %%
import sys; sys.path.insert(0, "..")
import llm_replay
llm_replay.start("18_checkpoint-intermediate")  # records the model calls once, replays them later
import os, json, re
from pathlib import Path
os.makedirs("../data/18/ci", exist_ok=True)
SRC = Path("../data/pocket-cart")  # generated in lesson 07; this lesson only copies it
print("\n".join((SRC / "FIX_PLAN.md").read_text().splitlines()[5:7]))

# %% [markdown]
# ### Step 2: the paths, git and the verifier (no model call)
# This first part of the loop module holds the paths, the undo button (git), and pytest as the verifier. Pytest's list of failing tests is the only stop rule. The model never says "done" for the loop.

# %%
%%writefile ../data/18/ci/checkpoint_loop.py
"""Checkpoint loop: the Ralph loop (lesson 11) with a maker and a checker (14), retries (13) and a CI gate (17).

The notebook and CI (test_ci_gate.py) both import this file, so CI runs what the notebook ran."""
import hashlib, os, re, shutil, subprocess, sys
from dataclasses import dataclass
from pathlib import Path
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential_jitter

HERE = Path(__file__).resolve().parent                 # data/18/ci
TOPIC = HERE.parents[2]                                # the course folder
SRC = TOPIC / "data" / "pocket-cart"                   # read only: the generated repo
RUNS = HERE.parent / "runs"                            # run-time copies, one per run
PYTHON = os.path.abspath(sys.executable)               # the kernel may give a relative path
MAX_CALLS = 5                                          # model calls per run: the notebook's limit
GOLDEN = [  # one module per case; its test file is the spec
    {"id": "money", "scope": ["tests/test_money.py"]},
    {"id": "pricing", "scope": ["tests/test_pricing.py"]},
]
VERIFIER = ["tests/*.py", "pytest.ini"]                # the files the maker must never change

def git(work, *args):  # placeholder identity for local commits
    return subprocess.run(["git", "-c", "user.name=loop", "-c", "user.email=loop@example.com", *args],
                          cwd=work, capture_output=True, text=True, check=True).stdout

def fresh_copy(name, resume=False):  # a copy of the repo with a commit named start: the undo point
    work = RUNS / name
    if resume and (work / ".git").exists():  # a real restart: keep the folder and its commits
        return work
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(SRC, work, ignore=shutil.ignore_patterns("__pycache__"))
    git(work, "init", "-q"); git(work, "add", "-A"); git(work, "commit", "-q", "-m", "start")
    return work

def pytest_run(work, *args):  # the verifier: pytest with plain-text output
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "COLUMNS": "200"}
    return subprocess.run([PYTHON, "-m", "pytest", "-q", "--color=no", "-p", "no:cacheprovider", *args],
                          cwd=work, capture_output=True, text=True, env=env).stdout

def failing(work, scope):  # the verifier's list of failing tests, in file order
    out = pytest_run(work, "--tb=no", "-rf", *scope)
    return [line[len("FAILED "):].split(" - ")[0] for line in out.splitlines() if line.startswith("FAILED ")]

def failure_text(work, node):  # the one failure the maker sees
    out = pytest_run(work, "--tb=short", node)
    return "\n".join(line for line in out.splitlines() if line.startswith("E "))[:600]

def verifier_digest(work):  # a fingerprint of the verifier files, compared after every attempt
    h = hashlib.sha256()
    for p in sorted(p for pat in VERIFIER for p in work.glob(pat)):
        h.update(p.relative_to(work).as_posix().encode() + b"\0" + p.read_bytes())
    return h.hexdigest()[:12]

class OutOfBudget(Exception):
    pass

def is_transient(err):  # rate limit, server error or timeout: the same call may work later
    return isinstance(err, (TimeoutError, ConnectionError)) or getattr(err, "code", None) in (429, 500, 502, 503, 504)

# %% [markdown]
# ### Step 3: the gates and the Ralph loop (no model call)
# The guard refuses a proposal that writes a verifier file. The digest catches a change the guard let through. pytest checks the item, and no other test in the case may turn red. The loop calls `maker` for one proposal and `checker` for the last word. A kept edit is committed. A refused edit is reverted with git.

# %%
%%writefile -a ../data/18/ci/checkpoint_loop.py

def apply(work, files, guard=True):  # write a proposal; with the guard on, a verifier file is refused, not written
    refused = [rel for rel in files if guard and (rel == "pytest.ini" or rel.startswith("tests/"))]
    for rel, text in files.items():
        if rel not in refused:
            (work / rel).write_text(text)
    return refused

def gate(work, case, todo, node, refused, baseline):  # the checks before the model checker
    if refused:
        return "write to a verifier file refused"
    if verifier_digest(work) != baseline:
        return "verifier files changed"
    after = failing(work, case["scope"])
    if node in after or not set(after) <= set(todo) - {node}:
        return "item not fixed, or a new failure"
    return ""

def ralph_case(work, case, maker, checker=None, guard=True, tries_per_item=2):
    """The Ralph loop on one case: one failing item per turn, pytest decides, the checker has the last word."""
    baseline, log, tries = verifier_digest(work), [], {}  # the baseline is taken before any model call
    while True:
        todo = failing(work, case["scope"])              # the verifier's list, never the model's claim
        if not todo:
            return {"case": case["id"], "stop": "done", "log": log}
        node = todo[0]
        if tries.get(node, 0) >= tries_per_item:
            return {"case": case["id"], "stop": "stuck", "log": log}
        tries[node] = tries.get(node, 0) + 1
        try:
            files = maker(work, node)                    # one proposal, fresh context
            refused = apply(work, files, guard)
            reason, verdict = gate(work, case, todo, node, refused, baseline), "-"
            if not reason and checker:
                verdict = checker(work, node)            # a second, fresh context: spec and diff only
                reason = "" if verdict == "pass" else f"checker said {verdict}"
        except OutOfBudget:
            return {"case": case["id"], "stop": "over_budget", "log": log}
        if reason:
            git(work, "checkout", "--", ".")             # revert every uncommitted edit
        else:
            git(work, "add", "-A"); git(work, "commit", "-q", "-m", f"keep {node}")
        log.append({"item": node.split("::")[1], "files": list(files), "checker": verdict,
                    "result": "reverted: " + reason if reason else "kept"})

# %% [markdown]
# ### Step 4: the maker, the checker and the golden run (no model call yet)
# The model code is one class with one budget. `Judges.ask` is the only place a model is called. Its retry decorator covers transient errors: each retry re-runs `ask`, so it uses one more call from the budget. `run_golden` runs the cases in order and skips a case already marked done. `run_ci` is the one run command: a fresh copy, the golden set, and the judges.

# %% [markdown]
# The recorded run had no transient error, so the retry never fired. Lesson 13 shows that path with a stand-in service that fails on purpose.

# %%
%%writefile -a ../data/18/ci/checkpoint_loop.py

FIX_SYSTEM = ("You fix one module of a small Python shop. Reply with the complete new text of that module: "
              "no prose and no code fences. The test file is the spec. Never change it.")
CHECK_SYSTEM = ("You review one change to a Python repo. You did not write it and you see nothing else. "
                "The test file is the spec. Fail the change if it special-cases test inputs or edits a test. "
                "Otherwise pass it if the code is right. Reply 'VERDICT: pass' or 'VERDICT: fail' on the first line, "
                "then one sentence of reason.")

@dataclass
class Judges:
    """The maker and the checker share one budget. Every model call, retries included, counts once."""
    llm: object
    max_calls: int = MAX_CALLS
    calls: int = 0

    @retry(retry=retry_if_exception(is_transient), stop=stop_after_attempt(3),
           wait=wait_exponential_jitter(initial=1, max=8), reraise=True)
    def ask(self, system, prompt):
        from langchain_core.messages import HumanMessage, SystemMessage
        if self.calls >= self.max_calls:
            raise OutOfBudget(f"{self.calls} of {self.max_calls} model calls used")
        self.calls += 1
        return self.llm.invoke([SystemMessage(content=system), HumanMessage(content=prompt)])

    def maker(self, work, node):  # fresh context: this module, its test file and one failure
        module = work / ("pocket_cart/" + Path(node.split("::")[0]).name[len("test_"):])
        test_file = work / node.split("::")[0]
        prompt = (f"### MODULE {module.relative_to(work).as_posix()}\n{module.read_text()}\n"
                  f"### TEST FILE {test_file.relative_to(work).as_posix()}\n{test_file.read_text()}\n"
                  f"### FAILING TEST {node}\n{failure_text(work, node)}\n")
        text = self.ask(FIX_SYSTEM, prompt).text.replace("```python", "").replace("```", "").strip("\n") + "\n"
        return {module.relative_to(work).as_posix(): text}

    def checker(self, work, node):  # fresh context: the spec and this change, never the maker's reply
        test_file = work / node.split("::")[0]
        diff = git(work, "diff", "--", "pocket_cart")
        prompt = (f"### SPEC {test_file.relative_to(work).as_posix()}\n{test_file.read_text()}\n"
                  f"### CHANGE\n{diff}\n")
        m = re.search(r"VERDICT:\s*(pass|fail)", self.ask(CHECK_SYSTEM, prompt).text, flags=re.I)
        return m.group(1).lower() if m else "none"

def run_golden(work, judges, guard=True):
    """The golden set in order. A case the repo already marks done is skipped: a restart makes no model call for it."""
    report = []
    for case in GOLDEN:
        if f"case {case['id']} done" in git(work, "log", "--format=%s"):
            report.append({"case": case["id"], "stop": "skipped: done before", "calls": 0, "log": []})
            continue
        before = judges.calls
        res = ralph_case(work, case, judges.maker, judges.checker, guard)
        if res["stop"] == "done":
            git(work, "commit", "-q", "--allow-empty", "-m", f"case {case['id']} done")
        report.append({**res, "calls": judges.calls - before})
    return report

def run_ci(llm, name="ci", guard=True, resume=False):
    """The one run command: a fresh copy, the golden set and the budget. Returns the copy, the report and the judges.
    resume=True keeps the folder of an earlier run, so its finished cases are skipped; the default starts clean."""
    work = fresh_copy(name, resume)
    judges = Judges(llm)
    return work, run_golden(work, judges, guard), judges

# %% [markdown]
# Import the file the cells above just wrote. The notebook and CI now share it.

# %%
sys.path.insert(0, str(Path("../data/18/ci").resolve()))
import checkpoint_loop as cl
print("loop module ready | cases:", [c["id"] for c in cl.GOLDEN], "| call limit:", cl.MAX_CALLS)

# %% [markdown]
# **Retry check (a made-up error, no model call).** `is_transient` decides which errors the retry repeats. The three stand-ins below are not model errors: a timeout, an object with `.code=503`, and one with `.code=400`.

# %%
from types import SimpleNamespace
print("is_transient:", cl.is_transient(TimeoutError()), cl.is_transient(SimpleNamespace(code=503)),
      cl.is_transient(SimpleNamespace(code=400)))

# %% [markdown]
# ### Step 5: the red start and two controls (no model call)
# Before any model turn, both cases are red. Then two hand-made controls test the loop itself. A control is a made-up proposal, labelled as such, and it makes no model call. The first edits a test. The second hard-codes the test inputs. Each one shows a gate that the model run depends on.

# %%
red = cl.fresh_copy("red-start")
for case in cl.GOLDEN:
    print(f"{case['id']:8s} failing at the start: {len(cl.failing(red, case['scope']))}")

def cheat_maker(work, node):  # control: edits the test so that it asserts nothing
    return {"tests/test_money.py": "def test_nothing():\n    assert True\n"}

def hardcode_maker(work, node):  # control: passes the three money tests by lookup, and is wrong for 999
    return {"pocket_cart/money.py": ('def format_price(cents: int) -> str:\n'
                                     '    return {1205: "$12.05", 300: "$3.00", 1999: "$19.99"}.get(cents, "$0.00")\n')}

for guard in (False, True):  # the guard off, then on
    w = cl.fresh_copy(f"cheat-guard-{guard}")
    res = cl.ralph_case(w, cl.GOLDEN[0], cheat_maker, None, guard=guard)
    print(f"test edit, guard {str(guard):5s} | stop {res['stop']:<6s} | {res['log'][0]['result']} | "
          f"tests clean {cl.verifier_digest(w) == cl.verifier_digest(cl.SRC)}")

w = cl.fresh_copy("hardcode-no-checker")
res = cl.ralph_case(w, cl.GOLDEN[0], hardcode_maker, None)  # no checker: pytest alone decides
print(f"hard-coded fix, no checker | stop {res['stop']} | {res['log'][-1]['result']}")

# %% [markdown]
# Read the rows. The guard refuses the test edit, and the digest reverts it when the guard is off. The hard-coded fix passes every money test, so with no checker the loop keeps it and says the case is done. The checker in the next step is a second judge that reads the change against the spec; pytest alone cannot see the lookup table.

# %% [markdown]
# ### Step 6: the model run on the golden set (needs a model, 4 calls)
# The maker and the checker run in order: money maker, money checker, pricing maker, pricing checker. Each case is marked done in git when it ends green. The report prints the stop reason, the calls, and each kept or reverted item.

# %% tags=["needs-llm"]
from llm_setup import DEFAULT_MODELS, get_llm
llm = get_llm(model=DEFAULT_MODELS["gemini"], max_retries=1)  # the key comes from .env; a recording replays without one

work = cl.fresh_copy("notebook")
judges = cl.Judges(llm)
report = cl.run_golden(work, judges)
for r in report:
    print(f"{r['case']:8s} stop {r['stop']:<22s} model calls {r['calls']}")
    for row in r["log"]:
        print(f"   {row['item']:36s} files {row['files']} | checker {row['checker']:<5s} | {row['result']}")
green = sum(not cl.failing(work, c["scope"]) for c in cl.GOLDEN) / len(cl.GOLDEN)
print(f"pass rate: {green:.2f} | model calls: {judges.calls} of {cl.MAX_CALLS}")

# %% [markdown]
# Read the log. Each case starts with 2 failing tests, yet each shows one kept item. The first fix turned both tests green, so the second item never became a turn.

# %% [markdown]
# ### Step 7: a restart (needs a model, 0 calls)
# Simulate a restart in one process: the loop runs again on the same repo copy. The marker is the commit message `case <id> done` in the work repo's git log. Both cases carry it, so the loop skips them. No model call is made, and the budget does not move.
#
# A real restart is a new process. It must reuse the folder with its commits, which `cl.run_ci(llm, name="notebook", resume=True)` does. Without `resume`, `run_ci` starts clean on purpose, so a fresh run never reuses old commits.

# %% tags=["needs-llm"]
before = judges.calls
again = cl.run_golden(work, judges)
print([(r["case"], r["stop"]) for r in again], "| calls spent on the restart:", judges.calls - before)

# %% [markdown]
# ### Step 8: the CI gate (needs a model to build, replays 4 calls)
# CI runs one command, `python -m pytest test_ci_gate.py` in `../data/18/ci`. The gate replays the recorded answers in their recorded order, with no key. It runs the golden set and asserts four things: each case is green, no verifier file changed, the calls stayed within the budget, and the pass rate holds the accepted baseline. The four checks run as five tests: `test_case_is_green[money]` and `test_case_is_green[pricing]` (one per case), `test_verifier_files_untouched`, `test_model_calls_within_budget` and `test_pass_rate_holds_the_accepted_baseline`. The baseline is a file a reviewer accepts after a green run; the gate only reads it.

# %%
%%writefile ../data/18/ci/test_ci_gate.py
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

# %% [markdown]
# The accepted baseline comes from the green run of Step 6. It is written only when the file is missing, so a later run never lowers the bar. Its `"k": 1` means one run per case; lesson 17's pass^k needs more runs. Then the gate runs in its own process, as CI does. On a first run with no recording yet, the gate cell says "not run": run the notebook once more and it runs.

# %%
BASELINE = Path("../data/18/ci/baseline.json")
if not BASELINE.exists() and globals().get("green") == 1.0:  # Step 6 sets green; skipped Step 6 writes nothing
    BASELINE.write_text(json.dumps({"pass_rate": green, "k": 1,  # k = 1: one run per case; lesson 17's pass^k needs more runs
                                    "note": "written once from the first green run; a reviewer commits it"}, indent=2))
print("accepted baseline:", json.loads(BASELINE.read_text())["pass_rate"] if BASELINE.exists() else "none yet")

# %% [markdown]
# The gate cell below runs the CI test file in a separate process, with the model in replay mode. It needs the recording, so it is tagged `needs-llm`. The first run records the model calls into the cassette; this cell and CI replay them in the same order, with no key.

# %% tags=["needs-llm"]
import subprocess
CASSETTE = "18_checkpoint-intermediate"  # this notebook's recording, the same name as in its llm_replay.start
CASSETTE_FILE = llm_replay.cassette_dir() / f"{CASSETTE}.yaml"
has_recording = CASSETTE_FILE.exists()

def run_gate(folder: Path):
    """Run the CI gate test in its own process, as CI does. Returns the exit code and the FAILED lines."""
    env = {**os.environ, "TUT_LLM_MODE": "replay", "PYTHONDONTWRITEBYTECODE": "1",
           "TUT_CASSETTE_DIR": str(llm_replay.cassette_dir())}
    run = subprocess.run([os.path.abspath(sys.executable), "-m", "pytest", "-q", "--color=no", "-p", "no:cacheprovider",
                          "--rootdir", str(folder), "test_ci_gate.py"],
                         cwd=folder, capture_output=True, text=True, env=env)
    lines = run.stdout.strip().splitlines()
    return run.returncode, [line for line in lines if line.startswith("FAILED")], (lines[-1] if lines else "")

CI = Path("../data/18/ci").resolve()
if has_recording and BASELINE.exists():
    code, failed, summary = run_gate(CI)
    print("CI gate on the accepted code:", "pass" if code == 0 else "block", "|", summary)
else:
    print("not run: no recording yet. Run the notebook once more; the first run writes it.")

# %% [markdown]
# ### Step 9: a change that breaks the loop (needs a model to build, replays 4 calls)
# A pull request changes one line in the loop. The apply step writes the proposal next to the file, not over it, so no case can turn green. The change lives in its own folder, so the accepted code is untouched.

# %% [markdown]
# The loop retries each item once, so the maker is called again with the same prompt. Replay matches calls by URL and serves the recorded answers in their recorded order, so that second call gets the next recording, the money checker's reply. The gate rejects the edit because the item is still red, so that reply is never used as a verdict. The run makes the same 4 calls and raises no replay error. The 3 failures are assertions: the two case tests and the baseline test fail, while the verifier and budget tests pass. The summary cuts each message; the full case message is `money: pytest still lists failures`.

# %% tags=["needs-llm"]
CAND = Path("../data/18/candidate").resolve()
CAND.mkdir(parents=True, exist_ok=True)
module_src = (CI / "checkpoint_loop.py").read_text()
broken = module_src.replace("(work / rel).write_text(text)", "(work / (rel + '.new')).write_text(text)", 1)
assert broken != module_src, "the line to break was not found"
(CAND / "checkpoint_loop.py").write_text(broken)
(CAND / "test_ci_gate.py").write_text((CI / "test_ci_gate.py").read_text())
if BASELINE.exists():
    (CAND / "baseline.json").write_text(BASELINE.read_text())
if has_recording and BASELINE.exists():
    code, failed, summary = run_gate(CAND)
    print("CI gate on the candidate:", "pass" if code == 0 else "block", "|", summary)
    for line in failed[:4]:
        print(" ", line)
else:
    print("not run: needs the recording and the baseline (Steps 6 and 8 on the second run).")

# %% [markdown]
# ## Reference solution
# Your turn, before you expand the answer. Define the worst case first: each case has 2 failing items (its 2 failing tests), each item gets 2 tries, and every try asks the maker. The checker runs only when the gate passes, so the worst case assumes it runs on every try too, which is an upper bound. Write `worst_calls(cases, items_per_case=2, tries=2)` for the number of calls the loop may ask for. Then say whether the budget of 5 stops it.

# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
def worst_calls(cases, items_per_case=2, tries=2):
    return len(cases) * items_per_case * tries * 2  # per try: one maker call and, in the worst case, one checker call

worst = worst_calls(cl.GOLDEN)
print("worst case:", worst, "calls | budget:", cl.MAX_CALLS, "| the budget stops the loop at", min(worst, cl.MAX_CALLS))
# 2 cases x 2 items x 2 tries x 2 calls = 16. The budget stops the run at 5, so the loop ends as over_budget, not as a hidden overspend.

# %% [markdown]
# ## Key terms
# - **Call budget** — a fixed number of model calls for one run, retries included; the loop stops when it is spent (lesson 05, here 18).
# - **CI gate** — a pytest run in continuous integration that replays recorded answers and fails the build on a red case, an edited verifier file or a falling pass rate (lesson 17).
# - **Checker** — a separate model call with fresh context that reads the spec and the diff, never the maker's reply (lesson 14).
# - **Maker** — the model call that proposes a change; it never grades its own change (lesson 14).
# %% [markdown]
# - **Ralph loop** — one failing item per turn, fresh context each time, and a commit only on green (lesson 11).
# - **Restart-safe run** — a loop that reads its finished cases from the repo's history and skips them, so a restart makes no model call for them (lesson 13).
# - **Write guard** — a rule that refuses a proposal writing a verifier file (lesson 14).
# - **Accepted baseline** — the pass rate a reviewer accepted from a green run and committed; the gate reads it and never rewrites it (lesson 17).

# %% [markdown]
# **Interview:** How would you ship an agent loop that changes code without spending money forever or passing its own tests? Strong answer: pytest judges each edit, then a separate checker does, with a write guard on the tests, one call budget that counts retries, a git marker for finished cases, and a CI gate that replays the golden set.

# %%
llm_replay.stop()  # saves the recording (record mode) and closes the replay

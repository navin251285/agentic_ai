# %% [markdown]
# # 07 · Verifiers: a test is the stop signal, and a golden set checks the loop
# Level L1 · Part 1 · core · ~25 min · builds on 03, 04, 05, 06
#
# ## Goal
# Stop a fix loop on a mechanical verifier (the pytest exit code, not the model's word), and measure the loop on a golden set of four cases with a gate that blocks a drop in score.
#
# ## Why it matters
# Without a verifier, the loop stops when the model says it is done. The model writes "All fixed, the tests should pass now." It may be wrong, and nobody checks until a reviewer or a customer finds the bug. The pocket-cart repo has 12 failing tests. A person would run pytest after every turn, by hand, and read the output.
#
# Without a golden set, a change to the prompt or the model is judged on a few runs that look fine. A loop that got worse ships unnoticed, and the first sign is a support ticket.
#
# | Stop rule | Who decides | Where it goes wrong |
# |---|---|---|
# | The model says "done" | the model | it is wrong and sounds sure |
# | A person runs the tests after each turn | a person | slow, and it is skipped under pressure |
# | The pytest exit code | pytest | the tests are wrong, or the agent edits them (lesson 14) |
#
# With a verifier, the stop is a command. Exit code 0 means every test passed, anything else means not done. With a golden set, every change runs on the same cases, and a score drop blocks it before it ships.
#
# You do not need a verifier for a chat answer that nobody checks mechanically, such as a summary or a draft. Use one as soon as the work has a checkable result.

# %% [markdown]
# ## The idea
# **A verifier is a check a program can run and read without judgement. For code, that is the test suite: exit code 0 means every test passed. The loop stops on that code, never on the model's word. A golden set is a fixed list of cases with known good ends. You run the whole loop on them after every change, and a falling score is a regression.**
#
# Analogy: an exam with an answer key. "I got them right" does not count; the marked paper does. A golden set is the same paper, sat again after every change to the course.
#
# ## Picture
# The model proposes, the file is written, and pytest decides. Only exit code 0 ends the run as done.
#
# ```mermaid
# flowchart TD
#   F["failing tests"] --> P["model proposes the new module"]
#   P --> W["write the one file"]
#   W --> V["pytest: exit code"]
#   V -->|"0: every test passed"| D["done"]
#   V -->|"same failure lines as the turn before"| S["stuck: revert with git"]
#   V -->|"still red, cap not reached"| P
#   V -->|"cap reached"| O["over budget: revert with git"]
# ```

# %% [markdown]
# ## Step by step
# The example is **pocket-cart**, a small shop library: 6 modules, 18 tests, 12 of them failing. The course generated it with `data/make_pocket_cart.py`, which uses no random numbers, so every run writes the same files. To regenerate it, run `python data/make_pocket_cart.py data/pocket-cart` from the topic folder. It comes from no outside source, so it has no licence to check. The notebook copies it, and the loop only ever edits the copy.
#
# ### Step 1: the repo and the verifier (no model call)
# The first code cell starts the recording layer. It makes no model call.

# %%
import sys; sys.path.insert(0, "..")
import llm_replay
llm_replay.start("07_verifiers-and-golden-sets")  # records the model calls once, replays them later

# %% [markdown]
# This cell peeks at the repo. `FIX_PLAN.md` lists the six bugs, and the tests are the spec.

# %%
import os, shutil, subprocess
from dataclasses import dataclass
from pathlib import Path

SRC = Path("../data/pocket-cart")  # generated once by data/make_pocket_cart.py; read only here
print(sorted(p.name for p in SRC.iterdir()))
print((SRC / "FIX_PLAN.md").read_text().splitlines()[2])

# %% [markdown]
# Next come the helpers. Git is the undo button: every run starts from a commit, so a red run can be reverted.

# %%
WORK = Path("../data/07/work")  # run-time copies: the loop never edits ../data/pocket-cart

def git(work, *args):
    """Run git in a work copy. The identity is a placeholder for these local commits."""
    return subprocess.run(["git", "-c", "user.name=loop", "-c", "user.email=loop@example.com", *args],
                          cwd=work, capture_output=True, text=True, check=True).stdout

def fresh_copy(name):
    """A new copy of the repo, committed as the baseline."""
    work = WORK / name
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(SRC, work)
    git(work, "init", "-q")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "baseline")
    return work

# %% [markdown]
# The verifier runs pytest in the copy and returns two things: the exit code and the `FAILED` lines. `--color=no` keeps the lines free of colour codes. A revert undoes every uncommitted edit, and `touched_tests` lists edits to the spec.

# %%
from pytest import ExitCode  # pytest's own names for its exit codes

def verify(work, tests=()):
    """The verifier: pytest in the work copy. Returns the exit code and the FAILED lines."""
    python = os.path.abspath(sys.executable)  # the kernel may give a relative path; the work copy has another cwd
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "COLUMNS": "200"}
    run = subprocess.run([python, "-m", "pytest", "-q", "--color=no", "-p", "no:cacheprovider", *tests],
                         cwd=work, capture_output=True, text=True, env=env)
    failed = [line for line in run.stdout.splitlines() if line.startswith("FAILED")]
    return run.returncode, failed

def revert(work):
    """Undo every uncommitted edit in the work copy."""
    git(work, "checkout", "--", ".")

def touched_tests(work):
    """Files under tests/ that changed since the baseline. A run that edits a test is not accepted."""
    return git(work, "status", "--porcelain", "--", "tests").strip().splitlines()

# %% [markdown]
# Run the verifier on a fresh copy. Nothing calls a model yet.

# %%
work = fresh_copy("verify-demo")
code, failed = verify(work)
print("exit code:", code, ExitCode(code).name, "| failing lines:", len(failed))

# %% [markdown]
# The exit code is the whole stop rule. pytest returns **0** (`OK`) when every test passed and **1** (`TESTS_FAILED`) when some failed. Other codes mean the run itself broke, for example **4** (`USAGE_ERROR`) for a test file that does not exist. Only 0 is done. The Common mistakes section shows what goes wrong when a loop treats "not 1" as done.

# %% [markdown]
# ### Step 2: the fix loop
# One function runs one case. It asks `propose` for a new module, writes it, runs the verifier, and decides. The decision uses the verifier alone: green is done, the same failure lines twice is stuck (lesson 06's repeat rule, applied to the verifier's output), and a cap is over budget. Red runs are reverted with git.
#
# The budget comes from lesson 05, simplified here to model turns only. It is a smaller class than lesson 05's: it counts turns and nothing else.
#
# `propose` is any function that returns new module text. Later we pass the real model. For the controls below we pass hand-made candidates, so the loop can be tested without a model call.

# %%
@dataclass
class Budget:  # model turns allowed; each run has its own cap, the golden set shares one
    max_turns: int
    turns: int = 0

def run_fix_loop(case, propose, shared, per_run=2):
    """Fix one module until its tests pass, the same failure repeats, or a cap is reached."""
    work = fresh_copy(case["id"])
    code, failed = verify(work, [case["tests"]])
    turns, stop = 0, "done"
    while code != 0:
        if turns >= per_run or shared.turns >= shared.max_turns:
            stop = "over_budget"
            break
        (work / case["file"]).write_text(propose(work, case, failed))
        shared.turns += 1
        turns += 1
        previous = failed
        code, failed = verify(work, [case["tests"]])
        if code != 0 and failed == previous:
            stop = "stuck"
            break
    touched = touched_tests(work)
    if code != 0: revert(work)  # revert runs only on red runs; a green run keeps its edits
    return {"id": case["id"], "stop": stop, "turns": turns, "green": code == 0,
            "tests_touched": bool(touched), "ok": stop == "done" and code == 0 and not touched}

# %% [markdown]
# ### Step 3: the golden set and two controls (no model call)
# A golden case names one module, the test file that is its spec, and the expected end: the tests pass and no test was edited. The set has four cases, each with two failing tests. Pocket-cart has 12 failures in all; the other two modules (pricing and cart) are left for lessons 08 and 11.
#
# The controls check the loop itself. A control is a hand-made candidate, labelled as such, not model output. The first comparison is against the failures before turn 1, so an unchanged file is stuck after one turn. Both controls below are tied to case G1-money on purpose: `delete_the_asserts` always rewrites `tests/test_money.py`, and `keep_guessing` returns `format_price`, which only fits `money.py`.

# %%
GOLDEN = [  # one module each; the expected end is: done, its test file green, no test edited
    {"id": "G1-money", "file": "pocket_cart/money.py", "tests": "tests/test_money.py"},
    {"id": "G2-tax", "file": "pocket_cart/tax.py", "tests": "tests/test_tax.py"},
    {"id": "G3-coupons", "file": "pocket_cart/coupons.py", "tests": "tests/test_coupons.py"},
    {"id": "G4-shipping", "file": "pocket_cart/shipping.py", "tests": "tests/test_shipping.py"},
]
golden = []  # filled by the model run in step 4

def no_change(work, case, failed):
    """Hand-made: the file stays as it is. No model call."""
    return (work / case["file"]).read_text()

def delete_the_asserts(work, case, failed):
    """Hand-made cheat: edits the test, not the code (G1-money only). No model call."""
    (work / "tests/test_money.py").write_text("def test_nothing():\n    assert True\n")
    return (work / case["file"]).read_text()

attempt = iter(range(1, 100))

def keep_guessing(work, case, failed):
    """Hand-made: a new wrong answer each turn, so the failure lines change and the cap ends the run (G1-money only). No model call."""
    return f"def format_price(cents):\n    return 'guess {next(attempt)}'\n"

controls = [("no change", no_change, GOLDEN[0]), ("edit the test", delete_the_asserts, GOLDEN[0]),
            ("keep guessing", keep_guessing, GOLDEN[0])]
for name, candidate, case in controls:
    res = run_fix_loop(case, candidate, Budget(max_turns=2))  # controls make no model call
    print(f"{name:14s} stop {res['stop']:<11s} turns {res['turns']} | green {res['green']} | "
          f"tests touched {res['tests_touched']} | ok {res['ok']}")

# %% [markdown]
# Read the three rows. "No change" stops as **stuck** after one turn: the same failure lines came back. "Edit the test" is **green**, so the verifier says done, but `ok` is False. This lesson only detects a test edit after the run; it does not block one. Revert runs only on red runs, so the green copy keeps the edited test. Lesson 14 adds the real guard that refuses the edit. "Keep guessing" gives new failure lines each turn, so no repeat rule fires. The cap ends it as **over budget** after two turns, and the red run is reverted.

# %% [markdown]
# ### Step 4: the golden run with the real model (5 calls at most)
# Every case draws from one shared budget of 5 model turns, and each case may use at most two. Five is the most calls this notebook may make, so the shared budget keeps the notebook inside that limit, whatever the model does.
#
# The model reads the module, the spec and the failing lines, and returns the whole new module. The answers are recorded once and replayed later, so no key is needed to run this notebook again.
#
# The cell below loads the model. The key comes from `.env`, and a recording replays without one. Without a key and without a recording, the golden list stays empty and the gate prints 'not run'.

# %% tags=["needs-llm"]
from langchain_core.messages import HumanMessage, SystemMessage
from llm_setup import DEFAULT_MODELS, get_llm

llm = get_llm(model=DEFAULT_MODELS["gemini"])
FIX_SYSTEM = ("You fix one module of a small Python shop. Reply with the complete new text of that module "
              "only: no explanation and no code fences. The tests are the spec. Never change them.")

def strip_fence(text):
    """Models sometimes wrap code in fences. Remove them, keep the code."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return text.strip() + "\n"

def model_fix(work, case, failed):
    """One model turn: the whole new module, from its source, the spec and the failing lines."""
    source = (work / case["file"]).read_text()
    spec = (work / case["tests"]).read_text()
    reply = llm.invoke([SystemMessage(content=FIX_SYSTEM),
                        HumanMessage(content=f"Module:\n{source}\nSpec (tests):\n{spec}\nStill failing:\n"
                                             + "\n".join(failed))])
    return strip_fence(reply.text)

# %% [markdown]
# Run the golden set. This is the only cell that calls the model, and its calls are the ones recorded.

# %% tags=["needs-llm"]
shared = Budget(max_turns=5)  # the most model turns this notebook makes
golden = [run_fix_loop(case, model_fix, shared, per_run=2) for case in GOLDEN]
for res in golden:
    print(f"{res['id']:12s} stop {res['stop']:<11s} turns {res['turns']} | ok {res['ok']}")
print(f"model turns used: {shared.turns} of {shared.max_turns} | recorded calls: {llm_replay.calls()}")

# %% [markdown]
# All four cases passed on turn 1, so the model never saw the failing lines come back. The stuck and over-budget exits above were shown only with hand-made controls, not with the model. The real retry on failing lines is for a later lesson. The budget adds up: 4 cases x 1 turn = 4; the fifth turn was spare.

# %% [markdown]
# ### Step 5: the golden gate (no model call)
# The gate reads the golden results and compares the score with the last accepted score. A change passes only if the score holds. Here the accepted score is set to 1.0 by hand to teach the gate. In real use it is the last reviewed run's score, stored in a file, so the gate never moves itself. In the recorded run every case ended done on its first turn, so the score is 1.00 and the gate passes. The demo line below uses a hand-made list to show the block path.

# %%
ACCEPTED = 1.0  # the golden score of the last accepted version; set by hand here, read from a file in real use

def golden_gate(results, accepted):
    """The score is the share of cases that are ok. Pass only if it holds the accepted score."""
    score = sum(r["ok"] for r in results) / len(results)
    return score, ("pass" if score >= accepted else "block")

score, verdict = golden_gate(golden, ACCEPTED) if golden else (0.0, "not run (needs-llm cell skipped)")
print(f"golden score {score:.2f} vs accepted {ACCEPTED:.2f} -> {verdict}")
print("demo, no model call:", golden_gate([{"ok": True}, {"ok": False}], ACCEPTED))  # 0.5 -> block

# %% [markdown]
# ## Under the hood
# The verifier is pytest's exit code, so the loop needs no parser. The golden gate is hand-written: a score and a threshold. A model reply that ends cleanly says the text ended, not that the work is right, so the verifier still decides done.
#
# **pass^k.** pass^k is the chance that the loop succeeds on all k independent runs. If each run has chance p, that is p^k, so p^k is arithmetic here, not a result. A per-run rate of 0.9 over 5 runs gives 0.59: all five pass only about 59% of the time. The code below uses that invented rate. This notebook cannot measure pass^k, because a replayed recording repeats one answer. A real pass^k needs k live runs per case, which lesson 18 covers.

# %%
rate = 0.9  # an arithmetic example, not a measurement
print({k: round(rate ** k, 3) for k in (1, 3, 5)})  # the chance all k runs succeed

# %% [markdown]
# **LLM-as-judge limits.** A judge model can grade an answer when no test exists. Before you trust it, label a sample of outputs by hand and check that the judge agrees with you. Blog posts suggest 50 to 100 labels; that is a rule of thumb, not a standard. Until the judge is checked, use a deterministic check first.
#
# %% [markdown]
# ## At work
# - Production loops gate on deterministic checks first, and on an LLM judge only when no test exists. Spotify reported that its LLM judge vetoes about 25% of its background-agent sessions ([Spotify, Part 3](https://engineering.atspotify.com/2025/12/feedback-loops-background-coding-agents-part-3)). → lesson 14
# - The loop's own tests must not change. Anthropic's harness post calls editing or removing tests "unacceptable" ([Anthropic, long-running harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)), so the loop needs a guard for that. → lesson 14
# - A regression gate in CI compares the golden score with a threshold file, and reports pass^k over three to five runs. → lesson 18

# %% [markdown]
# ## Common mistakes
# 1. **Treating "not 1" as done.** A usage error such as a missing test file returns a different non-zero code. A check that only looks for 1 would call that run finished.

# %% tags=["raises-exception"]
code, _ = verify(work, ["tests/test_missing.py"])
assert code == 0, f"not done: pytest exit code {code}"  # AssertionError: not done: pytest exit code 4

# %% [markdown]
# Fix: stop only on exit code 0. Anything else is not done, and the run reports the code.
#
# 2. **A golden set of one case.** A single case can pass by luck. Use several cases, and one run each is not enough to trust a score: pass^k is the test for that (under the hood above).

# %% [markdown]
# ## Try it
# Take a fresh copy named `try-it`. Edit `tests/test_money.py` by hand so that its assertions are gone, then call `verify`. Predict the exit code before you run it. Then call `revert` on the copy and run `verify` again. Predict the exit code and the number of failing lines.

# %%
# your code here: start with w = fresh_copy("try-it")

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution", "hide-cell"]
w = fresh_copy("try-it")
(w / "tests/test_money.py").write_text("def test_nothing():\n    assert True\n")
print("after the edit:", verify(w, ["tests/test_money.py"])[0], "(green: the test was replaced)")
revert(w)
code, failed = verify(w, ["tests/test_money.py"])
print("after revert:", code, "with", len(failed), "failing lines")

# %% [markdown]
# Save the recording. This cell is the last code cell of the notebook.

# %%
llm_replay.stop()  # saves the recording

# %% [markdown]
# ## Recap
# - A verifier is a check a program reads without judgement. For code it is pytest: exit code 0 means done, and no other code does.
# - The loop stops on the verifier, not on the model's word. Same failure lines twice is stuck; a cap is over budget; red runs are reverted with git.
# - A green check can still be wrong if the agent edits the tests. Refuse any edit to the spec.
# - A golden set is a fixed list of cases. Its score is the regression gate: a change that lowers it is blocked.
#
# **Interview:** "How does a coding agent know it has finished?" A strong answer: a deterministic verifier, here the test suite's exit code, decides done; the loop never trusts the model's claim; the test files are read-only to the agent, so a green run cannot be faked; and a golden set of cases gates every change to the prompt or model.

# %% [markdown]
# # 11 · The Ralph loop: one item per iteration, fresh context, commit on green
# Level L3 · Part 2 · core · ~30 min · builds on 10
#
# ## Goal
# Run an outer loop that fixes one failing test per iteration, gives each model call a fresh and small context, keeps an edit only when pytest is green, and stops only when pytest reports no failing test. Show that a red edit is reverted and that a model's "DONE" claim does not end the loop.
#
# ## Why it matters
# Without a loop that works one item at a time, a repo with twelve failing tests goes wrong in three ways:
#
# - One big prompt with every failing line. One wrong module spoils the whole reply, and nothing says which one.
# - One long chat. Each turn repeats the last, so the input grows and old mistakes stay in view.
# - The model says "DONE". The run ends, and a person finds the red tests later.
#
# With this loop each failing test gets one small call. A green edit is committed. A red edit is reverted, and the next item still runs. You do not need it for one failing test: one call and one pytest run are enough.

# %% [markdown]
# ## The idea
# **The Ralph loop picks the next failing test from the verifier, not from the model. It gives the model a fresh context with only that item, keeps the edit if the test passes and nothing else turns red, and reverts it if not. It stops when the verifier lists no failing test.**
#
# Analogy: a proofreader working through a list of typos. Each pass fixes one typo, and a page is kept only if it reads right and no new typo appeared. The list comes from the page, not from the proofreader's memory, and the job ends when the page is clean, not when the proofreader says so.
#
# Geoffrey Huntley wrote up this pattern in January 2026 and called it the Ralph loop. The model is not the stop rule here: pytest is.

# %% [markdown]
# ## Picture
# The outer loop asks pytest for the next failing test. The model sees one item at a time, and git keeps or undoes the edit.
#
# ```mermaid
# flowchart TD
#   L["Outer loop: pytest lists the failing tests"] -->|"none left"| D["done: the verifier is green"]
#   L -->|"one item"| F["Fresh context: its module, its test file, its failure"]
#   F --> M["Model: one call, the whole module"]
#   M --> W["Write the module"]
#   W --> V{"pytest: item passes, nothing new fails, tests untouched?"}
#   V -->|"yes"| K["git commit: keep it"]
#   V -->|"no"| R["git checkout: revert it"]
#   K --> L
#   R --> C{"item tried twice, or budget used?"}
#   C -->|"no"| L
#   C -->|"yes"| S["stop: stuck or over budget"]
# ```

# %% [markdown]
# ## Step by step
# ### Step 1: the repo and the verifier (no model call)
# `pocket-cart` is the generated shop repo from lesson 07. It has twelve failing tests in six modules. The loop works on a copy, so `../data/pocket-cart` is never edited.

# %%
import os, re, shutil, subprocess, sys
from pathlib import Path

sys.path.insert(0, "..")
import llm_replay
llm_replay.start("11_ralph-loop")  # records the model calls once, replays them later

SRC = Path("../data/pocket-cart")  # generated once; this lesson only reads it
WORK = Path("../data/11")          # run-time copies of the repo
PYTHON = os.path.abspath(sys.executable)  # the kernel may give a relative path
print((SRC / "FIX_PLAN.md").read_text().splitlines()[2])

# %% [markdown]
# The verifier is pytest in the copy. It runs with `--color=no`, so the summary lines start with `FAILED` in plain text. The loop reads the failing node ids from that summary, not from the model.

# %%
def pytest(work, *args):
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "COLUMNS": "200"}
    return subprocess.run([PYTHON, "-m", "pytest", "-q", "--color=no", "-p", "no:cacheprovider", *args],
                          cwd=work, capture_output=True, text=True, env=env)

def failing(work, scope):  # the verifier's list, in file order
    out = pytest(work, "--tb=no", "-rf", *scope).stdout
    return [line[len("FAILED "):].split(" - ")[0] for line in out.splitlines() if line.startswith("FAILED ")]

def failure_text(work, node):  # the only failure the model sees
    out = pytest(work, "--tb=short", node).stdout
    return "\n".join(line for line in out.splitlines() if line.startswith("E "))[:600]

ALL = ["tests"]
print("failing in the source repo (read only):", len(failing(SRC, ALL)))

# %% [markdown]
# Git is the undo button. Each run starts from a commit, so a red edit can be reverted, and a green one is committed as one step.

# %%
def git(work, *args):  # placeholder identity for these local commits
    return subprocess.run(["git", "-c", "user.name=loop", "-c", "user.email=loop@example.com", *args],
                          cwd=work, capture_output=True, text=True, check=True).stdout

def fresh_copy(name):  # a new copy of the repo, committed as the baseline
    work = WORK / name
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(SRC, work)
    git(work, "init", "-q")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "baseline")
    return work

def keep(work, node): git(work, "add", "-A"); git(work, "commit", "-q", "-m", f"fix {node}")
def revert(work): git(work, "checkout", "--", ".")  # undo every uncommitted edit

def tests_touched(work):  # any change under tests/ is a rejected edit
    return git(work, "status", "--porcelain", "--", "tests").strip()

work = fresh_copy("start")
print("failing at start:", len(failing(work, ALL)), "| first:", failing(work, ALL)[0])

# %% [markdown]
# ### Step 2: the outer loop (no model call)
# One iteration takes the first failing test from pytest. It asks `propose` for a new module, writes it, and runs pytest again. The edit is kept only when the item now passes and no other test in scope turned red. A test edit is always rejected. The loop stops when pytest lists nothing, or when a cap is reached.
#
# The budget counts model calls only. A hand-made `propose` costs nothing, so the controls below do not use it. The `Budget` class and the `results` dict are set up in the same cell as the loop.

# %%
class Budget:  # counts model calls; the controls never count one
    def __init__(self, max_calls): self.max_calls, self.calls = max_calls, 0

results = {}  # filled by the model runs in step 5; stays empty when that cell is skipped

def ralph(work, scope, propose, budget, per_item=2):
    log, tries = [], {}
    while True:
        todo = failing(work, scope)
        if not todo:  # the only way to finish: the verifier lists nothing
            return {"stop": "done", "log": log}
        node = todo[0]
        if tries.get(node, 0) >= per_item:
            return {"stop": "stuck", "item": node, "log": log}
        if budget.calls >= budget.max_calls:
            return {"stop": "over_budget", "left": len(todo), "log": log}
        tries[node] = tries.get(node, 0) + 1
        module = work / ("pocket_cart/" + Path(node.split("::")[0]).name[len("test_"):])
        reply = propose(work, node, module, failure_text(work, node), budget)
        module.write_text(reply["text"])
        after = failing(work, scope)
        # item fixed, no new failure, tests/ untouched
        ok = node not in after and set(after) <= set(todo) - {node} and not tests_touched(work)
        keep(work, node) if ok else revert(work)
        log.append({"item": node, "claimed_done": reply["claimed"], "tokens": reply["tokens"],
                    "result": "kept" if ok else "reverted", "left": len(failing(work, scope))})

# %% [markdown]
# ### Step 3: two hand-made controls (no model call)
# A control is a made-up edit, labelled as such, to test the loop itself. The first edit breaks the module and says "DONE: yes". The loop must revert it and must not stop on that claim. The second edit also changes a test. The loop must refuse it.

# %%
def wrong_edit(work, node, module, failure, budget):
    """Hand-made control: breaks the module and claims it is done. No model call."""
    return {"text": "def format_price(cents):\n    return 'wrong'\n", "claimed": "yes", "tokens": 0}

def cheat_edit(work, node, module, failure, budget):
    """Hand-made control: edits the test instead of the code. No model call."""
    (work / "tests/test_money.py").write_text("def test_nothing():\n    assert True\n")
    return {"text": module.read_text(), "claimed": "yes", "tokens": 0}

for name, candidate in [("wrong edit", wrong_edit), ("edit the test", cheat_edit)]:
    w = fresh_copy("control-" + name.replace(" ", "-"))
    res = ralph(w, ["tests/test_money.py"], candidate, Budget(max_calls=2))  # controls never count a call
    row = res["log"][0]
    print(f"{name:14s} stop {res['stop']:<7s} | claimed done {row['claimed_done']} | "
          f"result {row['result']} | still red {row['left']} | tests clean {not tests_touched(w)}")

# %% [markdown]
# Read the rows. "Wrong edit" says DONE and is still red, so pytest reverts it and the loop tries the same item again, then stops as **stuck** after two tries. The model's word did not end the run. "Edit the test" is refused the same way: the test folder changed, so the edit is reverted and the item is tried again. Both controls end stuck, and both show `tests clean True` after the revert. Neither used a model call.

# %% [markdown]
# ### Step 4: the model, one fresh context per item
# Each iteration sends one call. Its context is the module, its test file and the one failure. There is no earlier chat, so the input stays small whatever the iteration number. The model replies with the whole module and a `DONE:` line. The loop logs that line and does not act on it. `reply.text` and `usage_metadata` are fields of the langchain-core message the model returns.

# %% tags=["needs-llm"]
from langchain_core.messages import HumanMessage, SystemMessage
from llm_setup import DEFAULT_MODELS, get_llm

llm = get_llm(model=DEFAULT_MODELS["gemini"])  # the key comes from .env; a recording replays without one

ITEM_SYSTEM = ("You fix one module of a small Python shop. The test file is the spec: never change it. "
               "Fix only what the failing test asks. Reply with the complete new text of the module, "
               "then one line 'DONE: yes' or 'DONE: no' for the whole suite. No prose, no code fences.")

def model_fix(work, node, module, failure, budget):
    """One call, fresh context: this module, its test file and this one failure. Nothing from earlier calls."""
    test_file = work / node.split("::")[0]
    prompt = (f"### MODULE {module.relative_to(work)}\n{module.read_text()}\n"
              f"### TEST FILE {test_file.relative_to(work)}\n{test_file.read_text()}\n"
              f"### FAILING TEST {node}\n{failure}\n")
    reply = llm.invoke([SystemMessage(content=ITEM_SYSTEM), HumanMessage(content=prompt)])  # a new list each call
    budget.calls += 1
    text = reply.text.replace("```python", "").replace("```", "")
    claims = re.findall(r"^DONE:\s*(yes|no)", text, flags=re.M | re.I)
    return {"text": re.sub(r"^DONE:.*$", "", text, flags=re.M | re.I).strip("\n") + "\n",
            "claimed": claims[-1].lower() if claims else "none",
            "tokens": reply.usage_metadata["input_tokens"]}

# %% [markdown]
# ### Step 5: the real runs (up to 4 model calls, recorded 2)
# Run A works on the two failing money tests. Run B works on the two failing pricing tests. Each run has a budget of two calls. If the first fix also fixes the second test, the loop finishes after one call, because pytest lists nothing left.

# %% tags=["needs-llm"]
for name, scope in [("money", ["tests/test_money.py"]), ("pricing", ["tests/test_pricing.py"])]:
    w = fresh_copy("run-" + name)
    budget = Budget(max_calls=2)
    res = results[name] = ralph(w, scope, model_fix, budget)
    print(f"{name}: stop {res['stop']} | model calls {budget.calls} | "
          f"left in scope {len(failing(w, scope))}")
    for row in res["log"]:
        print(f"  {row['item'].split('::')[1]:32s} claimed done {row['claimed_done']:<4s} "
              f"input tokens {row['tokens']:>5} | {row['result']}")

# %% [markdown]
# ### Step 6: what the runs show (no model call)
# The summary counts the model's claims against pytest's result. A claim of "yes" while pytest still lists a failure is a **premature completion**. The loop did not stop there.
#
# The count below is expected to be 0 in this recording: the model's claims matched pytest both times. Step 3 is where premature completion is demonstrated, with the hand-made control that says "DONE: yes" while two tests are still red.

# %%
rows = [r for res in results.values() for r in res["log"]]  # zero rows if the model cell was skipped
early = [r for r in rows if r["claimed_done"] == "yes" and r["left"] > 0]
print("iterations:", len(rows), "| kept:", sum(r["result"] == "kept" for r in rows),
      "| premature completions:", len(early), "| stops:", {k: v["stop"] for k, v in results.items()})

# %% [markdown]
# **What the recorded run showed** (one sample, the course's default Gemini model, recorded 2026-10-27). Each run made one call. The first fix rewrote the whole module and fixed both tests in scope, so each loop ended as **done** after one iteration. Each call had 324 to 346 input tokens, and the model's `DONE: yes` matched pytest both times. No edit was reverted, so the revert path ran only in the hand-made controls. A different model or a harder module may need the second try, and the loop allows exactly one more call per item.

# %% [markdown]
# ## Under the hood
# `ralph` in Step 2 is the hand-written version of this loop, about 20 lines on top of pytest and git. No library in the course stack runs a Ralph loop, so the `interview` hand-code is that function. The published form is a shell sketch, not run here:
#
# ```bash
# # shell sketch (not run): one prompt file, the agent run again and again
# while :; do cat PROMPT.md | <agent CLI> ; done
# ```
#
# A bare `while` has no stop rule and keeps paying. The four parts `ralph` adds are: the stop from the verifier's list (`failing`), a call cap (`Budget`), one item per fresh call (`propose`), and keep or revert (`keep` / `revert`). The last one is the backpressure: a failing test pushes the bad edit back.

# %% [markdown]
# ## At work
# - Teams keep one item per run and commit each green step, so a bad edit costs one revert, not a whole night of work. Huntley's Ralph write-up (2026-01-17) names this pattern: tests as backpressure, commit on green. → lesson 12 covers the state the loop keeps between items.
# - Anthropic's notes on long-running agents (2025-11-26) use a feature list in JSON, edited only by the agent that passes it, and "one feature per session". Models corrupt a Markdown list more easily than JSON, so the list format matters. → lesson 12.
# - Codex issues show goals that complete too early: "File-backed Goal prematurely completes" (2026-10-14), and "automatic Goal turns continue after verified work completion" (2026-10-24). Anthropic's harness post says removing or editing tests is "unacceptable", so the test folder is read-only to the loop. → lesson 14 covers the checker that is separate from the writer.

# %% [markdown]
# ## Common mistakes
# Wrong: the loop stops when the model says it is done.
# The control in Step 3 shows why not: "wrong edit" claims `DONE: yes` while pytest still lists failing tests. The stop is the verifier's empty list, never the reply. The cell below runs that control and asserts on the real result.

# %% tags=["raises-exception"]
w = fresh_copy("mistake-claimed-done")
row = ralph(w, ["tests/test_money.py"], wrong_edit, Budget(max_calls=2))["log"][0]
assert row["claimed_done"] == "yes" and row["left"] == 0, f"not done: pytest still lists {row['left']} failing tests"  # AssertionError

# %% [markdown]
# Right: stop on the verifier's list, and say so in the log. The claim is data, not a stop.
#
# Wrong: keeping every edit, red or green, so the next item starts on a broken file.
# The fix is the revert on red. A reverted item is tried again, and then stuck, not hidden.

# %% [markdown]
# ## Try it
# Change `per_item` from 2 to 1 in `ralph`, and run the "wrong edit" control again. Which stop does the loop report, and after how many tries? Then: what does `per_item=3` cost in worst-case model calls for 12 failing items, and what caps it?

# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
w = fresh_copy("try-wrong-edit")
res = ralph(w, ["tests/test_money.py"], wrong_edit, Budget(max_calls=2), per_item=1)
print(f"per_item=1: stop {res['stop']} after {len(res['log'])} try | item {res.get('item', '-')}")
print("per_item=3, 12 failing items, worst case:", 3 * 12, "model calls, capped by max_calls")  # 36
# Each try is one model call when the model edits, so the worst case is per_item times the failing items.

# %% [markdown]
# Save the recording. This is the last cell that touches the model layer.

# %%
llm_replay.stop()  # saves the recording (record mode) and closes the replay

# %% [markdown]
# ## Recap
# - The outer loop takes the next failing test from pytest, never from the model's claim.
# - Each model call sees one module, its test file and one failure. Nothing from earlier calls is sent.
# - A green edit is committed. A red edit is reverted. A test edit is always rejected.
# - The loop stops on an empty verifier list, a stuck item or a call cap. A "DONE" claim is logged, not obeyed.
#
# **Interview:** Why does a Ralph loop fix one test per iteration with a fresh context? Strong answer: a small context keeps each call cheap and focused, one item means a red result undoes one change, and the verifier, not the model, decides "done", so a premature completion is caught.

# %% [markdown]
# # 12 · State outside the context: progress file, feature list, git and SQLite
# Level L3 · Part 2 · core · ~25 min · builds on 11
#
# ## Goal
# Keep a loop's state in files and a SQLite table, so a new process after a crash resumes at the right item with its tries and model calls intact.
#
# ## Why it matters
# Lesson 11's fresh context means each call knows nothing about the last one, and a crash ends the process that held the loop's memory. Without state outside the process:
#
# | Without state | What goes wrong |
# |---|---|
# | Restart from the baseline | Kept fixes are paid for again |
# | Tries in a Python variable | A restart gets two more tries on a failed item |
# | Budget in the process | A restart gets a full budget again |
# | "Where were we?" asked of the model | A guess, from a long chat |
#
# With state, a restart reads the table, the verifier and git, and keeps its caps. You do not need it for a loop that finishes in one run with no crash.

# %% [markdown]
# ## The idea
# **The loop keeps four kinds of state, each with one job. pytest says what is still red. git says what was kept. The progress file and the feature list are for a person or a new session to read. The SQLite table says how many tries and model calls each item and run has used. Each iteration reads these first, never the chat, so a new process resumes where the old one stopped.**
#
# Analogy: a hospital shift handover. The next nurse reads the chart, not last shift's memory, and the medication limit still holds.
#
# Anthropic's long-running harness uses the same pieces; here the spine (the fixed spec, `FIX_PLAN.md`) is never edited by the loop.

# %% [markdown]
# ## Picture
# Every iteration, and every restart, starts by reading the state. A cap is checked against the table, not against the process's memory.
#
# ```mermaid
# flowchart TD
#   S["Start of an iteration, or a restart"] --> R["Read the state, not the chat"]
#   R --> V["pytest: what is still red"]
#   R --> G["git log: what was kept"]
#   R --> T["SQLite table: tries and model calls used"]
#   V --> N{"item left, tries and calls under the caps?"}
#   T --> N
#   N -->|"no"| X["stop: done, stuck or over budget"]
#   N -->|"yes"| M["one model call, fresh context"]
#   M --> W["write, check, keep or revert"]
#   W --> P["append a row to the table and a line to the progress file"]
#   P --> S
# ```

# %% [markdown]
# ## Step by step
# ### Step 1: the repo, the spine and the verifier (no model call)
# `pocket-cart` is the generated shop repo from lesson 07. This lesson uses two of its modules: four failing tests in `money` and `pricing`. Each run works on a copy in `../data/12`, so `../data/pocket-cart` is never edited. The helpers below come from lessons 07 and 11, in the same form.

# %%
import json, os, shutil, subprocess, sys
import sqlite3
from pathlib import Path

sys.path.insert(0, "..")
import llm_replay
llm_replay.start("12_state-across-iterations")  # records the model calls once, replays them later

SRC = Path("../data/pocket-cart")          # generated once; this lesson only reads it
ROOT = Path("../data/12")                  # run-time state: repos, progress files, feature lists, the table
PYTHON = os.path.abspath(sys.executable)   # the kernel may give a relative path
SCOPE = ["tests/test_money.py", "tests/test_pricing.py"]  # two modules, four failing tests
shutil.rmtree(ROOT, ignore_errors=True)    # a clean start each time this notebook runs
ROOT.mkdir(parents=True)
print((SRC / "FIX_PLAN.md").read_text().splitlines()[2])  # the spine: the fixed spec

# %% [markdown]
# **The helpers.** The same as lessons 07 and 11: pytest lists the failing ids and the failure text the model will see.

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

# %% [markdown]
# **More helpers.** Git keeps one green fix as a commit, or undoes an edit. `start_run` makes the copy with a baseline commit and a feature list.

# %%
def git(work, *args):  # placeholder identity for these local commits
    return subprocess.run(["git", "-c", "user.name=loop", "-c", "user.email=loop@example.com", *args],
                          cwd=work, capture_output=True, text=True, check=True).stdout

def keep(work, node):  # one green item = one commit; returns its short id
    git(work, "add", "-A"); git(work, "commit", "-q", "-m", f"fix {node}")
    return git(work, "rev-parse", "--short", "HEAD").strip()

def revert(work):  # undo every uncommitted edit; the table records "-" as no commit
    git(work, "checkout", "--", ".")
    return "-"
def tests_touched(work): return git(work, "status", "--porcelain", "--", "tests").strip()
def repo_of(run): return ROOT / run / "repo"

def start_run(run, scope):  # the first process only: a copy, a baseline commit, a feature list
    (ROOT / run).mkdir(parents=True, exist_ok=True)
    shutil.copytree(SRC, repo_of(run))
    git(repo_of(run), "init", "-q"); git(repo_of(run), "add", "-A")
    git(repo_of(run), "commit", "-q", "-m", "baseline")
    todo = failing(repo_of(run), scope)
    (ROOT / run / "feature_list.json").write_text(json.dumps([{"id": n, "passes": False} for n in todo], indent=1))

print("failing at start:", failing(SRC, SCOPE), "(read only, no copy yet)")

# %% [markdown]
# ### Step 2: the state and the loop (no model call)
# Four pieces of state, one function each. The table is opened on every call, so a restart reads the file, not memory. `where_we_are` is the start-of-iteration routine. `iterate` is one process: it loops until the verifier is green or a cap stops it, and every decision reads the state first. `claimed` is the model's own "DONE" claim; the verifier decides what counts. The key (run, node, attempt) makes each try one row.
#
# A real crash would kill the Python process. Here we raise an exception and reopen the DB connection; as far as the state goes it is the same, since nothing is carried over except files. `crash_at` is a test-only hook, not for production.

# %%
def open_db():  # a new connection each time: a restart reads the file, not memory
    db = sqlite3.connect(ROOT / "loop_state.db")
    db.execute("create table if not exists items (run text, node text, attempt integer, result text, "
               "claimed text, model integer, commit_id text, primary key (run, node, attempt))")
    db.commit()
    return db

def mark(run, node, passes):  # the feature list is written only here, after pytest has run
    path = ROOT / run / "feature_list.json"
    feats = {f["id"]: f["passes"] for f in json.loads(path.read_text())}
    feats[node] = passes
    path.write_text(json.dumps([{"id": n, "passes": p} for n, p in feats.items()], indent=1))

def record(db, run, node, attempt, ok, reply, commit):  # the table row first, then the progress line
    db.execute("insert into items values (?, ?, ?, ?, ?, ?, ?)",
               (run, node, attempt, "kept" if ok else "reverted", reply["claimed"], reply["model"], commit))
    db.commit()  # saved before anything else can stop the process
    with open(ROOT / run / "progress.md", "a") as f:
        f.write(f"try {attempt} on {node.split('::')[1]}: {'kept ' + commit if ok else 'reverted'}; model calls {reply['model']}\n")

def where_we_are(db, run, work, scope):  # the start-of-iteration routine: verifier, table, git; never the chat
    todo = failing(work, scope)                                     # what is still red
    tries = dict(db.execute("select node, count(*) from items where run = ? group by node", (run,)))
    calls = db.execute("select coalesce(sum(model), 0) from items where run = ?", (run,)).fetchone()[0]
    commits = len(git(work, "log", "--oneline").splitlines())       # what was kept
    return {"todo": todo, "tries": tries, "calls": calls, "commits": commits}

# %% [markdown]
# **The loop.** `iterate` is one process. Every stop check reads the state first. The stops come before the model call, so a spent cap costs nothing.

# %%
def iterate(run, db, scope, propose, per_item=2, max_calls=3, crash_at=None):  # one process; each stop check reads the table
    work, here = repo_of(run), 0
    while True:
        s = where_we_are(db, run, work, scope)
        if not s["todo"]:
            return "done"
        node = s["todo"][0]
        attempt = s["tries"].get(node, 0) + 1
        if attempt > per_item:
            return "stuck"
        if s["calls"] >= max_calls:
            return "over_budget"
        module = work / ("pocket_cart/" + Path(node.split("::")[0]).name[len("test_"):])
        reply = propose(work, node, module, failure_text(work, node))
        module.write_text(reply["text"])
        after = failing(work, scope)
        ok = node not in after and set(after) <= set(s["todo"]) - {node} and not tests_touched(work)
        commit = keep(work, node) if ok else revert(work)
        if ok:  # every other item that is now green gets its flag
            for n in s["todo"]:
                if n not in after: mark(run, n, True)
        record(db, run, node, attempt, ok, reply, commit)
        here += 1
        if crash_at == here:
            raise RuntimeError("simulated power cut, after the table write")

# %% [markdown]
# ### Step 3: the real run, with a crash in the middle (needs a model)
# Process 1 fixes the money tests with one model call, saves the row, and then the power is cut. Process 2 opens the database file again. It finds the money item kept, so it skips it, and it sends one call for the pricing item. Two model calls in all. A restart that forgot would start from the baseline and pay for money again. This step proves the first row of the table above: kept fixes are not paid for again.
#
# The model call uses lesson 11's prompt and one fresh context per call. It returns `"model": 1`, so the table counts it.

# %% tags=["needs-llm"]
import re
from langchain_core.messages import HumanMessage, SystemMessage
from llm_setup import DEFAULT_MODELS, get_llm

llm = get_llm(model=DEFAULT_MODELS["gemini"])  # the key comes from .env; a recording replays without one

# %% [markdown]
# **The model call.** Lesson 11's prompt, one fresh context per call. The returned `"model": 1` is what the table counts.

# %%
ITEM_SYSTEM = ("You fix one module of a small Python shop. The test file is the spec: never change it. "
               "Fix only what the failing test asks. Reply with the complete new text of the module, "
               "then one line 'DONE: yes' or 'DONE: no' for the whole suite. No prose, no code fences.")

def model_fix(work, node, module, failure):
    """One call, fresh context: this module, its test file and one failure. The loop writes the call to the table."""
    test_file = work / node.split("::")[0]
    prompt = (f"### MODULE {module.relative_to(work)}\n{module.read_text()}\n"
              f"### TEST FILE {test_file.relative_to(work)}\n{test_file.read_text()}\n"
              f"### FAILING TEST {node}\n{failure}\n")
    reply = llm.invoke([SystemMessage(content=ITEM_SYSTEM), HumanMessage(content=prompt)])
    text = reply.text.replace("```python", "").replace("```", "")
    claims = re.findall(r"^DONE:\s*(yes|no)", text, flags=re.M | re.I)
    return {"text": re.sub(r"^DONE:.*$", "", text, flags=re.M | re.I).strip("\n") + "\n",
            "claimed": claims[-1].lower() if claims else "none", "model": 1}

# %% [markdown]
# **Process 1, then process 2.** Process 1 runs until the simulated cut. Process 2 opens the database file again and carries on.

# %% tags=["needs-llm"]
start_run("real", SCOPE)
db = open_db()
print("start: still red", len(failing(repo_of("real"), SCOPE)))
try:  # process 1: the power is cut after the first row is saved
    print("process 1:", iterate("real", db, SCOPE, model_fix, crash_at=1))
except RuntimeError as exc:
    print("process 1 stopped:", exc)
db.close()
db = open_db()  # process 2 opens the file as a restart would
s = where_we_are(db, "real", repo_of("real"), SCOPE)
print(f"after the crash: still red {len(s['todo'])} | model calls so far {s['calls']} | commits {s['commits']}")
print("process 2:", iterate("real", db, SCOPE, model_fix))
print("model calls in all:", where_we_are(db, "real", repo_of("real"), SCOPE)["calls"])

# %% [markdown]
# ### Step 4: the caps survive a crash (no model call)
# A hand-made control (no model call) breaks the money module and claims it is done. Process 1 tries it once and is cut off. Process 2 reads the table, finds one try, and so has one try left before the item is stuck. Total: two tries on the item, not two more after the restart. This step proves the second row of the table above: a restart does not reset the tries.

# %%
def wrong_edit(work, node, module, failure):
    """Hand-made control (no model call): breaks the module and claims it is done."""
    return {"text": "def format_price(cents):\n    return 'wrong'\n", "claimed": "yes", "model": 0}

CTL = ["tests/test_money.py"]
start_run("ctl", CTL)
db = open_db()
try:  # process 1: one wrong try, then the power cut
    iterate("ctl", db, CTL, wrong_edit, crash_at=1)
except RuntimeError as exc:
    print("process 1 stopped:", exc)
db.close()
db = open_db()  # process 2 reads the table
print("process 2:", iterate("ctl", db, CTL, wrong_edit, per_item=2))  # attempt 2 <= per_item so it runs; attempt 3 > 2 returns stuck
print("tries on the item across both processes (cap is 2):", db.execute("select count(*) from items where run = 'ctl'").fetchone()[0],
      "| tests folder clean:", not tests_touched(repo_of("ctl")))

# %% [markdown]
# ### Step 5: read the state (no model call)
# Nothing is read from memory here. The table, the progress file and the feature list are what the next session would read.

# %%
db = open_db()  # a fresh connection, as a new process would open it
for run, node, attempt, result, model, commit in db.execute(
        "select run, node, attempt, result, model, commit_id from items order by rowid"):
    print(f"{run:5s} {node.split('::')[1]:34s} try {attempt} {result:9s} model {model} commit {commit}")

# %% [markdown]
# The progress file: the loop appends one line per try. A person reads it.

# %%
print((ROOT / "real" / "progress.md").read_text())  # the progress file: one line per try

# %% [markdown]
# The feature list and the commits: one commit per green fix, and the flags flip only after pytest passes.

# %%
print("feature_list.json, real run:", [f["passes"] for f in json.loads((ROOT / "real" / "feature_list.json").read_text())])
print(git(repo_of("real"), "log", "--oneline"))  # what was kept: one commit per green fix

# %% [markdown]
# **What the recorded run showed** (one sample, the course's default Gemini model, recorded 2026-10-27). Process 1 made one model call. Its fix made both money tests pass, so the row says `kept`, and the power cut came after that row was written. Process 2 read the table and went straight to the pricing item: one more model call, then done. Two model calls in all, and no money item paid for twice. The control shows the caps surviving a crash: process 2 found one try already in the table, made one more hand-made try, and then stopped the item as stuck. Two tries in all, and no model call.
#
# The row count and the commit list above are the evidence. Read them, not the chat. If the model had needed another try, the table would show it.

# %% [markdown]
# ## At work
# - Anthropic's harness notes (2025-11-26) keep a progress file and a JSON feature list where only the item's passing run may flip `passes`, plus git commits as memory between sessions. Teams that keep state only in the chat lose it at the first crash. → lesson 13 makes the repeated write safe; lesson 26a adds the durable checkpoint and a crash drill.
# - The same post reports that a later agent "saw existing progress and declared the project finished too early". This lesson avoids it: the list of work comes from pytest, never from the feature file. → lesson 14 adds a separate checker that does not write the code.
# - Claude Code compacts old turns automatically, and its docs warn that instructions given only early in a chat can be lost in the summary. A loop that keeps its rules in files, not the first prompt, survives this. → lesson 15 measures context growth and compaction.

# %% [markdown]
# ## Common mistakes
# Wrong: the tries live in a Python dict. A crash ends the process, and the dict goes with it.
# The cell below shows the bug with the real item name from the control run. It asserts what a restart must see.

# %% tags=["raises-exception"]
node = db.execute("select node from items where run = 'ctl' limit 1").fetchone()[0]
tries_before_crash = {node: 1}   # process 1 tried the item once
tries_after_restart = {}         # process 2 starts with an empty dict
assert tries_after_restart.get(node, 0) == 1, "the restart forgot the first try"  # AssertionError

# %% [markdown]
# Right: write the try to the table before anything else can stop the process, and count from the table. The check above then reads 1, because the row is on disk.
#
# Wrong: treating the feature list as the to-do list. A `passes: false` flag can be stale after a crash, while pytest always reports what is red now. The loop picks `todo` from pytest and writes the flags after it.

# %% [markdown]
# ## Try it
# Write one query that prints, per run, the model calls spent and the items kept. Then answer: suppose the real run had been given `max_calls=2` and had already spent 2 calls. Would a restart call the model? Why?

# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
db = open_db()
for run, calls, kept in db.execute("select run, sum(model), sum(result = 'kept') from items group by run"):
    print(f"{run:5s} model calls {calls} | kept {kept}")
# The real run: 2 calls, 2 kept. The control: 0 calls, 0 kept.
# A restart would not call the model. The loop checks the verifier before the budget, so a finished run
# returns done. If the run were still red, the call check would return over_budget before any call.

# %% [markdown]
# Save the recording. This is the last cell that touches the model layer.

# %%
llm_replay.stop()  # saves the recording (record mode) and closes the replay

# %% [markdown]
# ## Recap
# - State lives in four places: pytest (what is red), git (what was kept), the progress file and feature list (for a person), and the SQLite table (tries and calls).
# - A new process reads that state and continues. A kept item is not repeated, and a spent try or call is not given back.
# - The to-do list comes from pytest. The feature list is written after pytest runs, so it cannot mark an item done early.
# - Compaction (shrinking old chat turns) comes in lesson 15; the durable checkpointer in lesson 26a.
#
# **Interview:** Where does a loop keep its state across iterations and crashes, and why not in the chat? Strong answer: the verifier, git and a durable table hold facts a new process can check. The chat is lost on a crash and grows each turn. The table keeps the tries and budget, so a restart cannot reset the caps.

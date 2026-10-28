# %% [markdown]
# # 24 · Checkpoint: a triggered loop with approvals and isolated runs
# Level L5 · Part 3 · core · ~30 min · builds on 20, 21, 22, 23
#
# ## Goal
# One scheduled tick starts three pocket-cart fixes. Each run gets its own worktree, branch and grant list. A model proposes one edit per run. A run's work reaches `main` only after a reviewer approves it at a gate, and an approval that arrives after the lease has lapsed is refused.
#
# ## Why it matters
# Lessons 20 to 23 each fix one failure of an unattended loop. Without them together, this is what one pocket-cart run looks like:
#
# | Without the four parts | What goes wrong |
# |---|---|
# | One shared checkout (lesson 21) | Run B's revert erases run A's fix, and nobody can tell which run changed what |
# | No task key or lease (lesson 20) | The schedule and a second worker both start the same fix |
# | No grant list (lesson 23) | The model edits a test to make it pass, or touches a file no fix needs |
# | No gate (lesson 22) | The fix lands in `main` with nobody reading the diff |
#
# With all four, each fix has one owner, one folder, one allowed file and one human answer before it merges. You do not need this for one fix you run by hand and read yourself.

# %% [markdown]
# ## The idea
# **A heartbeat adds one task per fix and a worker claims a task with a lease, so each fix has one owner. The owner works in its own worktree and may edit only the module its grant names. It runs its own test file and commits only on green. A green run parks at an approval gate, holding its lease for a review window. The merge into `main` checks the lease in the same transaction as the write, so a late or stale approval is refused and the task goes back to the queue.**
#
# Analogy: a shared kitchen with a pass. The ticket board gives each dish one cook. Each cook has a station of their own and may use only the pans on their list. A plate goes out only after the head chef tastes it, and a plate that comes back after the ticket was reassigned is thrown away.

# %% [markdown]
# ## Picture
# ```mermaid
# flowchart TD
#   H["Heartbeat: one task per fix"] --> C["Claim: one owner and one attempt per task, lease 90 s"]
#   C --> W["Worktree and branch per run: edit only the granted module"]
#   W --> T{"The run's own tests green?"}
#   T -->|"no"| X["Branch stays at main: nothing to review"]
#   T -->|"yes"| P["Park at the gate: lease held for the review window"]
#   P --> G{"Reviewer answers inside the window?"}
#   G -->|"approve, lease still held"| M["Fenced merge into main"]
#   G -->|"approve, lease lost"| F["Refused: task back in the queue"]
#   G -->|"reject"| R["Task rejected, branch kept"]
# ```

# %% [markdown]
# ## Requirements
# 1. A heartbeat adds the three fixes as tasks, once each. A second heartbeat adds none. Each worker claims one task and gets an owner and an attempt number.
# 2. A grant list: a run may edit only its module and run only its own test file. A merge is never a run's action.
# 3. The model proposes one exact replacement per run. A proposal outside the grant is refused, and so is one whose old text is not found exactly once.
# 4. Each run works in its own worktree. Only a green run commits, and only green runs reach the gate.
# 5. The gate pauses with the diff shown. A merge checks the lease in the same transaction. A refused merge returns the task to the queue.
#
# This notebook makes 3 model calls, one per run (limit 5). The reviewer's answers are typed in: a person's decisions, not model output.

# %% [markdown]
# ## Build it
# Each step adds one part. The repo is generated in lesson 07 and this notebook only copies it. Everything the runs write goes to `../data/24/`.

# %% [markdown]
# ### Step 1: the repo, copied and committed (no model call)
# `main` starts as a copy of pocket-cart with its own git history. The whole suite is red at the start, as it was in lesson 07.

# %%
import sys
sys.path.insert(0, "..")
import llm_replay
llm_replay.start("24_checkpoint-production")  # records the model calls once, replays them later
import shutil, sqlite3, subprocess
from pathlib import Path
ROOT = Path("../data/24").resolve()  # run-time files only: the repo, the worktrees and the two databases
shutil.rmtree(ROOT, ignore_errors=True)
ROOT.mkdir(parents=True)
MAIN = ROOT / "main"        # the repo every run starts from
WT = ROOT / "worktrees"     # one folder per run, made by git
SRC = Path("../data/pocket-cart")  # the course repo: read only
PROPOSALS = {}  # filled by the model step (step 4); stays empty if that step is skipped

# %% [markdown]
# Two helpers come next. `git` runs in the repo, and `pytest_in` is the verifier: exit code 0 means every test in the target passed.

# %%
GIT = ["git", "-c", "user.name=loop-course", "-c", "user.email=loop-course@example.com"]
def git(*args, cwd=MAIN):
    r = subprocess.run([*GIT, *args], cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr.strip())
    return r.stdout.strip()
def pytest_in(cwd, *targets):  # the verifier: exit code 0 means every test passed
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "--color=no", *targets],
                       cwd=cwd, capture_output=True, text=True)
    return r.returncode, r.stdout.strip().splitlines()[-1]
shutil.copytree(SRC, MAIN, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
git("init", "-q", "-b", "main")
git("add", "-A")
git("commit", "-q", "-m", "pocket-cart as shipped")
print("whole suite on main:", pytest_in(MAIN))

# %% [markdown]
# ### Step 2: the schedule, a heartbeat and the claims (no model call)
# The heartbeat is the scheduled tick. It adds one task per fix, and a repeat adds nothing. A worker claims the first open task in one write transaction, and the claim gives it a lease and an attempt number. Four workers ask; the fourth finds the queue empty. The clock is a number the caller passes in, so every run prints the same result.

# %%
LEASE_S = 90    # a claim lasts 90 s; a renewal would extend it
WAIT_S = 3600   # a run parked at the gate keeps its lease for one review window (one hour here)
TASKS = ["money", "tax", "coupons"]  # the three fixes in pocket-cart's fix list
DB = sqlite3.connect(ROOT / "runs.db", isolation_level=None, check_same_thread=False)  # isolation_level=None: Python opens no transaction of its own, so each write sets its own with begin immediate
# Tasks are claimed first by name (alphabetical: coupons, money, tax), not by the order of the fixes.
DB.execute("create table tasks (name text primary key, status text default 'open', owner text, "
           "attempt integer default 0, lease_until real default 0)")
def heartbeat(db):  # the scheduled tick: add each fix that is not a task yet
    return sum(db.execute("insert or ignore into tasks (name) values (?)", (t,)).rowcount for t in TASKS)
def claim(db, owner, now):  # one write transaction: take the first open or lapsed task
    db.execute("begin immediate")  # the write lock comes before the read
    row = db.execute("select name from tasks where status = 'open' or (status in ('leased', 'waiting') "
                     "and lease_until < ?) order by name limit 1", (now,)).fetchone()
    if row:
        db.execute("update tasks set status = 'leased', owner = ?, lease_until = ?, attempt = attempt + 1 "
                   "where name = ?", (owner, now + LEASE_S, row[0]))
    attempt = db.execute("select attempt from tasks where name = ?", (row[0],)).fetchone()[0] if row else 0
    db.execute("commit")
    return (row[0], owner, attempt) if row else None
print("t=0 heartbeat adds:", heartbeat(DB))
print("t=0 the same heartbeat again adds:", heartbeat(DB), "(no duplicates)")

# %% [markdown]
# Now four workers ask for work, one after another. Each claim is one transaction, so the three tasks go to three workers and the fourth gets nothing.

# %%
CLAIMS = {}  # name -> (owner, attempt): one owner per task at a time
for owner in ["worker-a", "worker-b", "worker-c", "worker-d"]:
    got = claim(DB, owner, now=0)
    if got:
        CLAIMS[got[0]] = (got[1], got[2])
    print(owner, "claims:", got)

# %% [markdown]
# ### Step 3: the grant list (no model call)
# The grant list is fixed in code before any run starts. Every action passes `permit` first. A run may edit its one module and read its own test file. Anything else, including a merge, is refused. The four checks below are the grant list at work; the first is allowed.

# %%
MODULE = {"money": "pocket_cart/money.py", "tax": "pocket_cart/tax.py", "coupons": "pocket_cart/coupons.py"}
GRANTS = {name: {"edit": MODULE[name], "test": f"tests/test_{name}.py"} for name in TASKS}
def permit(run, action, path=None):  # checked before every action; the default answer is no
    grant = GRANTS.get(run)
    if grant is None:
        return False, f"no run named {run}"  # an unknown run gets nothing
    if action == "edit" and path == grant["edit"]:
        return True, "granted"
    if action == "test" and path == grant["test"]:
        return True, "granted"
    return False, f"{action} on {path or '-'} is not granted to {run}"  # merges and pushes belong to the gate
for run, action, path in [("money", "edit", "pocket_cart/money.py"), ("money", "edit", "tests/test_money.py"),
                          ("money", "merge", None), ("rogue", "edit", "pocket_cart/money.py")]:
    print(f"{run:8s} {action:6s} {str(path):24s}", permit(run, action, path))

# %% [markdown]
# ### Step 4: the model proposes one edit per run (needs a model, 3 calls)
# Each run gets one call. The model sees its module, its test file and pytest's last line, and returns a `Fix`: the path, the exact old text and the new text. The proposal is checked against the grant before it is kept. The model never runs a command and never decides that a run is done.

# %% tags=["needs-llm"]
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, SystemMessage
from llm_setup import get_llm
class Fix(BaseModel):
    path: str  # the one module to edit
    old: str   # exact text to replace, copied from that module, found once
    new: str   # the replacement text
SYSTEM = ("You fix one bug in a small Python shop library. Propose one exact replacement inside the one module "
          "you are given. The test file is the spec: never propose a change to a test.")
CALLS = 0
def propose(name):  # one model call per run
    global CALLS
    path, test = MODULE[name], GRANTS[name]["test"]
    _, last = pytest_in(MAIN, test)
    question = (f"Module {path}:\n{(MAIN / path).read_text()}\n\nTest file {test}:\n{(MAIN / test).read_text()}"
                f"\n\nPytest says: {last}")
    fix = get_llm().with_structured_output(Fix).invoke([SystemMessage(content=SYSTEM), HumanMessage(content=question)])
    CALLS += 1
    return fix
VERDICTS = []
for name in TASKS:
    fix = propose(name)
    ok, why = permit(name, "edit", fix.path)
    VERDICTS.append(f"{name} {fix.path}: {why}")
    if ok:
        PROPOSALS[name] = fix
print("proposals:", " | ".join(VERDICTS))
# A deliberate bad proposal, built by hand (no model call): it asks to edit a test, so permit refuses it
# and it never reaches PROPOSALS.
bad = Fix(path="tests/test_money.py", old="assert", new="pass")
ok, why = permit("money", "edit", bad.path)
print(f"deliberate bad fix, money on {bad.path}: {why} (kept: {ok})")
print("model calls:", CALLS, "of 5")

# %% [markdown]
# ### Step 5: one worktree per run, two at a time (no model call)
# `git worktree add` gives each run its own folder and its own branch, both from `main`. A run edits only its folder. It runs its own test file, and it commits only when that file is green. A pool of two caps the runs in flight. The check in front of the write is `permit` again, because the grant applies at the moment of the write.

# %%
from concurrent.futures import ThreadPoolExecutor
WT.mkdir(parents=True, exist_ok=True)
for name in TASKS:
    git("worktree", "add", "-q", "-b", f"run/{name}", str(WT / name), "main")
def run_fix(name):  # one run in its own folder: edit its module, run its tests, commit only on green
    wt, fix = WT / name, PROPOSALS.get(name)
    if fix is None:
        return name, "no proposal", ""
    ok, why = permit(name, "edit", fix.path)
    if not ok:
        return name, f"denied: {why}", ""
    text = (wt / fix.path).read_text()
    if text.count(fix.old) != 1:
        return name, "old text not found exactly once", ""
    (wt / fix.path).write_text(text.replace(fix.old, fix.new))
    code, last = pytest_in(wt, GRANTS[name]["test"])
    if code:
        return name, f"red: {last}", ""  # the branch stays at main: nothing goes to review
    git("add", "-A", cwd=wt)
    git("commit", "-q", "-m", f"fix: {name}", cwd=wt)
    return name, "green", git("log", "-1", "--format=%h", cwd=wt)

# %% [markdown]
# The pool runs the three runs, two at a time. Then the table of results and the state of `main` are printed.

# %%
with ThreadPoolExecutor(max_workers=2) as pool:  # the cap: two runs at a time
    RESULTS = list(pool.map(run_fix, TASKS))
for name, status, commit in RESULTS:
    print(f"{name:8s} {status:40s} {commit}")
# "worktrees: 4" is main plus three runs (money, tax, coupons), one folder each.
print("main still clean:", git("status", "--short") or "clean", "| worktrees:", len(git("worktree", "list").splitlines()))

# %% [markdown]
# ### Step 6: the approval gate and a fenced merge (no model call)
# This is lesson 22's graph with two extra nodes. `park` runs before the gate and writes the lease for the review window. `review` pauses and shows the reviewer the diff. `merge` checks the lease in the same transaction as the merge, and a refused merge sends the task back to the queue. `park` writes before the pause, but it is a different node, so it does not run again on resume. `review` writes nothing.

# %%
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command
from langgraph.checkpoint.sqlite import SqliteSaver
class Run(TypedDict):
    name: str
    owner: str
    attempt: int
    now: float
    decision: str
    status: str
def park(s):  # before the gate: the lease now covers the review window
    # here `now` is the claim time (30.0 from gate()); the lease for a parked run is now + WAIT_S = 30 + 3600 = 3630
    DB.execute("update tasks set status = 'waiting', lease_until = ? where name = ? and owner = ? and attempt = ?",
               (s["now"] + WAIT_S, s["name"], s["owner"], s["attempt"]))
    return {}
def review(s):  # the gate: pauses here; on resume this node runs again from its first line, so it writes nothing
    # `now` is first the claim time (from park), then the answer time: the return below replaces it with reply["now"]
    diff = git("show", "--stat", "--format=", f"run/{s['name']}")
    reply = interrupt({"run": s["name"], "owner": s["owner"], "attempt": s["attempt"], "diff": diff})
    return {"decision": reply["decision"], "now": reply["now"]}  # the answer and the time it arrived
def merge(s):  # the side effect, fenced: the lease must still be ours in the same write transaction
    DB.execute("begin immediate")
    held = DB.execute("select 1 from tasks where name = ? and owner = ? and attempt = ? and status = 'waiting' "
                      "and lease_until >= ?", (s["name"], s["owner"], s["attempt"], s["now"])).fetchone()
    if not held:  # the window closed: nothing merges, and the task goes back to the queue
        DB.execute("update tasks set status = 'open', owner = null where name = ? and owner = ? and attempt = ?",
                   (s["name"], s["owner"], s["attempt"]))
        DB.execute("commit")
        return {"status": "refused: review window closed, task back in the queue"}
    git("merge", "-q", "--no-edit", f"run/{s['name']}")
    DB.execute("update tasks set status = 'merged' where name = ?", (s["name"],))
    DB.execute("commit")
    return {"status": "merged"}
def reject(s):  # the reviewer says no: the branch is kept for the record and the task closes
    DB.execute("update tasks set status = 'rejected' where name = ? and owner = ? and attempt = ?",
               (s["name"], s["owner"], s["attempt"]))
    return {"status": "rejected"}
def after_review(s):
    return "merge" if s["decision"] == "approve" else "reject"
# %% [markdown]
# The four nodes are defined. Next, the wiring: `build` connects them, `run` starts one graph call and closes its checkpoint file, and `gate` starts one run, stops at the pause and delivers the answer.

# %%
def build(path):  # the graph: park, review, then merge or reject
    g = StateGraph(Run)
    for name, fn in [("park", park), ("review", review), ("merge", merge), ("reject", reject)]:
        g.add_node(name, fn)
    g.add_edge(START, "park")
    g.add_edge("park", "review")
    g.add_conditional_edges("review", after_review, {"merge": "merge", "reject": "reject"})
    g.add_edge("merge", END)
    g.add_edge("reject", END)
    # one connection per call, closed in run(); check_same_thread=False because the graph may use it from another thread than the one that opened it
    return g.compile(checkpointer=SqliteSaver(sqlite3.connect(path, check_same_thread=False)))
def run(payload, cfg=None):  # one call = one process: build, run, close the checkpoint file
    g = build(ROOT / "checkpoints.db")
    try:
        return g.invoke(payload, cfg)
    finally:
        g.checkpointer.conn.close()
def gate(name, reply):  # start one run's graph, stop at the gate, then deliver the reviewer's answer
    owner, attempt = CLAIMS[name]
    cfg = {"configurable": {"thread_id": f"{name}-{attempt}"}}
    out = run({"name": name, "owner": owner, "attempt": attempt, "now": 30.0}, cfg)
    shown = out["__interrupt__"][0].value  # what the reviewer sees
    print(f"{name}: reviewer sees {shown['diff'].splitlines()[0]} | owner {shown['owner']}, attempt {shown['attempt']}")
    return run(Command(resume=reply), cfg)["status"]

# %% [markdown]
# ### Step 7: the reviewer's answers and the result (no model call)
# All three runs were green, so all three reach the gate. Money and coupons are answered inside the window, so they merge. Tax is answered at t = 5000, after its window closed at t = 3630, so its merge is refused and the task goes back to the queue. Expected output: money and coupons show `merged`, tax shows `refused`, the test exit codes are money 0, coupons 0 and tax 1, and the whole suite on `main` is still red, because tax's fix is the one missing from it. The gate, not the model, decided what reached `main`.

# %%
REPLIES = {"money": {"decision": "approve", "now": 600.0},
           "coupons": {"decision": "approve", "now": 700.0},
           "tax": {"decision": "approve", "now": 5000.0}}  # tax arrives after its review window
GREEN = [name for name, status, _ in RESULTS if status == "green"]
OUTCOMES = {name: gate(name, REPLIES[name]) for name in GREEN}  # gate() prints one line per reviewed run
print("outcomes:", OUTCOMES)
print("tasks:", DB.execute("select name, status, owner, attempt from tasks order by name").fetchall())
print("main log:", git("log", "--oneline").splitlines()[:4])
# exit code per test file on main: 0 = passing. Expected: money 0, coupons 0, tax 1 (its fix is not merged).
print("test exit codes:", {name: pytest_in(MAIN, GRANTS[name]["test"])[0] for name in TASKS},
      "| whole suite:", pytest_in(MAIN))

# %% [markdown]
# ## Try it
# The gate checks the lease with a comparison, the same one `merge` runs in SQL. Fill in the body of `can_merge` so it returns `True` when the lease still covers the answer time, and `False` when it has lapsed. Then run it on money (answered at 600, lease to 3630) and tax (answered at 5000).

# %%
# your code here
def can_merge(now, lease_until):  # answer time, lease end
    return None  # replace this line with the comparison

print("money:", can_merge(600.0, 3630.0), "| tax:", can_merge(5000.0, 3630.0))

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below. The solution stays hidden until you click it.
# ## Reference solution

# %% tags=["solution"]
def can_merge(now, lease_until):  # the same test merge() runs in SQL: the lease still covers this answer
    return lease_until >= now
print("money:", can_merge(600.0, 3630.0), "| tax:", can_merge(5000.0, 3630.0))

# %% [markdown]
# ## At work
# - Spotify's background coding agent runs independent verifiers before a pull request opens, and an LLM judge vetoes about a quarter of the changes. A change that passes CI can still be functionally wrong, so the gate matters → lesson 17 (the CI gate) and lesson 22 (the approval gate).
# - Anthropic's long-running agent harness keeps its progress in a progress file and in git history, with a JSON feature list as the checklist. Rules about what the agent may touch are enforced in code, as a grant list does here → lesson 23.
# - Scheduled loops in production run from cron, systemd or a CI scheduler, with a state file and a lock so one run at a time owns a task. Running this as a service comes later → lesson 28.

# %% [markdown]
# ## Key terms
# - **Grant list** — the named set of actions one run may take, fixed in code and checked before each action (lesson 23).
# - **Fenced merge** — a write that checks the owner and attempt in the same transaction, so a stale worker's result is refused (lesson 20).
# - **Review window** — how long a parked run keeps its lease while a person decides; an answer after it is refused (lesson 22).
# - **Git worktree** — a second working folder for the same repo, with its own branch, so runs cannot overwrite each other (lesson 21).
# - **Interrupt** — LangGraph's pause at a gate; the state is saved until the answer arrives (lesson 22).
#
# **Interview:** How would you let an unattended loop change code safely? Strong answer: one owner per task from a lease, one worktree and one grant list per run, a green test file before any review, and a human approval at a gate with a fenced merge, so a late or stale approval cannot land.

# %%
llm_replay.stop()  # saves the recording (record mode) and closes the replay

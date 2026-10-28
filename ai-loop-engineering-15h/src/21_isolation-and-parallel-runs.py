# %% [markdown]
# # 21 · Isolation: one git worktree per run, subagents and review bandwidth
# Level L5 · Part 3 · core · ~25 min · builds on 20
#
# ## Goal
# Run three loop runs at the same time on one repo, each in its own git worktree and branch, so that no run can overwrite another run's files, and keep the review queue to the size a reviewer can read.
#
# ## Why it matters
# Lesson 20 starts runs from triggers. When two runs start together and both edit the same checkout, the repo becomes a shared desk where everyone writes on the same page:
#
# | Two runs in one checkout | What goes wrong |
# |---|---|
# | Run A and run B both edit files in the same folder | Each run's diff contains the other run's changes |
# | Run B reverts on red with `git checkout -- .` | The revert also undoes run A's fix |
# | Run A's tests run while run B is half-written | A passes or fails for a reason that has nothing to do with A |
# | Ten runs finish at night | Ten branches to review, and no one can tell which edit came from which run |
#
# With one worktree and one branch per run, each run has its own files. A revert or a failed test touches only that run. You do not need this for one run that you watch by hand.
#
# %% [markdown]
# ## The idea
# **A git worktree is a second working folder linked to the same repository. It has its own branch and its own files, and it shares the history with the main checkout. A run gets one worktree, created from a known commit, and its verifier runs inside that folder. Revert-on-red then undoes only that run. The number of runs in flight is capped, and finished branches wait in a review queue whose size matches the number of reviewers. Worktrees isolate files; they do not isolate the machine, so network and shell rules come later.**
#
# Analogy: a restaurant kitchen with one cutting board per cook. Every cook works on their own board from the same order sheet. Nobody's mess lands on another cook's dish, and the pass only sends out as many plates as the expediter can check.
#
# %% [markdown]
# ## Picture
# One repository, three runs. Each run has its own folder and verifier. The main checkout is never written by a run.
#
# ```mermaid
# flowchart TD
#   R["One repo: shared history"] --> M["main checkout: read only for runs"]
#   R --> A["worktree run/money: own files, own branch"]
#   R --> B["worktree run/tax: own files, own branch"]
#   R --> C["worktree run/coupons: own files, own branch"]
#   A --> VA["verifier: tests/test_money.py"]
#   B --> VB["verifier: tests/test_tax.py"]
#   C --> VC["verifier: tests/test_coupons.py"]
# ```
#
# %% [markdown]
# ## Step by step
# ### Step 1: a copy of the pocket-cart repo, and its red tests (no model call)
# The course's pocket-cart repo is read-only in `../data/pocket-cart`. This step copies it into a new git repo under `../data/21/`, so every run starts from a known commit. The tests are the spec from `FIX_PLAN.md`: each module has a test file, and the whole suite is still red.
# %%
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path("../data/21").resolve()        # run-time files only
shutil.rmtree(ROOT, ignore_errors=True)    # a clean start each time this notebook runs
MAIN = ROOT / "main"                       # the repo every run starts from
WT = ROOT / "worktrees"                    # one folder per run, made by git
SRC = Path("../data/pocket-cart")          # the course repo (read-only)
PY = sys.executable                        # the Python that runs this notebook
GIT = ["git", "-c", "user.name=loop-course", "-c", "user.email=loop-course@example.com"]

def git(*args, cwd=MAIN):
    r = subprocess.run([*GIT, *args], cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr.strip())
    return r.stdout.strip()

def pytest_in(cwd, *targets):  # the verifier: exit code 0 means every test passed
    r = subprocess.run([PY, "-m", "pytest", "-q", "--color=no", *targets], cwd=cwd, capture_output=True, text=True)
    return r.returncode, r.stdout.strip().splitlines()[-1]

shutil.copytree(SRC, MAIN, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
git("init", "-q", "-b", "main")
git("add", "-A")
git("commit", "-q", "-m", "pocket-cart as shipped")
print("commits:", git("log", "--oneline"))
print("whole suite:", pytest_in(MAIN))
# %% [markdown]
# ### Step 2: the shared checkout, and why it fails (no model call)
# Run A fixes the money cents padding. Run B fixes the tax rounding in the same checkout. Run B's verifier runs the whole suite, which is still red for other reasons, so its rule says revert. Watch what the revert does to run A.
# %%
MONEY = ("pocket_cart/money.py", "{cents % 100}", "{cents % 100:02d}")
TAX = ("pocket_cart/tax.py", "cents * rate_percent // 100", "(cents * rate_percent + 50) // 100")
COUPON = ("pocket_cart/coupons.py", "COUPONS[code]", "COUPONS[code.strip().upper()]")

def edit(root, path, old, new):  # one exact replacement; fails loudly if the text moved
    f = root / path
    text = f.read_text()
    assert old in text, f"{path}: pattern not found"
    f.write_text(text.replace(old, new))

edit(MAIN, *MONEY)                          # run A writes its fix into the shared checkout
edit(MAIN, *TAX)                            # run B writes its fix into the same checkout
print(git("status", "--short"))             # both files are modified, and no one can tell which run changed what
print("run B verdict:", pytest_in(MAIN))    # the whole suite is still red
git("checkout", "--", ".")                  # run B's revert-on-red: undo its own edit...
print("after the revert:", git("status", "--short") or "clean")
print("run A's money fix still there?", "02d" in (MAIN / MONEY[0]).read_text())  # ...and run A's too
# %% [markdown]
# ### Step 3: one worktree and one branch per run (no model call)
# `git worktree add -b <branch> <folder> main` creates a new folder and a new branch from the same commit. The three runs start from identical files. Each run's folder is a sibling under `../data/21/worktrees/`.
# %%
RUNS = {"money": MONEY, "tax": TAX, "coupons": COUPON}
TESTS = {"money": "tests/test_money.py", "tax": "tests/test_tax.py", "coupons": "tests/test_coupons.py"}
WT.mkdir(parents=True, exist_ok=True)
for name in RUNS:
    git("worktree", "add", "-q", "-b", f"run/{name}", str(WT / name), "main")
print(git("worktree", "list"))
# %% [markdown]
# ### Step 4: three runs in parallel, two at a time (no model call)
# Each run edits its own folder, runs its own test file, and commits only if its verifier passes. A pool of two workers caps the runs in flight, so the machine and the reviewer see at most two runs at once. The edits in the three folders do not touch each other.
# %%
def run_fix(name):
    wt = WT / name
    edit(wt, *RUNS[name])
    code, last = pytest_in(wt, TESTS[name])
    if code == 0:  # commit only what passed; a red run leaves its branch at main
        git("add", "-A", cwd=wt)
        git("commit", "-q", "-m", f"fix: {name}", cwd=wt)
    return name, code, last

from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=2) as pool:   # the cap: two runs at a time
    for name, code, last in pool.map(run_fix, RUNS):
        print(f"{name:8s} exit={code}  {last}")
print("main still clean:", git("status", "--short") or "clean")
# %% [markdown]
# ### Step 5: a red run undoes only itself (no model call)
# A fourth run tries a wrong coupon fix: it looks the code up in lower case, but the keys are upper case. Its verifier goes red. Its revert runs in its own folder, so the fixes on the other branches are untouched.
# %%
WRONG = ("pocket_cart/coupons.py", "COUPONS[code]", "COUPONS[code.strip().lower()]")
git("worktree", "add", "-q", "-b", "run/retry", str(WT / "retry"), "main")
edit(WT / "retry", *WRONG)
print("retry verdict:", pytest_in(WT / "retry", TESTS["coupons"]))
git("checkout", "--", ".", cwd=WT / "retry")       # revert-on-red, inside this worktree only
print("money branch still fixed:", "02d" in git("show", "run/money:pocket_cart/money.py"))
print("tax branch still fixed:", "+ 50" in git("show", "run/tax:pocket_cart/tax.py"))
# %% [markdown]
# ### Step 6: the review queue, sized to the reviewers (no model call)
# Every branch with commits waits for review. The reviewer can read `REVIEW_SLOTS` branches at a time; the rest wait in order. The red `retry` run has no commits, so it is discarded: its worktree and branch go away.
# %%
REVIEW_SLOTS = 2   # diffs one reviewer can read in a session
git("worktree", "remove", "--force", str(WT / "retry"))   # the red run is discarded
git("branch", "-D", "run/retry")
ready = git("for-each-ref", "--format=%(refname:short)", "refs/heads/run/").split()
for b in ready:
    print(f"{b:14s}", git("diff", "--shortstat", f"main...{b}"))
print("in review now:", ready[:REVIEW_SLOTS])
print("waiting:      ", ready[REVIEW_SLOTS:])
# %% [markdown]
# ### Step 7: clean up the folders, keep the branches (no model call)
# A worktree folder is disposable; the branch is the record. Remove the folders when the run ends, prune the links, and keep each branch until its review is closed.
# %%
for name in RUNS:
    git("worktree", "remove", str(WT / name))   # refuses if the folder holds uncommitted work
git("worktree", "prune")
print("worktrees:", git("worktree", "list"))
print("branches kept for review:", git("for-each-ref", "--format=%(refname:short)", "refs/heads/run/").split())
# %% [markdown]
# ## At work
# - **Osmani's heartbeat triage uses one worktree per finding.** A daily heartbeat starts one worktree and one sub-agent per finding, and a second sub-agent reviews before the PR. Approvals around that PR are lesson 22's job.
# - **Coding agents create worktrees for you.** Claude Code runs subagents with `isolation: worktree`, and Codex gives each thread one. You still own the cleanup and the review queue (→ lesson 24 checkpoints the fleet).
# - **A worktree isolates files, not the machine.** Each run still has your shell, network and credentials. Anthropic's secure-deployment guide ranks a Docker container with `--network none` and `--read-only` above OS sandboxes (→ lesson 23 sets the permissions).
# - **Parallel runs multiply cost.** Osmani warns that sub-agents multiply tokens; the cap in Step 4 is the first brake (→ lesson 25 asks when a second agent pays).
#
# Go deeper: `git worktree lock`, for folders on removable drives.
#
# %% [markdown]
# ## Common mistakes
# Wrong: put two folders on one branch, or a run on `main`. Git refuses: a branch lives in one folder at a time. Fix: a new branch per run, as in Step 3.
# %% tags=["raises-exception"]
git("worktree", "add", str(ROOT / "second-main"), "main")   # main is already checked out in MAIN
# %% [markdown]
# Wrong: `rm -rf` a worktree folder. Git still lists it and blocks its branch. Use `git worktree remove`, then `git worktree prune`.
#
# Wrong: let every finished run reach review at once. The queue in Step 6 keeps the rest waiting.
#
# %% [markdown]
# ## Production checklist
# Before runs execute in parallel unattended, check each line. A "no" means a person must start or review the run.
#
# - [ ] Every run gets its own worktree and its own branch, created from a known commit.
# - [ ] No run writes to the main checkout.
# - [ ] A run's verifier runs inside its own worktree, and only its own tests gate its commit.
# - [ ] Revert-on-red runs in the run's own folder, never in a shared one.
# - [ ] Runs in flight have a cap, and finished branches have a review queue with a slot count.
# - [ ] Worktree folders are removed when a run ends; branches stay until review closes.
# - [ ] The run's network and shell rights are limited (lesson 23), because a worktree does not limit them.
#
# %% [markdown]
# ## Try it
# Make a fourth run, `run/docs`, from `main` in its own worktree. Add one line to `FIX_PLAN.md`, commit it, and print the review queue. Then answer: if you delete the `docs` folder with `git worktree remove`, is the commit lost?
# %%
# your code here
# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.
# %% tags=["solution"]
docs = WT / "docs"
git("worktree", "add", "-q", "-b", "run/docs", str(docs), "main")
with open(docs / "FIX_PLAN.md", "a") as f:
    f.write("\n7. Note from run 4: no code change, docs only.\n")
git("add", "-A", cwd=docs)
git("commit", "-q", "-m", "docs: note from run 4", cwd=docs)
for b in git("for-each-ref", "--format=%(refname:short)", "refs/heads/run/").split():
    print(f"{b:14s}", git("diff", "--shortstat", f"main...{b}"))
git("worktree", "remove", str(docs))
print("commit still on the branch:", git("log", "--oneline", "-1", "run/docs"))
# The folder is gone, but the commit lives in the shared history, so the branch still holds it.
# Removing a worktree removes files, not commits. Only deleting the branch can lose the work.
#
# %% [markdown]
# ## Recap
# - A worktree is a second folder with its own branch and files, linked to one repo. Each run gets one.
# - A revert-on-red or a half-written edit in a shared checkout touches every run. In its own worktree it touches one.
# - Cap the runs in flight, and size the review queue to the reviewers who will read it.
# - Remove folders when a run ends; branches are the record and stay until review closes. Worktrees do not limit network or shell rights.
#
# **Interview:** How do you run several coding agents on one repo without them stepping on each other? Strong answer: one git worktree and branch per run, created from a fixed commit; the verifier runs in that folder; revert-on-red stays inside it; a cap limits runs in flight and a review queue matches reviewer capacity; folders are removed, branches kept until review closes.

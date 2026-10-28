# %% [markdown]
# # 25 · Why one loop stops being enough: multi-agent cost, durability and scale
# Level L6 · Part 4 · core · ~20 min · builds on 24
#
# ## Goal
# Price one loop against several agents for the same three pocket-cart fixes. Count the tokens, find the merge conflict that splitting creates, and say when a second agent is worth its cost.
#
# ## Why it matters
# Lesson 24 ran three fixes, one worktree each. Before that, the simplest design is one loop that does all three fixes in turn. Without splitting into several agents, this is what happens:
#
# - Every turn re-sends the whole context, so the bill grows with each fix. The third fix pays for the first two again.
# - One branch holds every change. A person reads the whole diff at once, and one bad fix holds up the other two.
# - One agent does all the reading. Nothing runs in parallel, so the wall clock is the sum of the three fixes.
#
# ```mermaid
# flowchart TD
#   L["One loop: money, then tax, then coupons"] --> C["One growing context: each turn re-sends all of it"]
#   C --> B["One branch: one diff for a person to read"]
#   B --> F["One failure holds up all three fixes"]
# ```
#
# With several agents the wall clock and the context get smaller, but splitting adds costs of its own. You do not need several agents for one fix, for steps that depend on each other, or for a loop that already finishes inside its budget.

# %% [markdown]
# ## The idea
# **A second agent pays only when its piece of work is independent of the others, needs a context of its own, and its result can be checked. Each extra agent adds tokens, a handoff and a merge, and a person still reads what it changed.**
#
# Analogy: a restaurant kitchen. One cook makes every dish in order and keeps every ticket in their head, which slows as the tickets pile up. Three cooks each take one station, but they share the same pans, and every plate still goes past the head chef. Three cooks are faster only when the dishes do not need the same pan at the same time.

# %% [markdown]
# ## Picture
# With several agents: an orchestrator writes one brief per fix. Each worker starts with a fresh context in its own worktree. The merge queue lands one branch at a time, and a person reviews each diff.
#
# ```mermaid
# flowchart TD
#   O["Orchestrator: reads FIX_PLAN, writes one brief per fix"] --> W1["Worker money: own worktree, fresh context"]
#   O --> W2["Worker tax: own worktree, fresh context"]
#   O --> W3["Worker coupons: own worktree, fresh context"]
#   W1 --> Q["Merge queue: one branch at a time"]
#   W2 --> Q
#   W3 --> Q
#   Q -->|"clean"| R["Human review: one diff per branch"]
#   Q -->|"conflict"| X["Back to the worker: rebase on main"]
# ```

# %% [markdown]
# ## Already know this?
# This is the first lesson of Part 4 (durable runs, cost, operation and governance). Answer each question in one line. If you can answer all of them, skim the rest of this lesson and move on.
#
# 1. How does a run resume after its worker dies, without repeating a side effect? Skip to lesson 26a if you can answer it.
# 2. What does a lease expiry do to a run that is still working? Skip to lesson 26b.
# 3. Which number tells you a loop is worth what it costs? Skip to lesson 27.
# 4. Why is a monthly cap not enough for one tenant's runs? Skip to lesson 29a.
# 5. How do you roll out a change to a loop without a big-bang release? Skip to lesson 29b.

# %% [markdown]
# ## Explained
# ### The token multiplier
# Each model turn re-sends the context so far. Anthropic reports about 4x the tokens of a chat for an agent, and about 15x for a multi-agent research system. The multiplier depends on how much each agent reads.
#
# ### Handoffs
# A worker returns a summary to the orchestrator. What it leaves out is lost to everyone else.
#
# ### Conflicting agents
# Agents that change the same lines conflict at merge time. Worktrees separate folders, not lines.
#
# ### Review bandwidth
# Every branch is a diff a person must read. Four small branches are four reviews, and the fleet is only as fast as the people who check it.

# %% [markdown]
# ### Words used below
# - **Worktree:** a second working folder for the same repo, with its own branch, so two runs cannot overwrite each other's files.
# - **Merge queue:** lands branches into `main` one at a time, checking each against the latest `main`.
# - **Handoff:** a task or result passed from one agent to another. Only what the sender wrote down survives it.
# - **Comprehension debt:** code merged faster than people can read and explain it.
# - **Rebase:** replays a branch's commits on top of the latest `main`, so its changes sit on current code.

# %% [markdown]
# ## Worked example: one loop against three workers, in numbers
# The first cell measures the pocket-cart repo that a loop would carry. Pocket-cart is the course repo that lesson 07 builds, kept read-only in `data/pocket-cart/`. The cells below copy it into run-time files and never change the original. Tokens are estimated as characters divided by 4, a rough rule that a real tokenizer will not match exactly. The ratio between designs is the figure to read.

# %%
import shutil, subprocess
from pathlib import Path
SRC = Path("../data/pocket-cart")    # the course repo from lesson 07: read only
ROOT = Path("../data/25").resolve()  # run-time files only: the repo copy and the worktrees
shutil.rmtree(ROOT, ignore_errors=True)
ROOT.mkdir(parents=True)
MAIN, WT = ROOT / "main", ROOT / "worktrees"
CHARS_PER_TOKEN = 4  # rough rule for English and code
FILES = sorted(p for p in SRC.rglob("*") if p.is_file() and p.suffix in (".py", ".md") and "__pycache__" not in p.parts)
SIZE = {p.relative_to(SRC).as_posix(): len(p.read_text()) for p in FILES}
for name, n in SIZE.items():
    print(f"{name:28s} {n:5d} chars")
REPO = sum(SIZE.values())
print(f"whole repo: {REPO} chars, about {REPO // CHARS_PER_TOKEN} tokens")
print("\n--- tests/test_money.py, in full ---")
print((SRC / "tests" / "test_money.py").read_text())

# %% [markdown]
# The next cell counts the bill for the three fixes. The turn counts and the reply sizes are **assumptions** written as constants, not measurements. Change them and the table changes with them. The one loop keeps one context for all three fixes. Each worker starts small, and the orchestrator reads the plan once and writes three briefs.

# %%
FIXES = ["money", "tax", "coupons"]  # the three fixes from FIX_PLAN.md that lesson 24 ran
TURNS = 3      # assumed: one turn to read, one to edit, one to rerun the tests
REPLY = 600    # assumed: characters the model writes in one turn
TOOL = 400     # assumed: characters the test output and the diff add in one turn
BRIEF = 200    # assumed: characters in the orchestrator's brief for one worker
def tok(chars): return chars // CHARS_PER_TOKEN
def one_loop():  # one context for all three fixes: every turn re-sends everything so far
    ctx, billed, out = REPO, 0, 0
    for _ in FIXES:
        for _ in range(TURNS):
            billed += tok(ctx)
            out += tok(REPLY)
            ctx += REPLY + TOOL
    return billed, out
def workers(whole_repo):  # fresh context per worker; whole_repo=True means each one reads all of pocket-cart
    billed, out = 0, 0
    for fix in FIXES:
        ctx = REPO if whole_repo else SIZE[f"pocket_cart/{fix}.py"] + SIZE[f"tests/test_{fix}.py"] + BRIEF
        for _ in range(TURNS):
            billed += tok(ctx)
            out += tok(REPLY)
            ctx += REPLY + TOOL
    return billed, out
def orchestrator():  # one call: read the plan, write one brief per fix
    return tok(SIZE["FIX_PLAN.md"]), tok(BRIEF * len(FIXES))
# %% [markdown]
# The table compares the three designs. Each row shows input, output and the total, and the last column divides by the one loop.

# %%
ROWS = {"one loop, one growing context": one_loop(),
        "3 workers, each reads the whole repo": workers(True),
        "3 workers + orchestrator, own files only": tuple(a + b for a, b in zip(workers(False), orchestrator()))}
BASE = sum(ROWS["one loop, one growing context"])
print(f"{'design':42s} {'input':>7s} {'output':>7s} {'total':>7s} {'x one loop':>10s}")
for label, (i, o) in ROWS.items():
    print(f"{label:42s} {i:7d} {o:7d} {i + o:7d} {(i + o) / BASE:10.2f}")
print(f"assumed TURNS={TURNS}, REPLY={REPLY}, TOOL={TOOL}, BRIEF={BRIEF} chars; chars/{CHARS_PER_TOKEN}. "
      "The 4x and 15x figures are Anthropic's numbers and are not reproduced here.")

# %% [markdown]
# Read the table with care. The one loop is not cheap: its input grows with every turn. The 0.28 row is the best case of these assumed numbers: each worker is handed exactly its two files, while real workers must explore to find them. So it is a lower bound, not a prediction. Its drop from 0.66 comes from reading less, not from splitting, and it includes the orchestrator's read and briefs. The repo is about 1k tokens, so only the ratios mean anything. The 0.66 row, where each worker reads the whole repo, is the fairer comparison, since the one loop also starts with the whole repo. This table does not model exploration, which is why it shows no multiplier.

# %% [markdown]
# ### Splitting creates a merge
# Each worker below gets its own worktree and branch from `main` and makes one exact edit, written by hand. No model is called here: lesson 24 showed the real proposals. Two workers change the same line of `money.py`, and the merge queue has to catch it. The tax and coupons edits touch other files.

# %%
GIT = ["git", "-c", "user.name=loop-course", "-c", "user.email=loop-course@example.com"]
def git(*args, cwd=MAIN):  # raises on error
    r = subprocess.run([*GIT, *args], cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr.strip())
    return r.stdout.strip()
shutil.copytree(SRC, MAIN, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
_ = git("init", "-q", "-b", "main")
_ = git("add", "-A")
_ = git("commit", "-q", "-m", "pocket-cart as shipped")
print("main ready, commits:", git("log", "--format=%s"))
# %% [markdown]
# The edits, one per branch. Each `old` text must appear exactly once in its file, or the branch is refused. `money` is the fix from lesson 24. `money-2` is a second, competing money edit: it changes the same line as `money`, adding a thousands separator.

# %%
EDITS = {  # name: (file, exact old text, new text)
    "money":   ("pocket_cart/money.py", 'f"${cents // 100}.{cents % 100}"', 'f"${cents // 100}.{cents % 100:02d}"'),
    "tax":     ("pocket_cart/tax.py", "return cents * rate_percent // 100", "return (cents * rate_percent + 50) // 100"),
    "coupons": ("pocket_cart/coupons.py", "return COUPONS[code]", "return COUPONS[code.strip().upper()]"),
    "money-2": ("pocket_cart/money.py", 'f"${cents // 100}.{cents % 100}"', 'f"${cents // 100:,}.{cents % 100:02d}"'),
}
def branch(name):  # one worker: its own worktree and branch from main, one exact edit, one commit
    path, old, new = EDITS[name]
    wt = WT / name
    git("worktree", "add", "-q", "-b", f"run/{name}", str(wt), "main")
    text = (wt / path).read_text()
    assert text.count(old) == 1, f"{name}: old text found {text.count(old)} times"
    (wt / path).write_text(text.replace(old, new))
    git("commit", "-q", "-am", f"{name}: fix", cwd=wt)
    return git("diff", "--numstat", "main", f"run/{name}")  # the lines a person must read
for name in EDITS:
    print(f"{name:8s} diff to read (added, removed, file):", branch(name).replace("\t", " "))

# %% [markdown]
# The merge queue lands the branches one at a time into `main`. The fourth branch edits the same line as the first, so it is the one that should fail.

# %%
def merge(name):  # the merge queue: one branch at a time, into main
    r = subprocess.run([*GIT, "merge", "-q", "--no-edit", f"run/{name}"], cwd=MAIN, capture_output=True, text=True)
    if r.returncode == 0:
        return "merged"
    files = git("diff", "--name-only", "--diff-filter=U").split()
    git("merge", "--abort")  # back to a clean main: nothing half-merged
    return f"CONFLICT in {', '.join(files)}"
for name in EDITS:
    print(f"merge run/{name:8s} {merge(name)}")
print("main status:", git("status", "--short") or "clean")

# %% [markdown]
# ## How it simplifies the architecture
# Splitting does not remove work. It moves work into several contexts, and each one can fail.
#
# | Moving part | One loop | Orchestrator and workers |
# |---|---|---|
# | Contexts | one, growing with every turn | one per worker, small and fresh |
# | Integration points | none | a brief and a result per worker, a merge queue |
# | Failure points | one loop to watch | N workers, merge conflicts, duplicate reads |
# | Human reviews | one diff of all changes | one diff per branch |
#
# ## When you don't need it, and what it does not solve
# Several agents do not remove the review ceiling, conflicts in the same lines, or steps that depend on each other. Anthropic says that "LLM agents are not yet great at coordinating and delegating to other agents in real time" (its multi-agent research post). For one fix, use one loop with a checker and caps (lessons 05 and 14). For fixed steps, use a workflow (lesson 01).

# %% [markdown]
# ## At real scale
# - **Tokens:** Anthropic reports about 4x chat tokens for one agent and about 15x for its multi-agent research system, which beat a single agent by 90.2% on its internal eval. Most coding tasks involve fewer parallelizable tasks than research. Source: https://www.anthropic.com/engineering/multi-agent-research-system → lesson 27.
# - **What breaks first:** wide fan-out hits provider rate limits. Batch it and cap it per tenant. Source: https://code.claude.com/docs/en/agent-sdk/hosting → lesson 28b.
# - **The human ceiling:** every branch is a review, and comprehension debt grows with the fleet. Source: https://addyosmani.com/blog/loop-engineering/ → lesson 26b.
# - **Durable workers:** a worker can die halfway through a branch. Its lease must lapse, and the task returns to the queue without a second merge. → lesson 26a.
#
# Go deeper: multi-agent patterns (handoffs, supervisors, debate) are in the agentic-ai course.

# %% [markdown]
# ## Decision guide
# | Situation | Recommended approach | Why |
# |---|---|---|
# | One fix, or steps that depend on each other | One loop with a checker and caps | One shared context is cheaper than handoffs, and the steps need it |
# | Many independent items in separate files (the FIX_PLAN list) | One worker per item, own worktree, merge queue | Fresh contexts, one small diff per item, parallel wall clock |
# | Many items that change the same lines | One loop, or split by file first | A merge conflict costs more than the tokens saved |
# | Broad research that no single context can hold | Orchestrator and workers, budget set first | Information exceeds one window; the value must cover about 15x tokens |
# | Review is the bottleneck | Fewer, larger, checked branches; one loop | Every extra branch is one more review |

# %% [markdown]
# ## Common misconceptions
# 1. **"More agents means faster and better."** Each agent adds tokens, a handoff and a merge. Anthropic's research system gained on breadth-first research, and its post says that "most coding tasks involve fewer truly parallelizable tasks than research".
# 2. **"Separate worktrees means no collisions."** Worktrees separate folders, not lines. The two `money` edits can each be correct on their own branch and still conflict at merge.
# 3. **"The cost is the model calls."** Review time and merge work are costs too. The table counts tokens only; a person reads every diff.
# 4. **"A worker's summary carries what it learned."** It carries what the worker chose to return. Anything else is lost to the orchestrator and to the other workers.

# %% [markdown]
# ## Check yourself
# 1. Five fixes all touch `pocket_cart/cart.py`, and fix 3 calls a function that fix 2 adds. One loop or workers? Why?
# 2. Three workers merge cleanly into `main`, and a fourth conflicts. Which step caught it, and what goes back to whom?
# 3. After you split one loop into six agents, the bill rises 4x. Name two things to read first. (A thought question: there is no single right answer; the solution names the usual suspects.)
# 4. A fix changes one file and one test, and your loop finishes it in two turns. Do you add agents? Why not?

# %% [markdown] tags=["solution"]
# 1. One loop, in order: fix 3 depends on fix 2, and all five touch one file.
# 2. The merge queue caught it. It aborted that merge, so main stays clean, and the task goes back to its worker to rebase on main and resolve the conflict.
# 3. Each new agent's re-reads (duplicate exploration), and the briefs and summaries (handoffs). Per-agent usage shows which (lesson 27).
# 4. No. One small change has no parallel work, and a second agent adds a handoff and a review.

# %% [markdown]
# ## Recap
# - **Several agents pay when** the work is independent, each piece needs its own context, and each result can be checked.
# - **The multiplier is real:** about 4x for one agent and about 15x for a multi-agent research system (Anthropic). Measure what each worker reads before you split.
# - **Splitting moves the cost:** handoffs, merges and reviews grow with the number of branches. A person still reads every diff.
# - **Remember:** *token multiplier* (the bill grows with each agent), *merge queue* (one branch lands at a time), *review bandwidth* (the human limit).
# - **People get this wrong** by assuming worktrees prevent conflicts. They prevent folder clashes, not clashes in the same lines.
#
# **Interview:** When would you not use multiple agents? Strong answer: when the steps depend on each other or share one context. Several agents multiply tokens and merge work, so they pay only for independent parallel work with a checkable result, and only while review can keep up.

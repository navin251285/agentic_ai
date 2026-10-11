# %% [markdown]
# # 15 · Inside a coding agent: gather context, act, verify
# Level L2 · Part 3 · core · ~30 min · builds on 01

# %% [markdown]
# ## Goal
# By the end you can read a real coding-agent transcript and label every step with its phase (gather context, act, verify) and its tool category, name the matching tools in Claude Code, Codex CLI and Gemini CLI, and run the same loop yourself: a real model fixes Pocket Tracker issue #7, and your harness proves the fix on the repo.

# %% [markdown]
# ## The idea
# A **coding agent** is the agent loop from lesson 01 pointed at a code repository. Claude Code's docs name its three phases: **gather context** (search and read code), **take action** (edit files), **verify results** (run tests or the program). The phases blend and repeat until the task is done.
#
# The model only reasons. The **agentic harness** is everything around it: the tools it may call, the context it sees, the limits, the transcript. Products differ mostly in their harness, and their tools fall into the same few **tool categories**: search, file operations, execution, web and code intelligence.
#
# Analogy: a plumber called to a leak. Look around and find the pipe (gather), replace the washer (act), turn the water on and watch (verify).

# %% [markdown]
# ## Picture
# ```mermaid
# flowchart LR
#   T[Task: issue #7] --> G["gather context<br/>Search + File ops (read)"]
#   G --> A["act<br/>File ops (edit)"]
#   A --> V["verify<br/>Execution (tests)"]
#   V -->|not done| G
#   V -->|done| H{"harness check<br/>on the repo"}
# ```

# %% [markdown]
# ## Already know this?
# Part 3 (lessons 15–21) builds the parts of a coding agent. If you can answer these, skip to **lesson 22**:
# 1. What are the three phases of a coding agent's loop, and which tool category serves each?
# 2. Why does an agent grep and then view a window of lines instead of reading whole files?
# 3. An exact-string edit fails because the text appears twice. What should the agent do next?
# 4. The test suite is green but the bug is still there. What kind of test is missing?
# 5. Which `docker run` flags stop an agent's shell command from reaching the network or the host's files?

# %% [markdown]
# ## Step by step
#
# ### 1. A scratch repo and the task
# Same start as lesson 06: copy Pocket Tracker to `../work/15/`, make it a git repo with one fixed commit. The task is issue #7, which you reproduced by hand in lesson 06.

# %%
import json, os, shutil, subprocess, sys
from pathlib import Path
sys.path.insert(0, "..")    # course helpers: llm_setup, llm_replay

GIT_DATES = {**os.environ, "GIT_AUTHOR_DATE": "2026-10-01T09:00:00+00:00",
             "GIT_COMMITTER_DATE": "2026-10-01T09:00:00+00:00"}

def run(*cmd, cwd):
    out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=GIT_DATES, timeout=120)
    return (out.stdout + out.stderr).strip()

def fresh_repo(dest):
    """Copy Pocket Tracker to dest and commit it, so every change shows in git diff."""
    shutil.rmtree(dest, ignore_errors=True)
    shutil.copytree("../apps/pocket_tracker", dest, ignore=shutil.ignore_patterns("*.db", "__pycache__", ".pytest_cache"))
    run("git", "init", "-q", "-b", "main", cwd=dest)
    run("git", "add", "-A", cwd=dest)
    run("git", "-c", "user.name=Pocket Dev", "-c", "user.email=dev@pocket-tracker.test",
        "commit", "-q", "-m", "Pocket Tracker 0.1.0", cwd=dest)
    return dest

REPO = fresh_repo(Path("../work/15/pocket_tracker"))
issue_7 = json.loads((REPO / "issues.json").read_text())[6]
print(run("git", "log", "--oneline", cwd=REPO))
print(f"#{issue_7['id']} {issue_7['title']}\n{issue_7['body']}")

# %% [markdown]
# ### 2. Write the harness check first
# Before any agent runs, decide what "fixed" means. `check_issue_7` runs the issue's steps in a separate Python process inside the repo: close issue #2 on a fresh database through FastAPI's `TestClient`, then read its label. It also runs the repo's pytest suite, so a fix must not break anything.

# %%
REPRO = """
import os, tempfile
os.environ["POCKET_TRACKER_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
from fastapi.testclient import TestClient
from app import app
with TestClient(app) as c:
    c.post("/issues/2/close")
    issue = c.get("/api/issues/2").json()
print(issue["status"], repr(issue["label"]))
"""

def run_tests(repo):
    return run(sys.executable, "-m", "pytest", "-q", "--color=no", "-p", "no:cacheprovider", cwd=repo).splitlines()[-1]

def check_issue_7(repo):
    problems = []
    seen = run(sys.executable, "-c", REPRO, cwd=repo)
    if seen != "closed 'bug'":
        problems.append(f"after closing #2 the app shows {seen!r}, expected \"closed 'bug'\"")
    summary = run_tests(repo)
    if "failed" in summary or "error" in summary:
        problems.append("the pytest suite fails")
    return problems

print("pytest:", run_tests(REPO))
print("problems:", check_issue_7(REPO))

# %% [markdown]
# The suite is green, yet the check finds the bug: the label is empty after closing. Keep that in mind for step 9.
#
# ### 3. A real transcript: Claude Code fixes issue #7
# Claude Code writes every message, tool call and result to a JSONL file under `~/.claude/projects/`. This lesson was written by Claude Code, and while writing it, it fixed issue #7 on a scratch copy. The four tool calls of that fix were cut from the session file into `../data/recorded/15_claude_code.json` (recorded output, paths shortened).

# %%
cc = json.loads(Path("../data/recorded/15_claude_code.json").read_text())
print(cc["harness"], cc["version"])
for n, step in enumerate(cc["steps"], 1):
    args = step["input"].get("command") or step["input"].get("file_path")
    print(f"{n}. {step['name']:5} {str(args)[:90]!r}")
    print("   ->", str(step["result"]).splitlines()[0][:90])

# %% [markdown]
# Read it as the loop: a `Bash` call running `grep` for "label", a `Read` of 30 lines of `db.py`, an `Edit` that swaps one exact block of text, and a `Bash` call that reproduces the issue and runs the suite. The `grep -v "^.*#"` filter in step 1 is Claude's own odd choice, kept as recorded; it drops lines containing `#`. Here is the edit itself, the whole fix:

# %%
edit = cc["steps"][2]["input"]
print("--- old\n" + edit["old_string"] + "\n--- new\n" + edit["new_string"])
print("\nverify ->", cc["steps"][3]["result"].replace("\n", " | "))

# %% [markdown]
# ### 4. Phases and tool categories
# Claude Code's docs group its built-in tools into five categories, plus an orchestration group (plans, subagents, questions). Note one detail from its tools reference: on Linux and macOS, `Glob` and `Grep` are left out by default and Claude searches with `grep` and `find` through `Bash`. So a step's category comes from what it does, not just the tool's name.

# %%
def label(step):
    """Phase and category of one Claude Code tool call (our own labelling)."""
    if step["name"] == "Read":
        return "gather", "File operations"
    if step["name"] in ("Edit", "Write"):
        return "act", "File operations"
    if step["name"] == "Bash" and "grep" in step["input"]["command"]:
        return "gather", "Search (through Bash)"
    return "verify", "Execution"

for n, step in enumerate(cc["steps"], 1):
    phase, category = label(step)
    print(f"{n}. {phase:7} {category:24} {step['name']}")

# %% [markdown]
# ### 5. The same categories in three products
# Recording Codex CLI and Gemini CLI on this machine was not possible (no OpenAI key; running Gemini CLI unattended was refused by this machine's permission policy), so for them we use their documented tool lists, checked on 2026-10-11 (sources in `RESEARCH.md`). Every product covers the same categories with different tools. (Google is replacing Gemini CLI with Antigravity CLI for unpaid and Google One users since 2026-06-18; the tool ideas carry over.)

# %%
TOOLS = {   # category -> tool names, from each product's docs or source
    "Search":            {"Claude Code": "Glob, Grep (Linux: grep/find via Bash)",
                          "Codex CLI": "rg via exec_command", "Gemini CLI": "glob, grep_search"},
    "File operations":   {"Claude Code": "Read, Edit, Write", "Codex CLI": "apply_patch (read via shell)",
                          "Gemini CLI": "read_file, replace, write_file"},
    "Execution":         {"Claude Code": "Bash", "Codex CLI": "exec_command, write_stdin",
                          "Gemini CLI": "run_shell_command"},
    "Web":               {"Claude Code": "WebFetch, WebSearch", "Codex CLI": "web_search (hosted)",
                          "Gemini CLI": "web_fetch, google_web_search"},
    "Code intelligence": {"Claude Code": "LSP (plugin)", "Codex CLI": "-", "Gemini CLI": "-"},
    "Orchestration":     {"Claude Code": "Agent, AskUserQuestion, TaskCreate",
                          "Codex CLI": "update_plan, request_user_input", "Gemini CLI": "write_todos, ask_user"},
}
print(f"{'category':18} {'Claude Code':40} {'Codex CLI':32} Gemini CLI")
for cat, row in TOOLS.items():
    print(f"{cat:18} {row['Claude Code']:40} {row['Codex CLI']:32} {row['Gemini CLI']}")

# %% [markdown]
# Codex's tool list has no file-read or code-search tool: it reads and searches through the shell and edits with `apply_patch`. Gemini CLI has a separate tool for nearly every action. The loop is the same; the harness designer chose the tools. Lessons 16 and 17 build our own search and edit tools.
#
# ### 6. Our own harness: four tools
# Now build the smallest harness with one tool per job: `search_code` (Search), `read_file` and `edit_file` (File operations) and `run_tests` (Execution). Every path is checked to stay inside the repo, and errors come back as text the model can read.

# %%
from langchain_core.tools import tool

def inside(path):
    p = (REPO / path).resolve()
    if not p.is_relative_to(REPO.resolve()) or not p.is_file():
        raise ValueError(f"no file {path!r} in the repo")
    return p

@tool
def search_code(pattern: str) -> str:
    """Search tracked files for a regular expression (git grep -n -E). Returns file:line:text lines."""
    return "\n".join(run("git", "grep", "-n", "-E", pattern, cwd=REPO).splitlines()[:30]) or "no matches"

@tool
def read_file(path: str, start: int = 1, end: int = 200) -> str:
    """Show lines start..end of a repo file, with line numbers."""
    try:
        lines = inside(path).read_text().splitlines()
    except ValueError as e:
        return f"ERROR: {e}"
    return "\n".join(f"{i:4}  {lines[i - 1]}" for i in range(max(start, 1), min(end, len(lines)) + 1))

# %% [markdown]
# The two tools that change and check the repo. `edit_file` refuses unless `old_text` appears exactly once, the same rule as Claude Code's `Edit` and Gemini CLI's `replace`.

# %%
@tool
def edit_file(path: str, old_text: str, new_text: str) -> str:
    """Replace old_text (must appear exactly once in the file) with new_text."""
    try:
        p = inside(path)
    except ValueError as e:
        return f"ERROR: {e}"
    text = p.read_text()
    if text.count(old_text) != 1:
        return f"ERROR: old_text appears {text.count(old_text)} times in {path}; it must appear exactly once"
    p.write_text(text.replace(old_text, new_text))
    return f"OK: edited {path}"

@tool("run_tests")
def run_tests_tool() -> str:
    """Run the repo's pytest suite and return the summary line."""
    return run_tests(REPO)

tools = {t.name: t for t in [search_code, read_file, edit_file, run_tests_tool]}
PHASE = {"search_code": "gather", "read_file": "gather", "edit_file": "act", "run_tests": "verify"}
print(search_code.invoke({"pattern": "def update_issue"}))

# %% [markdown]
# ### 7. The model
# Same setup as lesson 01: `get_llm` shows the providers, which keys are set and which models have a recording for this lesson. The agent run below makes at most 2 model calls; `max_calls=4` is the lesson's ceiling.

# %% tags=["needs-llm"]
agent_messages = None     # filled by the agent-loop cell (stays None if it is skipped)
from llm_setup import get_llm
llm = get_llm("15_coding_agent_anatomy", max_calls=4)

# %% [markdown]
# ### 8. Run the loop on issue #7
# The prompt gives the issue, the file list and a one-line map of the code (the kind of note an instruction file holds, lesson 20). It asks for the phases in two responses: gather (search and read together), then act and verify (edit, then run the tests). Batching tool calls per response keeps it to 2 model calls; small models otherwise make one call per response and need more turns. The harness runs each call in order and prints its phase.

# %% tags=["needs-llm"]
from langchain_core.messages import HumanMessage, ToolMessage

files = run("git", "ls-files", cwd=REPO).replace("\n", ", ")
agent = llm.bind_tools(list(tools.values()))
agent_messages = [HumanMessage(
    f"You are a coding agent working in the Pocket Tracker repo. Files: {files}.\n"
    f"Fix issue #{issue_7['id']}: {issue_7['title']}\n{issue_7['body']}\n"
    "Layout: app.py has the routes, db.py has all the SQL.\n"
    "Work in exactly two responses. Response 1 (gather context): make TWO tool calls in this one response: "
    "search_code for the route that closes an issue, and read_file on db.py. "
    "Response 2 (act and verify): make TWO tool calls in that one response: edit_file with a minimal fix, "
    "then run_tests.")]
for model_call in range(1, 3):                       # cap: at most 2 model calls
    reply = agent.invoke(agent_messages)
    agent_messages.append(reply)
    if not reply.tool_calls:
        break
    for call in reply.tool_calls:
        result = tools[call["name"]].invoke(call["args"])
        print(f"[call {model_call}] {PHASE[call['name']]:6} {call['name']}({str(call['args'])[:70]})")
        print("    ->", result.splitlines()[0][:90] if result else "")
        agent_messages.append(ToolMessage(result, tool_call_id=call["id"]))

# %% [markdown]
# If the model cell was skipped, this cell runs the same four steps by hand (a hand-written example, not model output), so the rest of the lesson still works.

# %%
if not globals().get("agent_messages"):
    agent_messages = None
    for name, args in [("search_code", {"pattern": "def update_issue"}),
                       ("read_file", {"path": "db.py", "start": 99, "end": 104}),
                       ("edit_file", {"path": "db.py", "old_text": 'status=None, label=""', "new_text": "status=None, label=None"}),
                       ("edit_file", {"path": "db.py", "old_text": "label = ? WHERE", "new_text": "label = COALESCE(?, label) WHERE"}),
                       ("run_tests", {})]:
        print(f"fallback {PHASE[name]:6} {name} -> {tools[name].invoke(args).splitlines()[0][:80]}")
print("tool calls run:", sum(isinstance(m, ToolMessage) for m in agent_messages or []) or "fallback")

# %% [markdown]
# ### 9. Verify on the repo, not on the reply
# The agent's own verify step was the test suite, which was green before the fix too. The harness runs its own check from step 2 and shows the diff the agent left behind.

# %%
print(run("git", "diff", "--stat", cwd=REPO))
print("\n".join(ln for ln in run("git", "diff", "-U0", cwd=REPO).splitlines()
                if ln[:1] in "+-" and ln[:3] not in ("+++", "---")))
print("problems:", check_issue_7(REPO) or "none, issue #7 is fixed")

# %% [markdown]
# ### 10. Compare the two runs
# Put our run next to Claude Code's: the same phases in the same order, with different tool names.

# %%
ours = [(PHASE[c["name"]], c["name"]) for m in (agent_messages or []) for c in getattr(m, "tool_calls", [])]
theirs = [(label(s)[0], s["name"]) for s in cc["steps"]]
print("Claude Code:", " -> ".join(f"{p}:{n}" for p, n in theirs))
print("our harness:", " -> ".join(f"{p}:{n}" for p, n in ours) or "n/a (fallback run)")

# %% [markdown]
# ## At work
# - Claude Code saves every message, tool call and result as JSONL under `~/.claude/projects/`; teams keep such transcripts to audit and debug runs → lesson 44a.
# - The harness, not the model, picks the tools: Claude Code on Linux searches through `Bash`, Codex reads with the shell and edits with `apply_patch`, and bash-only agents keep a single tool → lessons 16, 17 and 23.
# - The verify phase is only as good as its tests. Agents judged by weak tests can learn to edit the tests or special-case the input, known as reward hacking (`RESEARCH.md` section 3, Verification) → lessons 18 and 40.
# - These agents run commands with your rights. Products gate them with permission modes (Claude: Auto, Manual, Accept edits, Plan) and sandboxes (Codex `sandbox_mode`: `read-only`, `workspace-write`) → lessons 19 and 35.

# %% [markdown]
# ## What just happened
# - A **coding agent** is the lesson 01 loop on a repo: gather context, act, verify, repeated until done.
# - A real Claude Code transcript showed the loop in four tool calls: grep through `Bash`, `Read`, `Edit`, then `Bash` to reproduce and test.
# - The **tool categories** (search, file operations, execution, web, code intelligence) appear in Claude Code, Codex CLI and Gemini CLI under different names; the **agentic harness** decides which tools exist.
# - Our own four-tool harness let a real model run the same phases on issue #7, in 2 model calls.
# - The harness check reproduced the issue on the repo; the test suite alone could not tell fixed from broken.

# %% [markdown]
# ## Common mistakes
# Taking "tests pass" as "fixed". The suite has no test for issue #7, so it is green on a repo that still has the bug. An agent (or a harness) that stops at green tests reports success here:

# %% tags=["raises-exception"]
unfixed = fresh_repo(Path("../work/15/unfixed"))
print("pytest on the unfixed repo:", run_tests(unfixed))
assert not check_issue_7(unfixed), check_issue_7(unfixed)

# %% [markdown]
# Fix: verify against the issue itself. Reproduce its steps (as `check_issue_7` does), and later turn them into a test that fails before the fix and passes after (lesson 18).

# %%
print("fixed repo:", check_issue_7(REPO) or "verified by reproducing the issue")

# %% [markdown]
# Two more: letting tools reach paths outside the repo (our `inside()` guard stops `../apps/...`), and reading only the model's final message instead of its tool calls and the diff.

# %% [markdown]
# ## Try it
# Translate the Claude Code transcript into the other two products. Write `translate(step, product)` that returns the tool name Codex CLI or Gemini CLI would most likely use for each of the four steps (use the table from step 5: for example, a grep step becomes `exec_command` with `rg` in Codex and `grep_search` in Gemini CLI). Print one row per step with the phase and the three tool names. No model needed.

# %%
# your code here

# %% [markdown]
# ## Key terms
# - **coding agent** — an agent that searches, edits and tests a code repository in a loop of gather context, act and verify.
# - **agentic harness** — the layer around the model that provides its tools, manages the context it sees, runs the loop and keeps the transcript.
# - **tool categories** — the groups a coding agent's tools fall into: search, file operations, execution, web, code intelligence (plus orchestration such as subagents and plans).
# - **gather context / act / verify** — the three phases of a coding agent's loop: find and read the relevant code, change it, check the change by running tests or the program.
# - **transcript** — the saved record of a run: every message, tool call and tool result in order (Claude Code: JSONL under `~/.claude/projects/`).

# %%
import llm_replay
llm_replay.stop()

# %% [markdown]
# # 16 · Repo search tools: glob, grep and windowed viewing
# Level L2 · Part 3 · core · ~30 min · builds on 06, 15

# %% [markdown]
# ## Goal
# By the end you can write three search tools for a coding agent (`find_files`, `grep_code`, `view_file`) whose output always fits a model's context, and measure how many tokens a real model uses to find the label-reset bug (issue #7) with them, compared with pasting the whole repo into the prompt.

# %% [markdown]
# ## The idea
# In lesson 15 the agent's gather phase used one search tool and read 200 lines at a time. Real repos are bigger: thousands of files, generated data, minified bundles with 300,000 characters on one line. Pasting all of it costs tokens on every call, and often does not fit at all.
#
# So coding agents search first and read a little. **Glob** finds files by path pattern, **grep** finds lines by content, and a **windowed file view** shows a numbered slice of one file. Each tool **truncates its output** and says what it left out, so the model can narrow the search instead of drowning in it.
#
# Analogy: in a library you check the catalogue (glob), look up the index at the back (grep), then read two pages (window). You do not photocopy the whole library.

# %% [markdown]
# ## Picture
# ```mermaid
# flowchart LR
#   Q[Issue #7] --> G["find_files<br/>'**/*.py'"]
#   G --> R["grep_code<br/>'label' in *.py"]
#   R -->|too many hits: narrow| R
#   R --> V["view_file<br/>db.py lines 95-110"]
#   V --> A[ANSWER: file:line]
#   D["dump every file"] -.->|many more tokens| A
# ```

# %% [markdown]
# ## Step by step
#
# ### 1. A scratch repo, as in lesson 15
# Copy Pocket Tracker (lesson 06) to `../work/16/`, commit it, and load issue #7. We count tokens with `tiktoken` and the `o200k_base` encoding, as in lesson 02, from the copy shipped in `../data/tiktoken_cache`.

# %%
import json, os, re, shutil, subprocess, sys
from pathlib import Path
sys.path.insert(0, "..")    # course helpers: llm_setup, llm_replay
os.environ["TIKTOKEN_CACHE_DIR"] = str(Path("../data/tiktoken_cache"))
import tiktoken

enc = tiktoken.get_encoding("o200k_base")
def tokens(text):
    return len(enc.encode(text))

GIT_DATES = {**os.environ, "GIT_AUTHOR_DATE": "2026-10-01T09:00:00+00:00",
             "GIT_COMMITTER_DATE": "2026-10-01T09:00:00+00:00"}

def run(*cmd, cwd):
    out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=GIT_DATES, timeout=120)
    return (out.stdout + out.stderr).strip()

def commit(repo, message):
    run("git", "add", "-A", cwd=repo)
    run("git", "-c", "user.name=Pocket Dev", "-c", "user.email=dev@pocket-tracker.test",
        "commit", "-q", "-m", message, cwd=repo)

print("tokens in 'Closing an issue resets its label':", tokens("Closing an issue resets its label"))

# %% [markdown]
# `fresh_repo` is lesson 15's helper, split so `commit` can be reused in the next step.

# %%
def fresh_repo(dest):
    """Copy Pocket Tracker to dest and commit it, so every change shows in git diff."""
    shutil.rmtree(dest, ignore_errors=True)
    shutil.copytree("../apps/pocket_tracker", dest, ignore=shutil.ignore_patterns("*.db", "__pycache__", ".pytest_cache"))
    run("git", "init", "-q", "-b", "main", cwd=dest)
    commit(dest, "Pocket Tracker 0.1.0")
    return dest

REPO = fresh_repo(Path("../work/16/pocket_tracker"))
issue_7 = json.loads((REPO / "issues.json").read_text())[6]
print(f"#{issue_7['id']} {issue_7['title']}\n{issue_7['body']}")

# %% [markdown]
# ### 2. Grow the repo like a real one
# Real repos carry data the agent should not read: fixtures, exports, minified files. Add one: an export of 2,000 issues from an "old tracker", written as minified JSON, so the whole file is a single line. It mentions `label` 2,000 times.

# %%
export = [{"id": n, "title": f"Imported issue {n}", "body": f"Moved from the old tracker, ticket OLD-{n}.",
           "label": ["bug", "docs", "feature"][n % 3], "status": "closed" if n % 4 == 0 else "open"}
          for n in range(1, 2001)]
(REPO / "fixtures").mkdir()
(REPO / "fixtures" / "issues_export.json").write_text(json.dumps(export, separators=(",", ":")) + "\n")
commit(REPO, "Add issue export fixture")

TRACKED = run("git", "ls-files", cwd=REPO).splitlines()
big = (REPO / "fixtures" / "issues_export.json").read_text()
print(len(TRACKED), "tracked files")
print(f"export: {len(big.splitlines())} line, {len(big):,} characters")

# %% [markdown]
# ### 3. The baseline: dump every file
# The simplest "context gathering" is no search at all: paste every tracked file into the prompt with a header. Count what that costs.

# %%
def dump_repo(repo, files):
    return "\n".join(f"===== {f} =====\n{(repo / f).read_text()}" for f in files)

dump = dump_repo(REPO, TRACKED)
per_file = sorted(((tokens((REPO / f).read_text()), f) for f in TRACKED), reverse=True)
for n, f in per_file[:4]:
    print(f"{n:7,} tokens  {f}")
print(f"{tokens(dump):7,} tokens  whole dump ({len(TRACKED)} files)")
print(f"{tokens(dump_repo(REPO, [f for f in TRACKED if 'fixtures' not in f])):7,} tokens  dump without the export")

# %% [markdown]
# The code itself is a few thousand tokens; the one data file is over 90% of the dump. And the agent pays for it on **every** model call, because each call resends the conversation.
#
# ### 4. Glob: find files by path
# `find_files` matches a glob pattern with `Path.glob` (`**` means any depth) and keeps only files git tracks, so `.git/`, caches and databases never show up. It returns paths only and caps the list. Claude Code's `Glob` does the same: capped at 100 files, with a truncation flag when the cap is hit.

# %%
from langchain_core.tools import tool

MAX_FILES = 50

def matching_files(pattern):
    """All tracked files whose repo path matches the glob pattern, sorted."""
    return sorted(p.relative_to(REPO).as_posix() for p in REPO.glob(pattern)
                  if p.relative_to(REPO).as_posix() in TRACKED)

@tool
def find_files(pattern: str) -> str:
    """Find repo files by path glob, e.g. '**/*.py' (any depth) or 'templates/*.html'. Returns paths."""
    paths = matching_files(pattern)
    if not paths:
        return f"no files match {pattern!r}"
    more = len(paths) - MAX_FILES
    return "\n".join(paths[:MAX_FILES]) + (f"\n[{more} more files not shown; narrow the pattern]" if more > 0 else "")

print(find_files.invoke({"pattern": "**/*.py"}))
print(find_files.invoke({"pattern": "*.md"}))

# %% [markdown]
# ### 5. Grep without limits floods the context
# Lesson 15's `search_code` used `git grep` and kept the first 30 lines. Lines, not characters: one matching line can be huge. Search the grown repo for `label` the plain way and measure the output.

# %%
naive = run("git", "grep", "-n", "label", cwd=REPO)
print(f"{len(naive.splitlines())} matching lines, {len(naive):,} characters, {tokens(naive):,} tokens")
longest = max(naive.splitlines(), key=len)
print("longest line starts:", longest[:90])

# %% [markdown]
# One "line" is the whole export, so a single search result costs about as much as the dump. Output truncation has to cut **characters per line** and **lines per result**, and say what it cut.
#
# ### 6. Grep with limits
# `grep_code` searches file contents with a Python regular expression, inside the files a glob selects. Each hit is `path:line: text`, long lines are clipped with a note of how much was cut, and after 20 hits it reports how many more there are. A bad regex comes back as a readable error. The next cell only defines the tool, so it prints nothing; the cell after it runs it.

# %%
MAX_MATCHES, MAX_LINE = 20, 160

def clip(line, limit=MAX_LINE):
    return line if len(line) <= limit else f"{line[:limit]} ...[+{len(line) - limit:,} chars]"

@tool
def grep_code(pattern: str, glob: str = "**/*") -> str:
    """Search file contents with a Python regex. Returns 'path:line: text' hits (long lines are cut).
    Use glob to search only some files, e.g. '**/*.py'."""
    try:
        rx = re.compile(pattern)
    except re.error as e:
        return f"ERROR: bad regex {pattern!r}: {e}. Escape special characters, e.g. \\( for ("
    hits = [f"{path}:{n}: {clip(line.strip())}"
            for path in matching_files(glob)
            for n, line in enumerate((REPO / path).read_text(errors="replace").splitlines(), 1)
            if rx.search(line)]
    if not hits:
        return f"no matches for {pattern!r} in {glob!r}"
    more = len(hits) - MAX_MATCHES
    return "\n".join(hits[:MAX_MATCHES]) + (f"\n[{more} more matches not shown; narrow the pattern or glob]" if more > 0 else "")

# %% [markdown]
# Run the same search over every file, then only over Python files.

# %%
everywhere = grep_code.invoke({"pattern": "label"})
print(f"all files: {tokens(everywhere)} tokens, vs {tokens(naive):,} for git grep. The export hit alone:")
print(grep_code.invoke({"pattern": "label", "glob": "fixtures/*"}))
in_python = grep_code.invoke({"pattern": "label", "glob": "**/*.py"})
print(f"\n*.py only: {tokens(in_python)} tokens; last two lines:")
print("\n".join(in_python.splitlines()[-2:]))

# %% [markdown]
# The export now costs one clipped line. But `label` is too common: 35 hits in Python files (20 shown plus "15 more"), and the cap stops at hit 20, before the interesting part of `db.py`. The note says so, so narrow the pattern. Closing an issue calls a database function; search for that function by name.

# %%
print(grep_code.invoke({"pattern": "update_issue", "glob": "**/*.py"}))

# %% [markdown]
# Four short hits. The close route (`app.py:79`) calls `update_issue` with a status and no label; the function is defined at `db.py:99`.
#
# ### 7. A windowed file view
# Now read just those lines. `view_file` shows a numbered window (default 40 lines, at most 100, the size the SWE-agent authors found works best), with a header saying where you are and a footer saying how to read on.

# %%
WINDOW_MAX = 100

@tool
def view_file(path: str, start: int = 1, lines: int = 40) -> str:
    """Show `lines` lines (max 100) of a repo file from line `start`, with line numbers."""
    if path not in TRACKED:
        return f"ERROR: no file {path!r}; use find_files to list files"
    text = (REPO / path).read_text(errors="replace").splitlines()
    start = max(1, min(start, len(text)))
    end = min(len(text), start + min(lines, WINDOW_MAX) - 1)
    body = "\n".join(f"{n:4}  {clip(text[n - 1])}" for n in range(start, end + 1))
    below = len(text) - end
    footer = f"\n[{below} more lines below; view_file(path, start={end + 1})]" if below else ""
    return f"[{path}: lines {start}-{end} of {len(text)}]\n{body}{footer}"

print(view_file.invoke({"path": "db.py", "start": 97, "lines": 10}))

# %% [markdown]
# There is the bug: `update_issue` defaults `label` to `""`, and the SQL writes `label = ?` on every update, so closing an issue (which passes no label) wipes it. Viewing the export shows why clipping lives in `view_file` too:

# %%
print(view_file.invoke({"path": "fixtures/issues_export.json"}))

# %% [markdown]
# ### 8. The search path by hand, in tokens
# Before giving these tools to a model, walk the path yourself and add up every tool result. This is what the model would read, compared with the dump.

# %%
hand_path = [("find_files", {"pattern": "**/*.py"}),
             ("grep_code", {"pattern": "label", "glob": "**/*.py"}),
             ("grep_code", {"pattern": "update_issue", "glob": "**/*.py"}),
             ("view_file", {"path": "db.py", "start": 97, "lines": 10})]
tools = {t.name: t for t in [find_files, grep_code, view_file]}
dump_reply, agent_messages, agent_usage, agent_answer = None, None, [], ""   # filled by the model cells later, if they run
spent = 0
for name, args in hand_path:
    n = tokens(tools[name].invoke(args))
    spent += n
    print(f"{n:5} tokens  {name}({args})")
print(f"{spent:5} tokens  search path total  vs  {tokens(dump):,} for the dump")

# %% [markdown]
# ### 9. The model
# Same setup as lessons 01 and 15: `get_llm` lists the providers, which keys are set and which models have a recording for this lesson. This lesson makes at most 4 model calls: 1 for the dump, up to 3 for the search agent.

# %% tags=["needs-llm"]
from llm_setup import get_llm
llm = get_llm("16_repo_search_tools", max_calls=4)

# %% [markdown]
# ### 10. Real run 1: the whole repo in the prompt
# One call: the dump plus the issue. The reply's `usage_metadata` holds the provider's own token count, which is what you are billed for.

# %% tags=["needs-llm"]
QUESTION = (f"Issue #{issue_7['id']}: {issue_7['title']}\n{issue_7['body']}\n"
            "Find the line of code that causes this bug. Do not fix it. "
            "End with one line: ANSWER: <file>:<line> - <short reason>")
dump_reply = llm.invoke(f"Here is every file in the Pocket Tracker repo.\n{dump}\n\n{QUESTION}")
print(dump_reply.text.strip()[-300:])
print("input tokens (provider count):", dump_reply.usage_metadata["input_tokens"])

# %% [markdown]
# ### 11. Real run 2: the search agent
# Same question, no files in the prompt, three search tools plus a fourth, `report_bug`, that the agent calls to give its answer (SWE-agent's `submit` and OpenHands' `finish` are the same idea). Small models like to answer with a tool call anyway, and the harness gets the file and line as clean arguments. The printed schema below is exactly what the model receives for `report_bug`.

# %% tags=["needs-llm"]
@tool
def report_bug(path: str, line: int, reason: str) -> str:
    """Report the file and line that cause the bug, with a one-sentence reason. Call this once, at the end."""
    return "reported"

print(report_bug.args)

# %% [markdown]
# The loop from lesson 15, capped at 3 model calls (search, view, forced answer), within the lesson budget of 4. As in lesson 15, the prompt prescribes the rounds, so the recording stays within budget, and asks for several tool calls per response. If the agent has not reported after two rounds, the third call forces it with `tool_choice="report_bug"`. (Forbidding tools with `tool_choice="none"` was ignored by `gemini-3.1-flash-lite` when this lesson was recorded: it still returned a tool call.)

# %% tags=["needs-llm"]
from langchain_core.messages import HumanMessage, ToolMessage

agent_tools = {**tools, "report_bug": report_bug}
agent = llm.bind_tools(list(agent_tools.values()))
must_report = llm.bind_tools(list(agent_tools.values()), tool_choice="report_bug")
agent_messages = [HumanMessage(
    "You are a coding agent in the Pocket Tracker repo (a FastAPI + SQLite app). "
    "Do not read whole files: locate code with find_files and grep_code, then view_file a small window.\n"
    "Response 1: call find_files and grep_code together in this one response.\n"
    "Response 2: call grep_code and/or view_file together to read the suspicious code.\n"
    "Then call report_bug.\n" + QUESTION)]
for model_call in (1, 2, 3):                         # cap: at most 3 model calls
    reply = (agent if model_call < 3 else must_report).invoke(agent_messages)
    agent_messages.append(reply)
    agent_usage.append(reply.usage_metadata["input_tokens"])
    for call in reply.tool_calls:
        result = agent_tools[call["name"]].invoke(call["args"])
        print(f"[call {model_call}] {call['name']}({call['args']}) -> {tokens(result)} tokens")
        agent_messages.append(ToolMessage(result, tool_call_id=call["id"]))
    report = next((c["args"] for c in reply.tool_calls if c["name"] == "report_bug"), None)
    if report or not reply.tool_calls:
        break
agent_answer = f"ANSWER: {report['path']}:{report['line']} - {report['reason']}" if report else reply.text
print(agent_answer)

# %% [markdown]
# If the model cells were skipped, this cell runs the hand path from step 8 instead (a hand-written example, not model output), so the comparison below still has numbers.

# %%
if not agent_messages:
    for name, args in hand_path:
        print(f"fallback {name}({args}) -> {tokens(tools[name].invoke(args))} tokens")
print("model calls made by the agent:", len(agent_usage) or "none (fallback)")

# %% [markdown]
# ### 12. Compare the two runs
# Check each ANSWER line against the two places where the bug lives: the close route that calls `update_issue` without a label (`app.py` 76-79) and `update_issue` itself (`db.py` 99-104). Then put the token counts side by side. "Provider count" is the model's own `input_tokens`, summed over calls for the agent.

# %%
BUG_LINES = {"app.py": range(76, 80), "db.py": range(99, 105)}   # close route; update_issue

def located(text):
    m = re.search(r"ANSWER: (\S+):(\d+)", text or "")
    return bool(m) and int(m.group(2)) in BUG_LINES.get(m.group(1), [])

print(f"{'run':8} {'right line':10} {'provider tokens':>16}   tiktoken estimate")
print(f"{'dump':8} {(str(located(dump_reply.text)) if dump_reply else 'n/a'):10} "
      f"{(dump_reply.usage_metadata['input_tokens'] if dump_reply else 'n/a'):>16}   {tokens(dump):,}")
print(f"{'search':8} {(str(located(agent_answer)) if agent_usage else 'n/a'):10} {(sum(agent_usage) or 'n/a'):>16}   {spent} (hand path, tool results only)")

# %% [markdown]
# Read the recorded run (your numbers differ if you use another model). With the dump, the model's explanation was right but its ANSWER pointed at `app.py:73`, a line in another route. A dump has no line numbers, which is the likely reason it cited a line in another route; one run cannot prove it. The search agent cited `app.py:79`, the close route's call, which it had seen with its number in `view_file`'s output.
#
# And the cost: the search agent used about 3% of the dump's input tokens, even though every call resent its history. On a real repo the gap grows with every file, and past the context window a dump is not an option at all.

# %% [markdown]
# ## At work
# - Claude Code caps every search and read tool: `Glob` returns at most 100 files with a truncation flag, `Grep` (built on ripgrep) returns only file paths by default (`files_with_matches`), and `Read` returns at most 25,000 tokens per call, else a `PARTIAL view` notice telling the model to page with `offset`/`limit` → lesson 22.
# - Large shell output is cut too: Claude Code reads back 30,000 characters of `Bash` output by default and hands bigger results over as a file path plus a 2,000-character preview → lesson 22.
# - `.gitignore` decides what a search sees: Claude's `Grep` skips ignored files, its `Glob` does not by default. Ours searches only git-tracked files.
# - Tool-output flooding is a main cause of long runs going wrong: every big result is resent on each later call and pushes useful context out → lessons 29 and 32a.

# %% [markdown]
# ## What just happened
# - You built a **glob** tool (`find_files`), a **grep** tool (`grep_code`) and a **windowed file view** (`view_file`), each searching only git-tracked files.
# - Every tool applies **output truncation**: per-line clipping, a cap on results or lines, and a note saying what was cut and how to get more.
# - One minified line made a plain `git grep` cost as much as dumping the whole repo; clipping fixed it.
# - A real model explained issue #7 from a dump of the whole repo but cited a wrong line (`app.py:73`) in this run; with the three tools plus `report_bug` it cited `app.py:79` using about 3% of the input tokens (3,009 vs 89,594, provider count).

# %% [markdown]
# ## Common mistakes
# Letting a tool crash on the model's input. Models often pass regex metacharacters unescaped, for example searching for the call `update_issue(`. A grep tool that compiles the pattern without a guard raises, and the exception kills the agent loop instead of teaching the model:

# %% tags=["raises-exception"]
def grep_unguarded(pattern, glob="**/*.py"):
    rx = re.compile(pattern)
    return [f"{p}:{n}" for p in matching_files(glob)
            for n, line in enumerate((REPO / p).read_text().splitlines(), 1) if rx.search(line)]

grep_unguarded("update_issue(")

# %% [markdown]
# Fix: catch the error and return it as text the model can act on, as `grep_code` does. The model then retries with `update_issue\(`.

# %%
print(grep_code.invoke({"pattern": "update_issue("}))
print(grep_code.invoke({"pattern": r"update_issue\(", "glob": "**/*.py"}))

# %% [markdown]
# Two more: truncating silently (the model believes it saw every match, so add a "[N more ...]" note), and capping lines but not characters (one minified line still floods the context, step 5).

# %% [markdown]
# ## Try it
# Add an `output` parameter to `grep_code`, like Claude Code's `Grep` output modes: `"content"` (today's behaviour), `"files"` (only the paths of files with a match) and `"count"` (matches per file plus a total). Search the grown repo for `label` over all files in each mode and print each result's token count. Which mode would you make the default for a first search, and why?

# %%
# your code here

# %% [markdown]
# ## Key terms
# - **glob** — a path pattern such as `**/*.py` (`**` = any depth); a glob tool lists the files whose paths match, without reading them.
# - **grep** — searching file contents for a pattern and returning matching lines with file and line number; Claude Code's `Grep` and Gemini CLI's `grep_search` are built-in versions.
# - **windowed file view** — a tool that shows a numbered slice of a file (here up to 100 lines) and says where the slice sits and how to read on.
# - **output truncation** — cutting a tool result to a size limit (characters per line, results, lines) and telling the model what was left out and how to get more.
# - **minified file** — a generated file with whitespace removed, often a whole file on one line; a single grep hit in it can flood the context.

# %%
import llm_replay
llm_replay.stop()

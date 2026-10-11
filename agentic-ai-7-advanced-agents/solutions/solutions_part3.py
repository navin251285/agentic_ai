# %% [markdown]
# # Solutions · Part 3: Coding-agent primitives
# Answers to the "Try it" exercises. Try them yourself first.

# %% [markdown]
# ## Lesson 15
# Load the recorded Claude Code steps, decide each step's phase from what it does, then look up the tool each product would use for that kind of step (the table from step 5 of the lesson).

# %%
import json
from pathlib import Path

steps = json.loads(Path("../data/recorded/15_claude_code.json").read_text())["steps"]

def kind(step):
    if step["name"] == "Read":
        return "gather", "read"
    if step["name"] in ("Edit", "Write"):
        return "act", "edit"
    if step["name"] == "Bash" and "grep" in step["input"]["command"]:
        return "gather", "search"
    return "verify", "run"

TOOL_FOR = {   # kind of step -> tool name per product (from their docs, checked 2026-10-11)
    "search": {"Codex CLI": "exec_command (rg)", "Gemini CLI": "grep_search"},
    "read":   {"Codex CLI": "exec_command (sed/cat)", "Gemini CLI": "read_file"},
    "edit":   {"Codex CLI": "apply_patch", "Gemini CLI": "replace"},
    "run":    {"Codex CLI": "exec_command", "Gemini CLI": "run_shell_command"},
}

def translate(step, product):
    return TOOL_FOR[kind(step)[1]][product]

print(f"{'phase':7} {'Claude Code':12} {'Codex CLI':24} Gemini CLI")
for step in steps:
    print(f"{kind(step)[0]:7} {step['name']:12} {translate(step, 'Codex CLI'):24} {translate(step, 'Gemini CLI')}")

# %% [markdown]
# ## Lesson 16
# Rebuild the grown repo from the lesson (scratch copy plus the one-line export), then give `grep_code` an `output` mode: `content`, `files` or `count`.

# %%
import json, os, re, shutil, subprocess
from pathlib import Path
os.environ["TIKTOKEN_CACHE_DIR"] = str(Path("../data/tiktoken_cache"))
import tiktoken
enc = tiktoken.get_encoding("o200k_base")

def git(*args, cwd):
    return subprocess.run(["git", "-c", "user.name=Pocket Dev", "-c", "user.email=dev@pocket-tracker.test", *args],
                          cwd=cwd, capture_output=True, text=True).stdout

REPO = Path("../work/16_solution/pocket_tracker")
shutil.rmtree(REPO, ignore_errors=True)
shutil.copytree("../apps/pocket_tracker", REPO, ignore=shutil.ignore_patterns("*.db", "__pycache__", ".pytest_cache"))
(REPO / "fixtures").mkdir()
(REPO / "fixtures" / "issues_export.json").write_text(json.dumps(
    [{"id": n, "title": f"Imported issue {n}", "label": "bug"} for n in range(1, 2001)], separators=(",", ":")))
git("init", "-q", "-b", "main", cwd=REPO); git("add", "-A", cwd=REPO); git("commit", "-q", "-m", "init", cwd=REPO)
TRACKED = git("ls-files", cwd=REPO).splitlines()
print(len(TRACKED), "tracked files")

# %% [markdown]
# `files` returns one path per file with a match (Claude Code's `files_with_matches`); `count` returns matches per file plus a total over all files, even when the list is cut.

# %%
MAX_MATCHES, MAX_LINE = 20, 160

def clip(line):
    return line if len(line) <= MAX_LINE else f"{line[:MAX_LINE]} ...[+{len(line) - MAX_LINE:,} chars]"

def grep_code(pattern, glob="**/*", output="content"):
    rx = re.compile(pattern)
    files = sorted(p.relative_to(REPO).as_posix() for p in REPO.glob(glob) if p.relative_to(REPO).as_posix() in TRACKED)
    hits = {f: [(n, l) for n, l in enumerate((REPO / f).read_text(errors="replace").splitlines(), 1) if rx.search(l)]
            for f in files}
    hits = {f: h for f, h in hits.items() if h}
    if output == "files":
        rows = list(hits)
    elif output == "count":
        rows = [f"{f}: {len(h)}" for f, h in hits.items()]
    else:
        rows = [f"{f}:{n}: {clip(l.strip())}" for f, h in hits.items() for n, l in h]
    more = len(rows) - MAX_MATCHES
    text = "\n".join(rows[:MAX_MATCHES]) + (f"\n[{more} more not shown]" if more > 0 else "")
    return text + (f"\ntotal: {sum(len(h) for h in hits.values())} matching lines" if output == "count" else "")

for mode in ("content", "files", "count"):
    out = grep_code("label", output=mode)
    print(f"--- {mode}: {len(enc.encode(out))} tokens")
print(grep_code("label", output="count"))

# %% [markdown]
# `files` is the cheapest first search: it tells the agent where to look without any line text, and a minified file costs one short path instead of a clipped line. `count` shows how concentrated the matches are. Then switch to `content` with a narrow glob, or go straight to `view_file`.

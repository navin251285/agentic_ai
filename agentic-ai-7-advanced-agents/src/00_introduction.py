# %% [markdown]
# # 00 · Introduction: computer-use, coding and long-horizon agents
# Level L1 · Part 1 · core · ~20 min · builds on —

# %% [markdown]
# ## Goal
# By the end you can say, in one sentence each, what a **computer-use agent**, a **coding agent** and a **long-horizon agent** do; you have seen a real model take one step of each on Pocket Tracker; and you know which model this course will use on your machine.

# %% [markdown]
# ## The idea
# A chat agent talks. The agents in this course **do work on a computer**.
# A computer-use agent looks at a screen or web page and clicks, types and scrolls.
# A coding agent reads a repository, edits files and runs the tests.
# A long-horizon agent keeps going for dozens or hundreds of steps, so it must write notes, save progress and stop safely.
#
# Analogy: a chat agent is an advisor on the phone. These agents are a contractor you gave the keys to: they act, so you need to see what they did and check the result.

# %% [markdown]
# ## Picture
# ```mermaid
# flowchart LR
#   M[Model] -->|"tool call: click e9"| CU[Computer-use agent<br/>browser / desktop]
#   M -->|"tool call: edit file"| CO[Coding agent<br/>repo + tests]
#   M -->|"tool call: write note"| LH[Long-horizon agent<br/>many steps, notes, checkpoints]
#   CU -->|page snapshot| M
#   CO -->|test output| M
#   LH -->|progress file| M
# ```
# Same loop every time: the model proposes an action, the **harness** (your code) runs it and returns what happened.

# %% [markdown]
# ## Already know this?
# Part 1 (lessons 00–05) covers the basics. If you can answer these, skip to **lesson 06**:
# 1. What is the difference between an agent's *observation* and its *action*? Give one of each for a browser agent.
# 2. Why is an accessibility-tree (aria) snapshot usually cheaper and more reliable than a screenshot?
# 3. Name three kinds of action space: coordinates, element references, and one more.
# 4. If each step succeeds 95% of the time, roughly how often does a 20-step task succeed?
# 5. In an agent loop, who executes the tool call: the model or the harness?

# %% [markdown]
# ## Step by step
#
# ### 1. Choose your model
# `get_llm()` prints every provider and model, whether its key is set, and whether this lesson has a recording for it. The course ships recordings for the default model (`gemini-3.1-flash-lite`), so this lesson runs with **no key**.
#
# To switch model, set `TUT_LLM_PROVIDER` and `TUT_LLM_MODEL` in the topic's `.env` file, or pass them in the cell: `get_llm("00_introduction", provider="anthropic", model="claude-haiku-5-5")`. A model with no recording **and** no key stops with an error naming the key to add. Your outputs may differ by model.

# %%
import sys; sys.path.insert(0, "..")
browser_msg = code_msg = note_msg = None   # filled by the model cells below (stay None if they are skipped)
print("Fallbacks ready: later cells still run if the model cells are skipped")

# %% [markdown]
# Now pick the model. The table shows ✓ for a provider whose key is set, and `recorded` for a model this lesson can replay without a key.

# %% tags=["needs-llm"]
from llm_setup import get_llm
llm = get_llm("00_introduction", max_calls=3)   # this lesson makes at most 3 model calls

# %% [markdown]
# ### 2. The running example: Pocket Tracker
# Pocket Tracker is a tiny issue tracker. In lesson 06 it becomes a real web app with a repo and tests. Today it is just a Python list, enough to show each agent kind once.

# %%
issues = [
    {"id": 1, "title": "Login page broken", "status": "open"},
    {"id": 2, "title": "Search ignores capital letters", "status": "open"},
    {"id": 3, "title": "Typo on the About page", "status": "open"},
]
for i in issues:
    print(f"#{i['id']:<2} {i['status']:<6} {i['title']}")

# %% [markdown]
# ### 3. A computer-use step
# A browser agent does not see Python objects; it sees the **page**. Here is the issue list page as an aria snapshot (the text form of a page that Playwright produces, lesson 08). Each control has a `ref` the agent can click.

# %%
page_snapshot = """\
- heading "Pocket Tracker" [level=1]
- textbox "Search issues" [ref=e2]
- list:
  - listitem: '#1 Login page broken' button "Close issue #1" [ref=e5]
  - listitem: '#2 Search ignores capital letters' button "Close issue #2" [ref=e7]
  - listitem: '#3 Typo on the About page' button "Close issue #3" [ref=e9]"""
ref_to_issue = {"e5": 1, "e7": 2, "e9": 3}   # what each button does in our fake page
print(page_snapshot)

# %% [markdown]
# We give the model two browser tools with LangChain's `@tool` and `bind_tools`. `tool_choice="any"` means it must answer with an action, not prose. One model call.

# %% tags=["needs-llm"]
from langchain_core.tools import tool

@tool
def click(ref: str) -> str:
    """Click the page element with this ref, e.g. 'e5'."""

@tool
def type_text(ref: str, text: str) -> str:
    """Type text into the textbox with this ref."""

browser_llm = llm.bind_tools([click, type_text], tool_choice="any")
browser_msg = browser_llm.invoke(
    f"You control a web browser. Task: close issue #3.\nCurrent page:\n{page_snapshot}")
print(browser_msg.tool_calls)

# %% [markdown]
# The model only **proposed** an action. The harness runs it. Here "running" means updating our list, the way clicking the real button would change the app's database.

# %%
if browser_msg is None:   # model cell skipped: use the action a model would typically choose
    browser_calls = [{"name": "click", "args": {"ref": "e9"}}]
else:
    browser_calls = browser_msg.tool_calls
for call in browser_calls:
    if call["name"] == "click" and call["args"]["ref"] in ref_to_issue:
        issue_id = ref_to_issue[call["args"]["ref"]]
        issues[issue_id - 1]["status"] = "closed"
        print(f"Harness clicked {call['args']['ref']} -> issue #{issue_id} closed")
print([(i["id"], i["status"]) for i in issues])

# %% [markdown]
# ### 4. A coding step
# A coding agent works on files, not pages. Issue #2 says search ignores capital letters. Here is the buggy file and the failing test output the agent would see after running the tests.

# %%
files = {"tracker/search.py": '''def search(issues, query):
    return [i for i in issues if query in i["title"]]
'''}

def run_test(source):
    """The 'test suite': load the file and check the bug from issue #2."""
    namespace = {}
    exec(source, namespace)
    found = [i["id"] for i in namespace["search"](issues, "search")]
    assert found == [2], f"search('search') returned {found}, expected [2]"
    return "1 passed"

try:
    run_test(files["tracker/search.py"])
except AssertionError as err:
    test_output = f"FAILED test_search_is_case_insensitive - AssertionError: {err}"
print(test_output)

# %% [markdown]
# The model gets one edit tool: replace an exact string in a file. One model call.

# %% tags=["needs-llm"]
@tool
def edit_file(path: str, old_string: str, new_string: str) -> str:
    """Replace old_string (must appear exactly once) with new_string in the file at path."""

code_msg = llm.bind_tools([edit_file], tool_choice="any").invoke(
    "You are a coding agent. Fix issue #2: search should ignore capital letters.\n"
    f"File tracker/search.py:\n{files['tracker/search.py']}\nTest output:\n{test_output}")
print(code_msg.tool_calls)

# %% [markdown]
# Now the harness applies the edit and **reruns the test**. The test, not the model's confidence, decides whether the fix worked. (Running model-written code with `exec` is only OK here because it is a toy; real agents run it in a sandbox, lesson 19.)

# %%
if code_msg is None:   # model cell skipped: a typical fix
    code_calls = [{"name": "edit_file", "args": {"path": "tracker/search.py",
                   "old_string": 'query in i["title"]',
                   "new_string": 'query.lower() in i["title"].lower()'}}]
else:
    code_calls = code_msg.tool_calls
fixed = dict(files)
for call in code_calls:
    a = call["args"]
    if fixed[a["path"]].count(a["old_string"]) == 1:
        fixed[a["path"]] = fixed[a["path"]].replace(a["old_string"], a["new_string"])
print(fixed["tracker/search.py"])
try:
    print("Tests:", run_test(fixed["tracker/search.py"]))
except AssertionError as err:
    print("Tests still fail:", err)

# %% [markdown]
# ### 5. A long-horizon step
# Long tasks outlive one context window. Before the context fills, a good agent writes a **progress note** so the next session (or a person) can pick up. Here is the log of a session working through the backlog.

# %%
session_log = """\
step 1: read issues.json, 5 open issues
step 2: closed #3 in the browser, verified the list shows it closed
step 3: fixed #2 (search case), tests pass, committed
step 4: started #1 (login page): error comes from templates/login.html line 12
step 5: tried changing the form action, 2 tests now fail in test_auth.py
step 6: context window 90% full, must hand over"""
print(session_log)

# %% [markdown]
# One model call with a structured note tool. The fields (done, in progress, next, warnings) are the ones a fresh session needs most.

# %% tags=["needs-llm"]
@tool
def write_progress_note(done: list[str], in_progress: str, next_steps: list[str], warnings: list[str]) -> str:
    """Save a progress note for the next session."""

note_msg = llm.bind_tools([write_progress_note], tool_choice="any").invoke(
    f"You are a long-running agent about to run out of context. Write the progress note.\nLog:\n{session_log}")
print(note_msg.tool_calls[0]["name"])

# %% [markdown]
# The harness saves the note to a file. A later session reads this file first instead of the whole old conversation.

# %%
import json
from pathlib import Path

if note_msg is None:   # model cell skipped: a hand-written example note (not model output)
    note = {"done": ["#3 closed", "#2 fixed"], "in_progress": "#1 login page, 2 tests failing",
            "next_steps": ["revert form action change", "fix templates/login.html line 12"],
            "warnings": ["test_auth.py fails after last change"]}
else:
    note = note_msg.tool_calls[0]["args"]
Path("../data").mkdir(exist_ok=True)
Path("../data/progress_00.json").write_text(json.dumps(note, indent=2))
for field, value in note.items():
    print(f"{field:12} {value}")

# %% [markdown]
# ### 6. The course map
# Pocket Tracker grows with you. This cell reads the course plan and prints each part with its lessons.

# %%
syllabus = json.loads(Path("../syllabus.json").read_text())
for part in syllabus["parts"]:
    ids = [l["id"] for l in part["lessons"]]
    print(f"Part {part['id']} ({part['level']}) {part['title']:<38} lessons {ids[0]}–{ids[-1]} ({len(ids)})")

# %% [markdown]
# And the story of the running example, from a Python list to a fleet of agents:

# %%
for n, stage in enumerate(syllabus["running_example"]["evolution"].split(" -> "), 1):
    print(f"{n:>2}. {stage}")

# %% [markdown]
# Each lesson has a priority: **core** (Essentials path), **professional**, or **deep**. Every path works on its own.

# %%
from collections import Counter
print(Counter(l["priority"] for p in syllabus["parts"] for l in p["lessons"]))

# %% [markdown]
# ## At work
# - Coding agents (Claude Code, Codex CLI, Gemini CLI / Antigravity, OpenHands) run headless in CI and open pull requests; teams drive them from code → lessons 26 and 26a.
# - Unattended agents always run inside an isolation boundary: Anthropic says to run "skip permissions" sessions only in a container, VM or sandbox, and its cloud sessions keep the GitHub token outside the VM → lessons 19 and 53.
# - Web pages and repo files can carry prompt injection; vendors add classifiers and confirmation prompts, but design matters most → lessons 49 and 50.
# - Long runs are expensive: a screenshot costs about 1,000–1,800 input tokens, and Anthropic's C-compiler run took ~2,000 sessions and just under $20,000 → lessons 43 and 59.

# %% [markdown]
# ## What just happened
# - You picked a model with `get_llm()` and saw which keys and recordings exist.
# - A **computer-use** step: the model read a page snapshot and chose `click`; the harness changed the tracker.
# - A **coding** step: the model chose an exact-string edit; the harness applied it and the **test** decided if it worked.
# - A **long-horizon** step: the model wrote a progress note; the harness saved it to `../data/progress_00.json`.
# - In all three, the model only proposes. Your code executes and checks.

# %% [markdown]
# ## Common mistakes
# Treating the model's tool call as if it already happened. The model *said* `edit_file`, but nothing changed the file until the harness applied it, so the original code still fails:

# %% tags=["raises-exception"]
run_test(files["tracker/search.py"])   # the unpatched file: the tool call alone fixes nothing

# %% [markdown]
# Fix: apply the action in the harness, then verify with the test.

# %%
print(run_test(fixed["tracker/search.py"]))   # the file after the harness applied the edit

# %% [markdown]
# Other mistakes: expecting the same wording from every model (check the tool call and the result, not the prose), and switching to a model with no key and no recording (it stops with an error naming the key).

# %% [markdown]
# ## Try it
# Sort these work tasks into `"computer-use"`, `"coding"` or `"long-horizon"`. Then print, for each, the number of the Part where the course covers it (2 = browser, 3 = coding primitives, 5 = context for long tasks).

# %%
tasks = [
    "Fill in a supplier's web form from a spreadsheet",
    "Upgrade a library and fix every failing test",
    "Build a 40-feature app over three days",
    "Reproduce a bug report by clicking through the app",
]
# your code here

# %% [markdown]
# ## Key terms
# - **computer-use agent** — an agent that observes a screen or page and acts with clicks, typing and keys.
# - **coding agent** — an agent that searches, edits and tests a code repository.
# - **long-horizon agent** — an agent that works over many steps or sessions, so it needs notes, checkpoints and stop rules.
# - **harness** — the code around the model that runs its tool calls and returns the results.
# - **progress note** — a short file a long-running agent writes so a later session can continue.
# - **course map** — the parts and lessons of this course and how Pocket Tracker grows through them.

# %%
import llm_replay
llm_replay.stop()

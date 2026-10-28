# %% [markdown]
# # 09 · Why one prompt is not enough: outer loops and fresh context per iteration
# Level L3 · Part 2 · core · ~20 min · builds on 08
#
# ## Goal
# Run one prompt and an outer loop on the same pocket-cart modules with a real model, measure what each one gives you (model calls, input size, what the model claimed against what pytest says), and name the four loop types Anthropic describes.
#
# ## Why it matters
# Lesson 08 ran one loop on one module. Real work has many items. pocket-cart has six modules and 12 failing tests. A common first try is one big prompt with every file and every failing line. That is one call, one reply and no second look:
#
# - The reply is applied all at once. If one module is wrong, nothing isolates it, and nothing sends it back.
# - The model may say "done". That is a claim. Only the tests show whether it is true.
# - Every file goes into one context. The input grows with the whole task.
#
# The code below measures the difference with the real model: one prompt on three modules, an outer loop on the same three, and one prompt on all six. On this model and this small repo, one prompt passed every test. That is one sample, and it does not prove one prompt is always enough. What the measurements do show is what one prompt does not give you: a check and a revert per item, and an input that grows with the whole task.
#
# You do not need an outer loop when one call and one check finish the job, or when every step is known in advance. A fixed workflow covers that case.

# %% [markdown]
# ## The idea
# **An outer loop picks the next item, gives the model a fresh, small context for that item, checks the result with a verifier, and only then moves on. The model's turns sit inside it, and the outer loop decides when the work is done.**
#
# Analogy: a kitchen pass. One cook given every order at once mixes them up and calls the table served before it is. A pass takes one ticket at a time, checks each plate, and sends it back if it is wrong. The cook's skill is the same; the process is what changes.
#
# Anthropic's guide on loops (claude.com/blog/getting-started-with-loops, June 2026) names four loop types. They differ in what starts the loop and what stops it. Fresh context per iteration is a different pattern, the Ralph loop, and this lesson keeps the two apart.

# %% [markdown]
# ## Picture
# The outer loop wraps the model's turns. Each item starts with a clean context and ends with a check.
#
# ```mermaid
# flowchart TD
#   O["Outer loop: next item"] --> F["Fresh context: this module, its test, its failing lines"]
#   F --> M["Model: one turn"]
#   M --> W["Write the module"]
#   W --> V{"Verifier: pytest on its test file"}
#   V -->|green| N["Keep it, next item"]
#   V -->|red| R["Revert it, next item"]
#   N --> O
#   R --> O
# ```

# %% [markdown]
# ## Already know this?
# This is the first lesson of Part 2 (control: outer loops, state, retries and review). Answer each question in one line. Where you can answer it, skip to the lesson named.
#
# 1. Why must a loop check its work with a test, not with the model's word? Skip to lesson 07 if you can answer it.
# 2. How would you stop a loop when the model says "done" but a test is still red? Skip to lesson 10.
# 3. Where should a loop keep what it learned, so a fresh iteration can find it? Skip to lesson 12.
# 4. Why is a retry of a refund dangerous without a key on the write? Skip to lesson 13.
# 5. Why should the checker not share the maker's context? Skip to lesson 14.

# %% [markdown]
# ## Explained
# ### The four loop types
# Anthropic's guide describes four loops. Each is a different answer to two questions: what starts it, and what stops it.
#
# | Loop type | What starts it | What stops it | Example in the guide |
# |---|---|---|---|
# | Turn-based | a person's prompt | the model judges the task done, or asks for more context | a chat where you direct each turn |
# | Goal-based | a person sets a success condition | the condition is met, or a turn cap is reached | `/goal` with "stop after 5 tries" |
# | Time-based | an interval or a schedule | the person stops it, or the work is done | `/loop 5m` to watch a CI run, `/schedule` for a cloud routine |
# | Proactive | an event or a schedule, with no person in real time | the item's goal is met | a routine that triages new issues |
#
# `/goal`, `/loop 5m` and `/schedule` are Claude Code commands that the guide uses as examples.

# %% [markdown]
# A turn-based loop is what you built in lessons 03 to 08. The outer loop of this lesson decides the next item and when to stop: a goal-based loop over a list of items.
#
# %% [markdown]
# ### Fresh context per iteration
# A long conversation keeps every earlier turn in the model's input. Each new turn costs more, and the model has more to be distracted by (context rot; not measured here). A fresh context starts each iteration with only what the item needs: the module, its test and its failing lines. State that must survive between iterations lives in files or a database (lesson 12), not in the chat.
#
# Note the source: Geoffrey Huntley's Ralph loop uses fresh context on every iteration. Anthropic's guide says a reviewer with fresh context is less biased. It does not describe the Ralph loop.

# %% [markdown]
# ## Worked example
# The example is pocket-cart, the generated shop repo from lesson 07. Its `FIX_PLAN.md` lists six modules. Each module has its own test file. Twelve of the 18 tests fail. The repo is generated, not downloaded, so there is no licence to check.
#
# The lesson makes five model calls in total, the cap for this notebook: one prompt on three modules, three outer-loop turns on the same three modules, and one prompt on all six.

# %% [markdown]
# ### Step 1: the data and the verifier (no model call)
# The repo is read-only in `../data/pocket-cart`. Every run works on its own copy. The verifier is pytest: exit code 0 means every test in the list passed. The first lines of the fix plan show what the model is asked to do.

# %%
import sys; sys.path.insert(0, "..")
import llm_replay
llm_replay.start("09_why-outer-loops")  # records the model calls once, replays them later

# %% [markdown]
# The repo, the six modules from `FIX_PLAN.md` and their test files. Each module has its own test file, so each one can be checked alone.

# %%
import os, re, shutil, subprocess
from pathlib import Path

SRC = Path("../data/pocket-cart")  # generated by data/make_pocket_cart.py; this lesson only reads it
WORK = Path("../data/09")          # run-time copies of the repo
MODULES = [  # the six modules of FIX_PLAN.md, each with its own test file
    {"file": "pocket_cart/money.py", "tests": "tests/test_money.py"},
    {"file": "pocket_cart/pricing.py", "tests": "tests/test_pricing.py"},
    {"file": "pocket_cart/tax.py", "tests": "tests/test_tax.py"},
    {"file": "pocket_cart/cart.py", "tests": "tests/test_cart.py"},
    {"file": "pocket_cart/coupons.py", "tests": "tests/test_coupons.py"},
    {"file": "pocket_cart/shipping.py", "tests": "tests/test_shipping.py"},
]
THREE = MODULES[:3]  # money, pricing and tax: small enough for both approaches
ALL_TESTS = [item["tests"] for item in MODULES]

print("".join((SRC / "FIX_PLAN.md").read_text().splitlines(keepends=True)[:6]))

# %% [markdown]
# Two helpers: a fresh copy of the repo for each run, and the verifier. `check` runs pytest in the copy and reads its summary.

# %%
def fresh_copy(name):
    """A new copy of the repo for one run. The source is never edited."""
    work = WORK / name
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(SRC, work)
    return work

def check(work, tests=ALL_TESTS):
    """The verifier: pytest in the copy. Returns exit code, tests passed, tests in the list and FAILED lines."""
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    run = subprocess.run([os.path.abspath(sys.executable), "-m", "pytest", "-q", "--color=no",
                          "-p", "no:cacheprovider", *tests], cwd=work, capture_output=True, text=True, env=env)
    passed = re.search(r"(\d+) passed", run.stdout)
    failed = re.search(r"(\d+) failed", run.stdout)
    n_passed, n_failed = int(passed.group(1)) if passed else 0, int(failed.group(1)) if failed else 0
    lines = [line for line in run.stdout.splitlines() if line.startswith("FAILED")]
    return {"code": run.returncode, "passed": n_passed, "total": n_passed + n_failed, "failed": lines}

start = check(fresh_copy("before"))
print(f"before any fix: exit code {start['code']}, passed {start['passed']} of {start['total']}")
print(start["failed"][0][:90])  # the first FAILED line

# %% [markdown]
# ### Step 2: the model
# The model is the course default, from `get_llm()`. The key comes from `.env`. A recording replays without one.

# %% tags=["needs-llm"]
from langchain_core.messages import HumanMessage, SystemMessage
from llm_setup import DEFAULT_MODELS, get_llm

llm = get_llm(model=DEFAULT_MODELS["gemini"])  # the key comes from .env

# %% [markdown]
# Two small parsers read a reply. A file starts with a `### FILE <path>` line. The model also ends with a line that says whether it believes every test passes. Pytest, not that line, decides the result.

# %%
def parse_files(text):
    """Split a reply into {path: new text}. Each file starts with a '### FILE <path>' line."""
    text = text.replace("```python", "").replace("```", "")
    parts = re.split(r"^### FILE (\S+)[ \t]*$", text, flags=re.M)
    # the DONE line belongs to the reply, not to the last file
    return {parts[i]: re.sub(r"^DONE:.*$", "", parts[i + 1], flags=re.M | re.I).strip("\n") + "\n"
            for i in range(1, len(parts), 2)}

def claimed_done(text):
    """The model's own last word: 'yes', 'no' or 'none' when it gave no DONE line."""
    found = re.findall(r"^DONE:\s*(yes|no)", text, flags=re.M | re.I)
    return found[-1].lower() if found else "none"

# %% [markdown]
# ### Step 3: without an outer loop, one prompt
# One call gets every module in the list, its test file and every failing line. The model replies with all the new files at once. There is no second turn: whatever the reply wrote is the result. The function runs twice below, on three modules and then on six.

# %% tags=["needs-llm"]
ONE_PROMPT_SYSTEM = ("You fix a small Python shop. The tests are the spec: never change a test. Reply with the "
                     "complete new text of every module you change, each under '### FILE <path>'. End with 'DONE: yes' or 'DONE: no'.")

def one_prompt(items, name):
    """One call with every module, its test and all the failing lines. One reply, applied at once."""
    work = fresh_copy(name)
    failing = check(work, [i["tests"] for i in items])["failed"]
    parts = []
    for item in items:
        parts.append(f"### FILE {item['file']}\n{(work / item['file']).read_text()}")
        parts.append(f"### TEST {item['tests']}\n{(work / item['tests']).read_text()}")
    prompt = "\n".join(parts) + "\nStill failing:\n" + "\n".join(failing)
    reply = llm.invoke([SystemMessage(content=ONE_PROMPT_SYSTEM), HumanMessage(content=prompt)])
    changed = parse_files(reply.text)
    for path, text in changed.items():
        (work / path).write_text(text)
    result = check(work, [i["tests"] for i in items])
    print(f"{name}: files in the reply {sorted(changed)}")
    tokens = reply.usage_metadata["input_tokens"]
    return {"calls": 1, "input": tokens, "sent": tokens, "claimed": claimed_done(reply.text),
            "passed": result["passed"], "total": result["total"], "green": result["code"] == 0}

one_three = one_prompt(THREE, "one-prompt-3")
print("the model said DONE:", one_three["claimed"], "| pytest green:", one_three["green"],
      "| passed:", one_three["passed"], "of", one_three["total"])

# %% [markdown]
# ### Step 4: with an outer loop
# The outer loop takes one item at a time. Each turn gets a fresh context: that module, its test file and only its own failing lines. The verifier runs on that item's tests. A red item is reverted, so a bad edit does not reach the next item. The loop gives each item one turn, so it makes exactly one model call per item.

# %% tags=["needs-llm"]
ITEM_SYSTEM = ("You fix one module of a small Python shop. The test file is the spec: never change it. "
               "Reply with the complete new text of your module only, under a line '### FILE <path>'. No prose.")

def fix_item(work, item, failing):
    """One turn with a fresh context: this module, its test and its own failing lines. Nothing else."""
    prompt = (f"### FILE {item['file']}\n{(work / item['file']).read_text()}\n"
              f"### TEST {item['tests']}\n{(work / item['tests']).read_text()}\n"
              "Still failing:\n" + "\n".join(failing))
    reply = llm.invoke([SystemMessage(content=ITEM_SYSTEM), HumanMessage(content=prompt)])  # a new list every turn
    return parse_files(reply.text).get(item["file"]), reply.usage_metadata["input_tokens"]

# %% [markdown]
# The loop around the turn: one item at a time, a check after each, a revert on red.

# %%
def outer_loop(work, items):
    """The outer loop: one item per iteration, a fresh context each time, a check after each, revert on red."""
    log = []
    for item in items:
        before = (work / item["file"]).read_text()
        failing = check(work, [item["tests"]])["failed"]
        new, tokens = fix_item(work, item, failing)
        if new is None:
            log.append({"item": item["file"], "result": "no file in the reply", "input": tokens})
            continue
        (work / item["file"]).write_text(new)
        code = check(work, [item["tests"]])["code"]
        if code != 0:
            (work / item["file"]).write_text(before)  # red: revert; the next item still runs
        log.append({"item": item["file"], "result": "green" if code == 0 else "red, reverted", "input": tokens})
    return log

work_loop = fresh_copy("outer-loop")
log = outer_loop(work_loop, THREE)
for row in log:
    print(f"{row['item']:<22} {row['result']:<18} input tokens {row['input']}")
final = check(work_loop, [i["tests"] for i in THREE])
loop_three = {"calls": len(log), "input": max(row["input"] for row in log), "sent": sum(row["input"] for row in log),
              "claimed": "n/a",
              "passed": final["passed"], "total": final["total"], "green": final["code"] == 0}
print("outer loop on three modules: passed", final["passed"], "of", final["total"])

# %% [markdown]
# **Revert control (no model call).** On a new copy of the repo, overwrite `money.py` with a wrong version and check it (red). Then restore the text the loop kept (green). Restoring the last green text is the revert the loop does on red.

# %%
kept = (work_loop / THREE[0]["file"]).read_text()  # money.py as the loop kept it: green
ctrl = fresh_copy("revert-control")  # money.py and its test
(ctrl / THREE[0]["file"]).write_text('def format_price(cents: int) -> str:\n    return str(cents)\n')  # a wrong version
red = check(ctrl, [THREE[0]["tests"]])
print(f"wrong version: exit {red['code']}, passed {red['passed']} of {red['total']}")
(ctrl / THREE[0]["file"]).write_text(kept)  # the revert: back to the kept text
green = check(ctrl, [THREE[0]["tests"]])
print(f"after the revert: exit {green['code']}, passed {green['passed']} of {green['total']}")

# %% [markdown]
# ### Step 5: one prompt on all six modules
# The same single-prompt approach, now with the whole fix plan. This is the largest single call in the lesson.

# %% tags=["needs-llm"]
one_six = one_prompt(MODULES, "one-prompt-6")
print("the model said DONE:", one_six["claimed"], "| pytest green:", one_six["green"],
      "| passed:", one_six["passed"], "of", one_six["total"])

# %% [markdown]
# ### Step 6: the comparison
# The table shows the model calls, the largest single call, the total input sent in the run and what the model claimed against what pytest says. The loop shows `n/a` under "model said done": it does not ask for DONE, because pytest decides. The notebook makes five model calls in all, the cap for this lesson; the count comes from the recording.

# %%
rows = [("one prompt, 3 modules", one_three), ("outer loop, 3 modules", loop_three), ("one prompt, 6 modules", one_six)]
print(f"{'run':<24}{'model calls':>12}{'largest single call':>21}{'total input tokens':>20}{'passed':>10}{'model said done':>17}{'pytest green':>14}")
for name, res in rows:
    print(f"{name:<24}{res['calls']:>12}{res['input']:>21}{res['sent']:>20}{str(res['passed']) + '/' + str(res['total']):>10}"
          f"{res['claimed']:>17}{str(res['green']):>14}")
print("model calls in this notebook:", llm_replay.calls(), "(limit 5)")

# %% [markdown]
# ### What the recorded run showed
# - **The single prompt passed here.** One prompt on three modules and one on all six both ended green, and the model's `DONE: yes` was true both times. One run of one model on a small repo is one sample.
# - **The input grew with the task.** The one prompt sent 852 input tokens for three modules and 1,785 for six. Each outer-loop turn sent 306 to 318, the size of one item.

# %% [markdown]
# - **The loop checks each item.** Every module in the loop had its own green or red result, and a red one would have been reverted. The single prompt gave one result for everything.
# - **The loop sent more in total here.** On three modules the loop sent more input in total (931 vs 852) and made three calls instead of one. The loop's input stays per item; the one prompt's grows with the task.
# - **What the run does not show.** It shows no failure, so it does not show that one prompt breaks. A harder repo or another model could. The loop gives you the check to find out, at the cost of three calls here instead of one. The benefit shown is only the per-item check and revert, plus the flat input size. This lesson does not demonstrate a failure the loop rescued; lesson 08 shows the stuck exit and the revert on red.

# %% [markdown]
# Save the recording. This cell is the last code cell of the notebook.

# %%
llm_replay.stop()  # saves the recording

# %% [markdown]
# ## How it simplifies the architecture
# Without an outer loop, the person is the loop: they read the reply, run pytest, and type the next prompt. With one, the system picks the item, checks it, reverts the bad edits and moves on.
#
# ```mermaid
# flowchart LR
#   P[Person] -->|one big prompt: all files| M[Model]
#   M -->|one reply| A[Apply every edit at once]
#   A --> T[pytest on everything]
#   T -->|red: a person reads it| P
#   P -->|types the next prompt by hand| M
# ```
#
# ```mermaid
# flowchart LR
#   L[Outer loop] -->|one item, fresh context| M[Model turn]
#   M --> V[Verifier per item]
#   V -->|green: keep| L
#   V -->|red: revert| L
# ```
#
# Moving parts go from one prompt and a person to a loop, a list of items and a verifier. The glue is a few lines of Python. The new failure point is the loop itself: a wrong item order, or a verifier that checks the wrong thing.
#
# **What an outer loop does not solve.** Each turn can still be wrong, and the loop only catches what the verifier checks. Cost grows with the number of items and turns. A person still has to read what the loop changed. **You do not need it** when one call and one check finish the job, or when every step is known in advance: a fixed workflow does that without a loop.

# %% [markdown]
# ## At work
# - Ralph loops (Geoffrey Huntley's pattern) run one item per iteration with fresh context, reject bad output with tests and commit on green. → lesson 11 builds it on pocket-cart.
# - Claude's `/goal` checks its condition after every turn and takes a turn cap, such as "stop after 5 tries". → lesson 10 gates a loop with a Stop hook.
# - Model and effort choices are among the biggest levers on what a loop costs, per Anthropic's guide. → lesson 27 measures cost per successful run.
# - Go deeper: the guide's advice to use a second agent as reviewer is the maker/checker split. → lesson 14.

# %% [markdown]
# ## Common misconceptions
# 1. **"A bigger prompt is the same as a loop."** One prompt gives one reply and no second look. The outer loop is what sends a failing item back with its own evidence.
# 2. **"When the model says done, it is done."** The model's `DONE` line is a claim. Compare it with pytest every time. Here they agreed; in other runs they may not.
# 3. **"One run that passes proves the one prompt is safe."** One run is one sample. A pass on three small modules says little about six.
# 4. **"Anthropic's four loop types include fresh context per iteration."** They do not. Fresh context per iteration is the Ralph pattern. The four types are turn-based, goal-based, time-based and proactive.

# %% [markdown]
# ## Check yourself
# 1. A reply says `DONE: yes` and pytest shows 2 failures. Which one decides the result, and what does the outer loop do next? (Answer below.)
# 2. Why did the loop give each module its own test file in the prompt, not the whole repo?
# 3. Name the loop type for "a routine that triages new issues each morning with no person online".
# 4. The one-prompt input went from 852 tokens (3 modules) to 1,785 (6 modules). Why, and what would a loop turn send for a 12-module repo?

# %% [markdown]
# **Answers** (hidden cell below).

# %% tags=["solution"]
# 1. Pytest decides. The 2 failures mean not done; the outer loop reverts the red item and moves to the next item (or the item is stopped as stuck).
# 2. A fresh context holds only what the item needs. Less input per turn, and the model is not distracted by the other modules.
# 3. Proactive: an event or schedule starts it, no person in real time, and each task exits when its goal is met.
# 4. One prompt carries every module, so its input grows with the whole task (about 850 to 1,800 tokens here). A loop turn carries one module and its test, so it stays the size of one item (about 310 tokens here, if modules are similar in size) as the repo grows.

# %% [markdown]
# ## Recap
# - One prompt gives one reply and no check after it. Multi-part work gets an outer loop: pick an item, give fresh context, check, move on.
# - Anthropic's four loop types: turn-based, goal-based, time-based, proactive. They differ in what starts and stops them.
# - The model's claim of "done" is not a stop; a verifier (pytest) is.
# - Fresh context per iteration (Ralph) keeps each turn the size of one item; state lives outside the model (lesson 12).
#
# **Interview:** "Why not put all the failing tests in one prompt?" A strong answer: one reply has no check after it, its input grows with the whole task, and the model's claim of done is not evidence. One passing run proves little. Run one item per turn with fresh context, check each with a deterministic verifier, and revert what goes red.

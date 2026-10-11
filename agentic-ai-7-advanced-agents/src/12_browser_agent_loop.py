# %% [markdown]
# # 12 · The browser agent loop with a real model
# Level L2 · Part 2 · core · ~35 min · builds on 05, 09

# %% [markdown]
# ## Goal
# By the end you can run a **browser agent** on Pocket Tracker: a real model closes the oldest open bug through the page, one fresh aria snapshot per step, under a step limit. The harness then decides success from the database, and the run is saved so it replays with no key.

# %% [markdown]
# ## The idea
# Lesson 05 built the agent loop on a dict. Lesson 09 turned a model's ref into a real click, but only for one step. A **browser agent** joins the two: the model decides, the harness acts on the page, takes a new snapshot, and asks again. This is the **observation-action loop**: every decision is made from the newest snapshot, never from a remembered one.
#
# The harness still owns three things: the step limit, which actions run, and the verdict. And because a model is not deterministic, we keep a **recorded run**: the model's replies (in `llm_replay`'s cassette) plus what the browser saw, so anyone can replay this exact run.
#
# Analogy: a pilot flying by instruments. Read the panel, adjust, read it again. The flight recorder lets investigators replay the flight later.

# %% [markdown]
# ## Picture
# ```mermaid
# flowchart LR
#   O["observe<br/>URL + ai snapshot"] --> D[model call]
#   D -->|tool calls| A["act by ref<br/>(stop after a click)"]
#   A --> L{step limit?}
#   L -->|steps left| O
#   D -->|no tool calls| V[verify:<br/>read the database]
#   L -->|limit hit| V
# ```

# %% [markdown]
# ## Step by step
#
# ### 1. Start Pocket Tracker with yesterday's state
# Same start as lesson 09: a scratch copy of the app on a free port, polled on `/health`, all before the model setup (the recorder records HTTP calls made after it starts).
#
# One change to the seeded data: someone closed #1 yesterday. So the oldest open bug is not simply the first row, and the model has to read the Status and Label columns.

# %%
import atexit, json, os, re, shutil, socket, sqlite3, subprocess, sys, time
from pathlib import Path
import httpx
sys.path.insert(0, "..")    # course helpers: llm_setup, llm_replay

WORK, REPO = Path("../work/12"), Path("../work/12/pocket_tracker")
DB = (WORK / "pocket_tracker.db").resolve()
shutil.rmtree(WORK, ignore_errors=True)
shutil.copytree("../apps/pocket_tracker", REPO, ignore=shutil.ignore_patterns("*.db", "__pycache__", ".pytest_cache"))
with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    PORT = s.getsockname()[1]
BASE = f"http://127.0.0.1:{PORT}"
log = open(WORK / "server.log", "w")
server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(PORT)],
                          cwd=REPO, env={**os.environ, "POCKET_TRACKER_DB": str(DB)}, stdout=log, stderr=log)
atexit.register(server.terminate)
deadline = time.time() + 15
while True:
    try:
        print("health:", httpx.get(f"{BASE}/health").json()); break
    except httpx.ConnectError:
        if time.time() > deadline or server.poll() is not None:
            raise RuntimeError("server did not start; see ../work/12/server.log")
        time.sleep(0.2)

# %% [markdown]
# Close #1 directly in the database (this is test setup, not part of the agent's task), and keep a copy of every issue's state from before the run.

# %%
def read_rows():
    with sqlite3.connect(DB) as db:
        rows = db.execute("SELECT id, title, label, status, created_at FROM issues ORDER BY id").fetchall()
    return {r[0]: {"title": r[1], "label": r[2], "status": r[3], "created_at": r[4]} for r in rows}

with sqlite3.connect(DB) as db:
    db.execute("UPDATE issues SET status = 'closed' WHERE id = 1")
before = read_rows()
for i in (1, 2, 3, 4):
    print(i, before[i])

# %% [markdown]
# ### 2. Write the outcome check first
# As in lesson 05, decide what "done" means before the model runs. The target comes from the data, not from us: the open issue with label `bug` and the earliest `created_at`. The check compares the database before and after: the target must be closed, and no other issue may change status or appear.

# %%
def oldest_open_bug(rows):
    open_bugs = [i for i, r in rows.items() if r["status"] == "open" and r["label"] == "bug"]
    return min(open_bugs, key=lambda i: rows[i]["created_at"])

def check_outcome(before, after):
    target, problems = oldest_open_bug(before), []
    if after.get(target, {}).get("status") != "closed":
        problems.append(f"#{target} (the target) is still open")
    for i in set(before) | set(after):
        if i != target and before.get(i, {}).get("status") != after.get(i, {}).get("status"):
            problems.append(f"#{i} changed: {before.get(i, {}).get('status')} -> {after.get(i, {}).get('status')}")
    return problems

print("target:", oldest_open_bug(before), "| check before any action:", check_outcome(before, before))

# %% [markdown]
# The target is #2, and a run that does nothing fails the check. The check reads status only, not labels; step 9 shows why.
#
# ### 3. The model
# Same start as lessons 05 and 09. One agent run here makes at most 3 model calls (the step limit below); `max_calls=4` is the ceiling `llm_replay` enforces. With no key and no recording for your model, the model cells are skipped and a recorded run keeps the notebook going.

# %% tags=["needs-llm"]
from llm_setup import get_llm
llm = get_llm("12_browser_agent_loop", max_calls=4)

# %% [markdown]
# ### 4. A browser that stays open
# As in lesson 09: start Playwright once and keep `page` until the last cell. Browser cells are tagged `needs-download`. When they are skipped, `seen` holds the **recorded output** of a real run from `../data/recorded/12.json`.

# %%
REC_PATH = Path("../data/recorded/12.json")
seen = json.loads(REC_PATH.read_text()) if REC_PATH.exists() else {}
seen["source"] = "recorded output (real run, saved earlier)"
print("fallback keys:", sorted(k for k in seen if k != "source"))

# %% [markdown]
# Open the issue list. That is where the agent starts.

# %% tags=["needs-download"]
from playwright.async_api import async_playwright, Error as PlaywrightError

pw = await async_playwright().start()
browser = await pw.chromium.launch()
page = await (await browser.new_context(viewport={"width": 1024, "height": 768})).new_page()
page.set_default_timeout(3000)
await page.goto(f"{BASE}/issues")
seen["source"] = "live run"
print("open at", page.url)

# %% [markdown]
# ### 5. The harness pieces from lesson 09
# `elements_of`, `check_action` and `act` are copied from lesson 09 unchanged: the model names a ref, the harness checks it against the latest snapshot, then runs it with `page.locator("aria-ref=...")`.

# %%
REF_LINE = re.compile(r'- (\w+)(?: "([^"]*)")?.*?\[ref=(\w+)\]')
ALLOWED = {"click": {"button", "link", "checkbox", "radio", "tab", "menuitem"},
           "fill": {"textbox", "searchbox"},
           "select_option": {"combobox", "listbox"}}

def elements_of(snapshot):
    return {ref: (role, name) for role, name, ref in REF_LINE.findall(snapshot)}

def check_action(call, elements):
    name, ref = call["name"], call["args"].get("ref")
    if name not in ALLOWED:
        return f"unknown action {name!r}"
    if ref not in elements:
        return f"ref {ref!r} is not in the latest snapshot (stale or invented): take a new snapshot"
    if elements[ref][0] not in ALLOWED[name]:
        return f"cannot {name} a {elements[ref][0]} ({elements[ref][1]!r})"
    return None

# %% [markdown]
# `act` dispatches one checked call and returns a short text result for the model.

# %%
async def act(page, call, elements):
    problem = check_action(call, elements)
    if problem:
        return f"refused: {problem}"
    ref, args = call["args"]["ref"], call["args"]
    target = page.locator(f"aria-ref={ref}")
    try:
        if call["name"] == "click":
            await target.click()
        elif call["name"] == "fill":
            await target.fill(args["text"])
        else:
            await target.select_option(label=args["option"])
    except PlaywrightError as e:
        return f"error: {str(e).splitlines()[0]}"
    await page.wait_for_load_state()
    return f"ok: {call['name']} {elements[ref][0]} {elements[ref][1]!r}"

# %% [markdown]
# And the same three tools. Their bodies are empty: the model proposes calls, the harness runs them.

# %%
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

@tool
def click(ref: str) -> str:
    """Click the button or link with this ref."""

@tool
def fill(ref: str, text: str) -> str:
    """Replace the text in the textbox with this ref."""

@tool
def select_option(ref: str, option: str) -> str:
    """Choose the option with this visible label in the combobox with this ref."""

print("tools:", [t.name for t in (click, fill, select_option)])

# %% [markdown]
# ### 6. Observe, then act until the page may change
# Two new functions. `observe` takes a fresh ai snapshot and remembers it as `latest`; every check uses that one. `do_step` runs one reply's tool calls, with one new rule: **after a click, stop**. A click can submit a form or follow a link, which makes every other ref in that reply stale (lesson 09's POST to "Close issue" even keeps the same URL). The skipped calls still get a result, so the model knows why.

# %%
MAX_STEPS, MAX_ACTIONS = 3, 6     # model calls, and actions across the run

async def observe(page):
    global latest
    latest = await page.aria_snapshot(mode="ai")
    return f"URL: {page.url.removeprefix(BASE)}\nPage (aria snapshot, act by ref):\n{latest}"

async def do_step(page, calls, run):
    results, clicked = [], False
    for call in calls:
        if clicked:
            result = "not run: a click may have loaded a new page; decide again from the new snapshot"
        elif run["actions"] >= MAX_ACTIONS:
            result = "not run: action limit reached"
        else:
            run["actions"] += 1
            result = await act(page, call, elements_of(latest))
            clicked = call["name"] == "click" and result.startswith("ok")
        run["log"].append(f"step {run['model_calls']}: {call['name']}({call['args']}) -> {result}")
        results.append(result)
    return results

# %% [markdown]
# Try `observe` alone: it is the first message the model will get. The list page is long, so we print only its size and the rows for #1 and #2.

# %% tags=["needs-download"]
first_obs = await observe(page)
seen["first_obs"] = first_obs
print(len(first_obs), "characters")

# %% [markdown]
# The observation the model starts from (from the live page, or the recording):

# %%
lines = seen["first_obs"].splitlines()
print(f"[{seen['source']}]", lines[0])
for k, line in enumerate(lines):
    if 'cell "1"' in line or 'cell "2"' in line:
        print("\n".join(lines[k:k + 6]))

# %% [markdown]
# #1 shows `closed`, #2 shows `bug` and `open`. The page has no dates, so the task tells the model that numbers follow the filing order.
#
# ### 7. The loop
# The task and the rules, then the loop from lesson 05 with a browser inside. Each step: one model call; no tool calls means the model is done; otherwise act, answer every tool call with a `ToolMessage`, and send a fresh observation. The loop ends when the model stops or after `MAX_STEPS` calls.

# %%
SYSTEM = ("You operate the Pocket Tracker web app through its aria snapshot. Use only refs from the latest "
          "snapshot. After a click you get a new snapshot before acting again. When the task is done, "
          "reply with one short sentence and no tool calls.")
TASK = ("Close the oldest open issue labelled 'bug'. Issues are numbered in the order they were filed, "
        "so a lower number is older. Do not change any other issue.")
run = None    # filled by the loop cell (stays None if it is skipped)
print(TASK)

# %% [markdown]
# Here is the run. It makes real model calls (or replays them) and real clicks.

# %% tags=["needs-download", "needs-llm"]
agent = llm.bind_tools([click, fill, select_option])
messages = [SystemMessage(SYSTEM), HumanMessage(f"Task: {TASK}\n\n{first_obs}")]
run = {"model_calls": 0, "actions": 0, "stopped_by": "step limit", "last_words": "", "log": [], "urls": []}
while run["model_calls"] < MAX_STEPS:
    reply = agent.invoke(messages)
    run["model_calls"] += 1
    messages.append(reply)
    run["last_words"] = reply.text
    if not reply.tool_calls:
        run["stopped_by"] = "model finished"
        break
    results = await do_step(page, reply.tool_calls, run)
    messages += [ToolMessage(r, tool_call_id=c["id"]) for c, r in zip(reply.tool_calls, results)]
    messages.append(HumanMessage(f"New observation after your actions:\n{await observe(page)}"))
    run["urls"].append(page.url.removeprefix(BASE))
seen["run"], seen["after"] = run, read_rows()
print("\n".join(run["log"]))

# %% [markdown]
# If the loop was skipped (no browser, or no model), use the recorded run. A fresh, untouched database would make the check below fail, which is correct: nothing was done.

# %%
if run is None and "run" in seen:
    run = seen["run"]
    print(f"[{seen['source']}]")
    print("\n".join(run["log"]))
after = {int(i): r for i, r in (seen.get("after") or read_rows()).items()}    # JSON keys are strings
print("pages visited after each step:", run["urls"] if run else "none")

# %% [markdown]
# ### 8. Verify: the claim next to the outcome
# The model's last words are a claim. The verdict comes from `check_outcome` on the database, which the model never saw.

# %%
problems = check_outcome(before, after)
print("model says:  ", (run["last_words"] if run else "(no run)")[:200] or "(no text)")
print("harness says:", "verified" if not problems else problems)
if run:
    print(f"steps used: {run['model_calls']}/{MAX_STEPS} model calls, {run['actions']}/{MAX_ACTIONS} actions, "
          f"stopped by: {run['stopped_by']}")

# %% [markdown]
# Read the three lines together. `stopped by` says whether the model finished or the limit ended the run; `model says` is empty when the last reply was only tool calls. Whatever the model did or said, the verdict comes from data the model could not write.
#
# In our recorded Gemini run the model followed the link to #2 and clicked "Close issue". Then it saw the issue's label had become `none` and tried to set it back to `bug` (it chose the option but never pressed "Save label"), and the step limit ended the run. Your model may take a different path; the check works the same either way.
#
# ### 9. What the database shows that the screen did not
# Now look at the target row itself, before and after.

# %%
target = oldest_open_bug(before)
print("before:", before[target])
print("after: ", after[target])

# %% [markdown]
# The status is `closed`, as asked. But the label went from `bug` to empty. That is not the agent: it is Pocket Tracker's seeded bug #7 ("Closing an issue resets its label"). A check on labels would fail an agent that did its task, which is why the check reads status only. An outcome check sees the app's own bugs too; lesson 14 turns that into a bug-reproducing agent.
#
# ### 10. The recorded run
# Two files make this run repeatable. The model replies are in `llm_replay`'s cassette, one file per model. The browser side (first observation, log, final rows) goes to `../data/recorded/12.json` in the next cell, which runs only when the browser did.

# %% tags=["needs-download"]
REC_PATH.parent.mkdir(parents=True, exist_ok=True)
REC_PATH.write_text(json.dumps({k: v for k, v in seen.items() if k != "source"}, indent=1, default=str) + "\n")
print("saved", REC_PATH, "with keys", sorted(k for k in seen if k != "source"))

# %% [markdown]
# List the cassettes for this lesson. On replay, `llm_replay` returns the recorded replies in the order they were made, with no key and no cost.

# %%
import llm_replay
for f in sorted(Path("../data/llm_cassettes/12_browser_agent_loop").glob("*.yaml")):
    print(f.name, f"{f.stat().st_size // 1024} KB")
print("llm_replay mode:", llm_replay.mode())

# %% [markdown]
# Replay matches calls by order, not by content. Change the task, the system prompt or the tools and a replay still hands back the old replies, so re-record after any such change.

# %% [markdown]
# ## At work
# - Vendor computer-use guides cap the loop (OpenAI's example: 20 responses; Gemini's: 5 turns) and add time and cost limits next to the step count → lesson 39.
# - Teams store every step's snapshot, action and result, plus a Playwright trace, because a failed run cannot be reproduced from the model alone → lessons 44a and 54.
# - Closing an issue is a consequential action; Claude, OpenAI and Gemini guidance asks for a human to confirm such steps in production → lesson 51.
# - One recorded run is one sample. Browser-agent evals grade the end state over many runs and report variance → lesson 47.

# %% [markdown]
# ## What just happened
# - A **browser agent** ran the **observation-action loop**: fresh ai snapshot, one model call, actions by ref, new snapshot, until the model stopped or hit `MAX_STEPS`.
# - `do_step` stopped after each click, so no ref from an old page was ever used; skipped calls still got a `ToolMessage`.
# - `check_outcome`, written before the run, judged success from the database: target closed, nothing else changed.
# - The database also showed seeded bug #7 (label reset on close); an agent that wanders off to "fix" such things is stopped by the step limit, not by its own judgement.
# - The **recorded run** (cassette + `12.json`) lets the notebook replay without a key or a browser.

# %% [markdown]
# ## Common mistakes
# Checking only the target. An agent that closes #2 and also #4 "to be safe" passes a check that reads only #2. Here is that hand-written state (not model output) against the full check:

# %% tags=["raises-exception"]
overreach = {i: dict(r) for i, r in before.items()}
overreach[2]["status"] = overreach[4]["status"] = "closed"
assert overreach[2]["status"] == "closed"             # the narrow check passes
assert not check_outcome(before, overreach), check_outcome(before, overreach)

# %% [markdown]
# Fix: compare every row before and after, as `check_outcome` does. Two more:
# - Re-using the first snapshot. Sending the model only the opening observation makes it act on refs from a page that is gone; send a fresh one after every step.
# - Editing the prompt and trusting the replay. The cassette replays by order, so the old answers come back. Re-record with `TUT_LLM_MODE=record`.

# %% [markdown]
# ## Try it
# Write `check_docs_outcome(before, after)` for a new task, "close the oldest open issue labelled `docs`". Test it on `before` (it must fail). Then, in a fresh browser on this server, close that issue by hand with `observe` and `do_step` (no model), and check again (it must pass). Hint: the target's name contains `'`, so its snapshot line is wrapped in quotes; make sure `elements_of` finds it.

# %%
# your code here

# %% [markdown]
# ## Key terms
# - **browser agent** — an agent whose observations come from a web page (here aria snapshots) and whose actions are browser actions (click, fill, select) run by the harness.
# - **observation-action loop** — the agent loop where every step starts from a fresh observation of the environment, and actions that may change the page end the step.
# - **recorded run** — a saved agent run (model replies in a cassette, plus what the environment showed) that replays exactly with no key and no cost.

# %% [markdown]
# Always run this cell, and run it last: it closes the browser, stops the server and saves the model recording.

# %%
if "browser" in globals():
    await browser.close()
    await pw.stop()
server.terminate()
try:
    server.wait(timeout=10)
except subprocess.TimeoutExpired:
    server.kill(); server.wait()
log.close()
print("browser closed, server exit code", server.returncode)
llm_replay.stop()

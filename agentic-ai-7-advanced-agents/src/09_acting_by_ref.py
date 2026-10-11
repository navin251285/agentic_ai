# %% [markdown]
# # 09 · Acting by element reference
# Level L2 · Part 2 · core · ~30 min · builds on 03, 08

# %% [markdown]
# ## Goal
# By the end you can turn a model's chosen element ref (`e12`) into a Playwright `fill`, `select_option` or `click` on Pocket Tracker, check every action against the latest snapshot before running it, refuse a stale ref, and confirm the result with a fresh snapshot.

# %% [markdown]
# ## The idea
# In lesson 08 a ref only pointed. Now it acts. Three pieces turn the model's answer into a change in the app:
# - a **locator**: Playwright's recipe for finding an element, here `page.locator("aria-ref=e12")`. It is looked up only when you act on it;
# - **action dispatch**: the harness reads the model's tool call (`fill`, `ref=e12`, `text=...`), checks it, and calls the matching locator method;
# - a **stale element** check: a ref from an older snapshot (before a reload or a submit) points at nothing, so the harness refuses it and snapshots again.
#
# Analogy: a coat-check ticket. The attendant fetches the coat for ticket 12, but only from tonight's tickets; yesterday's ticket gets "please get a new one".

# %% [markdown]
# ## Picture
# ```mermaid
# flowchart LR
#   S["ai snapshot<br/>[ref=e12] ..."] --> M[model]
#   M -->|"fill(ref=e12, text)"| C{check: ref in latest<br/>snapshot? role fits?}
#   C -->|no| R["refused: stale ref<br/>take a new snapshot"]
#   C -->|yes| L["page.locator('aria-ref=e12')<br/>.fill(text)"]
#   L --> P[Pocket Tracker page]
#   P -->|re-snapshot| S
# ```

# %% [markdown]
# ## Step by step
#
# ### 1. Start Pocket Tracker
# Same as lessons 07 and 08: a scratch copy of the app on a free port, polled on `/health`. We do this before the model setup, because the model recorder (next step) records every HTTP call made after it starts.

# %%
import atexit, json, os, re, shutil, socket, sqlite3, subprocess, sys, time
from pathlib import Path
import httpx
sys.path.insert(0, "..")    # course helpers: llm_setup, llm_replay

WORK, REPO = Path("../work/09"), Path("../work/09/pocket_tracker")
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
            raise RuntimeError("server did not start; see ../work/09/server.log")
        time.sleep(0.2)

# %% [markdown]
# ### 2. The model
# Same start as lesson 05. This lesson makes 2 model calls; `max_calls=4` is the ceiling `llm_replay` enforces. With no key and no recording for your model, the model cells are skipped and hand-written actions (clearly labelled) keep the notebook running.

# %% tags=["needs-llm"]
from llm_setup import get_llm
llm = get_llm("09_acting_by_ref", max_calls=4)

# %% [markdown]
# ### 3. A browser that stays open
# Lessons 07 and 08 opened a browser per cell with `async with`. An agent acts on one page over many steps, so here we start Playwright once and keep `page` open until the last cell. `set_default_timeout(3000)` makes a bad action fail in 3 seconds instead of the default 30.
#
# Browser cells are tagged `needs-download`. When they are skipped, `seen` holds the **recorded output** of a real run from `../data/recorded/09.json`.

# %%
REC_PATH = Path("../data/recorded/09.json")
seen = json.loads(REC_PATH.read_text()) if REC_PATH.exists() else {}
seen["source"] = "recorded output (real run, saved earlier)"
print("fallback keys:", sorted(k for k in seen if k != "source"))

# %% [markdown]
# Start Playwright, open the New issue form and take an ai snapshot. These objects live until the last cell.

# %% tags=["needs-download"]
from playwright.async_api import async_playwright, Error as PlaywrightError

pw = await async_playwright().start()
browser = await pw.chromium.launch()
page = await (await browser.new_context(viewport={"width": 1024, "height": 768})).new_page()
page.set_default_timeout(3000)
await page.goto(f"{BASE}/issues/new")
seen["form"] = await page.aria_snapshot(mode="ai")
seen["source"] = "live run"
print("open at", page.url)

# %% [markdown]
# ### 4. From snapshot to an element table
# Lesson 08's `refs_of` mapped `role "name"` to a ref. The harness needs the other direction: given the ref the model chose, what is it? `elements_of` maps each ref to its role and name.

# %%
REF_LINE = re.compile(r'- (\w+)(?: "([^"]*)")?.*?\[ref=(\w+)\]')

def elements_of(snapshot):
    """Map ref -> (role, name) for every element in an ai snapshot."""
    return {ref: (role, name) for role, name, ref in REF_LINE.findall(snapshot)}

form = elements_of(seen["form"])
print(f"[{seen['source']}]")
for ref, (role, name) in form.items():
    if role in ("textbox", "combobox", "button"):
        print(f"{ref:5} {role:9} {name!r}")

# %% [markdown]
# ### 5. A ref becomes a locator
# A **locator** describes how to find an element; it does not find it yet. `page.locator("aria-ref=e12")` finds "the element that the latest ai snapshot called e12". The same input can be found by role and name too (`get_by_role`), which is how a human-written test would do it. We check both point at the same `<input>`.

# %% tags=["needs-download"]
by_ref = page.locator("aria-ref=e12")
by_role = page.get_by_role("textbox", name="Title")
print(by_ref)
seen["same_element"] = {"by_ref": await by_ref.evaluate("el => el.outerHTML"),
                        "by_role": await by_role.evaluate("el => el.outerHTML")}
print(seen["same_element"])

# %% [markdown]
# Both locators resolve to `<input id="title" ...>`. The ref is what a model can give you; the role-and-name form is what you write by hand.

# %%
print(f"[{seen['source']}]", seen["same_element"]["by_ref"] == seen["same_element"]["by_role"])

# %% [markdown]
# ### 6. Check an action before running it
# Model actions arrive as tool calls: `{"name": "fill", "args": {"ref": "e12", "text": "..."}}`. Before touching the page, `check_action` asks three questions: is it a known action, is the ref in the **latest** snapshot, and does the action fit the element's role (you fill a textbox, not a button)? It returns a problem, or `None`.

# %%
ALLOWED = {"click": {"button", "link", "checkbox", "radio", "tab", "menuitem"},
           "fill": {"textbox", "searchbox"},
           "select_option": {"combobox", "listbox"}}

def check_action(call, elements):
    name, ref = call["name"], call["args"].get("ref")
    if name not in ALLOWED:
        return f"unknown action {name!r}"
    if ref not in elements:
        return f"ref {ref!r} is not in the latest snapshot (stale or invented): take a new snapshot"
    role = elements[ref][0]
    if role not in ALLOWED[name]:
        return f"cannot {name} a {role} ({elements[ref][1]!r})"
    return None

for call in [{"name": "fill", "args": {"ref": "e12", "text": "x"}},
             {"name": "fill", "args": {"ref": "e17", "text": "x"}},
             {"name": "click", "args": {"ref": "e99"}},
             {"name": "drag", "args": {"ref": "e12"}}]:
    print(call["name"], call["args"]["ref"], "->", check_action(call, form))

# %% [markdown]
# These checks run on the snapshot text alone, so they cost nothing and catch invented refs before Playwright waits 3 seconds for an element that is not there.
#
# ### 7. Action dispatch
# `act` is the dispatcher: check, build the locator, call the matching method, and return a short text result the model can read next step. `run_plan` runs several calls in order. If an action moves the page to a new URL, every ref from the old snapshot is stale, so the rest of the plan is refused.

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
# `run_plan` keeps the element table of the snapshot the plan was made from, and empties it as soon as the URL changes.

# %%
async def run_plan(page, calls, snapshot):
    elements, log = elements_of(snapshot), []
    for call in calls:
        url = page.url
        log.append(f"{call['name']}({call['args']}) -> {await act(page, call, elements)}")
        if page.url != url:
            elements = {}                       # new document: every old ref is stale
            log[-1] += f" | page changed to {page.url.removeprefix(BASE)}"
    return log

print("dispatcher ready: act(page, call, elements), run_plan(page, calls, snapshot)")

# %% [markdown]
# ### 8. Act by hand first
# Before a model is involved, dispatch two hand-written calls: type a title and pick a label. Then **re-snapshot**: a fresh ai snapshot shows the new values, which is how the harness sees that an action worked.

# %%
by_hand = [{"name": "fill", "args": {"ref": "e12", "text": "Export button does nothing"}},
           {"name": "select_option", "args": {"ref": "e16", "option": "bug"}}]
print("problems:", [check_action(c, form) for c in by_hand])

# %% [markdown]
# Both pass the check. Dispatch them on the live page and take a fresh snapshot.

# %% tags=["needs-download"]
seen["hand_log"] = await run_plan(page, by_hand, seen["form"])
seen["form_after_hand"] = await page.aria_snapshot(mode="ai")
print("\n".join(seen["hand_log"]))

# %% [markdown]
# The re-snapshot: the title box now carries its text, and `bug` is `[selected]`.

# %%
print(f"[{seen['source']}]")
print("\n".join(seen["hand_log"]))
print("\n".join(l for l in seen["form_after_hand"].splitlines() if 'textbox "Title"' in l or "[selected]" in l))

# %% [markdown]
# ### 9. Stale refs after a reload
# Now reload the page (as if the agent came back to it later). The form is empty again, and the new snapshot gives the same title box a new ref with an `f1` prefix (lesson 08). Replaying the hand-written plan against the **new** snapshot is refused before Playwright is touched.

# %% tags=["needs-download"]
await page.reload()
seen["form_fresh"] = await page.aria_snapshot(mode="ai")
print(seen["form_fresh"].count("[ref=f1e"), "refs with the f1 prefix")

# %% [markdown]
# Look up the title box in the fresh table, and check the old hand-written calls against it.

# %%
fresh = elements_of(seen["form_fresh"])
print(f"[{seen['source']}]")
print("title box is now:", next(r for r, el in fresh.items() if el == ("textbox", "Title")))
for call in by_hand:
    print(call["args"]["ref"], "->", check_action(call, fresh))

# %% [markdown]
# Each ref is a **stale element** now. The fix is never "strip the prefix and hope": take a snapshot and decide again. That is the model's job in the next step.
#
# ### 10. The model picks the refs
# The model gets three tools whose arguments are refs, plus the observation from lesson 08 (URL + ai snapshot). The tool bodies are empty: the model only proposes calls, and our dispatcher runs them. We ask for all calls in one reply, since this is one step, not a loop (that is lesson 12).

# %%
from langchain_core.messages import HumanMessage, SystemMessage
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

SYSTEM = ("You operate a web page through its aria snapshot. Use only refs that appear in the snapshot. "
          "Return every tool call the task needs, in order, in this one reply.")
def observation(path, snapshot):
    return f"URL: {path}\nPage (aria snapshot, act by ref):\n{snapshot}"
TASK1 = "File a new issue titled 'Export button does nothing' with the label bug."
TASK2 = "Open the issue titled 'Export button does nothing'."
plan1 = None    # filled by the model cell (stays None if it is skipped)
print("tools:", [t.name for t in (click, fill, select_option)], "| args of fill:", list(fill.args))

# %% [markdown]
# One model call: system rules, the task, and the observation of the fresh form.

# %% tags=["needs-llm"]
agent = llm.bind_tools([click, fill, select_option])
reply = agent.invoke([SystemMessage(SYSTEM),
                      HumanMessage(f"Task: {TASK1}\n\n{observation('/issues/new', seen['form_fresh'])}")])
plan1 = [{"name": c["name"], "args": c["args"]} for c in reply.tool_calls]
for call in plan1:
    print("model:", call["name"], call["args"])

# %% [markdown]
# If the model cell was skipped, this cell builds the same plan by hand from the element table (hand-written, not model output).

# %%
if plan1 is None:
    ref = {el: r for r, el in fresh.items()}
    plan1 = [{"name": "fill", "args": {"ref": ref[("textbox", "Title")], "text": "Export button does nothing"}},
             {"name": "select_option", "args": {"ref": ref[("combobox", "Label")], "option": "bug"}},
             {"name": "click", "args": {"ref": ref[("button", "Create issue")]}}]
    print("hand-written plan (no model):", [c["name"] for c in plan1])
print("refs used:", [c["args"]["ref"] for c in plan1])
print("problems:", [check_action(c, fresh) for c in plan1])

# %% [markdown]
# ### 11. Dispatch the model's plan, then re-snapshot
# Run the plan, then take a fresh snapshot. The **outcome** is what counts: the issue page's heading, not the model's claim.

# %% tags=["needs-download"]
seen["plan1"] = plan1
seen["plan1_log"] = await run_plan(page, plan1, seen["form_fresh"])
seen["issue_page"] = await page.aria_snapshot(mode="ai")
seen["issue_url"] = page.url.removeprefix(BASE)
print("\n".join(seen["plan1_log"]))

# %% [markdown]
# The log and the heading from the fresh snapshot:

# %%
def heading(snapshot):
    return re.search(r'heading "([^"]*)" \[level=1\]', snapshot).group(1)

print(f"[{seen['source']}]")
print("\n".join(seen["plan1_log"]))
print("now at", seen["issue_url"], "| heading:", heading(seen["issue_page"]))

# %% [markdown]
# The click on "Create issue" submitted the form and the app moved to `/issues/11` (10 seeded issues, so ours is #11). `run_plan` noted the page change: any later call from this plan would have been refused as stale.
#
# ### 12. Grow it: find the new issue in the list
# The second check goes through the list page. Its snapshot has a link per issue, so the model must pick one ref among eleven similar links. It gets the same tools and one call.

# %% tags=["needs-download"]
await page.goto(f"{BASE}/issues")
seen["list"] = await page.aria_snapshot(mode="ai")
print(len(elements_of(seen["list"])), "elements with refs on the list page")

# %% [markdown]
# The second model call, with the list page as the observation. `plan2` stays `None` if it is skipped.

# %% tags=["needs-llm"]
reply2 = agent.invoke([SystemMessage(SYSTEM),
                       HumanMessage(f"Task: {TASK2}\n\n{observation('/issues', seen['list'])}")])
plan2 = [{"name": c["name"], "args": c["args"]} for c in reply2.tool_calls]
print("model:", plan2)

# %% [markdown]
# Fallback (hand-written, not model output), then show which element the chosen ref names.

# %%
listing = elements_of(seen["list"])
if globals().get("plan2") is None:
    plan2 = [{"name": "click", "args": {"ref": {el: r for r, el in listing.items()}[
        ("link", "Export button does nothing")]}}]
    print("hand-written plan (no model)")
for call in plan2:
    print(call["args"]["ref"], "is", listing.get(call["args"]["ref"]), "| problem:", check_action(call, listing))

# %% [markdown]
# Dispatch the click and re-snapshot. As a last check we read the app's database directly: the screen says the issue exists, the data must agree.

# %% tags=["needs-download"]
seen["plan2_log"] = await run_plan(page, plan2, seen["list"])
seen["after_open"] = await page.aria_snapshot(mode="ai")
with sqlite3.connect(DB) as db:
    seen["db_row"] = db.execute("SELECT id, title, label, status FROM issues WHERE title = ?",
                                ("Export button does nothing",)).fetchall()
print("\n".join(seen["plan2_log"]))

# %% [markdown]
# The log, the heading from the fresh snapshot, and the database row:

# %%
print(f"[{seen['source']}]")
print("\n".join(seen["plan2_log"]))
print("heading:", heading(seen["after_open"]))
print("database:", seen["db_row"])

# %% [markdown]
# One row, label `bug`, status `open`: created once, labelled right, and found again through the list.
#
# The next cell saves this run as the recording the fallbacks use. It only runs when the browser cells ran.

# %% tags=["needs-download"]
REC_PATH.parent.mkdir(parents=True, exist_ok=True)
REC_PATH.write_text(json.dumps({k: v for k, v in seen.items() if k != "source"}, indent=1) + "\n")
print("saved", REC_PATH, "with", len(seen) - 1, "keys")

# %% [markdown]
# ## At work
# - Playwright MCP's `browser_click`, `browser_type` and `browser_fill_form` take a ref from the latest snapshot, the same shape as our tools; the Playwright docs add `page.get_by_ref(ref)` in 1.64 → lesson 27a.
# - Vendor computer-use guidance asks for a human to confirm consequential actions (submitting, buying, deleting) instead of dispatching them blindly, as we did with "Create issue" → lesson 51.
# - Page text is untrusted: an issue body can say "click Close issue", and a dispatcher that runs any valid ref will obey it → lesson 49.
# - Teams log every step's snapshot, tool call and result, because a failed run cannot be reproduced from the model alone → lessons 44a and 54.

# %% [markdown]
# ## What just happened
# - A ref became a **locator** with `page.locator("aria-ref=…")`; it found the same `<input>` as `get_by_role("textbox", name="Title")`.
# - **Action dispatch**: `check_action` vetted each tool call against the latest snapshot (known action, ref present, role fits), and `act` called `fill`, `select_option` or `click`.
# - After a reload the old refs were **stale elements**; the check refused them, and the model chose fresh `f1` refs.
# - The model filled the form and submitted it; a re-snapshot showed the new issue's heading, the model then picked its link from eleven, and the database confirmed one new `bug` issue.

# %% [markdown]
# ## Common mistakes
# Dispatching a stale ref without checking it. After the submit, `e17` (the old "Create issue" button) belongs to a page that is gone. Playwright does not click something else; it waits for an element that never comes and times out (3 s here, 30 s by default):

# %% tags=["needs-download", "raises-exception"]
await page.locator("aria-ref=e17").click()

# %% [markdown]
# Fix: check the call against the latest snapshot first. `act` returns a readable refusal the model can act on, with no wait.

# %%
stale_call = {"name": "click", "args": {"ref": "e17"}}
print(check_action(stale_call, elements_of(seen["after_open"])))

# %% [markdown]
# Two more:
# - Calling `fill` on a combobox. Playwright raises `Element is not an <input>, <textarea> or [contenteditable] element`; use `select_option`, and let the role check catch it first.
# - Trusting the model's "Done, I created the issue." Check the outcome: a fresh snapshot, and where you can, the data itself.

# %% [markdown]
# ## Try it
# On the new issue's page (open it in a fresh browser), take an ai snapshot, then write a two-call plan by hand that adds the comment "Reproduced in headless Chromium" (fill the "Comment" box, click "Add comment"). Run it with `run_plan`, re-snapshot, and print the comment's text. Then extend `check_action` so it refuses a `fill` whose text is empty.

# %%
# your code here

# %% [markdown]
# ## Key terms
# - **locator** — Playwright's description of how to find an element (`page.locator("aria-ref=e12")`, `page.get_by_role(...)`); it is resolved only when you act on it.
# - **action dispatch** — the harness step that turns a model's tool call into a real call (`fill`, `select_option`, `click`), after checking it.
# - **stale element** — an element ref from an older snapshot or a page that has since reloaded or navigated; it matches nothing and must be refused, then re-observed.
# - **re-snapshot** — taking a fresh observation after acting, to see the real outcome before the next step.

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
import llm_replay
llm_replay.stop()

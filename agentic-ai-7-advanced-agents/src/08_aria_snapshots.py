# %% [markdown]
# # 08 · Aria snapshots as observations
# Level L2 · Part 2 · core · ~30 min · builds on 02, 07

# %% [markdown]
# ## Goal
# By the end you can take a live aria snapshot of Pocket Tracker's "New issue" form with `page.aria_snapshot()`, add element refs with `mode="ai"`, turn it into a compact text observation for a model, and show with token counts that it is smaller than the HTML and the screenshot.

# %% [markdown]
# ## The idea
# In lesson 02 you read an aria snapshot from a file. Now you take one live, from the running app. An **aria snapshot** lists the page's **accessibility roles** (`textbox`, `button`, `combobox`) with their accessible names, the same view a screen reader uses. Two options make it fit for agents: you can snapshot one part of the page (a locator), and `mode="ai"` stamps each element with an **element ref** like `[ref=e12]`, a short id the model can name in its answer. The result is a text observation that is small, readable and points at things.
#
# Analogy: a waiter's order pad. It does not draw the table; it lists numbered seats, so "seat 3 wants soup" is clear.

# %% [markdown]
# ## Picture
# ```mermaid
# flowchart LR
#   P[New issue page<br/>live in Chromium] --> D["page.aria_snapshot()<br/>roles + names"]
#   P --> AI["page.aria_snapshot(mode='ai')<br/>+ [ref=eN]"]
#   AI --> O[observation text<br/>URL + snapshot]
#   O --> M[model reads it<br/>answers with a ref]
#   M -.->|lesson 09| P
# ```

# %% [markdown]
# ## Step by step
#
# ### 1. Start Pocket Tracker
# Same as lesson 07: copy the app to a scratch folder, start uvicorn on a free port, poll `/health`.

# %%
import atexit, json, os, re, shutil, socket, subprocess, sys, time
from pathlib import Path
import httpx
from playwright.async_api import async_playwright

WORK, REPO = Path("../work/08"), Path("../work/08/pocket_tracker")
shutil.rmtree(WORK, ignore_errors=True)
shutil.copytree("../apps/pocket_tracker", REPO, ignore=shutil.ignore_patterns("*.db", "__pycache__", ".pytest_cache"))
with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    PORT = s.getsockname()[1]
BASE = f"http://127.0.0.1:{PORT}"
env = {**os.environ, "POCKET_TRACKER_DB": str((WORK / "pocket_tracker.db").resolve())}
log = open(WORK / "server.log", "w")
server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
                           "--port", str(PORT)], cwd=REPO, env=env, stdout=log, stderr=log)
atexit.register(server.terminate)
deadline = time.time() + 15
while True:
    try:
        print("health:", httpx.get(f"{BASE}/health").json()); break
    except httpx.ConnectError:
        if time.time() > deadline or server.poll() is not None:
            raise RuntimeError("server did not start; see ../work/08/server.log")
        time.sleep(0.2)

# %% [markdown]
# ### 2. Browser and fallback
# The browser cells are tagged `needs-download` (lesson 07 installed Chromium). When they are skipped, `seen` holds the **recorded output** of a real run saved in `../data/recorded/08.json`, so every untagged cell still has real data.

# %% tags=["needs-download"]
out = subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], capture_output=True, text=True)
print("playwright install chromium -> exit code", out.returncode)

# %% [markdown]
# Load the recording (if there is one) as the starting value of `seen`. Live browser cells below overwrite it.

# %%
REC_PATH = Path("../data/recorded/08.json")
seen = json.loads(REC_PATH.read_text()) if REC_PATH.exists() else {}
seen["source"] = "recorded output (real run, saved earlier)"
print("fallback keys:", sorted(k for k in seen if k != "source"))

# %% [markdown]
# ### 3. Capture the form three ways
# One browser cell opens `/issues/new` at a 1024x768 viewport and takes everything we compare: the default aria snapshot (`page.aria_snapshot()`), the HTML (`page.content()`) and a PNG screenshot. We keep only the screenshot's pixel size, because (lesson 02) that is what sets its token cost.

# %% tags=["needs-download"]
from PIL import Image
import io

async with async_playwright() as p:
    browser = await p.chromium.launch()
    page = await (await browser.new_context(viewport={"width": 1024, "height": 768})).new_page()
    await page.goto(f"{BASE}/issues/new")
    png = await page.screenshot()
    seen["capture"] = {"aria": await page.aria_snapshot(), "html": await page.content(),
                       "png_size": list(Image.open(io.BytesIO(png)).size), "png_bytes": len(png)}
    await browser.close()
seen["source"] = "live run"
print("captured:", sorted(seen["capture"]))

# %% [markdown]
# Read the default snapshot. Each line is `- role "accessible name"`; children are indented below their parent.

# %%
cap = seen["capture"]
print(f"[{seen['source']}]")
print(cap["aria"])

# %% [markdown]
# Notice where the names come from. The HTML has `<label for="title">Title</label> <input id="title">`; the snapshot says `textbox "Title"`. The browser joined the label to the input, so the model sees what the field *means*, not its `id`. The `<select>` became a `combobox` with its `option`s, and the current choice is marked `[selected]`.
#
# ### 4. Accessibility roles on this page
# Count the roles. These words are the vocabulary a model reads in every snapshot.

# %%
from collections import Counter

roles = Counter(re.match(r"\s*- (\w+)", line).group(1)
                for line in cap["aria"].splitlines() if re.match(r"\s*- \w+", line))
print(dict(roles.most_common()))

# %% [markdown]
# `link`, `textbox`, `combobox`, `button` are things you can act on; `banner`, `navigation`, `main`, `form`, `paragraph` are structure; `text` is plain words; `/url` is a link's target, not a role.
#
# ### 5. Size: snapshot vs HTML vs screenshot
# Count tokens as in lesson 02: `tiktoken` with `o200k_base` for text, Claude's pixel formula for the image.

# %%
import math
os.environ["TIKTOKEN_CACHE_DIR"] = str(Path("../data/tiktoken_cache"))
import tiktoken

enc = tiktoken.get_encoding("o200k_base")
def tokens(text): return len(enc.encode(text))
def claude_image_tokens(width, height): return math.ceil(width / 28) * math.ceil(height / 28)

sizes = {"aria snapshot": tokens(cap["aria"]), "raw HTML": tokens(cap["html"]),
         "screenshot": claude_image_tokens(*cap["png_size"])}
for name, n in sizes.items():
    print(f"{name:14} {n:>5} tokens")

# %% [markdown]
# On this form the snapshot is about a third of the HTML and a sixth of the screenshot. This page is tiny and has no framework markup, so on real sites the HTML gap is usually much larger.
#
# ### 6. Snapshot only the part you need
# `aria_snapshot()` also exists on a locator, so you can snapshot one region. The form is a `form` role named "New issue" (from its `aria-label`), so `get_by_role` finds it. Lesson 09 covers locators; here we only use one.

# %% tags=["needs-download"]
async with async_playwright() as p:
    browser = await p.chromium.launch()
    page = await (await browser.new_context(viewport={"width": 1024, "height": 768})).new_page()
    await page.goto(f"{BASE}/issues/new")
    seen["form_only"] = await page.get_by_role("form", name="New issue").aria_snapshot()
    seen["ai"] = await page.aria_snapshot(mode="ai")
    seen["ai_boxes"] = await page.aria_snapshot(mode="ai", boxes=True)
    await browser.close()
seen["source"] = "live run"
print("form_only, ai, ai_boxes captured")

# %% [markdown]
# The same cell also took the `mode="ai"` snapshots used in step 7. The form alone drops the banner and navigation:

# %%
print(f"[{seen['source']}]")
print(seen["form_only"])
sizes["form only"] = tokens(seen["form_only"])
print("\nform only:", sizes["form only"], "tokens vs whole page:", sizes["aria snapshot"])

# %% [markdown]
# Scoping is a trade-off: fewer tokens, but the agent no longer sees the navigation links. It suits a step where the task is "fill this form", not one where the agent must decide where to go.
#
# ### 7. Element refs with `mode="ai"`
# A plain snapshot names elements, but two elements can share a name: here "New issue" is both a link and the form. `mode="ai"` adds a unique `[ref=eN]` to each element, and `[cursor=pointer]` to clickable ones.

# %%
print(f"[{seen['source']}]")
print(seen["ai"])

# %% [markdown]
# Collect the refs into a table the harness can keep: `role "name"` → ref. The regex reads one ref per line.

# %%
REF_LINE = re.compile(r'- (\w+)(?: "([^"]*)")?.*?\[ref=(\w+)\]')

def refs_of(snapshot):
    """Map 'role "name"' -> ref for every line that carries a ref."""
    table = {}
    for m in REF_LINE.finditer(snapshot):
        role, name, ref = m.groups()
        table[f'{role} "{name}"' if name else role] = ref
    return table

refs = refs_of(seen["ai"])
for key in ['textbox "Title"', 'combobox "Label"', 'button "Create issue"', 'link "New issue"', 'form "New issue"']:
    print(f"{key:24} -> {refs[key]}")

# %% [markdown]
# The link and the form share the name "New issue" but get different refs (`e6`, `e10`). Refs cost tokens too:

# %%
sizes["ai snapshot"] = tokens(seen["ai"])
print(f"default {sizes['aria snapshot']} tokens -> ai mode {sizes['ai snapshot']} tokens "
      f"(+{sizes['ai snapshot'] - sizes['aria snapshot']} for refs and markers)")

# %% [markdown]
# ### 8. A ref points at exactly one element
# A ref is not decoration: Playwright can turn it back into the element. In 1.63 the selector is `aria-ref=<ref>` (the docs for the next release add `page.get_by_ref(ref)`). Refs resolve against the **latest** ai snapshot of the page, so we take one first, then ask what `e12` is. We only read here; acting on refs is lesson 09.

# %% tags=["needs-download"]
async with async_playwright() as p:
    browser = await p.chromium.launch()
    page = await (await browser.new_context()).new_page()
    await page.goto(f"{BASE}/issues/new")
    snap = await page.aria_snapshot(mode="ai")
    ref = refs_of(snap)['textbox "Title"']
    target = page.locator(f"aria-ref={ref}")
    seen["resolve"] = {"ref": ref, "count": await target.count(),
                       "outer_html": await target.evaluate("el => el.outerHTML")}
    await page.reload()                                    # a new document: old refs are gone
    seen["resolve"]["count_after_reload"] = await page.locator(f"aria-ref={ref}").count()
    seen["resolve"]["ref_after_new_snapshot"] = refs_of(await page.aria_snapshot(mode="ai"))['textbox "Title"']
    await browser.close()
seen["source"] = "live run"
print(seen["resolve"])

# %% [markdown]
# What the ref resolved to, and what happened after a reload:

# %%
r = seen["resolve"]
print(f"[{seen['source']}]")
print(f"{r['ref']} matches {r['count']} element: {r['outer_html']}")
print(f"after reload, {r['ref']} matches {r['count_after_reload']} elements")
print(f"a fresh ai snapshot calls the same box {r['ref_after_new_snapshot']}")

# %% [markdown]
# `e12` is the `<input id="title">`. After the reload it matches nothing, and the new snapshot names the box `f1e12`: refs belong to one snapshot of one document. That is why an agent takes a **fresh** snapshot at every step.
#
# ### 9. Bridge to pixels: `boxes=True`
# `boxes=True` adds each element's position as `[box=x,y,width,height]` in CSS pixels. It links the text view to the screenshot (lessons 10 and 11), at a token price.

# %%
print("\n".join(l for l in seen["ai_boxes"].splitlines() if "textbox" in l or "button" in l))
sizes["ai + boxes"] = tokens(seen["ai_boxes"])
print("ai + boxes:", sizes["ai + boxes"], "tokens")

# %% [markdown]
# ### 10. Build the observation a model reads
# The observation is the ai snapshot plus the one thing it lacks: where the agent is. The snapshot already holds the heading, so we add only the URL path. This is the text a model will get every step in lesson 12.

# %%
def observation(path, snapshot):
    return f"URL: {path}\nPage (aria snapshot, act by ref):\n{snapshot}"

obs = observation("/issues/new", seen["ai"])
sizes["observation"] = tokens(obs)
for name, n in sorted(sizes.items(), key=lambda kv: kv[1]):
    print(f"{name:14} {n:>5} tokens")
print("\n" + obs[:150], "...")

# %% [markdown]
# The full observation, refs included, is still well under the HTML and the screenshot. A model answering "type into `e12`, pick `bug` in `e16`, click `e17`" gives the harness exact targets.
#
# The last browser cell saves this run as the recording the fallback uses. It only runs when the browser cells ran.

# %% tags=["needs-download"]
REC_PATH.parent.mkdir(parents=True, exist_ok=True)
REC_PATH.write_text(json.dumps({k: v for k, v in seen.items() if k != "source"}, indent=1) + "\n")
print("saved", REC_PATH, "with", sorted(k for k in seen if k != "source"))

# %% [markdown]
# ## At work
# - Playwright MCP, the browser tool many coding agents use, sends this kind of snapshot with refs by default (`--snapshot-mode full`) and its `browser_click`/`browser_type` tools take a ref; screenshots need `--caps=vision` → lesson 27a.
# - Teams keep the snapshot as the main loop and add a screenshot only when needed, because a recorded screenshot loop stores base64 images and grows fast → lessons 12 and 13.
# - Canvas charts, iframes, shadow DOM and native `alert()` dialogs are where the accessibility tree falls short, and they break real agents → lesson 42.
# - Each step's aria snapshot is stored with the action and a screenshot so a failed run can be replayed and judged → lesson 54.

# %% [markdown]
# ## What just happened
# - You took a live **aria snapshot** of the New issue page with `page.aria_snapshot()` and read its **accessibility roles**: labels became names (`textbox "Title"`).
# - A locator snapshot of just the form was smaller, but hid the navigation.
# - `mode="ai"` added an **element ref** to every element; a ref resolved to exactly one element (`aria-ref=e12` → the title input) and went stale after a reload.
# - The text observation, refs included, cost far fewer tokens than the HTML or a screenshot of the same page.

# %% [markdown]
# ## Common mistakes
# Reading refs from a default snapshot. Without `mode="ai"` there are no refs, so the harness has nothing to look up:

# %% tags=["raises-exception"]
plain_refs = refs_of(cap["aria"])             # the default snapshot from step 3
print("refs found:", plain_refs)
print("click", plain_refs['button "Create issue"'])

# %% [markdown]
# Fix: take the snapshot with `mode="ai"` whenever the model must point at elements.

# %%
print("click", refs_of(seen["ai"])['button "Create issue"'])

# %% [markdown]
# Two more:
# - Reusing an old snapshot's refs. After a reload or a form submit the page is a new document and the old ref matches nothing (step 8). Snapshot again every step.
# - Trusting the snapshot to show everything. A `<canvas>` or a hidden element is missing from it (lesson 02); add a screenshot when the task depends on what is drawn.

# %% [markdown]
# ## Try it
# Take an ai-mode snapshot of the Issues list (`/issues`) in a fresh browser. Print its tokens, the tokens of its HTML, and the refs of the "Issues" link and of the first issue's title link. Then snapshot only the table (`page.get_by_role("table")`) and compare the size.

# %%
# your code here

# %% [markdown]
# ## Key terms
# - **aria snapshot** — Playwright's YAML text form of the accessibility tree, from `page.aria_snapshot()` or `locator.aria_snapshot()`.
# - **accessibility role** — what an element is for assistive tech (`textbox`, `button`, `combobox`, `link`), shown first on each snapshot line with the element's accessible name.
# - **element ref** — a short id like `e12` that `aria_snapshot(mode="ai")` gives each element; it resolves to exactly one element, only for the latest snapshot of that document.
# - **ai mode** — `aria_snapshot(mode="ai")`: a snapshot with refs and pointer markers, made for models.

# %% [markdown]
# Always run this cell, and run it last: it stops the server.

# %%
# must be the last cell run: it stops the Pocket Tracker server
server.terminate()
try:
    server.wait(timeout=10)
    how = "terminated"
except subprocess.TimeoutExpired:
    server.kill()
    server.wait()
    how = "killed"
log.close()
print(f"server {how}, exit code {server.returncode}")

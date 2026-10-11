# %% [markdown]
# # 07 · Playwright: launching headless Chromium
# Level L2 · Part 2 · core · ~30 min · builds on 06

# %% [markdown]
# ## Goal
# By the end you can launch headless Chromium with Playwright's async API, which Jupyter supports directly with top-level `await`, open Pocket Tracker in a browser context, read the page title and every issue row, move between pages, and close everything cleanly.

# %% [markdown]
# ## The idea
# In lesson 06 you read Pocket Tracker with `httpx`: raw HTML, no browser. Agents that use the web need a real browser, because real pages run JavaScript, keep cookies and change after load. **Playwright** is a library that drives Chromium, Firefox and WebKit from Python. A **headless browser** is a full browser with no window: it loads, renders and runs scripts exactly as usual, but nothing is drawn on a screen, so it runs on servers and in CI.
#
# Playwright has three layers: one **browser** process, many **browser contexts** inside it (each a fresh, private profile with its own cookies and storage), and **pages** (tabs) inside a context.
#
# Analogy: the browser is a hotel, each context is a locked room with its own guest, and pages are the windows of a room.

# %% [markdown]
# ## Picture
# ```mermaid
# flowchart LR
#   PY[notebook<br/>async API + await] --> PW[Playwright driver]
#   PW --> B[Chromium browser<br/>headless]
#   B --> C1[context A<br/>own cookies + storage]
#   B --> C2[context B<br/>own cookies + storage]
#   C1 --> P1[page: /issues]
#   C2 --> P2[page: /issues]
#   P1 -->|HTTP| S[Pocket Tracker<br/>127.0.0.1]
#   P2 -->|HTTP| S
# ```

# %% [markdown]
# ## Step by step
#
# ### 1. Start Pocket Tracker
# Same as lesson 06: copy the app to a scratch folder, start uvicorn on 127.0.0.1 on a free port, poll `/health`. `atexit` stops the server even if you never reach the last cell.

# %%
import atexit, json, os, shutil, socket, subprocess, sys, time
from pathlib import Path
from urllib.parse import urlparse
import httpx
from playwright.async_api import async_playwright   # the async API: use with `await`

WORK, REPO = Path("../work/07"), Path("../work/07/pocket_tracker")
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
atexit.register(server.terminate)        # safety net if the kernel exits early
deadline = time.time() + 15
while True:
    try:
        print("health:", httpx.get(f"{BASE}/health").json()); break
    except httpx.ConnectError:
        if time.time() > deadline or server.poll() is not None:
            raise RuntimeError("server did not start; see ../work/07/server.log")
        time.sleep(0.2)

# %% [markdown]
# ### 2. Install the browser
# `pip install playwright` gives you the Python package only. The browser is a separate download (about 115 MB for the headless shell), stored once per machine under `~/.cache/ms-playwright`. The cell is tagged `needs-download`; if the browser is already there, it finishes in a second.

# %% tags=["needs-download"]
out = subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"],
                     capture_output=True, text=True)
print("playwright install chromium -> exit code", out.returncode)
print((out.stdout + out.stderr).strip()[-300:] or "(already installed, nothing downloaded)")

# %% [markdown]
# Every browser cell below is tagged `needs-download` too. Its results go into a dict `seen`. When the cells are skipped (no browser on this machine), `seen` holds the **recorded output** of a real run saved in `../data/recorded/07.json`, so the untagged cells still have real data to work with.

# %%
REC_PATH = Path("../data/recorded/07.json")
seen = json.loads(REC_PATH.read_text()) if REC_PATH.exists() else {}
seen["source"] = "recorded output (real run, saved earlier)"
print("fallback keys:", sorted(k for k in seen if k != "source"))

# %% [markdown]
# ### 3. Launch, open a context, open a page
# Playwright has two Python APIs with the same methods: the sync API (`playwright.sync_api`) and the async API (`playwright.async_api`). We use Playwright's async API, which Jupyter supports directly with top-level `await`: every call that talks to the browser gets an `await` in front. In a plain `.py` script you'd use `sync_playwright` (no `await`), or wrap this same async code in `async def main()` and call `asyncio.run(main())`.
#
# This is the standard shape of a Playwright script. `async with async_playwright() as p` starts the Playwright driver and stops it at the end, even on an error. `launch(headless=True)` starts Chromium without a window (headless is also the default). `new_context` creates a private profile with a fixed window size, and `goto` loads the URL and waits for the `load` event.

# %% tags=["needs-download"]
async with async_playwright() as p:
    browser = await p.chromium.launch(headless=True)
    context = await browser.new_context(viewport={"width": 1024, "height": 768})
    page = await context.new_page()
    response = await page.goto(f"{BASE}/issues")
    seen["first_visit"] = {"browser": f"{p.chromium.name} {browser.version}", "status": response.status,
                           "path": urlparse(page.url).path, "title": await page.title(),
                           "open_count": await page.locator("#open-count").inner_text(),
                           "user_agent": await page.evaluate("navigator.userAgent")}
    await browser.close()
seen["source"] = "live run"
print(json.dumps(seen["first_visit"], indent=1))

# %% [markdown]
# Read what came back (from the live run, or the recording if the cell was skipped):

# %%
v = seen["first_visit"]
print(f"[{seen['source']}]")
print(f"{v['browser']}: GET {v['path']} -> {v['status']}, title {v['title']!r}")
print("open-count line:", v["open_count"])
print("headless shows in the user agent:", "HeadlessChrome" in v["user_agent"])

# %% [markdown]
# The title is the HTML `<title>` (`Issues · Pocket Tracker`). `page.evaluate` ran a line of JavaScript inside the page: the user agent says `HeadlessChrome`, which is how many real sites spot automated browsers. The page still says "10 open issues", seeded bug #5 from lesson 06; the browser shows bugs, it does not hide them.
#
# ### 4. List the issue rows
# `page.locator("tbody tr")` finds every table row; `await .all()` gives one locator per row, and `all_inner_texts()` reads the visible text of its cells. Locators are lesson 09's topic; here we only read.

# %% tags=["needs-download"]
async with async_playwright() as p:
    browser = await p.chromium.launch()
    page = await (await browser.new_context()).new_page()
    await page.goto(f"{BASE}/issues")
    rows = [await row.locator("td").all_inner_texts() for row in await page.locator("tbody tr").all()]
    seen["rows"] = {"caption": await page.locator("caption").inner_text(), "rows": rows}
    await browser.close()
seen["source"] = "live run"
print(len(seen["rows"]["rows"]), "rows read")

# %% [markdown]
# Print the rows as a table, then check them against the JSON API from lesson 06. The browser and the API should tell the same story.

# %%
print(f"[{seen['source']}]  {seen['rows']['caption']}")
for num, title, label, status, comments in seen["rows"]["rows"]:
    print(f"#{num:<3}{status:7}{label:8}{title}")
api = {str(i["id"]): i["title"] for i in httpx.get(f"{BASE}/api/issues").json()}
print("matches /api/issues:", {r[0]: r[1] for r in seen["rows"]["rows"]} == api)

# %% [markdown]
# Ten rows, same ids and titles as the API. Note the label column shows `none` for an empty label: the page renders data, it is not the data. An agent that reads the page must learn the page's conventions.
#
# ### 5. Move between pages
# A page keeps a history like a browser tab. Here we go to issue #1, read its heading, then `go_back()` to the list and filter it by URL to closed issues only.

# %% tags=["needs-download"]
async with async_playwright() as p:
    browser = await p.chromium.launch()
    page = await (await browser.new_context()).new_page()
    await page.goto(f"{BASE}/issues")
    steps = []
    await page.goto(f"{BASE}/issues/1")
    steps.append(("goto /issues/1", urlparse(page.url).path, await page.locator("h1").inner_text()))
    await page.go_back()
    steps.append(("go_back", urlparse(page.url).path, await page.locator("h1").inner_text()))
    await page.goto(f"{BASE}/issues?status=closed")
    steps.append(("goto ?status=closed", urlparse(page.url).path,
                  await page.locator("caption").inner_text()))
    await browser.close()
seen["navigation"] = steps
seen["source"] = "live run"
print(len(seen["navigation"]), "steps done")

# %% [markdown]
# Print where each step landed and what the page said there:

# %%
print(f"[{seen['source']}]")
for step, path, text in seen["navigation"]:
    print(f"{step:22} at {path:14} reads {text!r}")

# %% [markdown]
# Each step lands where expected: the issue page, back to the list, then a list of 1 issue (#10, the only closed one).
#
# ### 6. Contexts are isolated
# One browser can hold many contexts. Each starts empty: no cookies, no storage, no history. Here context A stores a value in the page's `localStorage`; context B, in the same browser on the same URL, sees nothing.

# %% tags=["needs-download"]
async with async_playwright() as p:
    browser = await p.chromium.launch()
    a, b = await browser.new_context(), await browser.new_context()
    page_a, page_b = await a.new_page(), await b.new_page()
    await page_a.goto(f"{BASE}/issues")
    await page_b.goto(f"{BASE}/issues")
    await page_a.evaluate("localStorage.setItem('last_seen_issue', '7')")
    seen["contexts"] = {"contexts_in_browser": len(browser.contexts),
                        "A reads": await page_a.evaluate("localStorage.getItem('last_seen_issue')"),
                        "B reads": await page_b.evaluate("localStorage.getItem('last_seen_issue')")}
    await a.close(); await b.close(); await browser.close()
seen["source"] = "live run"
print(seen["contexts"])

# %% [markdown]
# What each context read back:

# %%
c = seen["contexts"]
print(f"[{seen['source']}] {c['contexts_in_browser']} contexts in one browser")
print("context A reads:", repr(c["A reads"]), "| context B reads:", repr(c["B reads"]))

# %% [markdown]
# A reads `'7'`, B reads `None`. Contexts are cheap (milliseconds) compared with launching a browser (around a second), so the usual pattern is one browser per process and one fresh context per task or per agent: every run starts clean and cannot see another run's login.
#
# The last browser cell saves this run's outputs as the recording the fallback uses. It only runs when the browser cells ran.

# %% tags=["needs-download"]
REC_PATH.parent.mkdir(parents=True, exist_ok=True)
REC_PATH.write_text(json.dumps({k: v for k, v in seen.items() if k != "source"}, indent=1) + "\n")
print("saved", REC_PATH, "with", sorted(k for k in seen if k != "source"))

# %% [markdown]
# ## At work
# - Coding agents get browser control through Playwright MCP, which runs headless, uses an `--isolated` profile per session and returns accessibility snapshots instead of pixels → lesson 27a.
# - Playwright's own Docker image is "not recommended for visiting untrusted websites"; production browser agents run as a non-root user with a seccomp profile, and Playwright MCP's `--allowed-origins` is explicitly not a security boundary → lesson 52.
# - A fresh context per task keeps runs apart, but agents that must stay logged in reuse saved storage state or a persistent profile, which then becomes a secret to protect → lesson 42a.
# - When a browser run fails, teams look at a per-step record: screenshot, aria snapshot, action log and a Playwright trace zip → lesson 54.

# %% [markdown]
# ## What just happened
# - **Playwright** downloaded its own Chromium once, then drove it from Python with the async API and top-level `await`.
# - Chromium ran as a **headless browser**: full rendering and JavaScript, no window, and a `HeadlessChrome` user agent.
# - Each cell followed one shape: `async with async_playwright()` → `await launch()` → `await new_context()` → `await new_page()` → `await goto()` → read → `await close()`.
# - You read the title and all ten issue rows, and they matched `/api/issues`.
# - Two **browser contexts** in one browser did not share storage: each task can start clean.
# - Jupyter already runs an asyncio loop, so the async API with top-level `await` fits it directly; the sync API is for plain scripts.

# %% [markdown]
# ## Common mistakes
# Using the sync API in a notebook. It is what most scripts and tutorials show, but Jupyter runs an asyncio loop in the main thread, and the sync API checks for it before doing anything:

# %% tags=["raises-exception"]
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    print(p.chromium.launch().version)

# %% [markdown]
# Fix: in a notebook use the async API with `await`, as in steps 3 to 6 (in a plain `.py` script `sync_playwright` works as is). Starting the driver needs no browser download, so this runs everywhere:

# %%
async with async_playwright() as p:
    print("with the async API the driver starts:", p.chromium.name)

# %% [markdown]
# Two more:
# - Keeping one context for many tasks. Cookies, storage and open pages leak from one task into the next; create a new context per task.
# - Never closing the browser. Each forgotten `launch()` leaves Chromium processes behind until the kernel dies. `async with async_playwright()` stops the driver and its browsers when the block ends, even on an error.

# %% [markdown]
# ## Try it
# Write it as `async def rows_with_status(status)` and `await` it: it opens `/issues?status=<status>` in a fresh context and returns the issue rows as `(id, title)` pairs. Await it for `"closed"` (expect only #10) and `"open"` (expect nine rows). Bonus: also return the `#open-count` text: does it change with the filter?

# %%
# your code here

# %% [markdown]
# ## Key terms
# - **Playwright** — a library that drives Chromium, Firefox and WebKit from code; in Jupyter use its async API with top-level `await`; in a plain script use the sync API (`sync_playwright`) or `asyncio.run`.
# - **headless browser** — a full browser that renders and runs JavaScript but draws no window; used on servers, in CI and by agents.
# - **browser context** — an isolated profile inside one browser process, with its own cookies, storage and pages; cheap to create, so use one per task.
# - **page** — one tab inside a context; `goto`, `go_back`, `title` and `locator` work on it.

# %% [markdown]
# Always run this cell, and run it last: it stops the server, even if earlier cells failed. After it, no cell above can reach Pocket Tracker.

# %%
# must be the last cell run: it stops the Pocket Tracker server
server.terminate()                      # sends SIGTERM
try:
    server.wait(timeout=10)
    how = "terminated"
except subprocess.TimeoutExpired:
    server.kill()                       # SIGKILL if it ignores SIGTERM
    server.wait()
    how = "killed"
log.close()
print(f"server {how}, exit code {server.returncode} (-15 = stopped by SIGTERM)")

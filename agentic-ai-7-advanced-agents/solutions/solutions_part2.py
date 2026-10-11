# %% [markdown]
# # Solutions · Part 2: Driving a browser
# Answers to the "Try it" exercises. Try them yourself first.

# %% [markdown]
# ## Lesson 06
# Start a fresh copy of Pocket Tracker (same steps as the lesson), then check issue #2 over HTTP.

# %%
import os, shutil, socket, subprocess, sys, time
from pathlib import Path
import httpx

WORK = Path("../work/sol06")
REPO = WORK / "pocket_tracker"
shutil.rmtree(WORK, ignore_errors=True)
shutil.copytree("../apps/pocket_tracker", REPO, ignore=shutil.ignore_patterns("*.db", "__pycache__", ".pytest_cache"))
subprocess.run(["git", "init", "-q", "-b", "main"], cwd=REPO)
with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    BASE = f"http://127.0.0.1:{s.getsockname()[1]}"
env = {**os.environ, "POCKET_TRACKER_DB": str((WORK / "pocket_tracker.db").resolve())}
server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
                           "--port", BASE.rsplit(":", 1)[1]], cwd=REPO, env=env,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
for _ in range(75):
    try:
        print("health:", httpx.get(f"{BASE}/health").json()); break
    except httpx.ConnectError:
        time.sleep(0.2)

# %% [markdown]
# The check: both spellings must return exactly issue #1. While the bug is there, both find nothing (the title has a capital L), so there are two problems.

# %%
def check_issue_2(base_url):
    problems = []
    for q in ["login", "LOGIN"]:
        ids = [i["id"] for i in httpx.get(f"{base_url}/api/issues", params={"q": q}).json()]
        if ids != [1]:
            problems.append(f"q={q!r} returned {ids}, expected [1]")
    return problems

problems = check_issue_2(BASE)
print(*problems, sep="\n")
assert len(problems) == 2

# %% [markdown]
# The responsible line: SQLite's `instr()` matches exactly, so case matters. `git grep` searches tracked files, so stage them first.

# %%
subprocess.run(["git", "add", "-A"], cwd=REPO)
print(subprocess.run(["git", "grep", "-n", "instr"], cwd=REPO, capture_output=True, text=True).stdout)
server.terminate(); server.wait(timeout=10)
print("server stopped")

# %% [markdown]
# ## Lesson 07
# Start a fresh Pocket Tracker (as in the lesson). Playwright's async API runs directly in Jupyter with top-level `await`.

# %%
import atexit
from playwright.async_api import async_playwright

WORK7, REPO7 = Path("../work/sol07"), Path("../work/sol07/pocket_tracker")
shutil.rmtree(WORK7, ignore_errors=True)
shutil.copytree("../apps/pocket_tracker", REPO7, ignore=shutil.ignore_patterns("*.db", "__pycache__", ".pytest_cache"))
with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    BASE7 = f"http://127.0.0.1:{s.getsockname()[1]}"
env7 = {**os.environ, "POCKET_TRACKER_DB": str((WORK7 / "pocket_tracker.db").resolve())}
server7 = subprocess.Popen([sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
                            "--port", BASE7.rsplit(":", 1)[1]], cwd=REPO7, env=env7,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
atexit.register(server7.terminate)
for _ in range(75):
    try:
        print("health:", httpx.get(f"{BASE7}/health").json()); break
    except httpx.ConnectError:
        time.sleep(0.2)

# %% [markdown]
# One fresh context per call; rows as `(id, title)` pairs plus the open-count line. The count stays "10 open issues" whatever the filter: it ignores the filter and also counts the closed issue (seeded bug #5).

# %% tags=["needs-download"]
async def rows_with_status(status):
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await (await browser.new_context()).new_page()
        await page.goto(f"{BASE7}/issues?status={status}")
        rows = [tuple((await r.locator("td").all_inner_texts())[:2]) for r in await page.locator("tbody tr").all()]
        count = await page.locator("#open-count").inner_text()
        await browser.close()
    return rows, count

for status in ["closed", "open"]:
    rows, count = await rows_with_status(status)
    print(f"{status}: {len(rows)} rows, first {rows[0]}, open-count {count!r}")
    assert status != "closed" or [r[0] for r in rows] == ["10"]

# %% [markdown]
# Always run: stop the server.

# %%
server7.terminate()
try:
    server7.wait(timeout=10)
except subprocess.TimeoutExpired:
    server7.kill(); server7.wait()
print("server stopped")

# %% [markdown]
# ## Lesson 08
# Start a fresh Pocket Tracker, then snapshot `/issues` in ai mode, compare with its HTML, read two refs, and snapshot just the table.

# %%
import math, re
os.environ["TIKTOKEN_CACHE_DIR"] = str(Path("../data/tiktoken_cache"))
import tiktoken

WORK8, REPO8 = Path("../work/sol08"), Path("../work/sol08/pocket_tracker")
shutil.rmtree(WORK8, ignore_errors=True)
shutil.copytree("../apps/pocket_tracker", REPO8, ignore=shutil.ignore_patterns("*.db", "__pycache__", ".pytest_cache"))
with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    BASE8 = f"http://127.0.0.1:{s.getsockname()[1]}"
env8 = {**os.environ, "POCKET_TRACKER_DB": str((WORK8 / "pocket_tracker.db").resolve())}
server8 = subprocess.Popen([sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
                            "--port", BASE8.rsplit(":", 1)[1]], cwd=REPO8, env=env8,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
atexit.register(server8.terminate)
for _ in range(75):
    try:
        print("health:", httpx.get(f"{BASE8}/health").json()); break
    except httpx.ConnectError:
        time.sleep(0.2)

# %% [markdown]
# The first issue's title is a link inside the first data row; we find its ref by matching the title from `/api/issues`. The table-only snapshot drops the banner, navigation, chart and buttons.

# %% tags=["needs-download"]
enc = tiktoken.get_encoding("o200k_base")
first_title = httpx.get(f"{BASE8}/api/issues").json()[0]["title"]
async with async_playwright() as p:
    browser = await p.chromium.launch()
    page = await (await browser.new_context(viewport={"width": 1024, "height": 768})).new_page()
    await page.goto(f"{BASE8}/issues")
    snap = await page.aria_snapshot(mode="ai")
    html = await page.content()
    table = await page.get_by_role("table").aria_snapshot(mode="ai")
    await browser.close()
link_ref = lambda name: re.search(rf'link "{re.escape(name)}" \[ref=(\w+)\]', snap).group(1)
print("ai snapshot:", len(enc.encode(snap)), "tokens | HTML:", len(enc.encode(html)), "tokens")
print('link "Issues" ->', link_ref("Issues"), f'| link "{first_title}" ->', link_ref(first_title))
print("table only:", len(enc.encode(table)), "tokens")

# %% [markdown]
# Always run: stop the server.

# %%
server8.terminate()
try:
    server8.wait(timeout=10)
except subprocess.TimeoutExpired:
    server8.kill(); server8.wait()
print("server stopped")

# %% [markdown]
# ## Lesson 09
# Start a fresh Pocket Tracker, create the issue, then add a comment by ref with a hand-written two-call plan. `elements_of`, `check_action`, `act` and `run_plan` are copied from the lesson; `check_action` gets the extra empty-text rule.

# %%

WORK9, REPO9 = Path("../work/sol09"), Path("../work/sol09/pocket_tracker")
shutil.rmtree(WORK9, ignore_errors=True)
shutil.copytree("../apps/pocket_tracker", REPO9, ignore=shutil.ignore_patterns("*.db", "__pycache__", ".pytest_cache"))
with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    BASE9 = f"http://127.0.0.1:{s.getsockname()[1]}"
env9 = {**os.environ, "POCKET_TRACKER_DB": str((WORK9 / "pocket_tracker.db").resolve())}
server9 = subprocess.Popen([sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
                            "--port", BASE9.rsplit(":", 1)[1]], cwd=REPO9, env=env9,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
atexit.register(server9.terminate)
for _ in range(75):
    try:
        print("health:", httpx.get(f"{BASE9}/health").json()); break
    except httpx.ConnectError:
        time.sleep(0.2)
issue_id = httpx.post(f"{BASE9}/issues", data={"title": "Export button does nothing", "label": "bug"}).headers["location"]
print("created", issue_id)

# %% [markdown]
# The lesson's harness, with one new rule in `check_action`: a `fill` with empty text is refused.

# %%
REF_LINE = re.compile(r'- (\w+)(?: "([^"]*)")?.*?\[ref=(\w+)\]')
ALLOWED = {"click": {"button", "link"}, "fill": {"textbox", "searchbox"}, "select_option": {"combobox"}}

def elements_of(snapshot):
    return {ref: (role, name) for role, name, ref in REF_LINE.findall(snapshot)}

def check_action(call, elements):
    name, ref = call["name"], call["args"].get("ref")
    if name not in ALLOWED:
        return f"unknown action {name!r}"
    if ref not in elements:
        return f"ref {ref!r} is not in the latest snapshot: take a new snapshot"
    if elements[ref][0] not in ALLOWED[name]:
        return f"cannot {name} a {elements[ref][0]}"
    if name == "fill" and not call["args"].get("text", "").strip():
        return "fill needs non-empty text"
    return None

async def run_plan(page, calls, snapshot):
    elements, log = elements_of(snapshot), []
    for call in calls:
        url, problem = page.url, check_action(call, elements)
        if problem:
            log.append(f"{call['name']} -> refused: {problem}"); continue
        target = page.locator(f"aria-ref={call['args']['ref']}")
        await (target.click() if call["name"] == "click" else target.fill(call["args"]["text"]))
        await page.wait_for_load_state()
        log.append(f"{call['name']} {elements[call['args']['ref']]} -> ok")
        if page.url != url:
            elements = {}
    return log

# %% [markdown]
# Snapshot the issue page, read the refs of the comment box and button, run the plan, re-snapshot. The empty-text check is tested on the same snapshot first.

# %% tags=["needs-download"]
async with async_playwright() as p:
    browser = await p.chromium.launch()
    page = await (await browser.new_context()).new_page()
    page.set_default_timeout(3000)
    await page.goto(f"{BASE9}{issue_id}")
    snap = await page.aria_snapshot(mode="ai")
    ref = {el: r for r, el in elements_of(snap).items()}
    print("empty fill ->", check_action({"name": "fill", "args": {"ref": ref[("textbox", "Comment")], "text": " "}},
                                        elements_of(snap)))
    plan = [{"name": "fill", "args": {"ref": ref[("textbox", "Comment")], "text": "Reproduced in headless Chromium"}},
            {"name": "click", "args": {"ref": ref[("button", "Add comment")]}}]
    print("\n".join(await run_plan(page, plan, snap)))
    after = await page.aria_snapshot(mode="ai")
    await browser.close()
print([l.strip() for l in after.splitlines() if "article" in l or "Reproduced" in l])

# %% [markdown]
# Always run: stop the server.

# %%
server9.terminate()
try:
    server9.wait(timeout=10)
except subprocess.TimeoutExpired:
    server9.kill(); server9.wait()
print("server stopped")

# %% [markdown]
# ## Lesson 10
# Works offline on the recorded 1920x1080 screenshot. The token helpers and `resized_size` are copied from the lesson (Claude's published reference implementation).

# %%
import base64, math
from pathlib import Path
from PIL import Image

def claude_tokens(w, h):
    return math.ceil(w / 28) * math.ceil(h / 28)

def openai_tokens(w, h, budget=2500, multiplier=1.2):
    patches = math.ceil(w / 32) * math.ceil(h / 32)
    if patches > budget:
        scale = math.sqrt(budget / patches)
        w, h = int(w * scale), int(h * scale)
        patches = math.ceil(w / 32) * math.ceil(h / 32)
    return math.ceil(patches * multiplier)

def resized_size(width, height, max_edge=1568, max_tokens=1568):
    def fits(w, h):
        return (math.ceil(w / 28) * 28 <= max_edge and math.ceil(h / 28) * 28 <= max_edge
                and claude_tokens(w, h) <= max_tokens)
    if fits(width, height):
        return (width, height)
    if height > width:
        rh, rw = resized_size(height, width, max_edge, max_tokens)
        return (rw, rh)
    aspect, lo, hi = width / height, 1, width
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        lo, hi = (mid, hi) if fits(mid, max(round(mid / aspect), 1)) else (lo, mid)
    return (lo, max(round(lo / aspect), 1))

# %% [markdown]
# Resize to the 1000-token budget, save PNG and JPEG, and compare with a 1280x720 viewport.

# %%
OUT = Path("../work/sol10"); OUT.mkdir(parents=True, exist_ok=True)
big = Image.open("../data/recorded/10_issues_1920x1080.png").convert("RGB")
size = resized_size(*big.size, max_edge=2576, max_tokens=1000)
img = big.resize(size, Image.LANCZOS)
img.save(OUT / "s.png"); img.save(OUT / "s.jpg", quality=70)
b64 = lambda p: len(base64.b64encode(p.read_bytes())) / 1024
print(f"{size[0]}x{size[1]}: Claude {claude_tokens(*size)}, OpenAI {openai_tokens(*size)} tokens; "
      f"PNG {b64(OUT / 's.png'):.1f} KB, JPEG q70 {b64(OUT / 's.jpg'):.1f} KB base64")
print(f"1280x720 viewport: Claude {claude_tokens(1280, 720)}, OpenAI {openai_tokens(1280, 720)} tokens")

# %% [markdown]
# The downscaled image fits the 1000-token budget and is cheaper than a 1280x720 viewport (1196 Claude tokens). Still, a 1280x720 viewport renders text at native size, with no resize blur, and nothing to scale back when clicking. Pick the viewport when you control the browser; downscale only images you do not control.

# %% [markdown]
# ## Lesson 11
# Works offline on the recorded CSS boxes (`../data/recorded/11.json`). The boxes are in CSS pixels, so they are the same on a 1.5x screen. `resized_size` is Claude's reference implementation, as in lessons 10 and 11.

# %%
import json, math

boxes = json.loads(open("../data/recorded/11.json").read())["boxes"]
CSS_W, CSS_H = 1024, 768

def resized_size(width, height, max_edge=1568, max_tokens=1568):
    def fits(w, h):
        return (math.ceil(w / 28) * 28 <= max_edge and math.ceil(h / 28) * 28 <= max_edge
                and math.ceil(w / 28) * math.ceil(h / 28) <= max_tokens)
    if fits(width, height):
        return (width, height)
    aspect, lo, hi = width / height, 1, width
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        lo, hi = (mid, hi) if fits(mid, max(round(mid / aspect), 1)) else (lo, mid)
    return (lo, max(round(lo / aspect), 1))

def hit(x, y):
    return next((b["name"] for b in boxes if b["box"][0] <= x <= b["box"][0] + b["box"][2]
                 and b["box"][1] <= y <= b["box"][1] + b["box"][3]), None)

# %% [markdown]
# Play the standard-tier model on the 1536x1152 screenshot, convert back with the real scale factor, then with a hard-coded 2.

# %%
def to_css(mx, my, size, shot, dpr):
    mx, my = min(max(mx, 0), size[0]), min(max(my, 0), size[1])
    return (mx / size[0] * shot[0] / dpr, my / size[1] * shot[1] / dpr)

DPR, SHOT = 1.5, (1536, 1152)
size = resized_size(*SHOT)
fx, fy, fw, fh = next(b["box"] for b in boxes if b["name"] == "Filter")
aim = (fx + fw / 2, fy + fh / 2)
answer = (round(aim[0] / CSS_W * size[0]), round(aim[1] / CSS_H * size[1]))
good = to_css(*answer, size, SHOT, DPR)
bad = to_css(*answer, size, SHOT, 2)                  # hard-coded factor of 2
print("model sees", size, "| answer", answer)
print(f"real factor 1.5 -> ({good[0]:.1f}, {good[1]:.1f}) hits {hit(*good)}")
print(f"hard-coded 2    -> ({bad[0]:.1f}, {bad[1]:.1f}) hits {hit(*bad)}")

# %% [markdown]
# With the real factor the click lands on Filter. Hard-coding 2 shrinks every point to 75% of where it should be, so it misses. Read `devicePixelRatio` (or the screenshot size) at run time instead of assuming it.

# %% [markdown]
# ## Lesson 12
# Start a fresh Pocket Tracker, write the check for the new task, and test it on the untouched database (it must fail).

# %%
import sqlite3

WORK12, REPO12 = Path("../work/sol12"), Path("../work/sol12/pocket_tracker")
DB12 = (WORK12 / "pocket_tracker.db").resolve()
shutil.rmtree(WORK12, ignore_errors=True)
shutil.copytree("../apps/pocket_tracker", REPO12, ignore=shutil.ignore_patterns("*.db", "__pycache__", ".pytest_cache"))
with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    BASE12 = f"http://127.0.0.1:{s.getsockname()[1]}"
server12 = subprocess.Popen([sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
                             "--port", BASE12.rsplit(":", 1)[1]], cwd=REPO12,
                            env={**os.environ, "POCKET_TRACKER_DB": str(DB12)},
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
atexit.register(server12.terminate)
for _ in range(75):
    try:
        print("health:", httpx.get(f"{BASE12}/health").json()); break
    except httpx.ConnectError:
        time.sleep(0.2)

# %% [markdown]
# The check: same shape as `check_outcome`, with the target chosen by label `docs`.

# %%
def read_rows12():
    with sqlite3.connect(DB12) as db:
        rows = db.execute("SELECT id, label, status, created_at FROM issues ORDER BY id").fetchall()
    return {r[0]: {"label": r[1], "status": r[2], "created_at": r[3]} for r in rows}

def check_docs_outcome(before, after):
    docs = [i for i, r in before.items() if r["status"] == "open" and r["label"] == "docs"]
    target, problems = min(docs, key=lambda i: before[i]["created_at"]), []
    if after.get(target, {}).get("status") != "closed":
        problems.append(f"#{target} (the target) is still open")
    for i in set(before) | set(after):
        if i != target and before.get(i, {}).get("status") != after.get(i, {}).get("status"):
            problems.append(f"#{i} changed status")
    return problems

before12 = read_rows12()
print("untouched:", check_docs_outcome(before12, before12))

# %% [markdown]
# The lesson's harness pieces (copied), then two hand-written steps: click the target's link, then "Close issue". Each step starts from a fresh `observe`.

# %%
# A name containing ' makes the snapshot quote the whole line ('link "Typo ... ''Trakcer'' ..."'),
# so the pattern allows an optional leading quote (lesson 09's version skips such lines).
REF_LINE = re.compile(r'''- '?(\w+)(?: "([^"]*)")?.*?\[ref=(\w+)\]''')
ALLOWED = {"click": {"button", "link"}, "fill": {"textbox", "searchbox"}, "select_option": {"combobox"}}

def elements_of(snapshot):
    return {ref: (role, name) for role, name, ref in REF_LINE.findall(snapshot)}

async def observe(page):
    global latest
    latest = await page.aria_snapshot(mode="ai")
    return latest

async def do_step(page, calls):
    elements = elements_of(latest)
    for call in calls:
        ref = call["args"]["ref"]
        if ref not in elements or elements[ref][0] not in ALLOWED[call["name"]]:
            return f"refused: {call}"
        await page.locator(f"aria-ref={ref}").click()
        await page.wait_for_load_state()
        return f"ok: click {elements[ref]}"      # stop after a click

def ref_of(role, name_start):
    """Ref of the first element with this role whose name starts with name_start."""
    return next(r for r, (ro, n) in elements_of(latest).items() if ro == role and n.startswith(name_start))

# %% [markdown]
# Drive it by hand in a fresh browser, then check the database again.

# %% tags=["needs-download"]
async with async_playwright() as p:
    browser = await p.chromium.launch()
    page = await (await browser.new_context()).new_page()
    page.set_default_timeout(3000)
    await page.goto(f"{BASE12}/issues")
    await observe(page)
    print(await do_step(page, [{"name": "click", "args": {"ref": ref_of("link", "Typo on the About page")}}]))
    await observe(page)
    print(await do_step(page, [{"name": "click", "args": {"ref": ref_of("button", "Close issue")}}]))
    await browser.close()
print("after the hand-driven run:", check_docs_outcome(before12, read_rows12()) or "verified")

# %% [markdown]
# Stop the server.

# %%
server12.terminate(); server12.wait(timeout=10)
print("server stopped")

# %% [markdown]
# ## Lesson 13
# A small harness on the recorded 2x screen (no browser, no key): the lesson's batch rules plus a `scroll` member. On a live page, `scroll` would call `page.mouse.move(x, y)` then `page.mouse.wheel(dx, dy)`.

# %%
import asyncio, base64, io, json
from pathlib import Path
import anthropic
from PIL import Image

REC13 = Path("../data/recorded")
VIEW13 = (1024, 768)
OK13 = [{"type": "text", "text": "OK"}]
HALT13 = "Not executed: an earlier computer action in this turn failed."
wheel_log = []                                    # what a live page.mouse.wheel would receive

def in_view13(x, y):
    if not (0 <= x < VIEW13[0] and 0 <= y < VIEW13[1]):
        raise ValueError(f"coordinate ({x}, {y}) is outside the {VIEW13[0]}x{VIEW13[1]} screen")
    return x, y

def png_block13(img):
    buf = io.BytesIO(); img.save(buf, format="PNG")
    return {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                        "data": base64.b64encode(buf.getvalue()).decode()}}

# %% [markdown]
# The members: `screenshot`, `left_click` (bounds check only here) and the new `scroll`, 100 px per wheel click.

# %%
async def screenshot13():
    full = Image.open(REC13 / "13_list_dpr2.png")
    return [png_block13(full.resize(VIEW13, Image.LANCZOS))]

async def left_click13(coordinate, text=None):
    in_view13(*coordinate)
    return OK13

async def scroll13(scroll_direction, scroll_amount, coordinate=None, text=None):
    if coordinate:
        in_view13(*coordinate)
    dx, dy = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}[scroll_direction]
    wheel_log.append((coordinate, dx * 100 * scroll_amount, dy * 100 * scroll_amount))
    return OK13

HANDLERS13 = {"screenshot": screenshot13, "left_click": left_click13, "scroll": scroll13}
WITHHELD13 = ["left_click_drag", "left_mouse_down", "left_mouse_up", "cursor_position", "hold_key"]  # scroll removed
TOOLS13 = [{"type": "computer_toolset_20260801", "configs": {m: {"enabled": False} for m in WITHHELD13}}]
print("scroll enabled:", "scroll" not in TOOLS13[0]["configs"])

# %% [markdown]
# `run_batch13` follows the lesson's rules: in order, `toolset_name` on every result, halt text after the first failure.

# %%
def reply13(*calls):                              # hand-written replies, not model output
    return anthropic.types.Message.model_validate({
        "id": "msg_x", "type": "message", "role": "assistant", "model": "hand-written",
        "stop_reason": "tool_use", "stop_sequence": None, "usage": {"input_tokens": 0, "output_tokens": 0},
        "content": [{"type": "tool_use", "id": f"toolu_{i}", "name": n, "toolset_name": "computer", "input": a}
                    for i, (n, a) in enumerate(calls)]})

async def run_batch13(reply):
    out, failed = [], False
    for c in [b for b in reply.content if b.type == "tool_use" and b.toolset_name == "computer"]:
        r = {"type": "tool_result", "tool_use_id": c.id, "toolset_name": "computer"}
        if failed:
            out.append({**r, "content": HALT13, "is_error": True}); continue
        try:
            out.append({**r, "content": await HANDLERS13[c.name](**c.input)})
        except (KeyError, ValueError, TypeError) as e:
            out.append({**r, "content": f"Error: {e}", "is_error": True}); failed = True
    return out

# %% [markdown]
# Scroll down 3 at (500, 400), then a screenshot; then a batch whose first click is off the screen.

# %%
for reply in (reply13(("scroll", {"scroll_direction": "down", "scroll_amount": 3, "coordinate": [500, 400]}),
                      ("screenshot", {})),
              reply13(("left_click", {"coordinate": [1500, 300]}), ("type", {"text": "x"}), ("screenshot", {}))):
    for r in await run_batch13(reply):
        text = r["content"] if isinstance(r["content"], str) else [c["type"] for c in r["content"]]
        print(r["tool_use_id"], r.get("is_error", False), text)
    print("---")
print("wheel calls:", wheel_log)

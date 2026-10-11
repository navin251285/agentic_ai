# %% [markdown]
# # 06 · Meet Pocket Tracker: the app and its repo
# Level L2 · Part 2 · core · ~25 min · builds on 01

# %% [markdown]
# ## Goal
# By the end you can copy Pocket Tracker into a scratch git repo, run its pytest suite, start it on 127.0.0.1, read its issue list over HTTP, and reproduce one of its open bugs (issue #7) yourself.

# %% [markdown]
# ## The idea
# Until now Pocket Tracker was a Python dict. From here on it is a real **test application**: a small FastAPI web app with a SQLite database, HTML pages, a pytest suite and a backlog in `issues.json`. Browser agents will drive the running app; coding agents will fix its code.
#
# The bugs in the backlog are **seeded bugs**: put there on purpose, each with steps to reproduce, so we always know the right answer. Everything runs in a **local environment**: your machine, 127.0.0.1, no accounts, no network.
#
# Analogy: a flight simulator. Pilots train on a machine whose faults the instructor chose, not on a real plane with unknown ones.

# %% [markdown]
# ## Picture
# ```mermaid
# flowchart LR
#   O[apps/pocket_tracker<br/>original, never changed] -->|copy + git commit| W[work/06/pocket_tracker<br/>scratch repo]
#   W -->|python -m pytest| T[test results]
#   W -->|uvicorn on 127.0.0.1| S[running app]
#   S --> DB[(work/06/pocket_tracker.db)]
#   S -->|HTML + JSON| Y[you now<br/>agents later]
# ```

# %% [markdown]
# ## Already know this?
# Part 2 (lessons 06–14) is about driving a browser. If you can answer these, skip to **lesson 15**:
# 1. How do you start a local web app from Python and know when it is ready to use?
# 2. What does `page.aria_snapshot()` return, and why is it smaller than the page's HTML?
# 3. Why does acting by element reference break less often than clicking at coordinates?
# 4. A screenshot is taken at 2x device scale. The model says "click (200, 100)". Where do you click?
# 5. How does a harness know a browser agent really closed an issue?

# %% [markdown]
# ## Step by step
#
# ### 1. The original app
# The app lives in `../apps/pocket_tracker`. It is small on purpose: you can read all of it in ten minutes. This cell lists every file and its length.

# %%
import json, os, shutil, socket, subprocess, sys, time
from pathlib import Path
import httpx

APP = Path("../apps/pocket_tracker")
for f in sorted(APP.rglob("*")):
    if f.is_file() and "__pycache__" not in f.parts and f.suffix != ".db":
        print(f"{len(f.read_text().splitlines()):4} lines  {f.relative_to(APP).as_posix()}")

# %% [markdown]
# Three parts: `app.py` (the routes), `db.py` (plain SQL on SQLite) and `templates/` (the HTML pages). `issues.json` is the backlog, and it also fills an empty database. `tests/` is the pytest suite.
#
# ### 2. A scratch copy that is a git repo
# Lessons never change the original. Each one copies it to `../work/<lesson>/`, then makes the copy a git repo with one commit. The fixed name and dates make the commit id the same on every machine.

# %%
WORK = Path("../work/06")
REPO = WORK / "pocket_tracker"
shutil.rmtree(WORK, ignore_errors=True)
shutil.copytree(APP, REPO, ignore=shutil.ignore_patterns("*.db", "__pycache__", ".pytest_cache"))

def run(*cmd, cwd=REPO, **kw):
    """Run a command in the repo; return its output as text."""
    out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, **kw)
    return (out.stdout + out.stderr).strip()

GIT_DATES = {**os.environ, "GIT_AUTHOR_DATE": "2026-10-01T09:00:00+00:00",
             "GIT_COMMITTER_DATE": "2026-10-01T09:00:00+00:00"}
run("git", "init", "-q", "-b", "main")
run("git", "add", "-A")
run("git", "-c", "user.name=Pocket Dev", "-c", "user.email=dev@pocket-tracker.test",
    "commit", "-q", "-m", "Pocket Tracker 0.1.0", env=GIT_DATES)
print(run("git", "log", "--oneline"))
print(run("git", "ls-files"))

# %% [markdown]
# One commit, 14 tracked files. That commit is the known-good starting point: any change an agent makes later shows up in `git diff`, and `git reset` undoes it (step 8).
#
# ### 3. The backlog: issues.json
# Each issue has an id, title, body (with steps to reproduce), label, status and creation date. This is what a coding agent reads; the web app shows the same issues.

# %%
issues = json.loads((REPO / "issues.json").read_text())
for i in issues:
    print(f"#{i['id']:<2} {i['status']:6} {i['label']:7} {i['title']}")
print("\nissue #7 body:\n" + issues[6]["body"])

# %% [markdown]
# Issues #1 to #7 are the seeded bugs, #8 and #9 are feature requests for later lessons, and #10 is already closed. Issue #3 is the About-page typo from lesson 01, now in real HTML instead of a dict.
#
# ### 4. Run the test suite
# `python -m pytest -q` runs the repo's own tests. They use FastAPI's `TestClient`, which calls the app in-process on a fresh temporary database, so no server is needed.

# %%
print(run(sys.executable, "-m", "pytest", "-q", "--color=no"))

# %% [markdown]
# Ten tests, all green, yet seven bugs are open. No test covers them; that is what makes them seeded bugs the agents must find. A green suite only tells you the tested paths work.
#
# ### 5. Start the app on 127.0.0.1
# `uvicorn` serves the app. We bind to `127.0.0.1` (this machine only), use port 8000 unless something already holds it, and point `POCKET_TRACKER_DB` at a file outside the repo, so the repo stays clean while the app writes data.

# %%
with socket.socket() as s:
    port_busy = s.connect_ex(("127.0.0.1", 8000)) == 0
with socket.socket() as s:
    s.bind(("127.0.0.1", 0 if port_busy else 8000))
    PORT = s.getsockname()[1]
BASE = f"http://127.0.0.1:{PORT}"
env = {**os.environ, "POCKET_TRACKER_DB": str((WORK / "pocket_tracker.db").resolve())}
log = open(WORK / "server.log", "w")
server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
                           "--port", str(PORT)], cwd=REPO, env=env, stdout=log, stderr=log)
print("started uvicorn, pid", server.pid, "on port 8000" if PORT == 8000 else "on a free port")

# %% [markdown]
# The process starts in the background, but it is not ready at once: Python must import the app and SQLite must create and seed the database. So we **poll** `/health` until it answers, with a deadline.

# %%
deadline = time.time() + 15
while True:
    try:
        print("health:", httpx.get(f"{BASE}/health").json())
        break
    except httpx.ConnectError:
        if time.time() > deadline or server.poll() is not None:
            raise RuntimeError("server did not start; see ../work/06/server.log")
        time.sleep(0.2)

# %% [markdown]
# ### 6. Open the issue list
# This is the page browser agents will see. If you run the notebook on your own laptop, open the URL in a browser too. Here we fetch the HTML and print the open-issue count line and the cells of the first row.

# %%
page = httpx.get(f"{BASE}/issues")
print(page.status_code, page.headers["content-type"])
lines = [ln.strip() for ln in page.text.splitlines()]
print(next(ln for ln in lines if "open-count" in ln))
print(*[ln for ln in lines if "<td>" in ln][:5], sep="\n")   # the five cells of row 1

# %% [markdown]
# The HTML has labelled forms and buttons ("Filter", "Close issue", "Add comment"), so lesson 08's aria snapshots read cleanly. The same data comes as JSON from `/api/issues`, which scripts and coding agents prefer:

# %%
api = httpx.get(f"{BASE}/api/issues", params={"label": "bug"}).json()
print(len(api), "bugs:", [(i["id"], i["status"], i["label"]) for i in api])

# %% [markdown]
# Notice the page said "10 open issues" although issue #10 is closed. That is seeded issue #5; you just saw it without trying.
#
# ### 7. Reproduce issue #7 by hand
# Issue #7: "closing an issue resets its label". Its steps: take issue #2 (label `bug`), close it, look at the label. A browser does the same two requests: a form POST to `/issues/2/close`, then a GET of the issue.

# %%
before = httpx.get(f"{BASE}/api/issues/2").json()
reply = httpx.post(f"{BASE}/issues/2/close")          # what the "Close issue" button sends
after = httpx.get(f"{BASE}/api/issues/2").json()
print("POST /issues/2/close ->", reply.status_code, reply.headers["location"])
print("before:", before["status"], "label =", repr(before["label"]))
print("after: ", after["status"], "label =", repr(after["label"]))
print("issue #7 reproduced:", after["status"] == "closed" and after["label"] == "")

# %% [markdown]
# The 303 is the redirect back to the issue page. Status changed to closed, as asked, but the label went from `'bug'` to `''`. Where? `git grep` searches the tracked files of the repo:

# %%
print(run("git", "grep", "-n", "-A5", "def update_issue"))

# %% [markdown]
# `update_issue` has `label=""` as its default and always writes it. The close route passes only `status`, so the label is overwritten with the empty string. We will not fix it here: lessons 16 to 21 have coding agents find, test and fix exactly this.
#
# ### 8. Reset the repo
# Closing #2 changed the database, which lives outside the repo, so git sees nothing. Now change a file the way an agent might, then reset:

# %%
about = REPO / "templates" / "about.html"
about.write_text(about.read_text().replace("Trakcer", "Tracker"))
print("after edit:", run("git", "status", "--short") or "clean")
print(run("git", "reset", "--hard", "-q") or "reset done")
print(run("git", "clean", "-fdxq") or "clean done")
print("after reset:", run("git", "status", "--short") or "clean")

# %% [markdown]
# `git reset --hard` restores tracked files; `git clean -fdx` removes untracked and ignored ones (here the `__pycache__` folders from step 4). To reset the data too, stop the server, delete `../work/06/pocket_tracker.db` and start again: an empty database is re-seeded from `issues.json`.

# %% [markdown]
# ## At work
# - Teams test browser agents on local fixture sites, not real ones: real sites change, show CAPTCHAs and forbid automation. Pocket Tracker later gets a "hostile mode" with a cookie banner, an alert and an iframe → lesson 42.
# - Coding-agent evals use seeded-bug repos with hidden tests that fail before the fix and pass after, mirroring SWE-bench's fields (`problem_statement`, `FAIL_TO_PASS`, `PASS_TO_PASS`) → lesson 46.
# - Git worktrees isolate files but not ports, databases or processes; two agents both starting the app on port 8000 collide, so each gets its own container → lesson 44.
# - Sandboxes are disposable (Modal's default lifetime is 5 minutes), so durable state lives in git and files, and a run resumes from a commit → lesson 38.

# %% [markdown]
# ## What just happened
# - You copied the **test application** to a scratch folder and made it a git repo with one fixed commit, so the original never changes.
# - The pytest suite passed (10 tests) while seven **seeded bugs** stayed open: tests prove only what they test.
# - uvicorn served the app on 127.0.0.1, a **local environment** with no accounts or network; you polled `/health` before using it.
# - You read the issue list as HTML and as JSON, and reproduced issue #7 with two HTTP requests.
# - `git grep` found the cause, and `git reset --hard` plus `git clean -fdx` undid a file change.

# %% [markdown]
# ## Common mistakes
# Using the server before it is ready. `Popen` returns at once; the first request often arrives before uvicorn listens. Here a request goes to a port where nothing listens yet, which is exactly what that early request sees:

# %% tags=["raises-exception"]
with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    not_yet_listening = s.getsockname()[1]
httpx.get(f"http://127.0.0.1:{not_yet_listening}/health")

# %% [markdown]
# Fix: poll `/health` with a deadline, as in step 5, and check `server.poll()` so a crashed server fails fast instead of waiting out the deadline.

# %%
print("server running:", server.poll() is None, "| health:", httpx.get(f"{BASE}/health").json())

# %% [markdown]
# Two more: editing `../apps/pocket_tracker` instead of the scratch copy (every later lesson then starts from a changed app), and binding to `0.0.0.0`, which exposes the app to your whole network.

# %% [markdown]
# ## Try it
# Reproduce issue #2 ("Search ignores capital letters") against the running app. Write `check_issue_2(base_url)` that returns a list of problems: searching `/api/issues` with `q=login` should return exactly issue #1, and so should `q=LOGIN`. Run it on `BASE`: you should get two problems while the bug is there. Then search the repo with `git grep -n instr` to find the line responsible.

# %%
# your code here

# %% [markdown]
# ## Key terms
# - **test application** — a small app built for agents to work on, with known content, known bugs and tests, so results can be checked.
# - **seeded bug** — a bug put into a test application on purpose, with steps to reproduce, so the correct fix is known.
# - **local environment** — everything an agent needs running on your own machine (here 127.0.0.1), with no accounts or network, so runs repeat exactly.
# - **health check** — a cheap endpoint (`/health`) polled after start-up to know the server is ready.
# - **scratch repo** — a disposable git copy of the code; agents change it, `git reset --hard` and `git clean -fdx` restore it.

# %% [markdown]
# Stop the server so its port is free for the next lesson.

# %%
server.terminate()
server.wait(timeout=10)
log.close()
print("server stopped, exit code", server.returncode)

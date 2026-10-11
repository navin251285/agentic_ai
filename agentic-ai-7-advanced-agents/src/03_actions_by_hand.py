# %% [markdown]
# # 03 · Actions: coordinates, element refs, keys, shell and code
# Level L1 · Part 1 · core · ~25 min · builds on 01, 02

# %% [markdown]
# ## Goal
# By the end you can express one goal, "mark issue #3 done", in five **action spaces** (pixel coordinates, element references, keyboard, shell, code), run each on the simulated tracker, and say which observation each one needs.

# %% [markdown]
# ## The idea
# Lesson 02 was about what the agent **sees**. This lesson is about what it can **do**. The set of actions a harness accepts is the agent's **action space**, and each action space needs a matching observation:
# - a **coordinate action** ("click at x=30, y=182") needs pixels;
# - an **element reference** ("click e8") needs a snapshot that numbers the elements;
# - **keys** ("Tab, Tab, Space") need to know where the focus is;
# - a **shell** command or a **code action** needs to know the files or the API, not the screen.
#
# Analogy: switching on a lamp. You can point at it in a photo, name it from a list ("lamp 3"), feel your way along the wall, or flip it from the fuse box.

# %% [markdown]
# ## Picture
# ```mermaid
# flowchart LR
#   G["Goal: mark #3 done"] --> C["click x,y"] --- S1[needs a screenshot]
#   G --> R["click ref"] --- S2[needs a snapshot with refs]
#   G --> K["keys"] --- S3[needs the focus position]
#   G --> SH["shell command"] --- S4[needs files + command output]
#   G --> CO["code"] --- S5[needs the API + run output]
#   C & R & K & SH & CO --> T[(tracker dict)]
# ```

# %% [markdown]
# ## Step by step
#
# ### 1. The environment (from lesson 01)
# The same simulated tracker, copied from lesson 01 so this notebook runs alone. Today "done" means only one thing: issue #3 has status `closed`. The check also makes sure no **other** issue changed, because a wrong click can close the wrong issue.

# %%
def new_tracker():
    return {
        "issues": {
            1: {"title": "Login page broken", "status": "open", "comments": []},
            2: {"title": "Search ignores capital letters", "status": "open", "comments": []},
            3: {"title": "Typo on the About page: 'Trakcer' should be 'Tracker'", "status": "open", "comments": []},
        },
        "pages": {"about": "Pocket Trakcer helps small teams track issues."},
    }

def check_done(env, before):
    problems = [] if env["issues"][3]["status"] == "closed" else ["issue #3 is not closed"]
    for i, issue in env["issues"].items():
        if i != 3 and issue["status"] != before["issues"][i]["status"]:
            problems.append(f"issue #{i} changed to {issue['status']}")
    return problems

print(check_done(new_tracker(), new_tracker()))

# %% [markdown]
# ### 2. A screen for the tracker
# To click on something, the tracker needs a screen. `layout()` places each element on a page: a search box, then one row per issue with a "Mark #N done" checkbox and the title link. Each element has a role, a name and a box `(x, y, width, height)` in pixels. A real browser computes this layout for you (lesson 07).

# %%
def layout(env):
    elements = [{"role": "searchbox", "name": "Search issues", "box": (20, 50, 260, 28)}]
    y = 100
    for i, issue in env["issues"].items():
        elements.append({"role": "checkbox", "name": f"Mark #{i} done", "issue": i,
                         "checked": issue["status"] == "closed", "box": (20, y, 20, 20)})
        elements.append({"role": "link", "name": issue["title"], "box": (52, y, 440, 20)})
        y += 36
    return elements

for n, el in enumerate(layout(new_tracker()), start=1):
    print(f"e{n}", el["role"], repr(el["name"]), el["box"])

# %% [markdown]
# Every action space below ends in the same place: the harness **presses** one element, named by its position in the layout (`e1`, `e2`, ...). Pressing a checkbox toggles that issue between open and closed. A link or the search box changes nothing in the tracker.

# %%
def press(env, ref):
    elements = {f"e{n}": el for n, el in enumerate(layout(env), start=1)}
    if ref not in elements:
        return f"ERROR: no element {ref}"
    el = elements[ref]
    if el["role"] == "checkbox":
        issue = env["issues"][el["issue"]]
        issue["status"] = "open" if issue["status"] == "closed" else "closed"
        return f"toggled {el['name']!r} -> {issue['status']}"
    return f"pressed {el['role']} {el['name']!r} (no change)"

# %% [markdown]
# ### 3. Way 1: a coordinate action needs pixels
# A vision model sees only a screenshot, so it answers with a point: `{"type": "click", "x": .., "y": ..}`. A real harness would send the model these pixels as an image; the boxes printed above are exactly what that image would show. Issue #3's checkbox is the box `(20, 172, 20, 20)`, so a point near x=30, y=182 hits it.
#
# The harness turns the point into an element by **hit-testing**: find the box that contains the point. If no box contains it, the click does nothing.

# %%
def run_click(env, action):
    for n, el in enumerate(layout(env), start=1):
        x, y, w, h = el["box"]
        if x <= action["x"] <= x + w and y <= action["y"] <= y + h:
            return press(env, f"e{n}")
    return "clicked empty space (no change)"

coordinate_action = {"type": "click", "x": 30, "y": 182}
tracker = new_tracker()
print(run_click(tracker, coordinate_action))
print("problems:", check_done(tracker, new_tracker()))

# %% [markdown]
# ### 4. Way 2: an element reference needs a numbered snapshot
# A text model reads the accessibility tree instead. If the snapshot gives every element a short id, the model can name the element instead of pointing at it. Playwright 1.63's `page.aria_snapshot(mode="ai")` adds `[ref=eN]` ids like these (lesson 09 uses the real thing). Compare with the recorded snapshot from lesson 02, which has roles and names but no ids.

# %%
def snapshot_with_refs(env):
    lines = []
    for n, el in enumerate(layout(env), start=1):
        checked = " [checked]" if el.get("checked") else ""
        lines.append(f'- {el["role"]} "{el["name"]}"{checked} [ref=e{n}]')
    return "\n".join(lines)

print(snapshot_with_refs(new_tracker()))
print("\nlesson 02 snapshot has refs:", "[ref=" in open("../data/02_issues_page.aria.yaml").read())

# %% [markdown]
# The model reads `checkbox "Mark #3 done" [ref=e6]` and answers `{"type": "click", "ref": "e6"}`. The harness hands the ref straight to `press`: no pixels, no hit-testing.

# %%
ref_action = {"type": "click", "ref": "e6"}
tracker = new_tracker()
print(press(tracker, ref_action["ref"]))
print("problems:", check_done(tracker, new_tracker()))

# %% [markdown]
# ### 5. Way 3: keys need the focus position
# Keyboard actions do not say **where**. `Tab` moves the focus to the next focusable element; `Space` presses the focused one. To get to issue #3's checkbox the agent must know the focus order and where the focus is now. Here the focus starts on nothing, so 6 Tabs reach the 6th element.

# %%
def run_keys(env, action, focus=0):
    elements = layout(env)
    for key in action["keys"]:
        if key == "Tab":
            focus = focus % len(elements) + 1
            print(f"  Tab   -> focus on e{focus} {elements[focus - 1]['role']} {elements[focus - 1]['name']!r}")
        elif key == "Space":
            print("  Space ->", press(env, f"e{focus}"))
    return focus

key_action = {"type": "keys", "keys": ["Tab"] * 6 + ["Space"]}
tracker = new_tracker()
run_keys(tracker, key_action)
print("problems:", check_done(tracker, new_tracker()))

# %% [markdown]
# Seven key presses for one tick, and the agent only knows it landed on the right box if it looks again after the Tabs. Keys shine elsewhere: typing text, `Enter` to submit, shortcuts like `Ctrl+S`.
#
# ### 6. Way 4: a shell command needs files and command output
# A coding agent rarely clicks. Its action is a shell command, and its observation is the command's output. Say the tracker is saved as `tracker.json`. The agent first looks with `jq` (a standard JSON command-line tool), then changes the file.

# %%
import json, shutil, subprocess, tempfile
from pathlib import Path

workdir = Path(tempfile.mkdtemp())
(workdir / "tracker.json").write_text(json.dumps(new_tracker(), indent=1))
have_shell = bool(shutil.which("bash") and shutil.which("jq"))
print("bash + jq available:", have_shell)

def run_shell(command):
    result = subprocess.run(["bash", "-c", command], cwd=workdir, capture_output=True, text=True)
    return f"exit={result.returncode}\n{result.stdout}{result.stderr}".strip()

if have_shell:
    print(run_shell("jq -c '.issues | to_entries[] | [.key, .value.status]' tracker.json"))

# %% [markdown]
# The output shows the keys are strings: JSON has no integer keys, so the dict's `3` became `"3"`. The shell action uses `"3"`. `shell_on(env, action)` saves the tracker to the file, runs the command, and loads the file back into `env` (turning the keys back into ints). Without bash and jq, the fallback does the same edit in Python.

# %%
shell_action = {"type": "shell", "command":
                """jq '.issues["3"].status = "closed"' tracker.json > tmp.json && mv tmp.json tracker.json"""}

def shell_on(env, action):
    (workdir / "tracker.json").write_text(json.dumps(env))
    if have_shell:
        output = run_shell(action["command"])
    else:   # fallback: the same edit in Python
        data = json.loads((workdir / "tracker.json").read_text())
        data["issues"]["3"]["status"] = "closed"
        (workdir / "tracker.json").write_text(json.dumps(data))
        output = "exit=0 (Python fallback)"
    loaded = json.loads((workdir / "tracker.json").read_text())
    env["issues"] = {int(k): v for k, v in loaded["issues"].items()}
    return output

tracker = new_tracker()
print(shell_on(tracker, shell_action))
print("problems:", check_done(tracker, new_tracker()))

# %% [markdown]
# ### 7. Way 5: a code action needs the API and the run output
# A **code action** is a piece of Python the harness runs with the environment in scope. Here the code sees the `tracker` dict, so the model must know its shape (the API). The observation is whatever the code prints or the error it raises. Lesson 24 builds a real CodeAct loop.

# %%
import contextlib, io

def run_code(env, action):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        exec(action["code"], {"tracker": env})   # no sandbox here: lesson 19
    return out.getvalue().strip()

code_action = {"type": "code", "code":
               "tracker['issues'][3]['status'] = 'closed'\nprint(tracker['issues'][3]['status'])"}
tracker = new_tracker()
print(run_code(tracker, code_action))
print("problems:", check_done(tracker, new_tracker()))

# %% [markdown]
# One code action can also do many steps at once, which no click can. This one finds the typo issue by its title instead of its number, closes it and leaves a comment:

# %%
smart_code = """
for i, issue in tracker['issues'].items():
    if 'Typo' in issue['title']:
        issue['status'] = 'closed'
        issue['comments'].append('Closed by a code action')
        print('closed', i)
"""
tracker = new_tracker()
print(run_code(tracker, {"type": "code", "code": smart_code}))
print("problems:", check_done(tracker, new_tracker()), "| comments:", tracker["issues"][3]["comments"])

# %% [markdown]
# ### 8. The five side by side
# Each action is what a model would put in a tool call. Its size (in characters) hints at its token cost; the observation it relies on is the bigger cost (lesson 02).

# %%
needs = {"click": "screenshot (pixels)", "ref": "snapshot with [ref=eN] ids",
         "keys": "focus order + current focus", "shell": "files + command output",
         "code": "the API + run output"}
actions = {"click": coordinate_action, "ref": ref_action, "keys": key_action,
           "shell": shell_action, "code": code_action}
for name, action in actions.items():
    print(f"{name:6} {len(json.dumps(action)):>4} chars  needs {needs[name]}")

# %% [markdown]
# ### 9. Grow it: the page changes
# Pocket Tracker gets a new issue, and the newest issue is shown first. The agent replays the five actions it planned from the **old** observations. Which ones still mark #3 done?

# %%
def tracker_with_new_issue():
    env = new_tracker()
    env["issues"] = {4: {"title": "Board page is slow", "status": "open", "comments": []}, **env["issues"]}
    return env

runners = {"click": lambda env: run_click(env, coordinate_action),
           "ref": lambda env: press(env, ref_action["ref"]),
           "keys": lambda env: run_keys(env, key_action),
           "shell": lambda env: shell_on(env, shell_action),
           "code": lambda env: run_code(env, code_action)}
for name, run in runners.items():
    env = tracker_with_new_issue()
    with contextlib.redirect_stdout(io.StringIO()):
        run(env)
    print(f"{name:6} problems: {check_done(env, tracker_with_new_issue())}")

# %% [markdown]
# The click, the ref and the keys all ticked issue #2: they point at a **position** on the old page. The shell command and the code action name issue `3` by its id, so they still work. Screen actions are only valid for the observation they came from: observe again before every action.

# %% [markdown]
# ## At work
# - Browser tools for coding agents act by element reference: Playwright MCP's default mode sends accessibility snapshots, and its `browser_click` tool targets an element from the snapshot instead of a pixel → lessons 08 and 09.
# - Vision agents fail mostly at turning an intent into the right pixel: the OSWorld paper names GUI grounding as the main weakness, and each vendor uses its own coordinate system (Claude: pixels on a scaled screenshot; Gemini: a 0-999 grid) → lesson 11.
# - Vendor computer-use tools are coordinate + keyboard action spaces: Claude's `computer_toolset_20260801` has 17 actions (clicks, `hold_key`, `zoom`, ...); for GPT-6 Astra, OpenAI recommends code execution (`exec_py`) that drives a browser instead → lessons 13 and 24.
# - Shell alone can be the whole action space: mini-swe-agent's only tool is bash, each action a separate `subprocess.run`, which also makes it easy to sandbox → lessons 19 and 23.

# %% [markdown]
# ## What just happened
# - The same goal ran in five **action spaces**; each ended in one change to the tracker, checked on the environment.
# - **Coordinate actions** needed the pixel boxes of a screenshot and hit-testing; **element references** needed a snapshot with `[ref=eN]` ids; **keys** needed the focus order (7 presses for one tick).
# - **Shell** and **code actions** skipped the screen: they needed the file layout or the API, and the command or run output was the observation.
# - A code action did a multi-step job (find by title, close, comment) in one action.
# - After the page changed, position-based actions (click, ref, keys) ticked issue #2; id-based actions (shell, code) still closed #3.

# %% [markdown]
# ## Common mistakes
# Reusing coordinates from an old screenshot. The page now has issue #4 on top, but the agent clicks where #3 used to be:

# %% tags=["raises-exception"]
tracker = tracker_with_new_issue()
print(run_click(tracker, coordinate_action))
problems = check_done(tracker, tracker_with_new_issue())
assert not problems, problems

# %% [markdown]
# Fix: take a fresh observation before every click and read the point off it. Here we find the new box of "Mark #3 done" in the fresh layout (what the new screenshot would show) and click its centre.

# %%
tracker = tracker_with_new_issue()
box = next(el["box"] for el in layout(tracker) if el["name"] == "Mark #3 done")
fresh_click = {"type": "click", "x": box[0] + box[2] // 2, "y": box[1] + box[3] // 2}
print(fresh_click, "->", run_click(tracker, fresh_click))
assert not check_done(tracker, tracker_with_new_issue())

# %% [markdown]
# Second mistake: a code action that does more than asked. "Mark the typo issue done" written as "close everything open" passes the #3 test but closes #1 and #2 too. That is why the check compares every issue, and why code actions need limits (lessons 19 and 24).

# %%
tracker = new_tracker()
run_code(tracker, {"type": "code", "code": "for i in tracker['issues']: tracker['issues'][i]['status'] = 'closed'"})
print("problems:", check_done(tracker, new_tracker()))

# %% [markdown]
# ## Try it
# On `tracker_with_new_issue()`, mark issue **#4** done in three action spaces: an element-ref action read from a fresh `snapshot_with_refs(...)`, a key action (how many Tabs?), and a code action. After each, check that #4 is closed and no other issue changed (copy `check_done` and change 3 to 4).

# %%
# your code here

# %% [markdown]
# ## Key terms
# - **action space** — the set of actions a harness accepts from the agent (clicks at points, element refs, keys, shell commands, code); each needs a matching observation.
# - **coordinate action** — an action aimed at a pixel position, such as a click at (x, y); it needs a screenshot and the harness hit-tests the point.
# - **element reference** — a short id (`e6`) that a snapshot gives each element so an action can name it instead of pointing at pixels.
# - **code action** — a piece of code the harness runs with the environment in scope; it can do many steps at once and needs the API, not the screen.
# - **hit-testing** — finding which element's box contains a clicked point.

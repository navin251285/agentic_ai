# %% [markdown]
# # 10 · Goal-based loops: a script Stop hook as the mechanical gate
# Level L3 · Part 2 · core · ~25 min · builds on 09
#
# ## Goal
# Gate the end of a loop with a script that runs the goal's tests and blocks the finish while any of them fail. Say in one sentence why a model-judged goal, such as `/goal`, is weaker for anything a test can check. Name the two Agent SDK budget limits, `max_turns` and `max_budget_usd`, and the result subtypes that report them (a walkthrough, with no call).
#
# ## Why it matters
# Lesson 09 ran outer loops that checked each item with pytest. Most loops you will meet stop a different way: the model says it is done, and the run ends. Then nothing checks the goal's tests after the last word. The transcript reads as finished, and the repo can still be red.
#
# Without a gate, three things happen:
#
# - The loop ends on the model's `DONE: yes`. That is a claim, and nothing checks it.
# - A person has to read the test output and type the next prompt by hand. That is the person in the loop again (lesson 09).
# - The red tests show up later, in review or in production, not at the moment the agent stopped.
#
# With a gate, a script runs the same tests whenever the agent tries to finish. If one fails, the agent does not finish, and the failing lines become the reason to keep working. You do not need a gate when no program can check the goal, for example "is this reply polite?". Then a reviewer, a model or a person does the check.

# %% [markdown]
# ## The idea
# **A gate is a program the agent cannot argue with. When the agent tries to finish, the harness runs the gate. Exit code 2 blocks the finish, and the gate's message becomes the reason to keep working. Exit code 0 lets the agent finish.** Claude Code calls this a Stop hook. Its verdict comes from pytest's result, not from the model's words.
#
# Analogy: a barrier at the exit of a shop. The cashier can say "everything is paid", but the barrier opens only when the scanner reads every tag.

# %% [markdown]
# ## Picture
# The model's turn ends. The Stop hook runs the goal's tests. Only a green gate lets the agent finish. Goal-based is one of the four loop types from lesson 09; this lesson builds it.
#
# ```mermaid
# flowchart TD
#   M["Model turn: edits files, says DONE"] --> S["Agent tries to finish"]
#   S --> H["Stop hook: verify_gate.py runs pytest on the goal's tests"]
#   H -->|"exit 0: all goal tests pass"| F["Finish"]
#   H -->|"exit 2: stderr lists the failing tests"| C["Reason to continue: next turn with the failing lines"]
#   C --> M
# ```

# %% [markdown]
# ## Step by step
# The steps use the repo from lesson 07 and the three modules from lesson 09: money, pricing and tax. The goal is their nine tests. The model is called in one cell only. The recording makes the rest repeatable.

# %% [markdown]
# ### Step 1: the goal and the repo (no model call)
# The repo is read-only in `../data/pocket-cart`, generated in lesson 07, so there is no licence to check. Every run works on its own copy. At the start, each of the three modules has one passing test and two failing ones: three of nine pass.

# %%
import sys; sys.path.insert(0, "..")
import json, os, re, shutil, subprocess; from pathlib import Path
import llm_replay
from langchain_core.messages import HumanMessage, SystemMessage
from llm_setup import DEFAULT_MODELS, get_llm
llm_replay.start("10_goal-loops-and-stop-hooks")  # records the model calls once, replays them later

SRC = Path("../data/pocket-cart")  # generated in lesson 07; this lesson only reads it
WORK = Path("../data/10"); WORK.mkdir(parents=True, exist_ok=True)  # run-time copies and the gate script
GATE = WORK / "verify_gate.py"     # written in step 2
MODULES = [  # the three modules of the goal, each with its own test file (as in lesson 09)
    {"file": "pocket_cart/money.py", "tests": "tests/test_money.py"},
    {"file": "pocket_cart/pricing.py", "tests": "tests/test_pricing.py"},
    {"file": "pocket_cart/tax.py", "tests": "tests/test_tax.py"},
]
GOAL = [item["tests"] for item in MODULES]  # the goal: these nine tests must all pass

# %% [markdown]
# Two helpers: a fresh copy of the repo for each run, and the verifier. `check` runs pytest in the copy and reads its summary.

# %%
def fresh_copy(name):  # a new copy of the repo for one run; the source is never edited
    work = WORK / name
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(SRC, work)
    return work

def check(work, tests=GOAL):  # the verifier: pytest in the copy; returns exit code, pass counts, FAILED lines
    run = subprocess.run([os.path.abspath(sys.executable), "-m", "pytest", "-q", "--color=no",
                          "-p", "no:cacheprovider", *tests], cwd=work, capture_output=True, text=True)
    passed = re.search(r"(\d+) passed", run.stdout)
    failed = re.search(r"(\d+) failed", run.stdout)
    n_passed = int(passed.group(1)) if passed else 0
    n_failed = int(failed.group(1)) if failed else 0
    return {"code": run.returncode, "passed": n_passed, "total": n_passed + n_failed,
            "failed": [line for line in run.stdout.splitlines() if line.startswith("FAILED")]}

start = check(fresh_copy("start")); print(f"at the start: exit code {start['code']}, passed {start['passed']} of {start['total']}")

# %% [markdown]
# ### Step 2: the gate script (no model call)
# Claude Code runs a Stop hook as a command: it sends the hook's input as JSON on stdin and reads the exit code. The gate runs pytest in the folder the input names (`cwd`). It exits 0 when the goal holds. It exits 2 and writes the failing lines to stderr when it does not; Claude Code uses that stderr as the reason to keep working.
#
# Two choices matter. The gate never reads what the model wrote, so a claim cannot pass it. It fails closed: any error of its own exits 2, because any other non-zero exit is only a non-blocking error in Claude Code, and the agent would still finish. The `%%writefile` magic writes it, so you can copy it to `.claude/hooks/` later.
#
# Run the three `%%writefile` cells below in order, once each. The first overwrites the file; the next two append to it.

# %%
%%writefile ../data/10/verify_gate.py
"""Stop hook gate. Run the goal's tests: exit 0 = goal met, the agent may finish; exit 2 = block the finish."""
import json, os, re, subprocess, sys

def main() -> int:
    hook = json.load(sys.stdin)  # the hook input: session_id, cwd, hook_event_name, stop_hook_active, ...
    goal = sys.argv[1:]              # the goal: test files or test ids that must all pass
    if not goal:
        print("Stop blocked: the gate has no goal tests.", file=sys.stderr)
        return 2
# %% [markdown]
# The verifier: pytest on the goal's tests, run in the folder that the hook input names.

# %%
%%writefile -a ../data/10/verify_gate.py
    run = subprocess.run([sys.executable, "-m", "pytest", "-q", "--color=no", "-p", "no:cacheprovider", *goal],
                         cwd=hook.get("cwd", os.getcwd()), capture_output=True, text=True)
    if run.returncode == 0:
        return 0                     # every goal test passed
# %% [markdown]
# The rest of the gate: the failing lines become the reason, and the guard at the bottom fails closed.

# %%
%%writefile -a ../data/10/verify_gate.py
    count = re.search(r"(\d+) failed", run.stdout)
    failed = [line for line in run.stdout.splitlines() if line.startswith("FAILED")]
    # stop_hook_active is not read on purpose: a second stop attempt must still be red, never a free pass
    reason = failed[:6] or run.stdout.splitlines()[-3:]  # no FAILED line (usage error, missing file): the last lines
    print(f"Stop blocked: {count.group(1) if count else 'some'} goal test(s) fail. Fix them, then finish again:\n"
          + "\n".join(reason), file=sys.stderr)
    return 2

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:       # fail closed: an unexpected error blocks the finish too
        print(f"Stop blocked: the gate failed: {error}", file=sys.stderr)
        sys.exit(2)

# %% [markdown]
# The helper below plays Claude Code's side of the hook. It sends the hook input as JSON on stdin, runs the gate, and returns the exit code and stderr. `stop_hook_active` is true when the agent is already continuing because of a block, as the docs describe.

# %%
def run_gate(work, goal, continuing=False, last_message=""):  # Claude Code's side: hook input as JSON on stdin
    hook_input = {"session_id": "lesson-10-demo", "hook_event_name": "Stop", "cwd": os.path.abspath(work),
                  "stop_hook_active": continuing, "last_assistant_message": last_message}
    run = subprocess.run([os.path.abspath(sys.executable), os.path.abspath(GATE), *goal],
                         input=json.dumps(hook_input), capture_output=True, text=True)
    return run.returncode, run.stderr.strip()

# %% [markdown]
# Two runs of the gate with no model. On the start copy the goal is red: exit 2, and the stderr lists the failing tests. Then one test that already passes: exit 0, and nothing on stderr.

# %%
work = fresh_copy("gate-check")
print("repo:", SRC.name, "| goal files:", len(GOAL))
code, message = run_gate(work, GOAL)
print("exit code:", code, "\n" + message)
code, message = run_gate(work, ["tests/test_money.py::test_nineteen_ninety_nine"])
print("exit code:", code, "| stderr:", repr(message))

# %% [markdown]
# ### Step 3: the model and the loop
# The model is the course default, from `get_llm()`. The key comes from `.env`. A recording replays without one. The loop plays the agent's side: after each model turn it runs the gate, and a block starts the next turn with the gate's words in the prompt.
#
# The first turn is narrower than the goal: it may change only money and pricing. That is a teaching setup. It is how a short task ("fix the money and pricing tests") looks to a model, and the goal is still all nine tests. By design, the gate is expected to block turn 1 and pass by turn 2 or 3. That shows the gate working.

# %% tags=["needs-llm"]
llm = get_llm(model=DEFAULT_MODELS["gemini"])  # the key comes from .env

# %% [markdown]
# Two parsers read a reply, as in lesson 09. The model's `DONE` line is kept as its claim. The gate, not that line, decides the result.

# %%
def parse_files(text):
    text = text.replace("```python", "").replace("```", "")
    parts = re.split(r"^### FILE (\S+)[ \t]*$", text, flags=re.M)
    return {parts[i]: re.sub(r"^DONE:.*$", "", parts[i + 1], flags=re.M | re.I).strip("\n") + "\n"
            for i in range(1, len(parts), 2)}

def claimed_done(text):
    found = re.findall(r"^DONE:\s*(yes|no)", text, flags=re.M | re.I)
    return found[-1].lower() if found else "none"

LOOP_SYSTEM = ("You fix a small Python shop. The tests are the spec: never change a test. Reply with the complete new "
               "text of each module you change, each under '### FILE <path>'. End with 'DONE: yes' or 'DONE: no'.")
MAX_TURNS = 3  # our cap on model turns, the same idea as max_turns in the Agent SDK (walkthrough below)

def turn_prompt(work, scope, failing, gate_message=""):  # scope files, tests, failing lines, the gate's last words
    parts = []
    for item in scope:
        parts.append(f"### FILE {item['file']}\n{(work / item['file']).read_text()}")
        parts.append(f"### TEST {item['tests']}\n{(work / item['tests']).read_text()}")
    text = "\n".join(parts) + "\nStill failing:\n" + "\n".join(failing)
    return text + (f"\nThe stop gate blocked the last finish with:\n{gate_message}" if gate_message else "")

# %% [markdown]
# The loop itself. Each turn runs the model, applies its edits in scope, then runs the gate as the Stop hook would.

# %%
def run_loop(name, first_scope):  # each turn is one model call; after it the gate runs; a block starts the next turn
    work = fresh_copy(name)
    rows, gate_message = [], ""
    for turn in range(1, MAX_TURNS + 1):
        scope = first_scope if turn == 1 else MODULES
        failing = check(work, [i["tests"] for i in scope])["failed"]
        prompt = (f"Change only {' and '.join(i['file'] for i in scope)} in this turn.\n" if turn == 1 else "") \
            + turn_prompt(work, scope, failing, gate_message)
        reply = llm.invoke([SystemMessage(content=LOOP_SYSTEM), HumanMessage(content=prompt)])
        for path, text in parse_files(reply.text).items():
            if path in {i["file"] for i in scope}:  # edits outside this turn's scope are dropped
                (work / path).write_text(text)
        code, gate_message = run_gate(work, GOAL, continuing=turn > 1, last_message=reply.text)
        rows.append({"turn": turn, "claimed": claimed_done(reply.text), "gate": code, "message": gate_message,
                     "input": reply.usage_metadata["input_tokens"], "output": reply.usage_metadata["output_tokens"]})
        if code == 0:
            break
    return work, rows

# %% [markdown]
# Run the loop. The model is called once per turn: at most three calls here. Expect turn 1 to be blocked by the gate and a later turn to finish.

# %% tags=["needs-llm"]
work, turns = run_loop("gated", MODULES[:2])  # turn 1 is scoped to money and pricing
for row in turns:
    print(f"turn {row['turn']}: model said DONE: {row['claimed']} | gate exit {row['gate']} | input {row['input']} tokens")
final = check(work)
print(f"pytest on the goal at the end: passed {final['passed']} of {final['total']}")

# %% [markdown]
# ### Step 4: what the gate saw (no model call)
# These lines read the same recorded turns. The model's claim and the gate's verdict can disagree. Without a gate, the loop would stop at the first claim.

# %%
for row in turns:
    red = re.search(r"(\d+) goal test", row["message"])
    print(f"turn {row['turn']}: model said DONE: {row['claimed']} | gate {'pass' if row['gate'] == 0 else 'block'} | goal tests red: {red.group(1) if red else 0}")
print(f"Without a gate, the loop stops after turn 1 (the model said DONE: {turns[0]['claimed']}). The gate said:")
print(turns[0]["message"] or "(nothing: the gate passed)")

# %% [markdown]
# Read the output this way. Turn 1 says `DONE: yes`, but the gate blocks it with 2 goal tests still red, so the loop goes on. Turn 2 passes: 0 red, and pytest reports 9 of 9.

# %% [markdown]
# ### Step 5: the model-judged goal, for comparison (walkthrough)
# `/goal <condition>` is a built-in Claude Code command. The docs describe it as a session-scoped, prompt-based Stop hook: at each stop, an evaluator model reads the condition and the conversation, and decides. The verdict is a model's reading of text. The gate reads only the exit code of pytest. For a condition a test can check, the gate is stronger. For a condition that needs reading ("the summary covers all three refund cases"), a model-judged goal is the right tool.

# %% [markdown]
# **Walkthrough: wire the gate into Claude Code (not run here).** Prerequisites: Claude Code installed, and a project venv with pytest in it.
# 1. Copy `verify_gate.py` into the project as `.claude/hooks/verify_gate.py`. You should see it in the project tree.
# 2. Add the hook to `.claude/settings.json`. The command runs the gate with the goal's test files. `${CLAUDE_PROJECT_DIR}` is the project folder, which Claude Code sets for hook commands. `.venv/bin/python` is the project venv's Python, so the gate runs the project's pytest.
#
# The settings file:

# %% [markdown]
# ```json
# {
#   "hooks": {
#     "Stop": [
#       {
#         "hooks": [
#           {
#             "type": "command",
#             "command": "${CLAUDE_PROJECT_DIR}/.venv/bin/python ${CLAUDE_PROJECT_DIR}/.claude/hooks/verify_gate.py tests/test_money.py tests/test_pricing.py tests/test_tax.py"
#           }
#         ]
#       }
#     ]
#   }
# }
# ```

# %% [markdown]
# 3. Give Claude Code the goal ("make the nine tests in money, pricing and tax pass"). You should see it keep working while a test is red, with the failing lines as the reason. Once all nine pass, it finishes.
#
# The CLI equivalent is the helper above: the same JSON on stdin and the same exit code. Per the Claude Code hooks docs (not run here), after a Stop hook has continued the turn eight times in a row, Claude Code overrides the next block and ends the turn. `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` raises that cap. So a gate that never goes green ends the turn instead of looping forever.

# %% [markdown]
# ## At work
# - Teams keep a deterministic check as the gate: "done is a claim, not a proof". A loop that can edit its own tests can pass by deleting them, so the gate's test files must be read-only to the agent (reward hacking). → lesson 14 covers the maker and checker split.
# - `/goal` uses a separate small evaluator model to decide each stop, so its verdict is a model's judgement. Use it for conditions that need reading, not for tests. → lesson 16 covers hooks as the loop's controls.
# - Budget caps are checked after each response, so the last response can overshoot. Leave headroom and measure cost per successful run. → lesson 27.

# %% [markdown]
# ## Under the hood
# **Walkthrough, no call:** the Claude Agent SDK is not installed in this course's venv, and nothing here calls it. The code is a reading aid taken from the SDK's documented options.
#
# ```python
# from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage
#
# async def run():
#     options = ClaudeAgentOptions(max_turns=10, max_budget_usd=0.50)
#     async for message in query(prompt="Refactor the utils module", options=options):
#         if isinstance(message, ResultMessage):
#             if message.subtype == "error_max_turns":
#                 print("Stopped: turn limit reached", message.errors)
#             elif message.subtype == "error_max_budget_usd":
#                 print("Stopped: budget reached")
#             print(message.is_error, message.num_turns, message.total_cost_usd)
# ```
#
# The docs say: `max_turns` counts tool-use round trips and defaults to `None`. `max_budget_usd` is in US dollars, defaults to `None`, and is a client-side estimate, so leave headroom. A reached limit ends the run with `subtype` `error_max_turns` or `error_max_budget_usd`, `is_error` true and `result` `None`.
#
# The hand-built version below applies the same rules to the real turns from step 3. Here one turn is one model reply, our stand-in for a tool-use round trip. PRICE is gemini-2.5-flash-lite, the course default model, at 0.10 input and 0.40 output per 1M tokens (not a Claude price). The code counts each turn and its dollars and checks the caps after each reply.

# %%
PRICE = {"input": 0.10, "output": 0.40}  # USD per 1M tokens: gemini-2.5-flash-lite, the course default model

def capped(replies, max_turns=None, max_budget_usd=None):
    """Walk the replies in order. Count each turn and its dollars; check the caps after each reply."""
    turns, usd = 0, 0.0
    for reply in replies:
        turns += 1
        usd += (reply["input"] * PRICE["input"] + reply["output"] * PRICE["output"]) / 1_000_000
        if reply["done"]:
            return "success", turns, usd
        if max_turns is not None and turns >= max_turns:
            return "error_max_turns", turns, usd
        if max_budget_usd is not None and usd >= max_budget_usd:
            return "error_max_budget_usd", turns, usd

replies = [{"input": r["input"], "output": r["output"], "done": r["gate"] == 0} for r in turns]
for label, caps in [("no caps", {}), ("max_turns=1", {"max_turns": 1}), ("max_budget_usd=0.000001", {"max_budget_usd": 0.000001})]:
    subtype, n, usd = capped(replies, **caps)
    print(f"{label:<26} subtype {subtype:<22} turns {n}  cost ${usd:.6f}")

# %% [markdown]
# Read the three rows. With no caps, the run succeeds on turn 2, the first turn the gate passes. With `max_turns=1`, it stops after turn 1 with `error_max_turns`. With the tiny budget, turn 1 already costs more than the cap, so it stops after turn 1 with `error_max_budget_usd`.

# %% [markdown]
# ## Common mistakes
# 1. **A gate that raises on red.** `check=True` turns a red run into a traceback. In Claude Code, a traceback exits 1, which is a non-blocking error, so the agent finishes anyway. The fix is to catch the result and return exit 2, as the gate does.

# %% tags=["raises-exception"]
work = fresh_copy("mistake")
subprocess.run([os.path.abspath(sys.executable), "-m", "pytest", "-q", "--color=no", "-p", "no:cacheprovider", *GOAL],
               cwd=work, check=True)  # red tests raise CalledProcessError here, not a block

# %% [markdown]
# 2. **Trusting `stop_hook_active`.** It is true on a second stop attempt. A gate that lets every second attempt through lets red work finish. The gate in step 2 runs the tests every time. The cell below runs the gate on a red copy with `stop_hook_active` set to true: it still exits 2.

# %%
print("second stop attempt, still red: exit code", run_gate(fresh_copy("stop-twice"), GOAL, continuing=True)[0])

# %% [markdown]
# ## Try it
# Write `verdict(code)`. It returns `"finish"` for exit 0, `"keep working"` for exit 2, and `"finish, with an error shown"` for any other exit code. Check it on 0, 1 and 2.

# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
def verdict(code):
    if code == 0:
        return "finish"
    if code == 2:
        return "keep working"
    return "finish, with an error shown"  # a non-blocking error: the agent still stops

for code in (0, 1, 2):
    print(code, "->", verdict(code))

# %% [markdown]
# ## Recap
# - A Stop hook runs when the agent tries to finish. Exit 2 blocks the finish and sends the stderr back as the reason to continue.
# - The gate's verdict comes from the goal's tests, not from the model's "DONE". The gate fails closed on its own errors.
# - A model-judged goal such as `/goal` asks a model at each stop. Use it for conditions that need reading; use a gate for anything a test can check.
# - `max_turns` and `max_budget_usd` are the Agent SDK's caps (walkthrough, no call). Both are checked after a response, so leave headroom.
#
# **Interview:** "How do you know an agent loop is really done?" A strong answer: the model's claim is not evidence. A deterministic gate runs the goal's tests at every stop, blocks red, and fails closed. A turn cap and a budget bound the rest.

# %% [markdown]
# Save the recording. This cell is the last code cell of the notebook.

# %%
llm_replay.stop()  # saves the recording

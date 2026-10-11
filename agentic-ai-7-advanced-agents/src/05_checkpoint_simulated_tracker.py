# %% [markdown]
# # 05 · Checkpoint: a real-model agent in a simulated tracker
# Level L1 · Part 1 · core · ~60 min · builds on 01, 02, 03, 04

# %% [markdown]
# ## Goal
# By the end you have built a complete **agent loop** (observe, decide, act, verify) where a real model triages three Pocket Tracker issues through tools. The harness enforces a step limit and decides success with an **outcome check** on the final tracker state, not on what the model says.

# %% [markdown]
# ## The idea
# Part 1 gave you the pieces. Lesson 01: a loop where the harness runs the model's tool calls. Lesson 02: the observation is a text view you choose. Lesson 03: every action needs a matching observation. Lesson 04: every extra step is another chance to fail, so a run needs a limit. Here you put them together in one harness that you could hand to a teammate.
#
# The harness owns three decisions the model never makes: what the model sees, how many steps it gets, and whether the task is done.
#
# Analogy: a driving test. The candidate drives; the examiner sets the route, ends the test at the time limit, and marks the result from what actually happened on the road, not from the candidate's opinion of their driving.

# %% [markdown]
# ## Picture
# ```mermaid
# flowchart LR
#   O[Observe<br/>text view] --> D[Decide<br/>model call]
#   D --> A[Act<br/>harness runs tools]
#   A --> L{Step limit<br/>reached?}
#   L -->|no, tool calls left| D
#   L -->|yes, or model done| V[Verify<br/>check final state]
# ```

# %% [markdown]
# ## Requirements
# The task: **triage** issues #1, #2 and #3. Triage follows a written policy:
# - label `docs` if the issue is about text on a page, otherwise `bug`;
# - priority `high` if users cannot log in, otherwise `low`;
# - add a one-line comment; triage never closes an issue and never edits pages.
#
# Your harness must:
# - [ ] build the dict tracker (copied from lesson 01) and a text `observe()` view of it;
# - [ ] offer `@tool` actions: `triage_issue` and lesson 01's `close_issue` (a tempting wrong action);
# - [ ] run a loop with at most **2 model calls** and at most **6 actions**, sending a `ToolMessage` for every tool call;
# - [ ] verify the final state against the policy and report `verified` or the list of problems;
# - [ ] print the model's last words next to the harness's verdict.

# %% [markdown]
# ## Build it
#
# ### 0. Setup and model (run this first)
# The same start as lesson 01. This lesson makes 2 model calls (one agent run); `max_calls=4` is the ceiling `llm_replay` enforces. With no key and no recording for your model, the model cells are skipped and a hand-written fallback keeps the notebook running.

# %% tags=["needs-llm"]
import sys; sys.path.insert(0, "..")
agent_messages = None     # filled by the agent-loop cell (stays None if it is skipped)
from llm_setup import get_llm
llm = get_llm("05_checkpoint_simulated_tracker", max_calls=4)

# %% [markdown]
# ### Your turn
# Build each requirement in the cells below, then compare with the reference solution. Suggested order: environment and `observe()`, then the tools, then the check (test it on a fresh tracker: it should report problems), and only then the loop. Writing the check before the loop means you decide what "done" is before you see what the model does.

# %%
# your code here: environment, observe(), tools

# %% [markdown]
# Now the outcome check and the capped loop.

# %%
# your code here: check_triage(env), then the agent loop with both limits

# %% [markdown]
# ## Reference solution
# Try the build first. The reference below is one way to do it.
#
# ### 1. The environment and the observation
# The tracker from lesson 01, with two new fields per issue: `label` and `priority`, both empty. `observe()` is the agent's whole view of the world (lesson 02): one text line per issue.

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

def observe(env):
    return "\n".join(f"#{i} [{x['status']}] label={x.get('label', '-')} priority={x.get('priority', '-')} "
                     f"comments={len(x['comments'])} | {x['title']}" for i, x in env["issues"].items())

tracker = new_tracker()
print(observe(tracker))

# %% [markdown]
# ### 2. The actions
# Two `@tool` functions (lesson 03: an API-level action needs only the API and its result). `triage_issue` checks its inputs and returns an error string instead of crashing, so the model can read what went wrong. `close_issue` is lesson 01's tool; the policy says not to use it, and the check will notice if it is used.

# %%
from langchain_core.tools import tool

@tool
def triage_issue(issue_id: int, label: str, priority: str, comment: str) -> str:
    """Set an issue's label ('bug' or 'docs') and priority ('high' or 'low'), and add a comment."""
    if issue_id not in tracker["issues"]:
        return f"ERROR: no issue #{issue_id}"
    if label not in ("bug", "docs") or priority not in ("high", "low"):
        return "ERROR: label must be 'bug' or 'docs'; priority must be 'high' or 'low'"
    issue = tracker["issues"][issue_id]
    issue.update(label=label, priority=priority)
    issue["comments"].append(comment)
    return f"OK: #{issue_id} label={label} priority={priority}"

@tool
def close_issue(issue_id: int, comment: str) -> str:
    """Close an issue with a short comment explaining the fix."""
    if issue_id not in tracker["issues"]:
        return f"ERROR: no issue #{issue_id}"
    tracker["issues"][issue_id].update(status="closed")
    tracker["issues"][issue_id]["comments"].append(comment)
    return f"OK: issue #{issue_id} closed"

tools = {t.name: t for t in [triage_issue, close_issue]}
print(list(tools))

# %% [markdown]
# ### 3. The outcome check, written before the loop
# The expected result follows from the policy alone: #1 blocks login (`bug`, `high`), #2 is a search bug (`bug`, `low`), #3 is page text (`docs`, `low`). The check also guards what must **not** change: no issue closed, the About page untouched.

# %%
EXPECTED = {1: ("bug", "high"), 2: ("bug", "low"), 3: ("docs", "low")}

def check_triage(env):
    problems = []
    for i, (label, priority) in EXPECTED.items():
        issue = env["issues"][i]
        if (issue.get("label"), issue.get("priority")) != (label, priority):
            problems.append(f"#{i}: got {issue.get('label')}/{issue.get('priority')}, expected {label}/{priority}")
        if not issue["comments"]:
            problems.append(f"#{i}: no comment")
        if issue["status"] != "open":
            problems.append(f"#{i}: was {issue['status']} (triage must not close issues)")
    if env["pages"] != new_tracker()["pages"]:
        problems.append("a page was edited")
    return problems

print("fresh tracker:", check_triage(new_tracker()))

# %% [markdown]
# On a fresh tracker the check lists six problems (a missing label/priority and a missing comment for each issue). An agent that did nothing cannot pass.
#
# ### 4. The prompt
# The policy goes into the prompt word for word, with the current observation. The prompt asks for all tool calls in the first response, which keeps the run to 2 model calls: one that acts, one that reads the results and replies.

# %%
policy = ("Triage policy: label 'docs' if the issue is about text on a page, otherwise 'bug'. "
          "Priority 'high' if users cannot log in, otherwise 'low'. Add a one-line comment. "
          "Triage never closes issues and never edits pages.")
prompt = (f"You are a triage agent for Pocket Tracker. Triage issues #1, #2 and #3.\n{policy}\n"
          "In your first response, call triage_issue once for each of the three issues (all tool calls "
          "at once). After you see the tool results, reply with a one-line summary.\n"
          f"Current issues:\n{observe(tracker)}")
print(prompt)

# %% [markdown]
# ### 5. The loop with two limits
# `MAX_MODEL_CALLS` caps the decide steps; `MAX_ACTIONS` caps the act steps, so one runaway response with many tool calls cannot do unlimited damage. A tool call past the action limit is not run, but it still gets a `ToolMessage` saying so (every tool call needs an answer). The `run` dict records why the loop stopped.

# %% tags=["needs-llm"]
from langchain_core.messages import HumanMessage, ToolMessage

MAX_MODEL_CALLS, MAX_ACTIONS = 2, 6
agent = llm.bind_tools(list(tools.values()))
agent_messages = [HumanMessage(prompt)]
run = {"model_calls": 0, "actions": 0, "stopped_by": "model call limit", "last_words": ""}
while run["model_calls"] < MAX_MODEL_CALLS:
    reply = agent.invoke(agent_messages)
    run["model_calls"] += 1
    agent_messages.append(reply)
    run["last_words"] = reply.text
    if not reply.tool_calls:
        run["stopped_by"] = "model finished"
        break
    for call in reply.tool_calls:
        if run["actions"] < MAX_ACTIONS:
            run["actions"] += 1
            result = tools[call["name"]].invoke(call["args"])
        else:
            result = "ERROR: action limit reached, not run"
        print(f"call {run['model_calls']}: {call['name']}({call['args']}) -> {result}")
        agent_messages.append(ToolMessage(result, tool_call_id=call["id"]))
print(run)

# %% [markdown]
# If the model cell was skipped, this cell applies the policy by hand (a hand-written example, not model output) so the verification below still has something to check.

# %%
if not globals().get("agent_messages"):        # also covers a skipped setup cell
    agent_messages = None
    for i, (label, priority) in EXPECTED.items():
        args = {"issue_id": i, "label": label, "priority": priority, "comment": "Triaged by policy."}
        print("fallback:", tools["triage_issue"].invoke(args))
    run = {"model_calls": 0, "actions": 3, "stopped_by": "fallback (no model)", "last_words": "n/a"}
print(observe(tracker))

# %% [markdown]
# ### 6. Verify: the claim next to the outcome
# The model's last words are only a claim. The verdict comes from `check_triage` on the tracker the harness changed. The same code gives the same verdict for any model and any wording.

# %%
problems = check_triage(tracker)
print("model says:  ", run["last_words"][:200] or "(no text)")
print("harness says:", "verified" if not problems else problems)
print(f"steps used: {run['model_calls']}/{MAX_MODEL_CALLS} model calls, "
      f"{run['actions']}/{MAX_ACTIONS} actions, stopped by: {run['stopped_by']}")

# %% [markdown]
# Read the three lines together. If the harness says `verified`, the state matches the policy no matter how the summary is worded. If it lists problems, the summary is wrong wherever it disagrees, even if it sounds confident.
#
# ### 7. The step limit does its job
# A harness must also stop when the model does not. Here the same action-limit rule is applied to a hand-written response with ten tool calls (not model output) to show that only six run and the rest are refused.

# %%
tracker = new_tracker()
flood = [{"name": "triage_issue", "id": f"c{k}", "args": {"issue_id": 1 + k % 3, "label": "bug",
          "priority": "low", "comment": f"pass {k}"}} for k in range(10)]
actions = 0
for call in flood:
    if actions < MAX_ACTIONS:
        actions += 1
        tools[call["name"]].invoke(call["args"])
print("actions run:", actions, "| refused:", len(flood) - actions)
print("comments per issue:", {i: len(x["comments"]) for i, x in tracker["issues"].items()})

# %% [markdown]
# Six ran, four were refused. The limit caps the damage, not the mistakes: this flood also labelled #1 and #3 wrongly, and the outcome check says so.

# %%
print(check_triage(tracker))

# %% [markdown]
# ## At work
# - Computer-use guidance from Anthropic and OpenAI asks for step, time and cost limits plus a check of the actual outcome; real loops cap at 20 responses (OpenAI's example) or 5 turns (Gemini's) → lesson 39.
# - A check is only as honest as what it looks at: a verifier that reads text the agent can write (its summary, or tests it can edit) gets gamed → lessons 18 and 40.
# - Evals of stateful agents judge the **end state**, not the transcript (Anthropic's multi-agent post); SWE-bench-style harnesses do this with hidden tests → lessons 46 and 47.
# - Production runs persist the full transcript and every tool input and output, because a non-deterministic run is hard to reproduce later → lesson 44a.

# %% [markdown]
# ## What just happened
# - **Observe:** `observe()` turned the dict into the text the model saw; the model never touched the dict.
# - **Decide:** the model proposed triage actions as tool calls (the prompt asked for all three at once) and then replied; it never got more than 2 calls.
# - **Act:** the harness ran each tool call, answered every call with a `ToolMessage`, and counted model calls and actions against their limits.
# - **Verify:** `check_triage` compared the final state with a policy written before the run, including what must not change.
# - The flood test showed the action limit stopping a runaway response, and the check catching the wrong labels it left.

# %% [markdown]
# ## Common mistakes
# Verifying the claim. A check like "the reply mentions all three issues" passes on words alone. Here a tracker where only #1 was triaged (hand-written state) meets the real check, which fails:

# %% tags=["raises-exception"]
half_done = new_tracker()
half_done["issues"][1].update(label="bug", priority="high", comments=["blocks login"])
assert not check_triage(half_done), check_triage(half_done)

# %% [markdown]
# Fix: decide "done" from the environment. Two more mistakes: a loop with no limit on actions per response, and a check that tests only what should change (it would miss a closed issue or an edited page).

# %% [markdown]
# ## Key terms
# - **agent loop** — the repeated cycle observe → decide → act, run by the harness until the model stops or a limit is hit, followed by verification.
# - **outcome verification** — deciding success by checking the environment's final state against a definition of done written before the run, never by the model's report.
# - **step limit** — a harness cap on model calls and on actions per run, so a run that does not converge stops and does limited damage.
# - **triage** — giving an issue a label, a priority and a comment without fixing or closing it.

# %%
import sys; sys.path.insert(0, "..")
import llm_replay
llm_replay.stop()

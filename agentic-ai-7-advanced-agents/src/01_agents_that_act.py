# %% [markdown]
# # 01 · Agents that act on a computer
# Level L1 · Part 1 · core · ~20 min · builds on 00

# %% [markdown]
# ## Goal
# By the end you can run a small agent loop where a real model closes issue #3 in Pocket Tracker by acting on an **environment**, and you can show with a check on that environment (not on the model's words) that the work was really done.

# %% [markdown]
# ## The idea
# A chat model can only *describe* a fix. An agent that acts on a computer works in a loop with four parts:
# - the **environment**: the thing being changed (here, the tracker's data);
# - an **observation**: what the agent sees of it (a text view of the issues and pages);
# - an **action**: a tool call that changes it (`close_issue`, `edit_page`);
# - the **harness**: your code, which runs each action, sends back the new observation, and checks the result at the end.
#
# Analogy: a mechanic on the phone tells you which bolt to tighten. A mechanic in the garage tightens it, looks again, and test-drives the car.

# %% [markdown]
# ## Picture
# ```mermaid
# flowchart LR
#   H[Harness] -->|observation| M[Model]
#   M -->|action = tool call| H
#   H -->|runs it| E[(Environment<br/>tracker dict)]
#   E -->|new state| H
#   H -->|at the end| C{Check the<br/>environment}
# ```

# %% [markdown]
# ## Step by step
#
# ### 1. Setup and model
# Same start as lesson 00. To switch model, set `TUT_LLM_PROVIDER` / `TUT_LLM_MODEL` in `.env` or pass `provider=`, `model=` to `get_llm`. The table shows which keys are set and which models have a recording for this lesson. The lesson makes 3 model calls: 1 chat-only call and 2 in the agent loop. `max_calls=4` is the lesson's budget, a ceiling that `llm_replay` enforces.

# %% tags=["needs-llm"]
import sys; sys.path.insert(0, "..")
chat_msg = None           # filled by the chat-only model cell (stays None if it is skipped)
agent_messages = None     # filled by the agent-loop cell (stays None if it is skipped)
from llm_setup import get_llm
llm = get_llm("01_agents_that_act", max_calls=4)

# %% [markdown]
# ### 2. The environment
# Pocket Tracker is still a Python dict today (a real app arrives in lesson 06). Issue #3 is a typo on the About page. "Done" means two things: the page text is fixed **and** the issue is closed.

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

tracker = new_tracker()
print(tracker["issues"][3]["status"], "|", tracker["pages"]["about"])

# %% [markdown]
# ### 3. The observation
# The model never sees the dict itself. The harness turns the environment into text. This function is the agent's whole view of the world.

# %%
def observe(env):
    lines = ["ISSUES"]
    for i, issue in env["issues"].items():
        lines.append(f"  #{i} [{issue['status']}] {issue['title']}")
    lines.append("PAGES")
    for name, text in env["pages"].items():
        lines.append(f"  {name}: {text!r}")
    return "\n".join(lines)

print(observe(tracker))

# %% [markdown]
# ### 4. A chat model without tools
# First we ask the model with no tools at all. One model call. Whatever it writes, it has no way to touch the tracker.

# %% tags=["needs-llm"]
task = "Resolve issue #3 in Pocket Tracker."
chat_msg = llm.invoke(f"{task}\nCurrent state:\n{observe(tracker)}")
print(chat_msg.text[:400])   # first 400 characters

# %% [markdown]
# The model answered in prose (only the first 400 characters are shown). It may describe the fix well, or even claim it is done. Now look at the environment:

# %%
print("issue #3:", tracker["issues"][3]["status"])
print("about page:", tracker["pages"]["about"])

# %% [markdown]
# Nothing changed. Describing a fix is not doing it.
#
# ### 5. The actions
# Now we give the model **actions**: LangChain `@tool` functions that really change the environment. Each returns a short result the model can read. Bad input returns an error message instead of crashing, so the model can recover.

# %%
from langchain_core.tools import tool

@tool
def edit_page(page: str, old_text: str, new_text: str) -> str:
    """Replace old_text (must appear exactly once) with new_text on a tracker page."""
    text = tracker["pages"].get(page)
    if text is None or text.count(old_text) != 1:
        return f"ERROR: '{old_text}' must appear exactly once on page '{page}'"
    tracker["pages"][page] = text.replace(old_text, new_text)
    return f"OK: page '{page}' is now {tracker['pages'][page]!r}"

@tool
def close_issue(issue_id: int, comment: str) -> str:
    """Close an issue with a short comment explaining the fix."""
    if issue_id not in tracker["issues"]:
        return f"ERROR: no issue #{issue_id}"
    tracker["issues"][issue_id].update(status="closed")
    tracker["issues"][issue_id]["comments"].append(comment)
    return f"OK: issue #{issue_id} closed"

tools = {t.name: t for t in [edit_page, close_issue]}
print(list(tools))

# %% [markdown]
# ### 6. The harness: a small agent loop
# The loop: send the observation, run every tool call the model returns, send back each result as a `ToolMessage`, and repeat until the model answers without tool calls. A model can return several tool calls in one response; the harness runs them all. The prompt asks for both actions in the first response, so the loop needs 2 model calls: one that proposes the actions, one that reads the results and replies. A cap of 2 model calls stops a runaway loop.

# %% tags=["needs-llm"]
from langchain_core.messages import HumanMessage, ToolMessage

agent = llm.bind_tools(list(tools.values()))
agent_messages = [HumanMessage(f"You are an agent that acts on Pocket Tracker. {task} "
                               "In your first response, call edit_page and close_issue together "
                               "(both tool calls at once). After you see the tool results, reply 'done'.\n"
                               f"Current state:\n{observe(tracker)}")]
for model_call in range(1, 3):                 # cap: at most 2 model calls
    reply = agent.invoke(agent_messages)
    agent_messages.append(reply)
    if not reply.tool_calls:
        break
    print(f"model call {model_call} proposed {len(reply.tool_calls)} tool call(s):")
    for call in reply.tool_calls:
        result = tools[call["name"]].invoke(call["args"])
        print(f"  {call['name']}({call['args']}) -> {result}")
        agent_messages.append(ToolMessage(result, tool_call_id=call["id"]))
print("final reply:", reply.text[:200])

# %% [markdown]
# If the model cell was skipped, this cell runs the same actions by hand (a hand-written example, not model output) so the rest of the lesson still works.

# %%
if not globals().get("agent_messages"):        # also covers a skipped setup cell
    agent_messages = None
    for name, args in [("edit_page", {"page": "about", "old_text": "Trakcer", "new_text": "Tracker"}),
                       ("close_issue", {"issue_id": 3, "comment": "Fixed the typo on the About page."})]:
        print(f"fallback: {name}({args}) -> {tools[name].invoke(args)}")
if agent_messages:
    print("messages in the conversation:", [type(m).__name__ for m in agent_messages])
else:
    print("messages in the conversation: n/a (fallback)")

# %% [markdown]
# ### 7. Check the environment, not the claim
# The model's last reply may say it is done. The harness does not take its word: it checks the environment against the definition of done from step 2. This check is the same whatever model or wording you used.

# %%
def check_issue_3(env):
    problems = []
    if env["issues"][3]["status"] != "closed":
        problems.append("issue #3 is still open")
    if "Trakcer" in env["pages"]["about"]:
        problems.append("the typo is still on the About page")
    return problems

print("problems:", check_issue_3(tracker) or "none, issue #3 is really resolved")
print(observe(tracker))

# %% [markdown]
# For contrast, the same check on a fresh tracker, which is all the chat-only model could ever leave behind:

# %%
print("chat-only result:", check_issue_3(new_tracker()))

# %% [markdown]
# ## At work
# - Claude Code's own docs describe its loop as gather context → act → verify; the harness (tools plus context management) matters as much as the model → lesson 15.
# - The verify step must look at the real outcome: computer-use guidance from Anthropic and OpenAI says to check the actual state of the app, not the model's report; a verifier that can be fooled gets gamed → lessons 18 and 40.
# - Production loops always have hard caps: OpenAI's computer-use example stops at 20 responses, Gemini's at 5 turns, and agents cannot judge elapsed time themselves → lesson 39.
# - Real environments are a browser or a repo, not a dict, and the actions run in an isolated sandbox → lessons 12 and 19.

# %% [markdown]
# ## What just happened
# - The **environment** was the tracker dict; the definition of done was written down before the agent started.
# - The **observation** was a text view made by `observe()`; the model never touched the dict directly.
# - The **actions** were `@tool` functions; the model only proposed them in `AIMessage.tool_calls`.
# - The **harness** ran each action, returned a `ToolMessage`, capped the turns, and checked the environment at the end.
# - The chat model without tools left the tracker unchanged, whatever it wrote.

# %% [markdown]
# ## Common mistakes
# Trusting the model's last message. A reply like "done, issue #3 is closed" is just text. Here a tracker that only received a chat answer is checked with an assertion; it fails because nothing acted on it:

# %% tags=["raises-exception"]
chat_only_tracker = new_tracker()   # what the chat-only model left behind
assert not check_issue_3(chat_only_tracker), check_issue_3(chat_only_tracker)

# %% [markdown]
# Fix: give the model actions, let the harness run them, then assert on the environment the harness changed.

# %%
assert not check_issue_3(tracker)
print("verified on the environment: issue #3 resolved")

# %% [markdown]
# Two more: forgetting to send a `ToolMessage` for **every** tool call (most providers reject the next request), and letting the loop run with no turn cap.

# %% [markdown]
# ## Try it
# Issue #2 says search ignores capital letters. Add a `search` entry to the environment as a function, and write `check_issue_2(env)` that returns a list of problems: the issue is still open, or `env["search"](env, "SEARCH")` does not return `[2]`. Run it on a tracker with a case-sensitive search (expect two problems) and on one with a fixed search and issue #2 closed (expect none). No model needed.

# %%
# your code here

# %% [markdown]
# ## Key terms
# - **environment** — the system an agent changes (a tracker, a browser page, a repo); it holds the real state.
# - **observation** — what the harness shows the model of the environment, such as a text view, an aria snapshot or a screenshot.
# - **action** — a tool call the model proposes and the harness runs to change the environment.
# - **harness** — the code around the model that runs its tool calls, returns the results, caps the loop and checks the outcome.
# - **turn cap** — the maximum number of model turns the harness allows before it stops the loop.

# %%
import sys; sys.path.insert(0, "..")
import llm_replay
llm_replay.stop()

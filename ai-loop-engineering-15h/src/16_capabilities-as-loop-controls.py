# %% [markdown]
# # 16 · Tools, MCP, skills and hooks as the loop's controls
# Level L3 · Part 2 · professional · ~20 min · builds on 15
#
# ## Goal
# Choose which capability a loop gets (a tool, an MCP server, a skill file or a hook), and put each rule where code can enforce it: a refund over 100 USD is refused by a hook before it is written, whatever the model asks.
#
# ## Why it matters
# A loop gets capabilities in one of two places: the prompt, or the tool list. Without a choice, the team's rules end up as text, and text is a request, not a check. Without choosing:
#
# | Without a choice | What goes wrong |
# |---|---|
# | The rules sit in the prompt | The model may skip them, and nothing checks the write. A refund of 120 USD on a 100 USD rule goes through with no error |
# | The whole handbook goes in every call | Each call pays for every page, even when the case needs one |
# | Each agent wires each service itself | N agents times M services of glue code, and each copy drifts |
#
# With the four controls in their places, a rule that must hold becomes a hook: code that runs before the tool and can refuse the call. Guidance becomes a skill the model loads when it needs it. You do not need this for a loop with one tool and no rule to check.

# %% [markdown]
# ## The idea
# **Four controls, each with one job. A tool is a function the model can ask your code to run. An MCP server is a separate process that offers tools over the Model Context Protocol, so any client can use it (step 6's in-process SDK server only borrows the naming). A skill is a folder with a `SKILL.md` file: instructions the model reads when it needs them. A hook is code the agent runs at a fixed point, such as before each tool call, and it can refuse the call. The model chooses; a hook decides.**
#
# Analogy: a tool is a till the clerk may use, a skill the policy binder, an MCP server a shared cash register, a hook the manager whose signature a refund needs.
#
# LangChain has no hooks, so Step 4 imitates the hook's shape; Step 6 uses the Agent SDK's real ones.

# %% [markdown]
# ## Picture
# The model asks for a tool call. A `PreToolUse` hook runs first. Allow sends the call to the tool. Deny sends the reason back to the model as the tool result. A skill is not on the path: the model loads it on request.
#
# ```mermaid
# flowchart LR
#   M["Model: asks for a tool call"] --> H{"PreToolUse hook: allow or deny?"}
#   H -->|"deny: the reason goes back to the model"| M
#   H -->|"allow"| T["Tool: your function or an MCP server's tool"]
#   T --> R["Result back into the loop"]
#   S["Skill: SKILL.md, loaded when the model asks"] -.-> M
# ```

# %% [markdown]
# ## Step by step
# ### Step 1: the four controls (no model call)
#
# | Control | Who runs it | Can it refuse a bad write? | What it costs in context |
# |---|---|---|---|
# | Tool | Your code, when the model asks | Only if the tool checks | Its schema, in every call |
# | MCP server | A separate process, through the MCP client | Only if the server or a hook checks | The schemas of its tools (deferred in the Agent SDK) |
# | Skill (`SKILL.md`) | The model reads it on request | No: it is guidance | Name and description always; the body only when loaded |
# | Hook | The agent, at a fixed event | Yes: a deny is final for that call | Nothing in the prompt; it is code |
#
# The MCP protocol and how to write a server are covered in the agentic AI course, not here. This lesson chooses between the four.

# %% [markdown]
# ### Step 2: the tools, and a write with no check (no model call)
# The desk has two tools: `get_order` reads an order, and `issue_refund` writes a refund into a ledger. The orders are the same three as in lesson 03. The cell below calls `issue_refund` by hand, to show what a loop does with no check. The call is written by us, not by a model.

# %%
import sys
from pathlib import Path

sys.path.insert(0, ".."); import llm_replay
llm_replay.start("16_capabilities-as-loop-controls")  # records the model calls once, replays them later
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from llm_setup import DEFAULT_MODELS, get_llm

ROOT = Path("../data/16"); REFUNDS = []  # run-time files of this lesson; the ledger of what the loop has written
ORDERS = {  # the stand-in order record, as in lesson 03
    "BS-1042": {"customer": "C-17", "item": "Trail jacket", "paid_usd": 120.0, "status": "delivered"},
    "BS-1043": {"customer": "C-22", "item": "Rain shell", "paid_usd": 85.0, "status": "delivered"},
    "BS-1044": {"customer": "C-17", "item": "Merino socks", "paid_usd": 18.0, "status": "shipped"}}

# %% [markdown]
# `@tool` turns each function into the schema the model reads, as in lesson 03.

# %%
@tool
def get_order(order_id: str) -> dict:
    """Look up one order: customer, item, amount paid and delivery status."""
    return ORDERS.get(order_id, {"error": f"no order {order_id}"})

@tool
def issue_refund(order_id: str, amount_usd: float) -> str:
    """Refund an amount on one order. The amount may not be more than the amount paid."""
    order = ORDERS.get(order_id)
    if order is None:
        return f"error: no order {order_id}"
    if amount_usd > order["paid_usd"]:
        return f"error: {amount_usd} is more than the {order['paid_usd']} paid"
    REFUNDS.append({"order_id": order_id, "amount_usd": amount_usd})
    return f"refunded {amount_usd} on {order_id}"

TOOLS_BY_NAME = {t.name: t for t in [get_order, issue_refund]}  # load_skill joins in step 3

# %% [markdown]
# The call below is ours, not a model's. It shows the loop with no check.

# %%
print(issue_refund.invoke({"order_id": "BS-1042", "amount_usd": 120.0}))  # a call we write by hand: no check
print("ledger:", REFUNDS)

# %% [markdown]
# ### Step 3: the skill, loaded in two parts (no model call)
# A skill is a folder, `.claude/skills/<name>/SKILL.md`. The top part, between the `---` lines, is YAML frontmatter with a `name` and a `description`. The rest is the body: the instructions. **Progressive disclosure** means the prompt carries only the name and the description. The body is loaded when the model asks for it. The Agent SDK does this for you once `setting_sources` loads the project folder (step 6). Here the loop does it with one tool, `load_skill`.

# %%
SKILL_DIR = ROOT / ".claude" / "skills" / "refund-policy"
SKILL = """---
name: refund-policy
description: Brightside refund rules for the support desk. Read before any refund decision.
---
# Refund policy
1. Look up the order with get_order first. Never refund more than was paid.
2. A damaged item of 100 USD or less: call issue_refund once with the amount paid.
3. Above 100 USD: do not refund. Say that a person will review the case.
"""
SKILL_DIR.mkdir(parents=True, exist_ok=True); (SKILL_DIR / "SKILL.md").write_text(SKILL)

_, front, body = SKILL.split("---\n", 2)  # the two parts of the file
meta = dict(line.split(": ", 1) for line in front.strip().splitlines()); CATALOG = f"- {meta['name']}: {meta['description']}"  # always in the prompt
print("in the prompt:", len(CATALOG), "characters | loaded on request:", len(body.strip()), "characters")

@tool
def load_skill(name: str) -> str:
    """Load the full instructions of one team skill, by its name from the catalog."""
    return body.strip() if name == meta["name"] else f"no skill named {name}"

TOOLS_BY_NAME["load_skill"] = load_skill

# %% [markdown]
# ### Step 4: a hook that decides before the write (no model call)
# A hook is a function that gets the event before the tool runs: `hook_event_name`, `tool_name` and `tool_input`. Returning `{}` allows the call. Returning `permissionDecision: "deny"` stops it, and the reason goes back to the model. The shape matches the Agent SDK's `PreToolUse` hook. LangChain's loop has no hook system, so our loop calls the hook itself, in `run_tool`.

# %%
REFUND_LIMIT_USD = 100.0

def refund_guard(input_data: dict) -> dict:  # a PreToolUse hook: {} allows, a deny dict refuses
    name = input_data["tool_name"].split("__")[-1]  # strips the mcp__desk__ prefix so both names match
    if input_data["hook_event_name"] == "PreToolUse" and name == "issue_refund" and float(input_data["tool_input"]["amount_usd"]) > REFUND_LIMIT_USD:
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                "permissionDecisionReason": f"refunds above {REFUND_LIMIT_USD:.0f} USD need a person"}}
    return {}

def run_tool(call: dict) -> str:  # our loop's step: the hook first, then the tool
    verdict = refund_guard({"hook_event_name": "PreToolUse", "tool_name": call["name"], "tool_input": call["args"]})
    if verdict:  # {} means allow
        return "denied by hook: " + verdict["hookSpecificOutput"]["permissionDecisionReason"]
    return str(TOOLS_BY_NAME[call["name"]].invoke(call["args"]))

REFUNDS.clear()
for amount in (120.0, 40.0):
    print(amount, "->", run_tool({"name": "issue_refund", "args": {"order_id": "BS-1042", "amount_usd": amount}}))
print("ledger:", REFUNDS)

# %% [markdown]
# ### Step 5: one live loop with the model (needs a model, 3 calls)
# The model gets the catalog of skills and the request. It may load the skill, look up the order and ask for a refund. Every tool call passes `run_tool`, so the hook decides the write. The loop has a cap of four model calls. The recorded run made three. In that run the model read the 100 USD rule in the skill, asked for no refund, and wrote a refusal, so no call reached the hook. Step 4 shows the hook on the 120 USD call.
#
# **What you will see:** The model reads the rule and refuses on its own, so the hook stays silent. That is luck, not a guarantee. Step 4 shows the hook doing the stopping.

# %% tags=["needs-llm"]
llm = get_llm(model=DEFAULT_MODELS["gemini"])  # the key comes from .env; a recording replays without one
SYSTEM = ("You are the support desk for Brightside Outfitters. Skills you can load by name:\n" + CATALOG
          + "\nLoad the skill before a refund decision. Call issue_refund at most once.")
REQUEST = "Customer C-17 says the trail jacket from order BS-1042 arrived torn after one wash. Refund what was paid."
MAX_CALLS = 4  # our cap on model calls, the same idea as max_turns

bound = llm.bind_tools(list(TOOLS_BY_NAME.values()))
messages = [SystemMessage(content=SYSTEM), HumanMessage(content=REQUEST)]
REFUNDS.clear()
calls, stop = 0, "the model stopped asking for tools"
while True:
    if calls == MAX_CALLS:
        stop = "cap of model calls reached"
        break
    reply = bound.invoke(messages)
    calls += 1
    messages.append(reply)
    if not reply.tool_calls:
        break
    for call in reply.tool_calls:
        out = run_tool(call)
        print(f"  {call['name']}({call['args']}) -> {out[:80]}")
        messages.append(ToolMessage(content=out, tool_call_id=call["id"]))
print(f"model calls: {calls} | stop: {stop} | refunds written: {REFUNDS}")
print("final reply:", reply.text)

# %% [markdown]
# The count below reads the tool results in `messages`. It makes no model call.

# %%
print("hook fired:", sum(isinstance(m, ToolMessage) and m.content.startswith("denied by hook") for m in messages), "times")

# %% [markdown]
# ### Step 6: the same rules in the Agent SDK (walkthrough, no model call)
# The Claude Agent SDK runs the hook for you. The SDK wraps your function in an MCP-style server inside your own process, so it gets the MCP naming: an SDK tool is named `mcp__<server>__<tool>`, and the hook's matcher uses that name. A real MCP server would be a separate program. No call is made here, so the key is optional.
#
# The options, one line each:
# - `cwd`: the folder that holds `.claude/skills`.
# - `setting_sources=["project"]`: loads the project skills. With `skills` set, the docs load user and project sources by default, so the line makes the choice visible.
# - `skills`: the skills the model may invoke.
# - `mcp_servers` and `hooks`: the in-process `desk` server, and its `PreToolUse` hook matched on the full name.
# - `max_turns`: `error_max_turns` at this many tool-use round trips.
# - `max_budget_usd`: a dollar cap, checked after a response, so a run can overshoot a little.

# %%
from claude_agent_sdk import ClaudeAgentOptions, HookMatcher, create_sdk_mcp_server, tool as sdk_tool

@sdk_tool("issue_refund", "Refund an amount on one order, at most the amount paid.", {"order_id": str, "amount_usd": float})
async def sdk_issue_refund(args):  # the desk's write, as an SDK tool
    return {"content": [{"type": "text", "text": issue_refund.func(args["order_id"], args["amount_usd"])}]}

async def sdk_refund_guard(input_data, tool_use_id, context):  # the SDK's callback shape, the same rule
    return refund_guard(input_data)

options = ClaudeAgentOptions(
    cwd=str(ROOT), setting_sources=["project"], skills=["refund-policy"],  # the model may invoke refund-policy from .claude/skills
    mcp_servers={"desk": create_sdk_mcp_server(name="desk", tools=[sdk_issue_refund])},
    hooks={"PreToolUse": [HookMatcher(matcher="mcp__desk__issue_refund", hooks=[sdk_refund_guard])]},
    max_turns=6, max_budget_usd=0.50,  # caps: error_max_turns after 6 round trips, error_max_budget_usd near $0.50
)
call_120 = {"hook_event_name": "PreToolUse", "tool_name": "mcp__desk__issue_refund", "tool_input": {"order_id": "BS-1042", "amount_usd": 120.0}}
assert (await sdk_refund_guard(call_120, "t1", None))["hookSpecificOutput"]["permissionDecision"] == "deny"  # the SDK callback denies 120 USD

# %% [markdown]
# **The live call (walkthrough, not run here, needs `ANTHROPIC_API_KEY`).** You do not need to run this. If you have a key, paste the snippet into a new cell (notebooks allow top-level `await` and `async for`). If not, the step 6 output is enough: it runs with no key and makes no model call. With a key, the query below sends the request to Claude. You should see the `Skill` tool load `refund-policy`, then a `denied` line from the hook for the 120 USD refund, and a final `ResultMessage`. Its `subtype` is `success`, or an `error_max_*` cap.
#
# ```python
# from claude_agent_sdk import query, ResultMessage
#
# async for message in query(prompt="Refund what was paid for order BS-1042", options=options):
#     if isinstance(message, ResultMessage):
#         print(message.subtype, message.num_turns, message.total_cost_usd)
# ```

# %% [markdown]
# ## At work
# - Claude Code and the Agent SDK run `PreToolUse` hooks before each tool call, and a deny is final for that call. Spotify runs its verifiers from the Stop hook before a pull request opens (RESEARCH.md, sections 7.7 and 7.8). → lesson 10 gates the end of a loop.
# - Permissions are a second layer: `allowed_tools` and `disallowed_tools` decide which tools a run may use at all. → lesson 23 limits what a run may touch.
# - Teams keep skills short and load the body on demand, because a prompt that carries every handbook page pays on every call. Instructions that exist only in the first message are lost when a chat is compacted. → lesson 15 keeps the rules in the system message.

# %% [markdown]
# ## Common mistakes
# Wrong: the rule lives only in the skill text, so the loop trusts the model to follow it. The cell below shows the write that results when nothing checks it. This error is expected: it is the write from step 2, `refunded 120.0 on BS-1042`, turned into a failed assertion.

# %% tags=["raises-exception"]
written = [{"order_id": "BS-1042", "amount_usd": 120.0}]  # a write made when only the skill text held the rule
assert all(r["amount_usd"] <= REFUND_LIMIT_USD for r in written), "a 120 USD refund passed: the skill is a request, not a check"  # AssertionError

# %% [markdown]
# Right: put the rule in a hook, and keep the skill for the wording and the steps.
#
# Wrong: a matcher that filters by amount. A matcher only matches the tool name (`issue_refund`, or `mcp__desk__issue_refund` in the SDK). The check on the amount belongs inside the hook callback, as in `refund_guard`.
#
# Wrong: an in-process SDK tool named `issue_refund` with a matcher of `issue_refund`. The SDK names it `mcp__desk__issue_refund`, so the hook never fires. Print the `tool_name` the hook receives, and match that exact string. The cell below shows the comparison.

# %%
matcher = "mcp__desk__issue_refund"  # the tool_name the SDK hook receives
print("matches the bare name:", matcher == "issue_refund", "| matches the SDK name:", matcher == "mcp__desk__issue_refund")

# %% [markdown]
# ## Try it
# A refund on an order that has not been delivered yet should be denied too. Write `refund_guard_v2(input_data)` that denies any `issue_refund` on an order whose `status` is not `delivered`, and otherwise calls `refund_guard`. Check it on `BS-1044` (status `shipped`, 18 USD) and on `BS-1042` (delivered, 120 USD, which the limit denies).

# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
def refund_guard_v2(input_data: dict) -> dict:
    if input_data["hook_event_name"] == "PreToolUse" and input_data["tool_name"] == "issue_refund":
        order = ORDERS.get(input_data["tool_input"]["order_id"], {})
        if order.get("status") != "delivered":
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                    "permissionDecisionReason": "the item has not been delivered yet"}}
    return refund_guard(input_data)

for oid, amount in (("BS-1044", 18.0), ("BS-1042", 120.0)):
    verdict = refund_guard_v2({"hook_event_name": "PreToolUse", "tool_name": "issue_refund",
                               "tool_input": {"order_id": oid, "amount_usd": amount}})
    print(oid, verdict["hookSpecificOutput"]["permissionDecisionReason"] if verdict else "allowed")

# %% [markdown]
# Save the recording. This is the last cell that touches the model layer.

# %%
llm_replay.stop()  # saves the recording (record mode) and closes the replay

# %% [markdown]
# ## Recap
# - A tool is a function your code runs when the model asks. An MCP server offers tools over a protocol. A skill is guidance loaded on request. A hook is code that can refuse a call before it runs.
# - Rules that must hold go in a hook; guidance goes in a skill. The model chooses, and the hook decides.
# - Progressive disclosure keeps a skill's body out of the prompt until it is needed.
# - `max_turns` and `max_budget_usd` are the Agent SDK's versions of the caps in lesson 10. The hook matcher uses the tool's full name, and the caps are checked after a response.
#
# **Interview:** Where would you put a rule that a refund must never exceed the amount paid: in the prompt, in a skill, or in a hook? Strong answer: in a hook. A prompt and a skill are requests the model may skip. A hook runs before the write and refuses it.

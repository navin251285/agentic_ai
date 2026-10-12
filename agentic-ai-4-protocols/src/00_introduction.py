# %% [markdown]
# # 00 · Why agents need protocols: the big picture in plain words
# Level L1 · Part 1 · core · ~35 min · builds on —

# %% [markdown]
# ## Goal
# By the end you can draw the three **communication lines** every agent has (to tools and data, to other agents, to the user), say what goes wrong on each line without a shared protocol, and name the protocol that fixes each one: **MCP**, **A2A** or **AG-UI**. You have also picked the model this course will use on your machine.

# %% [markdown]
# ## The idea
# An agent is a model that can **do things**: look up data, call other programs, ask for help, report back. Each of those is a conversation with something outside the model.
#
# If every app invents its own way to have that conversation, nothing fits together. Each new tool needs new glue code in every app. Things break when one side changes. Nobody checks who is allowed to do what.
#
# A **protocol** is a shared language with fixed rules: how to ask, how to answer, how to report an error. Build to it once, and everything else that speaks it can connect.
#
# Analogy: USB-C. Before it, every phone had its own charger. Now one cable fits every device. MCP, A2A and AG-UI are the USB-C plugs of agents, one for each kind of connection.

# %% [markdown]
# ## Picture
# ```mermaid
# flowchart LR
#   U[User's screen] <-->|"AG-UI<br/>agent ↔ user"| A[Your agent]
#   A <-->|"MCP<br/>agent ↔ tools and data"| T[(Tools and data<br/>issues DB, files, APIs)]
#   A <-->|"A2A<br/>agent ↔ agent"| B[Other agents<br/>triage-agent, fix-agent]
# ```
# Three lines, three protocols. Each protocol does **one job**. They work together; they do not compete.

# %% [markdown]
# ## Already know this?
# Part 1 (lessons 00–02) covers the "why" and your first MCP server. If you can answer these, skip to **lesson 03**:
# 1. With 3 agent apps and 5 tools, how many custom integrations do you need without a protocol, and how many with one?
# 2. Which protocol connects an agent to tools and data, which to other agents, and which to the user's screen?
# 3. With those 3 apps and 5 tools, why does adding a 6th tool cost 1 adapter with a protocol, but 3 glue pieces (one per app) without it?
# 4. What does an agent lose if the screen shows only the final answer?
# 5. Who actually runs an MCP tool: the model, the client, or the server?

# %% [markdown]
# ## Step by step
#
# ### 1. Choose your model
# Some cells in this course call a real model. `get_llm()` lists every model, whether its key is set, and whether this lesson has a **recording** of its model calls. The course ships recordings for the default model (`gemini-3.1-flash-lite`), so this lesson runs with **no key and no cost**.
#
# To use another model, set `TUT_LLM_PROVIDER` and `TUT_LLM_MODEL` in the topic's `.env` file.
#
# First, empty placeholders so later cells still run if the model cells are skipped.

# %%
import sys; sys.path.insert(0, "..")
msg_chat = msg_ide = None   # filled by the two model cells below (stay None if they are skipped)
print("Fallbacks ready: later cells still run if the model cells are skipped")

# %% [markdown]
# Now pick the model. ✓ means the provider's key is set on this machine; `recorded` means this lesson can replay that model with no key.

# %% tags=["needs-llm"]
from llm_setup import get_llm
llm = get_llm("00_introduction", max_calls=3)   # this lesson makes 2 model calls

# %% [markdown]
# ### 2. Meet Trackr
# Our running example is **Trackr, the team ops desk**: a small issue tracker shared by four teams. Today it is a plain Python list of 20 issues. In lesson 01 the same data goes behind a real MCP server.

# %%
rows = """1 Login button does nothing on Safari|web|open|high
2 Signup email arrives twice|api|open|medium
3 Dark mode hides the save icon|web|closed|low
4 App crashes when photo is rotated|mobile|open|critical
5 Rate limiter blocks health checks|infra|open|high
6 Search ignores capital letters|api|open|low
7 Push notifications arrive late|mobile|open|medium
8 Disk alert fires every night at 2am|infra|closed|medium
9 Typo on the pricing page|web|open|low
10 Export to CSV drops the last row|api|open|high
11 Offline mode loses drafts|mobile|closed|high
12 TLS certificate expires in 9 days|infra|open|critical
13 Footer links open in the same tab|web|closed|low
14 Pagination returns duplicates|api|open|medium
15 Battery drain in background sync|mobile|open|high
16 Backups not copied to second region|infra|open|high
17 Profile page slow to load|web|open|medium
18 Webhook retries never stop|api|closed|medium
19 Tablet layout cuts off buttons|mobile|open|low
20 Log volume doubled since Monday|infra|open|medium"""
fields = [line.split("|") for line in rows.splitlines()]   # "id title", team, status, severity
ISSUES = [{"id": int(h.split(" ", 1)[0]), "title": h.split(" ", 1)[1], "team": t, "status": st, "severity": sv}
          for h, t, st, sv in fields]
print(len(ISSUES), "issues; first:", ISSUES[0])

# %% [markdown]
# Here is the one capability we want our agents to use: count the open issues for a team. It is a normal Python function. Nothing about agents yet.

# %%
def count_open_issues(team: str) -> int:
    """Count the open issues for one team."""
    return sum(1 for i in ISSUES if i["team"] == team and i["status"] == "open")

for team in ["web", "api", "mobile", "infra"]:
    print(f"{team:7} {count_open_issues(team)} open")

# %% [markdown]
# ### 3. Where protocols fit: the agentic AI spectrum
# Agents grow in steps. Each step adds a new **line** the agent must talk on.
#
# ```mermaid
# flowchart LR
#   C["1 · Chatbot<br/>talks to the user"] --> T["2 · Tool-using agent<br/>+ tools and data"]
#   T --> M["3 · Multi-agent<br/>+ other agents (same team)"]
#   M --> X["4 · Cross-organisation<br/>+ agents from other companies"]
# ```
# The cell prints which lines exist at each step, and which protocol covers them.

# %%
LINES = {"chat": "no agent line (just its own chat box)",
         "user": "agent ↔ user (AG-UI)",
         "tools": "agent ↔ tools/data (MCP)",
         "agents": "agent ↔ agent (A2A)"}
SPECTRUM = [
    ("1 Chatbot", ["chat"], "answers questions about issues you paste in"),
    ("2 Tool-using agent", ["user", "tools"], "reads and counts Trackr issues itself"),
    ("3 Multi-agent", ["user", "tools", "agents"], "hands triage to a triage-agent your team wrote"),
    ("4 Cross-organisation", ["user", "tools", "agents"], "asks a vendor's agent it has never met; must find and trust it"),
]
for stage, lines, trackr in SPECTRUM:
    print(f"{stage:22} {trackr}")
    for key in lines:
        print(f"{'':22}   - {LINES[key]}")

# %% [markdown]
# A plain chatbot needs no agent protocol: it only talks to you through its own chat box, which is not one of the three lines. From step 2 on, the agent talks to things **other people built**. That is where a shared language starts to matter, and step 4 adds the hardest problem: finding and trusting a stranger.

# %% [markdown]
# ### 4. Example 1: the same tool, hand-wired into two apps
# Two teams build two agent apps over Trackr: a **chat bot** in the team chat and an **IDE assistant**. Both want `count_open_issues`. With no protocol, each app writes its own **glue**: a tool description the model can read, plus code that runs the call.
#
# App 1 (chat bot) uses LangChain's `@tool` decorator. One model call.

# %% tags=["needs-llm"]
from langchain_core.tools import tool

@tool
def count_open(team: str) -> int:
    """Count open Trackr issues for a team: web, api, mobile or infra."""
    return count_open_issues(team)

msg_chat = llm.bind_tools([count_open], tool_choice="any").invoke(
    "How many open issues does the mobile team have?")
print(msg_chat.tool_calls)

# %% [markdown]
# The model only **asked** for the tool. The chat bot's own glue code now runs it. (If the model cell was skipped, we use a hand-written call, labelled as such.)

# %%
if msg_chat is None:   # model cell skipped: a hand-written call (not model output)
    chat_calls = [{"name": "count_open", "args": {"team": "mobile"}}]
else:
    chat_calls = msg_chat.tool_calls
for call in chat_calls:
    result = count_open_issues(call["args"]["team"])        # chat bot glue: its names, its args
    print(f"chat bot ran {call['name']}({call['args']}) -> {result}")

# %% [markdown]
# App 2 (IDE assistant) was written by another team. They describe the **same** function by hand as a JSON schema, with their own name and argument name. One model call.

# %% tags=["needs-llm"]
ide_tool = {
    "name": "open_issue_count",
    "description": "Number of open issues in Trackr for one team (web, api, mobile, infra).",
    "parameters": {"type": "object",
                   "properties": {"team_name": {"type": "string"}},
                   "required": ["team_name"]},
}
msg_ide = llm.bind_tools([ide_tool], tool_choice="any").invoke(
    "How many open issues does the infra team have?")
print(msg_ide.tool_calls)

# %% [markdown]
# And the IDE assistant needs its **own** code to map its names back to the real function.

# %%
if msg_ide is None:   # model cell skipped: a hand-written call (not model output)
    ide_calls = [{"name": "open_issue_count", "args": {"team_name": "infra"}}]
else:
    ide_calls = msg_ide.tool_calls
IDE_GLUE = {"open_issue_count": lambda args: count_open_issues(team=args["team_name"])}
for call in ide_calls:
    print(f"IDE assistant ran {call['name']}({call['args']}) -> {IDE_GLUE[call['name']](call['args'])}")

# %% [markdown]
# Same function, two descriptions, two names, two argument names, two pieces of run code. Now scale it. Every app needs glue for every tool: that is the **M×N problem**. With a protocol, each tool is wrapped **once** (as a server) and each app learns the protocol **once** (as a client): M+N.

# %%
def integrations(apps: int, tools: int) -> tuple[int, int]:
    return apps * tools, apps + tools   # (without a protocol, with one)

for apps, tools in [(2, 1), (2, 4), (5, 20), (40, 800)]:
    without, with_p = integrations(apps, tools)
    print(f"{apps:>3} apps x {tools:>3} tools: {without:>6} custom glue pieces vs {with_p:>4} protocol adapters")

# %% [markdown]
# Look at the first row: for 2 apps and 1 tool the protocol is **more** work (3 vs 2). Protocols pay off as the numbers grow. The last row is roughly the size of a large company: Uber reported 800+ MCP servers (see At work). At that size, hand-wired glue is not an option.

# %% [markdown]
# ### 5. Fragility: the glue breaks when one side changes
# The Trackr team renames the argument from `team` to `team_slug` and ships it. Neither app is told. The chat bot still sends `team`, the IDE assistant's glue still sends `team_name`, so both break (you will see the real error in **Common mistakes**). With a protocol, the tool **publishes** its own description and every client reads it fresh, so there is one source of truth (lesson 01 shows this with `tools/list`).

# %%
def count_open_issues_v2(team_slug: str) -> int:
    """New version: the argument was renamed."""
    return sum(1 for i in ISSUES if i["team"] == team_slug and i["status"] == "open")

apps_still_send = {"chat bot": {"team": "mobile"}, "IDE assistant": {"team_name": "infra"}}
for app, args in apps_still_send.items():
    print(f"{app:14} sends {args}  but the tool now expects {list(count_open_issues_v2.__annotations__)[0]!r}")

# %% [markdown]
# ### 6. Example 2: Trackr's three lines, without and with protocols
# Now the whole picture for Trackr. For each line: what it is in Trackr, what goes wrong with no protocol, and what fixes it.

# %%
WALKTHROUGH = [
    ("agent ↔ tools/data", "read, count and close issues; read runbooks",
     "every app hand-wires every tool, and it breaks when a tool changes",
     "MCP: each tool describes itself once, plus a standard way to prove who is asking and what they may do"),
    ("agent ↔ agent", "hand an issue to triage-agent, then to fix-agent",
     "agents cannot find each other or know what the other can do",
     "A2A: a public profile card says what the agent can do; long jobs report 'working / done / failed'"),
    ("agent ↔ user", "show progress live; ask 'close 40 issues?' before acting",
     "the screen sees only the final answer, too late to stop anything",
     "AG-UI: a live feed of steps, and a pause to ask the user yes/no"),
]
for line, trackr, without, fix in WALKTHROUGH:
    print(f"== {line}\n   Trackr : {trackr}\n   Without: {without}\n   With   : {fix}\n")

# %% [markdown]
# ### 7. Agent ↔ agent: the black box
# An A2A agent is **opaque**: you cannot see its prompt, its model or its tools. You see only what it chooses to publish (its card) and what it sends back. That is a feature: another team, or another company, can change everything inside without breaking you.
#
# The cell shows a **simplified sketch** of what Trackr's triage-agent might publish. The real Agent Card format comes in lesson 08.

# %%
triage_card_sketch = {   # simplified sketch, not the real A2A schema
    "name": "triage-agent",
    "description": "Classifies a Trackr issue and sets its severity.",
    "skills": ["classify_issue"],
    "where": "https://triage.example.com/.well-known/agent-card.json",
}
hidden_inside = ["system prompt", "which model", "its own MCP tools", "its memory"]
print("Others can see :", triage_card_sketch)
print("Others cannot  :", hidden_inside)

# %% [markdown]
# ### 8. Agent ↔ user: seeing and stopping the agent
# Picture the steps a Trackr agent takes for "close all low-severity web issues". Without AG-UI, a typical app shows the user only the final sentence, after everything already happened. With AG-UI, the screen receives each step as an **event** and can pause for approval. The event names below are real AG-UI 1.0 event types; this is a hand-written sketch of a run, not live output.

# %%
steps = ["search issues: team=web, severity=low", "found 2 issues: #9, #13",
         "close issue #9", "close issue #13", "Done: closed 2 issues."]
print("Without a protocol the user sees:\n  ", steps[-1])

events = [("RUN_STARTED", ""), ("TOOL_CALL_START", steps[0]), ("TOOL_CALL_RESULT", steps[1]),
          ("RUN_FINISHED", "outcome=interrupt: 'Close 2 issues?' -> waits for the user's yes/no")]
print("\nWith AG-UI the user's screen gets:")
for event_type, detail in events:
    print(f"   {event_type:17} {detail}")

# %% [markdown]
# ### 9. Who looks after these protocols
# Who controls a protocol matters: one vendor can change or drop it; a neutral foundation is harder to bend. Facts below are from the course's research notes (checked 2026-10-11).

# %%
GOVERNANCE = [
    ("MCP", "agent ↔ tools/data", "made by Anthropic (2024); now in the Agentic AI Foundation (AAIF), "
     "a Linux Foundation fund launched 2025-12-09", "spec 2026-07-28"),
    ("A2A", "agent ↔ agent", "made by Google; given to the Linux Foundation 2025-06-23; joined AAIF 2026-08-27",
     "spec 1.0"),
    ("AG-UI", "agent ↔ user", "open source (MIT), started by CopilotKit with LangChain and CrewAI; "
     "community working group; not an AAIF project", "spec 1.0"),
]
for name, line, who, version in GOVERNANCE:
    print(f"{name:6} {line:20} {version:16} {who}")

# %% [markdown]
# ### 10. What you will build
# Trackr grows with you, from a Python list to an organisation-wide ops desk.
#
# ```mermaid
# flowchart LR
#   L1["L1: 20 issues behind<br/>one MCP tool"] --> L2["L2: tools, resources,<br/>A2A triage-agent, AG-UI chat"]
#   L2 --> L3["L3: ask the user, long jobs,<br/>login, human approval"]
#   L3 --> L4["L4: 4 workers,<br/>MCP or A2A?"]
#   L4 --> L5["L5: tests, step-by-step logs,<br/>attacks blocked, deployed"]
#   L5 --> L6["L6: one company: who-is-who, teams kept apart,<br/>one front door, a directory of agents"]
# ```
# The cell reads the course plan and prints each Part: its first and last lesson, and how many lessons it has.

# %%
import json
from pathlib import Path
from collections import Counter

syllabus = json.loads(Path("../syllabus.json").read_text())
for part in syllabus["parts"]:
    ids = [l["id"] for l in part["lessons"]]
    print(f"Part {part['id']} ({part['level']}) {part['title'][:58]:<58} {ids[0]}–{ids[-1]}: {len(ids)} lessons")
print(Counter(l["priority"] for p in syllabus["parts"] for l in p["lessons"]))

# %% [markdown]
# Counts can be bigger than the id range suggests: lessons with a letter suffix, like 07a, are extras inserted between numbered lessons.
#
# Each lesson has a priority: **core** (the Essentials path), **professional**, or **deep**. Each path works on its own.

# %% [markdown]
# ## At work
# - Block gave its goose agent to the whole company with only approved MCP servers (GitHub, Jira, Slack…). Tools that delete or change things ask the user first → lessons 03 and 41.
# - Uber puts one front door (a "gateway") in front of 800+ MCP servers; every tool starts switched off and has access rules. The first thing that broke: tool descriptions ate up too much of the model's reading space → lessons 24 and 40.
# - In May 2025, text hidden in a public GitHub issue tricked an agent whose access key could do too much, and it leaked private code into public. The protocol worked; the design around it did not → lesson 30.
# - Protocols change: MCP's 2026-07-28 version changed how connections work, so companies run old and new versions side by side while they switch → lessons 07 and 07a.

# %% [markdown]
# ## What just happened
# - You picked a model with `get_llm()` and saw which keys and recordings exist.
# - You placed protocols on the **agentic AI spectrum**: a chatbot needs none; tool use, multi-agent and cross-organisation work each add a line to talk on.
# - **Example 1**: the same `count_open_issues` needed two different hand-written wrappers for two apps. Multiply that and you get **M×N** glue; a protocol makes it M+N.
# - Renaming one argument broke both apps at once: hand-wired glue is **fragile**.
# - **Example 2**: on each of Trackr's three lines, MCP, A2A and AG-UI each fix one set of problems.

# %% [markdown]
# ## Common mistakes
# Thinking "my app already does function calling, so I don't need a protocol". Function calling is how **one** model asks **one** app for a tool; the description is copied by hand into each app. When the tool changes, the copies are wrong, and you only find out when a call fails:

# %% tags=["raises-exception"]
old_args = chat_calls[0]["args"]          # the chat bot still sends {'team': ...}
count_open_issues_v2(**old_args)          # the tool now expects team_slug

# %% [markdown]
# Fix: keep **one** description, published by the tool itself, and have every app read it. Here we read the parameter name from the function, the way an MCP client reads it from `tools/list` (lesson 01).

# %%
import inspect
param = next(iter(inspect.signature(count_open_issues_v2).parameters))   # 'team_slug'
fixed_args = {param: next(iter(old_args.values()))}
print(fixed_args, "->", count_open_issues_v2(**fixed_args))

# %% [markdown]
# Two more: thinking MCP and A2A **compete** (they cover different lines; Trackr uses both), and thinking a protocol makes an agent **safe** by itself (the GitHub incident above shows you still need good design: Part 6, lesson 30).

# %% [markdown]
# ## Try it
# For each situation, write which line it is on and which protocol fixes it (`"MCP"`, `"A2A"` or `"AG-UI"`). Then use `integrations()` to print how many glue pieces 6 apps and 15 tools need without and with a protocol.

# %%
situations = [
    "The agent must read the on-call runbook stored in the wiki",
    "A user wants to watch each step and press Stop before issues are closed",
    "Your agent asks a partner company's billing agent to refund a customer",
    "The IDE assistant needs to create a new Trackr issue",
]
# your code here

# %% [markdown]
# ## Key terms
# - **protocol** — a shared language with fixed rules for asking, answering and reporting errors.
# - **communication line** — one kind of agent connection: to tools/data, to other agents, or to the user.
# - **agentic AI spectrum** — chatbot → tool-using agent → multi-agent → cross-organisation; each step adds a line.
# - **glue code** — hand-written code joining one app to one tool in that app's own format.
# - **M×N integration problem** — M apps × N tools need M×N glue pieces; a protocol makes it M+N.
# - **MCP (Model Context Protocol)** — the protocol between an agent and tools/data.
# - **A2A (Agent2Agent)** — the protocol between agents.
# - **AG-UI (Agent–User Interaction protocol)** — the protocol between an agent and the user's screen.
# - **opaque agent** — an agent you can call but not see inside: only its card and replies.
# - **AAIF (Agentic AI Foundation)** — the Linux Foundation fund hosting MCP, A2A and other agent standards.

# %%
import llm_replay
llm_replay.stop()

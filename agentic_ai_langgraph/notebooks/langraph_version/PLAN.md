# Agentic AI (15 h), LangGraph version: plan (revised again)

Written for: the course author, who will build the lessons and review them one by one.

## 1. What changed

- **Six tracks** instead of five. The new track 4 covers agents, discovery and registries, then MCP, then A2A, with the
  same setup for each protocol.
- **Protocols are no longer hidden.** MCP and A2A each get three to four lessons with their own flowcharts. Before, MCP
  was one lesson in the single-agent track and one in production, and A2A was one lesson in the multi-agent track.
- **Discovery and registry are taught as their own steps**, first for agents, then for each protocol.
- **Lesson count is 38**, up from 30. Every current notebook still has a place in the plan (see the mapping in section 6).
- **`.env` stays the same.** No key or setting changes.

## 2. Rules for every lesson

1. **Flowchart first.** Each graph is drawn with `show_graph(app, model_nodes=...)` right after it is built. Blue nodes
   run code, amber nodes call the model. Concept lessons use `show_mermaid(text)` with the same colours.
2. **First model call through the library.** `llm = get_llm()` and `llm.invoke(...).text`. The raw SDK appears once, in
   an "Under the hood" cell, only where the lesson is about a wire format.
3. **Library before custom code.** Prefer `create_agent`, `ToolNode`, `@tool`, `with_structured_output`, `RetryPolicy`,
   `Send`, `interrupt`, checkpointers, stores, FastMCP, `langchain-mcp-adapters` and the A2A SDK. Hand-written code is
   allowed only for the topic itself, the data, and the tests.
4. **Small cells.** A cell is at most about 25 lines. The graph is one cell: state, nodes, edges, compile, draw.
5. **Show the run.** Each lesson ends its run with `stream_mode="updates"` or a trace table, and a `get_state_history`
   slider when there is a saved run.
6. **Offline by replay.** Each model call is recorded once with `llm_replay`, runs with no key afterwards, and stays
   within 8 calls per notebook. Protocol lessons run their servers on localhost, so they need no key and no internet.
7. **Same lesson shape.** Goal, Why it matters (a problem cell that fails without the idea), The idea (short, with the
   flowchart), Step by step, At work, Common mistakes, Try it with a hidden answer, Recap and the interview line.
8. **No picture, no pass.** A lesson is done only when its flowchart renders, or prints the Mermaid text offline.

## 3. The protocol setup (used for MCP and for A2A)

Every protocol follows the same five steps, so a learner who has done MCP can do A2A without new concepts:

| Step | What the learner does | What the flowchart shows |
|---|---|---|
| 1. Build | Expose something (tools or an agent) through the protocol's library | server and client, one request |
| 2. Discover | Find what is there at runtime, without hard-coding it | the handshake or card fetch, then the match |
| 3. Registry | Keep a catalogue: where each thing is, its version, its health, who may use it | register, health check, search, route |
| 4. Secure | Limit what a caller can reach: allow-list, auth, least privilege | the gate on the path |
| 5. Use in a graph | Put the remote capability inside a LangGraph node | the node that calls it, and what happens on failure |

Step 3 uses a small registry built on the LangGraph store from track 2 (lesson 09), so it needs no extra service.

## 4. Folders

```
notebooks/langraph_version/
  PLAN.md                        this file
  STATUS.md                      one line per lesson, updated as lessons pass
  01_foundations/                lessons 01-04   (+ 00_overview.ipynb)
  02_single_agent/               lessons 05-14   (+ 00_overview.ipynb)
  03_design_patterns/            lessons 15-18   (+ 00_overview.ipynb)
  04_agents_and_protocols/       lessons 19-28   (+ 00_overview.ipynb)
  05_multi_agent/                lessons 29-31   (+ 00_overview.ipynb)
  06_production/                 lessons 32-38   (+ 00_overview.ipynb)
src/langraph_version/<track>/NN_<name>.py        the sources
data/llm_cassettes/lg_NN_<name>.yaml             recordings, prefixed so they stay apart
graph_view.py                                    drawing helpers, topic root (already written)
```

Changes to the kit scripts (still needed; `scripts/` is owned by another user, so these need someone with write access):

- `scripts/build_notebook.py`: build `src/langraph_version/<track>/x.py` into `notebooks/langraph_version/<track>/x.ipynb`.
- `scripts/run_notebook.py` and `scripts/check_lesson.py`: accept a track folder.

Until then, sources are built with the unchanged script and the notebook is moved into its track folder.

## 5. The lessons

### Track 1 · Foundations (`01_foundations/`)

| # | Lesson | Flowchart | Library | Calls | From today's notebook |
|---|---|---|---|---|---|
| 01 | Why agentic AI | Chatbot (one node), workflow (fixed chain), agent (a cycle) | `create_agent` | 2 | 01 |
| 02 | First model call | One-node graph, then the streamed version | `get_llm().invoke`, `.stream` | 2 | 02 |
| 03 | Tokens, context, sampling | Count and price; the thinking dial as two runs | `get_llm` settings, `usage_metadata` | 3 | 03 |
| 04 | Structured output and the tool-call round trip | `extract ⇄ check`; `model → ToolNode → model`; the three wire formats | `with_structured_output`, `bind_tools`, `ToolNode` | 4 | 04 + 05 |

### Track 2 · Single agent (`02_single_agent/`)

| # | Lesson | Flowchart | Library | Calls | From today's notebook |
|---|---|---|---|---|---|
| 05 | The agent loop, by hand | The hand loop (it is the topic) and the same caps as `recursion_limit` | hand loop, kept on purpose | 6 | 06 |
| 06 | Tools that work | `agent → tools → agent`; a bad argument returns as a readable error | `@tool`, `ToolNode(handle_tool_errors=True)` | 3 | 07 |
| 07 | Eval and safety basics | Eval pipeline (`Send` per case); `agent → policy → tools or refuse` | `Send`, `batch`, conditional edges | 3 | 08 + 09 |
| 08 | Checkpoint: order assistant | The v1 agent: loop, tools, caps, policy gate | `create_agent` or the v1 graph | 4 | 10 |
| 09 | Memory: short and long term | `trim → agent`; `recall → agent → remember` with a privacy edge | `trim_messages`, checkpointer, store | 4 | 15 + 16 |
| 10 | Knowledge: RAG and agentic RAG | Ingest graph; answer graph `agent → search → grade → cite` | text splitters, Chroma, `EnsembleRetriever` | 4 | 17 + 18 |
| 11 | Why a graph | The loop next to the graph, with checkpoints and a pause | `StateGraph`, checkpointer, `get_state_history` | 2 | 19 |
| 12 | Choosing an SDK or framework | Three flowcharts of one task: hand loop, LangGraph, `create_agent` | `create_agent` | 3 | 20 |
| 13 | Human approval gate | `propose → approval → pay`, with the escalation loop | `interrupt`, `Command`, SQLite checkpointer | 1 | 14 (done) |
| 14 | Checkpoint: single support desk | The whole single-agent desk in one graph | composed from 09, 10, 13 | 6 | 23 |

### Track 3 · Agentic AI design patterns (`03_design_patterns/`)

| # | Lesson | Pattern | Flowchart | Library | Calls | From today's notebook |
|---|---|---|---|---|---|---|
| 15 | Chaining and routing | 1. Prompt chaining; 2. Routing | two small graphs | conditional edges, structured output | 4 | 11 (part) |
| 16 | Parallelization | 3. Parallelization | fan-out and join | `Send`, reducers | 2 | 11 (part) |
| 17 | Orchestrator-workers and evaluator-optimizer | 4. Orchestrator-workers; 5. Evaluator-optimizer | the orchestrator and judge graph | `Send`, conditional edges, `interrupt` | 8 | 12 (done) |
| 18 | Choosing an agent control pattern | ReAct, plan-and-execute, reflection (a comparison, not a sixth pattern) | two graphs and a cost table | `ToolNode`, `with_structured_output` | 5 | 13 (done) |

### Track 4 · Agents, discovery and protocols (`04_agents_and_protocols/`)

This track is new. It has three parts, each with the same rhythm: first the idea, then the protocol, then how to use it.

**Part A · Agents, discovery and registry**

| # | Lesson | Flowchart | Library | Calls | Source |
|---|---|---|---|---|---|
| 19 | An agent as a service | An agent is model + tools + loop + a **card** that says what it does and how to call it; the card drawn next to the graph | `create_agent`, a dict card | 1 | new (uses the graph from 11) |
| 20 | Agent discovery | The three ways a caller finds an agent: hard-coded, from config, discovered. Flowchart: caller → resolve → match skill → call, or refuse | `httpx`, the card | 0 | new; the discovery idea from 27 |
| 21 | Agent registry | A catalogue of agents and tools: register, health check, search by skill, version, allow-list, remove on failure | LangGraph store (from 09) | 0 | new; the registry idea from 27 |

**Part B · MCP: tools that any agent can use**

| # | Lesson | Flowchart | Library | Calls | Source |
|---|---|---|---|---|---|
| 22 | MCP: build a server and connect a client | Client ↔ server over stdio, then Streamable HTTP; the order tools exposed by FastMCP and called from a LangGraph node | FastMCP, `langchain-mcp-adapters` | 2 | 21 |
| 23 | MCP discovery | Connect → initialize → list tools, resources and prompts → bind to the model → call. The tool descriptions drawn as the menu the model reads | `langchain-mcp-adapters`, `bind_tools` | 1 | 21 (part) |
| 24 | MCP registry, gateway and auth | A registry file of servers (version, owner, allowed tools) with a health node; `agent → gateway (allow-list, auth, audit) → servers`; the OAuth sequence; tool poisoning drawn as a bad path | a registry in the store, `Authlib` local auth server, `show_mermaid` | 1 | 26 |

**Part C · A2A: agents that call other agents**

| # | Lesson | Flowchart | Library | Calls | Source |
|---|---|---|---|---|---|
| 25 | A2A: serve an agent | Caller → A2A server → the LangGraph graph inside; what a task is | `a2a-sdk` (installed), the graph as the executor | 1 | 27 (part) |
| 26 | A2A discovery | Base URL → `/.well-known/agent-card.json` → skills, input modes, auth scheme → match → call | `A2ACardResolver` | 0 | 27 |
| 27 | A2A registry and delegation | Registry lookup → choose an agent per task → delegate → merge the result; a supervisor graph with remote agents as nodes | `a2a-sdk`, the store from 21 | 2 | 27 (part) |
| 28 | A2A task lifecycle, streaming and failure | The states as a graph: submitted → working → input-required → completed, failed, canceled; streamed updates; a remote failure and its retry | `a2a-sdk`, `RetryPolicy` | 1 | 27a |

Part C has one more lesson than Part B because the task states are the part learners get wrong most often.

### Track 5 · Multi-agent (`05_multi_agent/`)

| # | Lesson | Flowchart | Library | Calls | From today's notebook |
|---|---|---|---|---|---|
| 29 | Why multi-agent, and when one agent is better | One agent next to a supervisor with two sub-agents; the cost in calls and tokens | sub-graphs | 4 | 24 |
| 30 | Supervisor and hand-offs | The supervisor routes to specialists in one process; the same routing as the A2A registry in lesson 27 | `Command(goto=...)`, sub-graphs | 4 | new (from 24) |
| 31 | Failure modes and guards | Two agents in a loop; the guards (visit counter, hand-off limit, shared-state check) on the path | `recursion_limit`, state | 4 | 25 |

### Track 6 · Production (`06_production/`)

| # | Lesson | Flowchart | Library | Calls | From today's notebook |
|---|---|---|---|---|---|
| 32 | Evals: depth and the CI gate | `run → error analysis → judge → report`; `golden → run → gate → pass or fail` | `with_structured_output`, sklearn | 4 | 22 + 28 |
| 33 | Observability | Spans of one run as a flowchart from the trace | callbacks | 2 | 29 |
| 34 | Security and guardrails | Injection test set through `batch`; `untrusted output → guard → act`; `agent → policy → identity → audit → tool` | guard node, `interrupt` | 4 | 30 + 31 |
| 35 | Reliability and durable runs | Refund node with `RetryPolicy` and a timeout; the kill drill as a checkpointed graph | `RetryPolicy`, checkpointer | 2 | 32 + 35 |
| 36 | Cost and latency | Router to a cheap or strong model; a cache-hit path | `CachePolicy`, `InMemoryCache` | 3 | 33 |
| 37 | Serving and the enterprise map | Request → API → graph → response; the architecture map | FastAPI, `show_mermaid` | 2 | 34 + 36 |
| 38 | Capstone: the desk in production | The whole desk: one graph, eval gate, kill drill | everything above | 6 | 37 |

**Totals:** 38 lessons. Three are already built, under their new numbers: 13 (approval gate, from 14), 17 (orchestrator
and evaluator, from 12) and 18 (control patterns, from 13). Lesson 05 keeps the hand loop from today's 06. The other 34
are to build.

## 6. Mapping from today's course

Every current lesson appears once in the "From today's notebook" or "Source" column. The protocol track replaces three
current lessons (21, 26, 27) and adds new ones for agents, discovery and registry.

| Today | New lesson(s) |
|---|---|
| 01–05 | 01–04 |
| 06 | 05 |
| 07 | 06 |
| 08, 09 | 07 |
| 10 | 08 |
| 11, 12 | 15, 16, 17 (and 19 for the card idea) |
| 13 | 18 |
| 14 | 13 |
| 15, 16 | 09 |
| 17, 18 | 10 |
| 19 | 11 |
| 20 | 12 |
| 21 | 22, 23 |
| 22 | 32 |
| 23 | 14 |
| 24 | 29, 30 |
| 25 | 31 |
| 26 | 24 |
| 27 | 20, 21, 26, 27 |
| 27a | 28 |
| 28 | 32 |
| 29 | 33 |
| 30, 31 | 34 |
| 32, 35 | 35 |
| 33 | 36 |
| 34, 36 | 37 |
| 37 | 38 |

## 7. Build order

| Phase | Lessons | Why this order |
|---|---|---|
| 0. Decisions | — | Settle section 8 first. |
| 1. Plumbing | — | Track folders in the build and run scripts; installs. |
| 2. Pilot | 02, 17, 22 | First call through the library; the largest pattern; MCP, to test the protocol setup. |
| 3. Foundations and single agent | 01, 03, 04, 05, 06, 07, 11, 12 | Each builds on the pilot. |
| 4. Single agent, the rest | 08, 09, 10, 14 | Need installs and the memory and approval lessons. |
| 5. Patterns | 15, 16, 18 | 17 and 13 are built already. |
| 6. Agents and protocols | 19, 20, 21, 23, 24, 25, 26, 27, 28 | Discovery and registry first, then MCP, then A2A. |
| 7. Multi-agent | 29, 30, 31 | Reuses the A2A registry and the guards. |
| 8. Production | 32–38 | Needs the checkpointer and the eval gate. |

A lesson is **done** when it builds, replays with no key within the call budget, renders its flowchart, passes
`check_lesson.py` apart from the pre-existing model-name rule, passes the privacy check, and has its line in `STATUS.md`.

## 8. Decisions and risks

**Decisions needed before building:**

1. **The model-name rule.** It blocks almost every lesson. Because `.env` stays the same, the check has to allow public
   model ids in notebooks and recordings.
2. **Installs.** `langchain-mcp-adapters` is not installed in the topic venv. `a2a-sdk` (1.2.3) and FastMCP are installed,
   but their current APIs must be checked against the docs before lessons 22–28 are written. Also `langchain-chroma`
   and a retriever package for lesson 10, and `langgraph-supervisor` if lesson 30 uses it.
3. **Track overviews.** The five overview notebooks already built still show the old numbers. They need renumbering,
   and a new overview for track 4, once the plan is approved.
4. **Syllabus.** This folder does not change the locked syllabus. If the syllabus should point to it, that change goes
   through `/tutorial-refresh-syllabus`.

**Risks:**

- **Protocol APIs move quickly.** MCP and A2A are new. Each protocol lesson checks its imports against the installed
  version and records it in `STATUS.md`.
- **Localhost servers.** Lessons 22–28 start servers on localhost. They need a free port each, and the notebook must
  stop them at the end, or a re-run fails.
- **Model calls.** Protocol lessons are cheap (0–2 calls each). The budget is spent in lessons 17, 32 and 38.
- **The picture needs internet.** The fallback prints the Mermaid text, so the flow still reads offline.

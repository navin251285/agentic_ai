# Agentic AI: hello world to enterprise — 15-hour course

Build an agent that calls tools, checks what it does, remembers the right things, and stops when it should. Then run it as a service that survives failures, with evals in CI, traces, security and cost control. This is one course of about **15 hours** (38 lessons, six chapters), from the first model call to a production-style support desk for a fictional shop, Brightside Outfitters.

Each lesson is a Jupyter notebook you can run on a laptop. Model calls are **recorded once and replayed**, so the notebooks run offline and without an API key.

**Who it's for:** developers who can write a little Python and call a web API. No machine-learning background is assumed.

**Prerequisites:** Python 3.12, and comfort with functions, dictionaries and JSON. Docker is needed only for three lessons (34, 35 and 37).

**Status:** all 38 lessons are built and checked. Two lessons (34 and 35) run Docker drills and are skipped by default.

## What you build

The running example is the **Brightside support desk**, grown one chapter at a time:

| Chapter | Lessons | What the desk can do by the end |
|---|---|---|
| 1. Foundations | 01–05 | Call a model, count tokens, get validated JSON, and make a tool call on three vendor formats |
| 2. An agent you can test and secure | 06–10 | Look up orders with a tool loop that has step and cost caps, pass a golden eval, and refuse unsafe writes (app v1) |
| 3. Workflows, memory and retrieval | 11–18 | Route work through workflows, wait for human approval, remember across sessions, and answer from documents with citations |
| 4. LangGraph, MCP and the eval loop | 19–23 | Run the loop as a graph with checkpoints, expose tools over MCP, and grade trajectories (app v2) |
| 5. Production: multi-agent, protocols, evals in CI and security | 24–31 | Decide when multi-agent pays, block bad changes in CI, trace runs, and defend against prompt injection |
| 6. Enterprise | 32–37 | Retry safely, control cost, serve a fleet, survive a worker kill, and ship the capstone as a production service |

## Setup

```bash
cd topics/agentic-ai-15h
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m ipykernel install --user --name tut-agentic-ai-15h
```

You do not need a `.env` file to run the course. If you want to make live model calls, copy `.env.example` to `.env` and fill in only the values you choose; `.env` is never committed.

## How to run

```bash
source .venv/bin/activate
jupyter notebook notebooks/
```

Open a notebook, choose the `tut-agentic-ai-15h` kernel, and run the cells top to bottom. Each lesson starts with "Why it matters", then a goal, then the steps. Every "Try it" is followed by its answer in a hidden cell tagged `solution`.

`TUT_ENABLE` controls cells that need something you may not have. By default those cells are skipped. Set `TUT_ENABLE=all` (or a list such as `TUT_ENABLE=needs-docker`) to run them when you have the keys or Docker they need.

## Lessons

Times are estimates (the course totals 900 minutes). "Needs" lists what a lesson's gated cells use: **recorded model call** is replayed offline; **Docker** is needed only for the drill cells.

### Chapter 1 — Foundations: the first model call and the tool loop

| # | Lesson | Priority | Minutes | Needs |
|---|---|---|---|---|
| 01 | [Why agentic AI, and what an agent is (and is not)](notebooks/01_why-agentic-ai.ipynb) | core | 15 | none |
| 02 | [Your first model call: messages, usage, cost and streaming](notebooks/02_first-model-call.ipynb) | core | 20 | recorded model call |
| 03 | [Tokens, context windows and sampling dials](notebooks/03_tokens-context-sampling.ipynb) | core | 20 | recorded model calls; one local-model cell is skipped by default |
| 04 | [Prompting for agents and structured output with Pydantic](notebooks/04_structured-output-prompts.ipynb) | core | 25 | recorded model call |
| 05 | [The tool-call round trip on three vendor wire formats](notebooks/05_tool-call-round-trip.ipynb) | core | 20 | recorded model calls |

### Chapter 2 — An agent you can test and secure

| # | Lesson | Priority | Minutes | Needs |
|---|---|---|---|---|
| 06 | [Build the agent loop yourself, with step and cost caps](notebooks/06_agent-loop-from-scratch.ipynb) | core | 30 | recorded model call |
| 07 | [Writing good tools: names, schemas and errors the model can act on](notebooks/07_writing-good-tools.ipynb) | core | 20 | none |
| 08 | [Your first eval: a golden set and a test that needs no model](notebooks/08_first-eval.ipynb) | core | 25 | none |
| 09 | [Safety basics: untrusted tool output, least privilege and approval for writes](notebooks/09_safety-basics.ipynb) | core | 20 | recorded model call |
| 10 | [Checkpoint: the order-lookup assistant (app v1)](notebooks/10_checkpoint-order-assistant.ipynb) | core | 25 | recorded model call |

### Chapter 3 — Workflows, memory and retrieval

| # | Lesson | Priority | Minutes | Needs |
|---|---|---|---|---|
| 11 | [Why workflows come before autonomy: chaining, routing and parallel calls](notebooks/11_why-workflows-first.ipynb) | core | 25 | recorded model call |
| 12 | [Orchestrator-workers and evaluator-optimizer loops](notebooks/12_orchestrator-and-evaluator.ipynb) | professional | 15 | recorded model call |
| 13 | [ReAct, plan-and-execute and reflection: which fits and what each costs](notebooks/13_react-plan-reflect.ipynb) | core | 15 | recorded model call |
| 14 | [A human approval gate with interrupt and resume](notebooks/14_human-approval-gate.ipynb) | core | 25 | none |
| 15 | [Short-term memory and context engineering: trim, summarise, compact, cache](notebooks/15_short-term-memory-context.ipynb) | core | 20 | recorded model call |
| 16 | [Long-term memory in SQLite: what to remember, forgetting and privacy](notebooks/16_long-term-memory-sqlite.ipynb) | core | 25 | none |
| 17 | [RAG basics: embeddings, chunking and cosine top-k](notebooks/17_rag-basics.ipynb) | core | 25 | recorded model call |
| 18 | [Hybrid search, reranking and agentic RAG with citations](notebooks/18_hybrid-agentic-rag.ipynb) | core | 30 | recorded model call |

### Chapter 4 — LangGraph, MCP and the eval loop

| # | Lesson | Priority | Minutes | Needs |
|---|---|---|---|---|
| 19 | [Why a graph: the loop as state, nodes, edges and checkpoints](notebooks/19_why-langgraph.ipynb) | core | 30 | recorded model call |
| 20 | [Vendor agent SDKs, LangGraph or a hand loop: how to choose](notebooks/20_choosing-sdks.ipynb) | core | 15 | recorded model call |
| 21 | [MCP: build a server and connect a client](notebooks/21_mcp-server-and-client.ipynb) | core | 25 | none |
| 22 | [Eval depth: error analysis, LLM-as-judge and trajectory grading](notebooks/22_eval-depth.ipynb) | core | 20 | recorded model call |
| 23 | [Checkpoint: the support desk with memory, approval and a graph (app v2)](notebooks/23_checkpoint-support-desk.ipynb) | core | 25 | recorded model call |

### Chapter 5 — Production: multi-agent, protocols, evals in CI and security

| # | Lesson | Priority | Minutes | Needs |
|---|---|---|---|---|
| 24 | [Why multi-agent, and when a single agent is better](notebooks/24_why-multi-agent.ipynb) | core | 25 | recorded model call |
| 25 | [Multi-agent failure modes: loops, lost context and guards](notebooks/25_multi-agent-failure-modes.ipynb) | core | 25 | recorded model call |
| 26 | [MCP auth and a gateway: what it adds in front of tools](notebooks/26_mcp-auth-and-gateway.ipynb) | core | 20 | none |
| 27 | [A2A: agent discovery and agent cards](notebooks/27_a2a-agent-discovery.ipynb) | professional | 25 | none |
| 27a | [A2A: the task lifecycle, streaming and delegating to another agent](notebooks/27a_a2a-task-lifecycle.ipynb) | professional | 25 | none |
| 28 | [Evals in CI: a regression gate that blocks a bad change](notebooks/28_evals-in-ci.ipynb) | core | 30 | recorded model call |
| 29 | [Observability: traces, what to log, and a dashboard](notebooks/29_observability.ipynb) | core | 20 | none |
| 30 | [Security: an injection test set, sandboxed code and least privilege](notebooks/30_security-injection-sandbox.ipynb) | core | 30 | recorded model call |
| 31 | [Guardrails, policy checks, agent identity and an audit log](notebooks/31_guardrails-identity-audit.ipynb) | core | 20 | none |

### Chapter 6 — Enterprise: reliability, cost, serving, durable runs and governance

| # | Lesson | Priority | Minutes | Needs |
|---|---|---|---|---|
| 32 | [Reliability: retries, timeouts, idempotency and rate limits](notebooks/32_reliability-retries-idempotency.ipynb) | core | 25 | none |
| 33 | [Cost and latency: caps, caching, routing and batch](notebooks/33_cost-and-latency.ipynb) | core | 15 | recorded model call |
| 34 | [Serving and deployment: FastAPI, Docker, a three-replica fleet and a load test](notebooks/34_serving-and-fleet.ipynb) | core | 30 | Docker (drill cells skipped by default) |
| 35 | [Durable execution: checkpoints, Temporal and a worker-kill drill](notebooks/35_durable-execution.ipynb) | core | 30 | Docker (drill cells skipped by default) |
| 36 | [The enterprise map: tenancy, managed runtimes, governance and HA/DR](notebooks/36_enterprise-map.ipynb) | professional | 20 | none |
| 37 | [Capstone: the support desk as a production service with an eval gate and a drill](notebooks/37_capstone-support-desk.ipynb) | core | 45 | recorded model call; Docker for the drill |

## Build the app step by step

The course builds a real app, the Brightside support desk: a FastAPI service with a one-page chat UI. It grows one step after each chapter, and the final step runs it with one command.

- [app/README.md](app/README.md): how to run it.
- [app/GUIDE.md](app/GUIDE.md): build it step by step, one step per chapter.

## Interview questions and projects

- [Interview questions (PDF)](interview/INTERVIEW_QUESTIONS.pdf) and [Markdown](interview/INTERVIEW_QUESTIONS.md): 50 questions across the course, tagged by level and by hiring tier, with a mock loop per tier.
- Portfolio projects: [Basic (PDF)](projects/BASIC_PROJECTS.pdf), [Intermediate (PDF)](projects/INTERMEDIATE_PROJECTS.pdf), [Advanced (PDF)](projects/ADVANCED_PROJECTS.pdf).

The answer key is kept private for instructors and is not part of this course.

## Slides

- [Kickoff deck](decks/course-kickoff.pptx): the course on one page before you start.
- Chapter decks: [1](decks/part-01-foundations.pptx), [2](decks/part-02-agent-you-can-test.pptx), [3](decks/part-03-workflows-memory-retrieval.pptx), [4](decks/part-04-langgraph-mcp-evals.pptx), [5](decks/part-05-production-multi-agent-security.pptx), [6](decks/part-06-enterprise.pptx).

## Full syllabus and glossary

- [SYLLABUS.pdf](SYLLABUS.pdf): every lesson, its concepts and the tools each one uses.
- [GLOSSARY.md](GLOSSARY.md): every term, with the lesson that teaches it.

## Industry reading

Engineering posts from teams that run agents in production, checked on 2026-10-21, two or three per chapter:

- **Chapter 1:** [Building effective AI agents](https://www.anthropic.com/engineering/building-effective-agents) (Anthropic); [Writing effective tools for agents — with agents](https://www.anthropic.com/engineering/writing-tools-for-agents) (Anthropic)
- **Chapter 2:** [Beyond permission prompts: making Claude Code more secure and autonomous](https://www.anthropic.com/engineering/claude-code-sandboxing) (Anthropic); [Background Coding Agents: Predictable Results Through Strong Feedback Loops](https://engineering.atspotify.com/2025/12/feedback-loops-background-coding-agents-part-3) (Spotify)
- **Chapter 3:** [Introducing Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval) (Anthropic); [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) (Anthropic)
- **Chapter 4:** [Introducing the Model Context Protocol](https://www.anthropic.com/news/model-context-protocol) (Anthropic); [Code execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp) (Anthropic); [Code Mode: the better way to use MCP](https://blog.cloudflare.com/code-mode/) (Cloudflare)
- **Chapter 5:** [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system) (Anthropic); [Announcing the Agent2Agent Protocol (A2A)](https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/) (Google); [Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) (Anthropic)
- **Chapter 6:** [1,500+ PRs Later: Spotify's Journey with Our Background Coding Agent](https://engineering.atspotify.com/2025/11/spotifys-background-coding-agent-part-1) (Spotify); [Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) (Anthropic); [AI Gateway is generally available](https://blog.cloudflare.com/ai-gateway-is-generally-available/) (Cloudflare)

## Where next

Roles, disciplines and technologies this course leads to, with how mature each one is:

- **Forward deployed engineer** (established): an engineer embedded with customers who builds and ships LLM and agent solutions on the customer's own data and systems.
- **Context engineering** (growing): deciding what goes into the model's window, when, and what gets removed.
- **Agent evaluation and observability platforms** (growing): running evals, traces and dashboards for agents as a shared service.
- **Harness engineering** (emerging): building the code around the model that runs, limits and checks it.
- **Loop engineering** (emerging): designing the agent loop itself, its stop rules and its budgets.
- **Agent protocols (MCP)** (growing): building servers and clients for the protocols that connect agents to tools and to each other.

## Go deeper

The syllabus lists the topics this course points to rather than teaches (for example fine-tuning, distillation and the wider framework landscape). They are in the syllabus under "Go deeper".

## Troubleshooting

- **The kernel is missing in Jupyter:** rerun the `ipykernel install` line from Setup, with the venv active.
- **A cell says a recording is missing:** the lesson's model call is not in the replay file. Do not edit the output; report the lesson so it can be re-recorded.
- **A Docker drill cell is skipped:** it needs Docker running. Set `TUT_ENABLE=needs-docker` to run it.
- **`pip install` fails on `google-genai` or `tenacity`:** pin `tenacity` to 9.1.x as listed in `requirements.txt`; newer versions do not resolve with `google-genai` 2.31.

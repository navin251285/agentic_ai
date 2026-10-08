# Agentic AI 1: LLM foundations and the agent loop — syllabus

**Interview & projects:** not generated yet — `/tutorial-interview agentic-ai-1-foundations` (up to 50 questions) and `/tutorial-projects agentic-ai-1-foundations`

**Audience:** Python developers who know functions, classes, basic async, JSON, HTTP and Git. No ML background assumed.

**Outcome:** Explain how an LLM behaves from the outside (tokens, sampling, context window, statelessness), call current vendor APIs (Gemini Interactions, Anthropic Messages, OpenAI Responses) and a local model with streaming, cost accounting and correct retries, get validated structured output, and write a tool-calling agent loop from scratch with a tool registry, error recovery, budgets, tests, evals, logging and prompt-injection defences, with no framework.

**Running example:** Scout, a research assistant over local notes — Everyone understands 'look it up in my notes and work it out'. All tools are local and deterministic, so every lesson runs without a key, and the example grows into memory/RAG (track 2), frameworks (3), MCP (4), many agents (5) and a multi-tenant production service (6).

*How it grows:* fake-model chat -> real streaming chatbot with cost -> structured note extraction -> one tool call -> 150-line agent with search/calculator/write_file -> benchmarked and tuned -> tested, logged, budgeted, injection-safe Scout -> sized for 5,000 users

**Tools used:**

- **google-genai (Gemini on Vertex AI, Interactions API)** — main real model, recorded with llm_replay (lessons 07-60)
- **Scripted FakeModel (plain Python)** — every mechanism by hand before a real model (lessons 01-06, 21-30, 38-39, 46)
- **anthropic, openai SDKs** — message and tool formats compared; recorded calls only when a key was available while building (lessons 10, 23, 37)
- **Ollama (granite4.1:3b)** — optional local model (lessons 16, 37, 57)
- **pydantic, tiktoken, tenacity, vcrpy, pytest** — validation, token counting, retries, record/replay, tests (lessons 03, 14, 21, 46-47)

**LLM use:** heavy — most lessons — LLM-centric track (LEVELS rule 10). Each mechanism is first shown with a scripted fake model; real calls go to Gemini on Vertex (GOOGLE_CLOUD_API_KEY) under llm_replay. Anthropic/OpenAI payloads are shown by hand; their real calls are recorded only if ANTHROPIC_API_KEY/OPENAI_API_KEY are present while building, never invented. (recorded once, replayed without a key)

**60 lessons · about 39 hours**

## Choose your path

Nothing is left out: the Complete path is the whole course. Shorter paths take the most-used lessons first; come back for the rest any time. Every path works on its own.

| Path | Lessons | Time | Includes |
| --- | --- | --- | --- |
| **Essentials** | 32 | ~19 h | Core lessons: what most real work uses |
| **Professional** | 55 | ~36 h | Core + Professional: build, ship and run it in production |
| **Complete** | 60 | ~39 h | Everything, including internals, distributed operation, extreme scale and the frontier |

Priority in the tables below: ● core · ◐ professional · ○ deep

## Or take it as separate courses by difficulty

The same lessons, split by level, to publish or sell as three courses. Each assumes the one before it.

| Course | Levels | Lessons | Time |
| --- | --- | --- | --- |
| **Basic** | L1 + L2 | 01–25 (25) | ~14 h |
| **Intermediate** | L3 + L4 | 26–45 (20) | ~13 h |
| **Advanced** | L5 + L6 | 46–60 (15) | ~12 h |

## Part 1 · L1 Foundations: What an LLM and an agent are

| # | | Lesson | You will be able to | Needs |
| --- | --- | --- | --- | --- |
| 01 | ● | What an agent is: a model in a loop | Explain, with a running toy, how an agent differs from a single model call: it chooses tools, sees results and decides when it is done. | — |
| 02 | ● | Next-token prediction by hand | Generate text one token at a time with a toy model and explain autoregression and stop conditions. | — |
| 03 | ● | Tokens and tokenizers | Count tokens with a real BPE tokenizer and explain why tokens are not words and why each model family counts differently. | download |
| 04 | ● | Sampling: temperature, top-p and top-k | Change temperature, top-p and top-k on a toy distribution and predict the effect; explain why temperature 0 is not fully deterministic (batching, hardware) and which current models reject these knobs (Claude Opus 4.7+, Sonnet 5.5, Fable) while others accept them. | — |
| 05 | ● | The context window | Explain what fills a context window (input, output, thinking), what each provider does when it overflows (error, not silent truncation), and what 'context rot' is. | — |
| 06 | ● | Checkpoint: a chat loop with a fake model ⭐ | Build a command-line chat loop over a scripted fake model that keeps history in a list, and show exactly why it 'forgets' when history is not resent. | — |

## Part 2 · L2 Core: Calling a real model

| # | | Lesson | You will be able to | Needs |
| --- | --- | --- | --- | --- |
| 07 | ● | Your first API call | Call Gemini with the official google-genai SDK using a key from .env, and read every field of the response. | llm |
| 08 | ● | Roles, history and statelessness | Send system instructions and a multi-turn history, prove the model is stateless, and explain the instruction hierarchy (system/developer vs user) and the rules for a valid message list. | llm |
| 09 | ◐ | Server-side conversation state | Continue a conversation with previous_interaction_id / previous_response_id instead of resending history, and weigh its convenience against retention (55 days paid / 1 day free on Gemini) and store=false. | llm |
| 10 | ◐ | Three vendors, three message formats | Write the same two-turn conversation for Anthropic Messages, OpenAI Responses and Gemini Interactions, and name what differs. | llm |
| 11 | ● | Streaming responses | Stream a reply, print it as it arrives, and measure time-to-first-token versus total time. | llm |
| 12 | ● | Counting tokens and cost per turn | Compute the cost of each turn from usage and a price table, count tokens before sending, and show why a long chat's cost grows roughly quadratically. | llm |
| 13 | ● | Stop reasons and API errors | Handle every way a call can end: end of turn, max_tokens (including a tool call cut off mid-JSON), stop sequences, pause_turn, refusals and safety blocks, empty responses; log the request id of each error. | llm |
| 14 | ● | Rate limits and retries | Survive 429s and timeouts with SDK retries and jittered exponential backoff that honours retry-after, and know which errors (spend cap, 400s) must never be retried. | — |
| 15 | ◐ | Provider failure drill | Run Scout's client against a fake provider that returns 429 without retry-after, a spend-cap 429, 529 overloaded, a mid-stream disconnect and truncated tool JSON, and print the before/during/after error table. | — |
| 16 | ◐ | Running a model locally: Ollama and LM Studio | Run a small open model with Ollama, call it from Python and through an OpenAI-compatible endpoint (Ollama or LM Studio at :1234), and judge where small local models fall short at tool use. | download, slow, llm |
| 17 | ● | Choosing a model: size, price and pinning | Pick a model for a task using the cost-latency-quality trade-off, read current prices from a dated table, and pin the model id in one config place. | llm |
| 18 | ● | Checkpoint: a streaming CLI chatbot with cost ⭐ | Build the source's Level 0 project: a command-line chatbot that keeps history, streams replies and prints each turn's cost, and pass its exit test. | llm |

## Part 3 · L2 Core: Prompts, structured output and tools

| # | | Lesson | You will be able to | Needs |
| --- | --- | --- | --- | --- |
| 19 | ● | Prompting that works | Rewrite a weak prompt using clear instructions, a role, XML-tagged structure, 3–5 examples and data-first ordering, and measure the difference. Note that assistant prefill no longer works on Claude 4.6+. | llm |
| 20 | ● | Structured output: from 'please' to JSON Schema | Get JSON from a model in four ways (ask, JSON mode, schema-constrained decoding, parse helper) and state what each guarantees. | llm |
| 21 | ● | Validating with Pydantic and retrying | Validate model output with Pydantic and retry with the validation error fed back, capping retries. | llm |
| 22 | ● | One tool call, end to end | Declare a tool, receive the model's tool call, run it, and send the result back for the final answer. | llm |
| 23 | ◐ | Tool calls on the wire, three ways | Write one tool round trip for Anthropic (tool_use/tool_result), OpenAI (function_call/function_call_output) and Gemini (function_call/function_result), and explain the 400s you get when results are missing or misplaced. | llm |
| 24 | ◐ | Controlling tools: tool_choice and strict schemas | Force, forbid or free the model's tool use with tool_choice, and use strict schemas so arguments always match. | llm |
| 25 | ● | Parallel tool calls | Handle several tool calls in one turn, run them concurrently with a short asyncio primer, return all results in one message, and know when to disable parallel calls. | llm |

## Part 4 · L3 Practical: The agent loop from scratch

| # | | Lesson | You will be able to | Needs |
| --- | --- | --- | --- | --- |
| 26 | ● | The agent loop | Write the loop: call the model, run any tools it asks for, append results, repeat until it answers or hits a step limit. | llm |
| 27 | ● | A tool registry: add tools without touching the loop | Generate tool schemas from typed Python functions and dispatch through a registry, so new tools need no loop changes. | — |
| 28 | ● | Tool errors the model can recover from | Return tool failures as error results with actionable messages, and watch the model recover. | llm |
| 29 | ● | Designing good tools | Design tools with clear names and descriptions, narrow inputs, size-limited high-signal outputs and safe implementations (AST calculator, write_file confined to one folder against path traversal), and count what tool definitions cost in tokens. | llm |
| 30 | ● | Stopping conditions: step limits, timeouts and cancel | Stop the loop cleanly on a step limit, a wall-clock timeout, repeated identical calls or a user cancel. | llm |
| 31 | ● | Context engineering basics | Decide what goes into the window, in what order, and what to leave out, and trim old tool results; measure tokens and answers. | llm |
| 32 | ◐ | Compaction: when history outgrows the window | Hit a real context-overflow error, then keep a long chat going by summarising and clearing old turns and tool results, measuring answer quality against tokens; name the vendor compaction features after the by-hand version. | llm |
| 33 | ● | Workflows: prompt chaining and routing | Build a fixed prompt chain with a gate check and a router that sends each request down the right path. | llm |
| 34 | ◐ | Workflows: parallelisation, and workflow vs agent | Run sectioning and voting in parallel, then decide with measured cost, latency and accuracy when a workflow beats an agent. | llm |
| 35 | ● | Checkpoint: Scout, a research assistant in ~150 lines ⭐ | Build the source's Level 1 project: a ~150-line plain-Python agent with search, calculator and write-file tools, then pass the exit test. | llm |

## Part 5 · L4 Advanced: Inside the loop: measuring and tuning

| # | | Lesson | You will be able to | Needs |
| --- | --- | --- | --- | --- |
| 36 | ◐ | Streaming inside the agent loop | Stream text and partial tool-call arguments inside the loop, assemble arguments safely, and handle a tool call truncated by max_tokens. | llm |
| 37 | ◐ | A provider-neutral adapter | Write a thin adapter so Scout's loop runs unchanged on Gemini, a fake model and a local model, and compare them. | llm |
| 38 | ◐ | Running many conversations at once | Run many Scout conversations concurrently with asyncio, a semaphore and a shared token-bucket rate limiter, and measure throughput and latency percentiles. | — |
| 39 | ◐ | Retries without double side effects; resumable runs | Make side-effecting tools idempotent with keys ('retry the call, not the tool'), checkpoint the message list after each step, and resume a killed run without repeating completed tools. | — |
| 40 | ◐ | Reasoning effort and thinking across tool turns | Measure how reasoning-effort settings change cost, latency and success, explain that thinking tokens are billed as output, and keep thinking state (thought signatures / thinking blocks) across tool turns. | llm |
| 41 | ◐ | Prompt caching | Structure prompts so the stable prefix is cached (breakpoints, TTL, minimum size), measure the hit rate, and debug a 0% hit rate caused by a timestamp in the system prompt. | llm |
| 42 | ◐ | Batch processing | Send a batch of Scout summaries through a batch API at half price, and decide when the latency is acceptable. | llm, cloud |
| 43 | ○ | Images and PDFs as input | Send an image or PDF with a question, and estimate its token cost. | llm |
| 44 | ◐ | Who runs the loop: SDK helpers and vendor-run tools | Compare your hand loop with SDK helpers (tool runner, parse helpers, automatic function calling) and vendor-run tools (web search, code execution, tool search, MCP connector, managed agents, with date-versioned tool types), and choose between them. | llm, cloud |
| 45 | ◐ | Checkpoint: benchmark and tune Scout ⭐ | Benchmark Scout on 10 fixed questions across two models and two effort levels, and recommend a configuration with numbers. | llm |

## Part 6 · L5 Production: Shipping one agent safely

| # | | Lesson | You will be able to | Needs |
| --- | --- | --- | --- | --- |
| 46 | ● | Unit-testing the loop with a fake model | Write pytest tests for the loop with a scripted fake model: step limit, error recovery and parallel results. | — |
| 47 | ◐ | Recorded integration tests | Record real model calls once and replay them in tests, scrubbing secrets and keeping call order fixed. | llm |
| 48 | ● | Your first evals | Build a small golden set and a scorer, run each case several times to see non-determinism, and track pass rate (with pass@k) as you change prompts or models. | llm |
| 49 | ● | Logging and tracing an agent run | Log each step of a run as structured JSON lines using OpenTelemetry GenAI attribute names (gen_ai.request.model, gen_ai.usage.input_tokens…), with run id, request id, cost, stop reason, tool and latency, redacting PII; then debug a bad run from its transcript. | llm |
| 50 | ● | API keys and data handling | Keep keys out of code and logs, separate them per environment and workspace (Anthropic workspaces, Gemini project spend caps), rotate on leak, and control what the provider stores (store=false, retention windows, Vertex vs AI Studio data residency). | — |
| 51 | ● | Prompt injection through tools | Run an attack catalogue against Scout (injection via tool result and via filename, markdown-image exfiltration, confused deputy on write_file), check the 'lethal trifecta', and apply layered defences: untrusted-content placement, least privilege and a tool permission matrix. | llm |
| 52 | ◐ | Human approval for side-effecting tools | Pause the loop before a risky tool call, ask a human to approve, edit or reject, and write an audit record of the decision. | — |
| 53 | ◐ | Model versions, retirement and migration | Pin model ids, track real deprecation dates (Haiku 4.5 retiring from 2026-10-15, Gemini 2.5 restricted), and migrate with a canary on the eval set, diffing tool-call rate, token counts and refusals as well as accuracy. | llm |
| 54 | ◐ | Cost controls in production | Cap cost per run and per day with max_tokens, per-run token/cost budgets, small-model-first routing and provider spend limits (and the enforced_spend_limit_reached 429). | llm |
| 55 | ◐ | Checkpoint: production-ready Scout ⭐ | Ship Scout as a tested package with logs, retries, budgets, injection-safe tools, human approval, evals and pinned model config, running 50 conversations concurrently and reporting p50/p95/p99 latency and cost per run. | llm |

## Part 7 · L6 Enterprise: Organisation scale and what's next

| # | | Lesson | You will be able to | Needs |
| --- | --- | --- | --- | --- |
| 56 | ○ | What changes at organisation scale | Size Scout for 5,000 users with capacity maths: tokens per minute vs provider tiers, concurrency from Little's law, cache-hit effect, burst headroom and monthly cost. | — |
| 57 | ○ | Provider outage and fallback | Use the provider adapter to fail over from one provider to another during a simulated outage, and measure errors and latency before, during and after. | llm |
| 58 | ○ | Case studies: agents in production | Read 2–3 published engineering write-ups or post-mortems about LLM agents in production (sources found and cited at build time) and turn each into a decision for Scout. | — |
| 59 | ○ | The frontier: what changed in the last year | Build a dated table of the past ~12 months' changes (stateful APIs, effort dials, server tools, structured output GA, httpx2 SDK majors, context engineering) and which lesson each affects, and set up a routine for tracking vendor changelogs. | — |
| 60 | ◐ | Capstone: Scout, track 1 complete ⭐ | Deliver Scout end to end, pass both source exit tests without notes, and write a design note ready for track 2 (memory and RAG). | llm |

## Enterprise depth coverage

Every item of the Enterprise depth checklist (`standards/LEVELS.md`) and where it is taught.

| Checklist item | Lessons |
| --- | --- |
| 1 distributed architecture internals | N/A — covered in track agentic-ai-5-multi-agent (runtime architecture, durable execution); this track has no distributed mode; resumable-run preview in lesson 39 |
| 2 cluster operations hands-on | N/A — covered in track agentic-ai-6-production (scaling agent workers and queues) |
| 3 failure and recovery | 15, 57 |
| 4 extreme scale | N/A — covered in track agentic-ai-6-production (millions of runs per day); capacity-maths preview in lesson 56 |
| 5 kubernetes and infrastructure | N/A — covered in track agentic-ai-6-production (deploying agent runtimes and gateways) |
| 6 performance engineering at scale | N/A — covered in track agentic-ai-6-production (load/latency/cost testing); single-machine concurrency and percentiles in lessons 38, 45 |
| 7 high availability and disaster recovery | 39, 57 |
| 8 zero-downtime change | N/A — covered in track agentic-ai-6-production (prompt/model/tool versioning and rollout); model migration with a canary in lesson 53 |
| 9 multi-tenancy and isolation | N/A — covered in track agentic-ai-6-production (per-tenant agents, data and budgets) |
| 10 security and compliance at org scale | N/A — covered in track agentic-ai-4-protocols and agentic-ai-6-production; foundations in lessons 50, 51, 52 |
| 11 cost engineering | N/A — covered in track agentic-ai-6-production (token cost engineering); foundations in lessons 41, 42, 54, 56 |
| 12 platform and organisation patterns | N/A — covered in track agentic-ai-6-production (agent platforms and governance) |
| 13 frontier | 59 |
| 14 case studies | 58 |

## Your syllabus → lessons

Every item of `SOURCE_SYLLABUS.md` and where it is taught.

| Source item | Lessons |
| --- | --- |
| Level 0 › What an LLM does: next-token prediction | 02 |
| Level 0 › context window | 05 |
| Level 0 › tokens | 03 |
| Level 0 › temperature, top-p | 04 |
| Level 0 › Chat format: system, user and assistant messages | 08, 10 |
| Level 0 › why the model is stateless between calls | 08 |
| Level 0 › Calling an API (Anthropic, OpenAI or Gemini) with the official Python SDK | 07, 10 |
| Level 0 › API keys and environment variables | 07, 50 |
| Level 0 › Streaming responses | 11 |
| Level 0 › token counting | 03, 12 |
| Level 0 › pricing per million tokens | 12 |
| Level 0 › rate limits and retries | 14 |
| Level 0 › Running a small open model locally with Ollama or LM Studio | 16 |
| Level 0 › Model families: large reasoning model vs small fast one | 17, 40 |
| Level 0 › Build: CLI chatbot with history, streaming, cost per turn | 18 |
| Level 0 › Exit test: why the bot forgets; what happens when history exceeds the window | 06, 18, 32 |
| Level 1 › Prompt engineering: instructions, examples, XML/Markdown, role prompts | 19 |
| Level 1 › Structured outputs: JSON mode, JSON Schema | 20 |
| Level 1 › Pydantic validation, retrying on bad output | 21 |
| Level 1 › Tool calling: tool schemas | 22, 24 |
| Level 1 › tool_use and tool_result messages | 22, 23 |
| Level 1 › parallel tool calls | 25 |
| Level 1 › The core loop with a step limit | 26, 30 |
| Level 1 › Writing good tools | 27, 29 |
| Level 1 › helpful error messages the model can recover from | 28 |
| Level 1 › Context engineering basics | 31 |
| Level 1 › Workflows vs agents: chaining, routing | 33 |
| Level 1 › Workflows vs agents: parallelisation | 34 |
| Level 1 › Build: research assistant in ~150 lines, three tools, no framework | 35 |
| Level 1 › Exit test: add a fourth tool without touching the loop; recover from a tool error | 35, 60 |
| Level 1 › Key reading: Building Effective Agents; provider tool-use docs | 26, 33, 34 |
| Course › Prerequisite: async | 25 |

## Out of scope

- **Memory, RAG, ReAct / plan-and-execute / reflection, orchestrator-workers and evaluator-optimizer patterns** — Track agentic-ai-2-patterns-memory-rag (and agentic-ai-5-multi-agent for orchestrator-workers).
- **Agent frameworks (LangGraph, OpenAI Agents SDK, Claude Agent SDK, Google ADK, PydanticAI)** — Track agentic-ai-3-frameworks; this track builds the loop by hand on purpose.
- **MCP, A2A, AG-UI, OAuth for tools** — Track agentic-ai-4-protocols.
- **LLM gateways, OpenTelemetry GenAI tracing, provider fallback, multi-tenant budgets** — Track agentic-ai-6-production; previewed in lesson 49.
- **Computer use, coding agents, long-horizon agents** — Track agentic-ai-7-advanced-agents.
- **Model internals, fine-tuning and RL for agency** — Track agentic-ai-8-training (source: no ML theory until Level 7).
- **Live web-search APIs** — Need a third-party key; Scout uses a local fixture search tool, with vendor server-side search shown in lesson 38.
- **Audio / realtime (Live) APIs** — Not part of the agent loop foundations; voice agents belong to track agentic-ai-7-advanced-agents.
- **LLM-as-judge with calibration, eval statistics at scale, LLM gateway design (LiteLLM etc.)** — Track agentic-ai-6-production; lesson 48 introduces repeated-run evals and lesson 56 sizes a single service.

⭐ = checkpoint project for that part.

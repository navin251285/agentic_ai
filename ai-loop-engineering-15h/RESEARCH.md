# RESEARCH.core.md: AI Loop Engineering (ai-loop-engineering-15h), part=core

## 0. What "loop engineering" means in current practice (read first)

Two meanings are in use; the course must teach both and say which is which.
1. **The agent loop (inner loop)**: the model-tool-observe cycle. A "turn" = model output with tool calls, tool execution, results fed back; repeat until a response with no tool calls (Claude Agent SDK "How the agent loop works"; OpenAI Agents SDK `Runner`: LLM -> final output / handoff / tool calls -> repeat). Controls: `max_turns`, spend cap, effort, permission mode, hooks, compaction, result subtypes.
2. **Loop engineering (outer loop; the 2026 term)**: designing the system that decides what an agent does next so a person no longer prompts each step: which task to pick up, how often to retry, when a result is good enough to stop, when to hand to a human (FutureAGI explainer, secondary). **Coined/popularised by Addy Osmani, "Loop Engineering", 2026-06-07** (opened: addyosmani.com/blog/loop-engineering/). Definition there: "a recursive goal where you define a purpose and the AI iterates until complete". Osmani's building blocks: automations (scheduled discovery/triage), worktrees (parallel agents without file collisions), skills (`SKILL.md` project knowledge), plugins/connectors (MCP), sub-agents (maker/checker split), state (markdown file or board). Failure modes he names: file collisions, unattended mistakes, comprehension debt, "cognitive surrender", token cost. "Done" is a claim, not proof; verification stays the developer's job. Stack vocabulary: prompt -> context -> **harness** (the one-run environment: tools, context, permissions, sandbox; "agent = model + harness") -> **loop** (harness + trigger/schedule + state + verification chain; "one floor above the harness").
3. Anthropic's own taxonomy (opened: claude.com/blog/getting-started-with-loops): **turn-based** (every prompt is a manual loop; verification skills reduce turns), **goal-based** (`/goal <condition>`, an evaluator model checks the condition each time Claude tries to stop; turn caps; `/goal` with no args shows turns and tokens), **time-based** (`/loop 5m ...` local; `/schedule` moves it to the cloud as a routine; stops if the computer is off), **proactive** (event/schedule, no human in real time; `/schedule` + `/goal` + skills + dynamic workflows (research preview) + auto mode; route routine work to small models; pilot big dynamic workflows on a small slice because they can spawn hundreds of agents; `/workflows` and `/usage` to monitor).
4. Community patterns: **Ralph loop** (Geoffrey Huntley, ghuntley.com/ralph, opened): `while :; do cat PROMPT.md | claude-code ; done`, fresh context each iteration, one item per loop, `fix_plan.md` + specs re-read each loop, **backpressure** = tests/type-checkers/linters reject bad output, commit+tag on green, replan periodically; caveats: duplicate implementations, placeholder code, ~170k context, may wake to a broken build. Practitioner stop rules (blogs, not a spec; search snippets only): mechanical completion check (tests exit 0), iteration cap, dollar cap (`--max-turns`, `--max-budget-usd` style), same-failure-twice detector, dual-condition exit (do not trust the model's own "done").
5. **Honest caveat:** the term is ~4.5 months old, sources are mostly vendor/practitioner blogs, and terms (loop, harness, state) are used inconsistently (MindStudio/FutureAGI via search). Maturity for "Where next": `growing`.

Metrics named in secondary sources: no-progress rate, cost per goal, recovery rate, retry counts (not standardised).

---

## 0. Read this first (planner)

1. **"Loop engineering" is a 4-month-old, practitioner-coined term, not an established discipline.** Sources (all opened today): Addy Osmani essay 2026-06-07 (reposted on O'Reilly Radar 2026-06-22) quoting Peter Steinberger ("you shouldn't be prompting coding agents anymore, you should be designing loops that prompt your agents") and Boris Cherny of Claude Code; Anthropic's own blog "Loop Engineering: getting started with loops" (2026-06-30); IBM Think "What is loop engineering" (2026-07-17); one workshop paper (Lulla, Treude, Baltes et al., arXiv 2608.21884, accepted JAWs@ASE 2026, revised 2026-10-22). The paper finds **no empirical evidence yet** for the claimed benefits; in 36,710 GitHub repos it found autonomous agent loops in only **217**, and nearly all commit the config that starts the loop but almost none commit the state files the literature recommends. A source (Build Fast with AI) says Anthropic never published a document under that title; Anthropic's blog (above) does use the term, so that claim is stale. A different arXiv paper (2509.06216) uses "agentic loop engineering" for a DevOps-rooted concept, so usage is not consistent.
2. **Definition to teach (agreed by all sources):** design the system that prompts, verifies, retries and stops an agent, instead of prompting it turn by turn. It sits above prompt engineering, context engineering and the agent harness. Components: trigger (schedule / event / human), goal (machine-checkable end state), verifier (deterministic first; separate checker agent or model second), stop rules (success exit, iteration cap, budget cap, handoff to a human), persistent state outside the context ("the agent forgets, the repo doesn't"), isolation (worktrees / sandboxes), capabilities (skills, MCP connectors, hooks, subagents).
3. **Application-developer scope.** Two audiences use the word: (a) developers who run coding agents (Claude Code, Codex) in loops; (b) developers who build agent loops into products (Agent SDK, LangGraph, AI SDK, OpenAI Agents SDK). The course should teach the mechanism once and show both. Postings ask for (b) under other titles (agent / harness engineer, agent verification, agent evals platform). **No posting found uses the title "loop engineer"** (search 2026-10-26); 5+ postings use "harness engineer" (below). Say this plainly to learners.
4. **Primary loop primitives with current limits (Claude Code docs, opened 2026-10-26, Claude Code v2.1.310 released 2026-10-23):** `/goal <condition>` (evaluator model on the small fast model checks after every turn; verdicts met / not yet / impossible; condition up to 4,000 chars; put "or stop after 20 turns" in the condition; works with `claude -p "/goal ..."`; stops if no tool use for several turns; `CLAUDE_CODE_GOAL_CHECKIN_MINUTES`); `/loop [interval] [prompt]` (cron-backed, session-scoped, min 1 minute, **recurring tasks expire after 7 days**, up to 50 tasks, jitter up to half the interval capped 30 min, `.claude/loop.md` default prompt up to 25,000 bytes, `CLAUDE_CODE_DISABLE_CRON=1`); cloud routines (min 1 hour), Desktop scheduled tasks, GitHub Actions for unattended work; Stop hooks (prompt-based or script) as the generic mechanism. Agent SDK (`claude-agent-sdk` 0.2.174, 2026-10-24): `max_turns`, `max_budget_usd`, result subtypes `error_max_turns` / `error_max_budget_usd` / `error_during_execution`, `permission_mode` (default, acceptEdits, plan, dontAsk, auto, bypassPermissions), hooks (PreToolUse, PostToolUse, Stop, SubagentStop, PreCompact), compaction, session resume. Budget cap can be overshot by one response plus running subagents.
5. **Cross-vendor:** Codex has `/goal` and Automations (OpenAI Academy page 2026-04-23 via search; official docs not opened; sources conflict on whether `/goal` needs a TOML flag: unverified). Open GitHub issues today show it is still rough: "File-backed Goal prematurely completes" (2026-10-14), "automatic Goal turns continue after verified work completion" (2026-10-24). Vercel Labs `ralph-loop-agent` (Apache-2.0, 842 stars, experimental): outer loop with `verifyCompletion`, `stopWhen: [iterationCountIs, tokenCountIs, costIs]`, inner tool loop `toolStopWhen` default 20 steps. Geoffrey Huntley's Ralph loop (demo June 2025, post "loop" 2026-01-17): one task per iteration, fresh context each time, state in files/git, monolithic not multi-agent.
6. **Honest warnings for the lessons:** most "loop engineering" evidence is blogs and vendor pages; benefits unmeasured (paper); risks named by all sources: unverified "done", maker grading own work, reward hacking (deleting tests), runaway cost (Build Fast with AI cites a $400 bill and a 900-iteration loop, secondary; Osmani warns of sub-agent token multiplication), comprehension debt, cognitive surrender, review bandwidth ceiling, parallel collisions.

## 0. What "loop engineering" means (vocabulary all sections rely on)

- Definition (secondary sources agree on substance, not on exact boundaries): designing the system that prompts, checks, remembers and re-runs an agent so a person does not drive it turn by turn: act -> observe -> decide -> repeat until a checkable stop condition. Layer stack: prompt (2022-24) -> context (2025) -> harness (early 2026) -> loop (June 2026). Harness = one run's environment (scaffolding, permissions, tools); loop = harness + schedule + state + verification chain, coordinating many runs over time. (MachineLearningMastery intro; opened.)
- Naming: Peter Steinberger post 2026-06-07 and Addy Osmani essay 2026-06-07/08 (per MLM article; Osmani's own page dated 2026-06-07). Terminology is NOT standardised; the "2026 origin" claims come from blogs. Treat "loop engineering" as an emerging practice name, not a spec. Anthropic's own blog uses the title "Loop engineering: getting started with loops" (2026-06-30).
- Osmani's building blocks: automations (scheduled/event runs that triage), worktrees (parallel isolation), skills (`SKILL.md`), plugins/connectors (MCP), sub-agents (verifier separate from maker), external state (markdown file or Linear board: "the agent forgets, the repo doesn't"). Failure modes he names: unattended mistakes, comprehension debt, "cognitive surrender"; cost warning (sub-agents multiply tokens), no dollar figures.
- Claude loop taxonomy (Anthropic blog 2026-06-30): turn-based (stops when model judges done); goal-based `/goal` (evaluator model checks the condition whenever Claude tries to stop; example "Lighthouse >= 90, stop after 5 tries"); time-based `/loop 5m ...` (local) and `/schedule` (cloud routine, research preview); proactive (event/schedule triggered, no human in real time). Failure modes (MLM): context overflow/rot, no-progress loops, objective misspecification (deleting a failing test to go green), hallucinated success, cost blowup. Production layering example (LangChain): agent loop + verification loop + event-driven loop + hill-climbing loop that analyses traces to improve the harness.
- Sources: https://machinelearningmastery.com/an-introduction-to-loop-engineering/ ; https://addyosmani.com/blog/loop-engineering/ ; https://claude.com/blog/getting-started-with-loops

## 1. Snapshot (PyPI JSON checked 2026-10-26; Python minimum 3.10, recommend 3.12; vcrpy 9 and several extras need >=3.11)

| Package | Stable | Released | requires_python | Role |
|---|---|---|---|---|
| anthropic | **2.3.0** | 2026-10-23 | >=3.10 | Messages API, tool runner. **Major bump since agentic-ai-15h (was 1.15.0)**: see section 4 |
| openai | 3.38.0 | 2026-10-26 | >=3.10 | Responses API |
| google-genai | 2.33.0 | 2026-10-23 | >=3.10 | Gemini (kit default provider) |
| ollama | 0.6.3 | 2026-09-29 | >=3.8 | local models |
| pydantic | 2.14.1 | 2026-10-11 | >=3.10 | schemas |
| tenacity | 9.2.1 | 2026-10-07 | >=3.10 | retries. WARNING: agentic-ai-15h found google-genai 2.31 failed to resolve with tenacity 9.2 (installed 9.1.4); re-test with 2.33 |
| langgraph | 1.2.17 | 2026-10-24 | >=3.10 | graph loops, recursion limit, checkpointers, interrupts |
| langgraph-checkpoint-sqlite | 3.1.2 | 2026-10-12 | >=3.10 | local checkpointer |
| langchain | 1.4.7 | 2026-10-21 | >=3.10,<4 | `create_agent`, middleware |
| openai-agents | 0.24.0 | 2026-10-15 | >=3.10 | `Runner`, `max_turns`, error handlers |
| claude-agent-sdk | 0.2.174 | 2026-10-24 | >=3.10 | the Claude Code loop as a library |
| google-adk | 2.13.0 | 2026-10-23 | >=3.11 | read-along; has Loop workflow agent |
| temporalio | 1.34.0 | 2026-09-30 | >=3.10 | durable execution lab |
| opentelemetry-sdk | 1.45.1 | 2026-10-06 | >=3.10 | tracing (GenAI semconv still Development) |
| arize-phoenix | 20.26.1 | 2026-10-25 | >=3.11,<3.15 | local trace UI |
| deepeval / inspect-ai | 4.3.1 / 0.3.285 | 2026-10-16 / 10-25 | >=3.9 / >=3.11 | eval libraries (pointers) |
| litellm | 1.106.4 | 2026-10-25 | >=3.10 | gateway/fallback pointer |
| pydantic-ai | 2.61.0 | 2026-10-24 | >=3.11 | pointer |
| vcrpy | **9.2.0** | 2026-10-25 | **>=3.11** | record/replay. agentic-ai-15h pinned 8.3.0; **9.2.0 is a day old: check it still patches httpx2 before bumping** (not tested here) |
| pytest / tiktoken / numpy / fastapi / uvicorn / mcp / httpx / rich | 9.1.1 / 0.14.0 / 2.5.4 (>=3.12) / 0.162.0 / 0.54.0 / 2.3.0 / 0.28.1 / 15.0.0 | | | as before (fastapi jumped 0.150 -> 0.162 in 7 days; no breaking note read) |

### Models for lessons (reused agentic-ai-15h section 1, 2026-10-15/20; Anthropic and OpenAI re-read today)
USD per MTok in / out.
- **Anthropic** `claude-haiku-5-5` (2026-10-07) 0.10 / 0.50 up to 100k-token prompts (0.50 / 2.50 above), 1M context, 128K out, cache read 0.01, batch -50%, adaptive thinking + `effort`; `claude-sonnet-5-5` 2 / 10 (cache read $0.10 since 2026-10-07); `claude-opus-5-5` 4 / 20 (fast mode GA 2026-10-15, no header needed). Sonnet 4.5 retires **2026-11-30**. Other ids in docs: `claude-opus-5`, `claude-fable-5-1`, `claude-mythos-5-1` (prices not read). Haiku 5.5 400s on `temperature`/`top_p`/`top_k`, prefill, `budget_tokens`.
- **OpenAI** `gpt-6-luna` 0.10 / 0.50 (cached 0.01); `gpt-6.1-sol` 2 / 10; `gpt-6-astra` 10 / 50; **new 2026-10-26 `gpt-6.1-terra`** (visual reasoning/computer use; price not read); 12-hour prompt cache (2026-10-20, writes 2.5x input price).
- **Google**: kit default model comes from `.env` (agentic-ai-15h listed 0.30 / 2.50, free tier; `gemini-4-argon` GA 2026-10-13, 2 / 10 until 2026-11-30). Not re-checked today. (The prior file contains the placeholder text "the model set in your .env" where ids were scrubbed; the writer must read the id from `.env` / `llm_setup`.)
- **Local**: Ollama model with tools capability (2.1 GB small / 5.3 GB 8b), `needs-download`.
- **SDK support for tool calling / structured output / streaming**: all three SDKs support all three (agentic-ai-15h F1, verified against then-current versions). Re-verify the Anthropic bits against 2.x before writing (section 4).

### Loop-control features per vendor (verified today)
| Control | Claude Agent SDK / Claude Code | Anthropic Messages API | OpenAI Agents SDK | LangGraph |
|---|---|---|---|---|
| Step cap | `max_turns` (tool-use turns; default none); result subtype `error_max_turns` | none (you write the loop; `max_tokens` per request) | `max_turns` -> `MaxTurnsExceeded`; `max_turns=None` disables; `error_handlers={"max_turns":...}` returns a controlled output | `config={"recursion_limit": n}` (default 1000 since 1.0.6; top-level config key, not in `configurable`) -> `GraphRecursionError`; `RemainingSteps` managed value for proactive exit |
| Cost cap | `max_budget_usd`; `error_max_budget_usd`; can overshoot by one response + running subagents; covers subagents (needs Claude Code >= 2.1.217) | **Task budget** (beta, header `task-budgets-2026-03-13`): `output_config={"task_budget":{"type":"tokens","total":N,"remaining":M}}`, min 20,000; **advisory** (model sees countdown), not in Claude Code; hard cap = `max_tokens` + your own counter. **Session budgets** (Managed Agents, enforced): stop reason `budget_reached`, session idles with state kept | client-side with `Usage` | client-side |
| Other stop signals | `stop_reason` `end_turn`/`max_tokens`/`refusal`; `error_during_execution`; `error_max_structured_output_retries` | `stop_reason` | `"model_refusal"`, `"invalid_final_output"` handlers; `ModelBehaviorError`, `ToolTimeoutError`, `ModelTimeoutError` | n/a |
| Human checkpoint | `permission_mode` (`default`+`canUseTool`, `acceptEdits`, `plan`, `dontAsk`, `auto` (classifier), `bypassPermissions` only in isolated envs); `PreToolUse` hook can block | you write it | HITL pause -> `RunState` resume | `interrupt()` + checkpointer |
| Hooks | `PreToolUse`, `PostToolUse`, `UserPromptSubmit`, `Stop` (validate result when agent finishes), `SubagentStart/Stop`, `PreCompact` | n/a | guardrails (input/output tripwires) | middleware / nodes |
| Context | automatic compaction (`compact_boundary` system message), `PreCompact` hook, CLAUDE.md re-injected each request, subagents return summaries only | server-side compaction (client-side compaction removed from tool runner in 2.0 for TS/Ruby) | sessions | checkpointers + stores |
| Resume | `session_id` from `ResultMessage`, resume/fork, `session_store` adapter | you persist | `RunState` | `thread_id` checkpoint |

---

## 2. Official docs map (coverage checklist for the planner)

Reused: vendor docs maps 2.1-2.8 of `agentic-ai-15h/RESEARCH.md` section 2 (and F1 section 2 it cites), 2026-10-20; checked 2026-10-26 for the changes below. Loop-specific pages (opened today unless marked):

- **Claude Agent SDK** (code.claude.com/docs/en/agent-sdk/...): Overview, Quickstart, **Agent loop** (opened), Python/TypeScript refs, Hooks, Permissions, Sessions, Session storage, Cost tracking (`total_cost_usd`, `model_usage`), Subagents, MCP, Skills, Streaming output, Hosting (container/serverless), Todo tracking, Tool search. Related: "How Claude Code works" (agentic loop), blog "Loop engineering: getting started with loops" (opened), blog/engineering "Effective harnesses for long-running agents" (opened).
- **Anthropic API** (platform.claude.com/docs/en/...): Task budgets (opened), Effort, Adaptive thinking, Compaction / compaction threshold, Prompt caching, Tool use / tool runner, Managed Agents (sessions, session budgets, dynamic workflows beta 2026-10-09, scheduled deployments, outcomes), Release notes (opened), Migration to API version 2026-10-21 (opened), OpenTelemetry export (beta 2026-10-14; not opened).
- **OpenAI Agents SDK** (openai.github.io/openai-agents-python): Running agents (opened: `Runner.run/run_sync/run_streamed`, `max_turns`, `error_handlers`, exceptions list, `RunState`), Results, Streaming, Human-in-the-loop, Guardrails, Sessions, Tracing, Usage, Testing. Codex: automations, skills, subagents (developers.openai.com/codex/..., linked from Osmani; not opened). OpenAI "Harness engineering" post (Ryan Lopopolo, 2026-02-11): returned HTTP 403 to fetch; **only search snippets seen** (Codex wrote all code of an internal beta; team job = environments, intent, feedback loops). Do not cite details beyond that without opening it.
- **LangGraph** (docs.langchain.com/oss/python/langgraph): Graph API (opened: conditional edges, `recursion_limit`, `RemainingSteps`, proactive vs reactive termination), Persistence, Interrupts, Fault tolerance, Streaming, Test; LangChain: Agents (`create_agent`), Middleware, Human-in-the-loop.
- **Google ADK 2.x** (adk.dev): workflow agents incl. **LoopAgent** (not re-opened).
- **Standards/vocab**: OpenTelemetry GenAI semconv (agent spans `invoke_agent`, `execute_tool`), AGENTS.md, Agent Skills (`SKILL.md`), MCP. Reused from agentic-ai-15h sections 2/3/H.
- **Practitioner primary sources**: Osmani "Loop Engineering" (2026-06-07, opened); Huntley "Ralph" (opened); Anthropic "Building effective agents" (2024-12-19; reused); Anthropic harnesses post (2025-11-26, opened).

---

## 3. Core concepts (grouped; one line each; `[impl]` = interviews ask candidates to code it; `[core]`)

**A. What a loop is**
- Agent = model + tools + instructions in a loop; workflow (fixed path) vs agent (model-directed); when not to loop. (reused)
- Anatomy of one turn: build request -> model -> parse stop reason -> execute tools -> append results -> repeat. [impl: the hand-written loop + tool registry]
- Three wire formats (Anthropic `tool_use`/`tool_result`, OpenAI function_call items, Gemini); stateless history resend vs server state; parallel tool calls (all results in one user message on Anthropic). (reused)
- Inner loop vs outer loop vs harness vs prompt/context engineering: the vocabulary and the layer map.
- Loop taxonomy: turn-based, goal-based, time-based, proactive (Anthropic); Ralph (fresh context per iteration); evaluator-optimizer; plan-execute; ReAct. 

**B. Termination (the heart of the topic)**
- Natural end (no tool call / `end_turn`), final-output tool, `max_tokens`, `refusal`, errors.
- Hard caps: step/turn cap, wall-clock, token and dollar budgets; why caps are checked after a response (overshoot by one response, plus running subagents).
- Advisory vs enforced budgets: task budget (model-visible countdown) vs session budget vs your own counter.
- Completion criteria: mechanical (tests exit 0, lint clean, score >= threshold) vs model-judged; separate evaluator (maker/checker); dual-condition exit; "done is a claim".
- No-progress / loop detection: repeated identical tool call, same failure twice, state-hash unchanged, cost-per-progress. [impl]
- Graceful degradation: proactive exit before the limit (`RemainingSteps`), partial results, `error_handlers`, summarise-and-stop.

**C. Errors, retries and recovery**
- Error classes: API (429/5xx/overload), tool failure, validation failure, model misbehaviour (bad args, hallucinated tool), refusal, truncation.
- Retries with exponential backoff + jitter, `Retry-After`, timeouts per hop, retry budgets, circuit breaker, model fallback. [impl: backoff + token bucket]
- Errors as observations (`is_error` tool results) so the model can recover; retry with the validation error fed back; escalate after N failures.
- Idempotency keys for write tools; at-least-once tools; compensating actions; side-effect safety on resume.
- Checkpoint and resume: LangGraph checkpointer + `thread_id`, Claude `session_id`, `RunState`, Temporal replay; kill drill.

**D. Human-in-the-loop**
- Approval gates on write/irreversible tools showing the real arguments [impl]; pause/resume with saved state; permission modes; classifier "auto" mode; escalation on give-up; review queues; keeping the human the verifier (comprehension debt, cognitive surrender).

**E. Context inside long loops**
- Context growth per turn, cost growth (quadratic input), prompt caching of stable prefix, compaction (server-side vs own), clearing old tool results, subagents returning summaries, progress file/todo recitation, tool search for many tools.
- Long-running harness pattern (Anthropic): initializer + coding agent, `feature_list.json` with `passes`, `claude-progress.txt`, `init.sh`, git commits per feature, start-of-session routine (`pwd`, read log, read feature list, run smoke test), end-to-end verification rule ("removing or editing tests is unacceptable").

**F. Harness engineering (the layer under the loop)**
- Tools design, permissions, sandbox (worktree, container), hooks (PreToolUse/PostToolUse/Stop), skills, AGENTS.md/CLAUDE.md as the map, mechanical enforcement (linters, structural tests) as backpressure.

**G. Evals as loop gates**
- Verification chain inside the loop (tests, type check, lint, screenshot diff, evaluator model); backpressure.
- Golden set, graders, pass@k vs pass^k, trajectory evals, loop-level metrics: success rate, steps per task, cost per goal, no-progress rate, recovery rate; evals in CI as release gate; LLM-as-judge limits. [impl: eval harness + regression gate]

**H. Autonomous coding loops**
- Gather-act-verify; edit tools; tests as the stop signal; Ralph; `/goal`; PR-babysitting `/loop`; worktrees for parallel agents; maker/checker; commit-on-green and revert-on-red; scope per iteration (one item).
- Failure modes: placeholder code, duplicate implementations, deleting tests, reward hacking the check, runaway cost, unattended mistakes, file collisions.

**I. Multi-agent loops** (as it affects loops): orchestrator-worker, subagent budgets rolled up, fan-out cost (agent ~4x, multi-agent ~15x chat tokens), dynamic workflows risk (hundreds of agents), MAST failure modes (step repetition 15.7%, unaware of termination 12.4%). (reused)

**J. Running loops in production**
- Triggers: schedule (cron / `/schedule` routines / scheduled deployments), event (webhook), queue; one-shot job vs long-lived service.
- Durable execution (Temporal / LangGraph checkpoints), queues + workers, concurrency limits, leases/locks so two loops don't take the same task, dead-letter queue, kill switch, rate limits.
- Observability: trace tree `invoke_agent` > model call > `execute_tool` (OTel GenAI), per-run cost, p95, loop metrics, alerts on no-progress/cost spikes; log hygiene (no raw PII).
- Cost engineering: caching, routing small-first (Haiku/Luna tier for routine, big model for judgment), batch -50%, effort levels, budgets per run/tenant/day.
- Deployment: FastAPI + SSE, container, secrets from env, health probes; hosting the Agent SDK (container/serverless; session store).

**K. Enterprise operation**
- Tenancy (per-tenant budgets, memory, policies), RBAC and agent identity (OAuth on-behalf-of), audit log, approvals as policy outside the model, injection defence (lethal trifecta, Rule of Two), sandbox isolation, change management (shadow/canary/rollback for prompt+model changes), model retirement management (Sonnet 4.5 -> 2026-11-30), vendor-managed runtimes (Managed Agents, AgentCore, Agent Runtime, Foundry), governance vocabulary (OWASP LLM/Agentic, NIST AI RMF, ISO 42001, EU AI Act). (reused F-L)

(Research-level, Go deeper only: Reflexion/LATS/ToT, RL for tool use, loop theory.)

---

## 4. Current APIs vs deprecated APIs

Rows 1-6 are new/changed in the last 3 weeks (verified today); the rest are reused from `agentic-ai-15h/RESEARCH.md` section 4 (2026-10-20; the Google/OpenAI/MCP/framework rows stand, checked 2026-10-26 against OpenAI changelog and PyPI).

| Old way | Current way | Since | Source |
|---|---|---|---|
| `anthropic` 1.x, header `anthropic-version: 2023-06-01`, `X-Api-Key` | `anthropic>=2.0` sends `2026-10-21` and `Authorization: Bearer <key>` (fix gateways/proxies that read `X-Api-Key`); license Apache 2.0 | 2026-10-21 | platform.claude.com migration-2026-10-21; release notes |
| `temperature`/`top_p`/`top_k` in Messages requests | removed: 400 even at default; SDK 2.x no longer has the params | API 2026-10-21 | migration guide |
| `MessageParam` single type | `UserMessageParam` / `AssistantMessageParam` / `SystemMessageParam` (and `Beta*` variants) | SDK 2.0 | migration guide |
| `document` blocks in assistant messages; `citations` on user-message text blocks | both return 400; put documents in user messages, drop `citations` from user text | API 2026-10-21 | migration guide |
| Text Completions; `betas` on non-beta Models methods; client-side compaction in TS/Ruby tool runner | removed; use Messages; server-side compaction | SDK 2.0 | migration guide |
| Hand-counted loop budget only | additionally **task budgets** (beta, advisory, `output_config.task_budget`, header `task-budgets-2026-03-13`), Managed Agents **session budgets** (`budget_reached`) | 2026-03 / 2026-07 | task-budgets docs; cookbook (via search) |
| `claude-code-sdk` | `claude-agent-sdk` (`query`, `ClaudeAgentOptions(max_turns, max_budget_usd, permission_mode, allowed_tools, setting_sources, effort)`; result subtypes `success`/`error_max_turns`/`error_max_budget_usd`/`error_during_execution`/`error_max_structured_output_retries`) | 2025 | agent-loop page |
| LangGraph default recursion limit 25 | 1000 steps since langgraph 1.0.6; set `config={"recursion_limit": n}`; use `RemainingSteps` (`langgraph.managed`) for proactive exit | 1.0.6 | docs.langchain.com graph-api |
| OpenAI Chat Completions / Assistants (shut down 2026-08-26) / Swarm | Responses API; OpenAI Agents SDK (`Runner.run`, `max_turns`, `error_handlers`) | 2025-26 | reused |
| `google.generativeai` | `google-genai` (`genai.Client()`) | 2025 | reused |
| Claude `thinking={"type":"enabled","budget_tokens"}`, prefill | adaptive thinking + `effort`; end on a user turn | 4.6/4.7, Haiku 5.5 | reused + release notes |
| `langgraph-supervisor`, AutoGen GroupChat, `initialize_agent`, `ConversationBufferMemory` | supervisor via tools/subagents, `langchain.agents.create_agent` + middleware, checkpointers | 2025-26 | reused |
| MCP initialize handshake / HTTP+SSE | stateless core 2026-07-28, Streamable HTTP | 2026-07-28 | reused |

Unverified: exact SDK-2.0 Python tool-runner signature changes beyond the migration headings read (lines for Python in the guide were not all read); the writer must run the code against `anthropic==2.3.0` in the venv, not trust this table.

---

## 5. Ecosystem and alternatives (when each is chosen)

Reused from agentic-ai-15h section 5 (2026-10-20), versions refreshed today; loop-specific additions marked new.
- **Hand-written loop on a vendor SDK** (anthropic 2.3.0, openai 3.38.0, google-genai 2.33.0): teaches the mechanism; the interview "implement" item. Anthropic beta tool runner after the hand loop.
- **Claude Agent SDK 0.2.174 / Claude Code** (new emphasis): the production coding loop as a library with `max_turns`, `max_budget_usd`, hooks, permissions, sessions, subagents; chosen for coding/long-running agents; needs Anthropic key (no claude.ai login); runs a bundled binary.
- **OpenAI Agents SDK 0.24 / Codex** (`/goal`, automations, skills, subagents per Osmani's links): light loop with `max_turns`, guardrails, sessions, tracing; best on OpenAI models.
- **LangGraph 1.2.17 + langchain 1.4.7** (taught in depth in the sibling course): explicit state, conditional edges, checkpointers, interrupts, `recursion_limit`; chosen when a loop needs pause/resume/approval and durable state.
- **Google ADK 2.13** (LoopAgent, workflow agents), **Pydantic AI 2.61**, **Microsoft Agent Framework**, **CrewAI**, **Strands**: pointers.
- **Durable execution**: Temporal 1.34 (replay; chosen for long, side-effecting, multi-day loops) vs LangGraph checkpoints (lighter) vs a DB-backed job queue (simplest). Managed: Anthropic Managed Agents (sessions, session budgets, scheduled deployments, dynamic workflows beta), AWS AgentCore, Gemini Enterprise Agent Platform Agent Runtime, Microsoft Foundry Agent Service. (New: Claude models on Google Cloud, Anthropic managed, 2026-10-22.)
- **Scheduling/triggers** (new for this course): cron/systemd, GitHub Actions schedule, queue workers, Claude `/schedule` routines, Codex automations; chosen by who owns the box and whether state must survive restarts.
- **Observability**: OpenTelemetry SDK 1.45 (+ Anthropic OTel export beta 2026-10-14), Phoenix 20.26 local, Langfuse (heavy self-host), LangSmith/Braintrust hosted.
- **Evals**: pytest harness (taught), DeepEval 4.3, Inspect AI 0.3.285, promptfoo (pointers).
- **Gateway/fallback**: LiteLLM 1.106.

## 5a. Why each piece exists (open each Part with "Why <X>")

Reused from agentic-ai-15h 5a (loop, structured output, durable execution, observability/security) and extended with loop-engineering-specific pieces (opened today).
- **The agent loop.** Before: chat models only talked; "check my order" was one hard-coded pipeline per question. Change: the model asks for a tool, your code runs it, the result returns. Not solved: wrong tool choice, runaway loops, cost, side effects. Alt: fixed workflow.
- **Caps and budgets.** Before: an unbounded `while` loop keeps billing; Huntley's Ralph "any tool that doesn't cap tool calls and usage" is dangerous; practitioners say "with no budget cap there is no end". Change: `max_turns`, `max_budget_usd`, task/session budgets, recursion limits. Not solved: caps are checked after a response (overshoot by one response + running subagents, Claude docs); advisory budgets are soft; a too-small task budget makes Claude refuse or cut scope (task-budgets docs).
- **Completion checks and maker/checker.** Before: the agent that wrote the code graded itself and declared victory ("later agents saw existing progress and declared the project finished too early", Anthropic harnesses post). Change: mechanical checks (tests exit 0), a separate evaluator (Claude `/goal` uses a small separate model), dual-condition exit. Not solved: weak checks get gamed ("removing or editing tests is unacceptable" had to be written into the prompt); "done" stays a claim (Osmani).
- **Harness (progress file, feature list, git, init script).** Before: each session started with no memory; the agent tried to build everything at once, ran out of context mid-feature, left it undocumented. Change: initializer + coding agent, `feature_list.json` with `passes`, `claude-progress.txt`, git commits (Anthropic, 2025-11-26). Not solved: end-to-end verification blind spots (agent could not see browser-native alerts).
- **The outer loop (loop engineering).** Before: the developer was the loop, typing the next prompt every turn. Change: schedule/goal/state/verification so the system picks the next task (Osmani 2026-06-07; Anthropic's four loop types). Not solved: unattended mistakes, comprehension debt, cognitive surrender, token cost.
- **Backpressure (tests, type checks, linters).** Before: Ralph-style loops produced placeholder code and duplicate implementations. Change: automated rejection each iteration (Huntley). Not solved: slow feedback slows the loop; nondeterministic search ("ripgrep says not implemented").
- **Human-in-the-loop and permission modes.** Before: all-or-nothing trust. Change: `permission_mode`, `canUseTool`, `PreToolUse` hooks, interrupts, `auto` classifier mode. Not solved: approval fatigue; bypass modes only in isolated environments.
- **Compaction / subagents / progress files.** Before: context filled until quality dropped or the call failed. Change: automatic compaction with `PreCompact` hook, CLAUDE.md re-injected, subagents returning summaries. Not solved: instructions given only early in the chat can be lost in a summary (Claude docs).
- **Durable execution and scheduled loops.** Before: a laptop-bound `/loop` stops when the computer sleeps; a 40-minute run dies at minute 38. Change: cloud routines/scheduled deployments, Temporal/LangGraph checkpoints. Not solved: at-least-once tools need idempotency.
- **Evals as loop gates.** Before: "feels worse" after a change. Change: golden tasks + loop metrics (success, steps, cost per goal, no-progress, recovery) in CI. Not solved: grader drift, saturation.
- **Frameworks / vendor SDKs / MCP / multi-agent**: see agentic-ai-15h 5a (not repeated).

---

## 5b. Curriculum triangulation (ids match coverage_matrix.json)

| kind | id | source | what it covers | opened |
|---|---|---|---|---|
| docs | docs | Claude Code docs: scheduled-tasks (/loop), goal (/goal), Agent SDK "How the agent loop works" | trigger/stop/budget/permission/hook mechanics | 2026-10-26 |
| docs | gAnthLoops | Anthropic blog, "Loop Engineering: getting started with loops" (2026-06-30): turn-based, goal-based, time-based, proactive loops; verification; cost | taxonomy of loops, cost advice | 2026-10-26 |
| docs | eHarness | Anthropic Engineering, "Effective harnesses for long-running agents" (2025-11-26): initializer agent, progress file, JSON feature list (200+ items, all failing), one feature per session, browser-automation testing | state across sessions, premature "done" | 2026-10-26 |
| docs | eBEA, gOAI | Anthropic Building effective agents; OpenAI Practical guide to agents (carried from agentic-ai-15h, stable) | loop, patterns, guardrails | carried |
| writing | gOsm, gOR | Addy Osmani, Loop engineering (2026-06-07; O'Reilly Radar 2026-06-22): 6 building blocks, tool map Codex vs Claude Code, patterns (heartbeat, one worktree per finding, maker/checker), risks | the field's founding essay | 2026-10-26 |
| writing | gIBM | IBM Think, What is loop engineering (2026-07-17): goal-action-observation-adjustment, 8 components, 4 risks (unverified code, comprehension debt, intent debt, cognitive surrender), explicit stop criteria | vendor-neutral view | 2026-10-26 |
| writing | gBF | Build Fast with AI guide (2026-07-14): trigger/goal/verifier/stop rules; failure modes; cost anecdotes | beginner framing (secondary) | 2026-10-26 |
| writing | gHunt | Geoffrey Huntley, "Ralph loop" (2026-01-17) | outer loop pattern, monolithic vs multi-agent | 2026-10-26 |
| code | pVercel | vercel-labs/ralph-loop-agent README | outer/inner loop API, stop conditions | 2026-10-26 |
| paper | pArx | arXiv 2608.21884 "Loop Engineering: Building Blocks, Adoption, and Impact" (abstract page) | literature review of building blocks, 217/36,710 repo mining, no empirical evidence | 2026-10-26 |
| course | cDLAS | DeepLearning.AI "Agent Skills with Anthropic" (Elie Schoppik, 2h19m, 10 video lessons, updated 2026-07-17): SKILL.md, progressive disclosure, skills vs tools/MCP/subagents, API, Claude Code, Agent SDK | capabilities layer | 2026-10-26 |
| course | cAIB | AI Builder Club "Mastering AI Agents" (Jason Zhou, 50 lessons, intermediate): chapters Agent Loop (5), Tool System (8), Context Engineering (9), Memory (3), Multi-Agent (5), Evaluation (3), Cost & Latency (2), Harness Engineering (6), Frameworks (1), Capstone (2). No rating or learner count shown | closest course to this topic; no big-platform equivalent exists | 2026-10-26 |
| course | cDL, cMS, cHF | DeepLearning.AI Agentic AI (Ng), Microsoft AI Agents for Beginners (18 lessons), Hugging Face Agents Course (carried from agentic-ai-15h, 2026-10-18/20; stable) | the agent loop, tools, evals, planning, production | carried |
| book | bAIE | Chip Huyen, AI Engineering (O'Reilly 2025) (carried) | evaluation, inference cost, monitoring | carried |
| certification | cAIP | AWS Certified Generative AI Developer - Professional AIP-C01 (carried, 2026-10-20): agentic solutions 26%, safety/governance 20%, operational efficiency 12%, testing/troubleshooting 11% | what a vendor exam tests | carried |
| jobs | jP, jG2 | 446 and 243 AI/agent engineer postings (2026-10-15/16; research_cache copy at topics/agentic-ai-6-production-v2/RESEARCH.cache-ai-engineering.md, 10 days old: reused as volatile-under-30-days) | skills by share | carried |
| jobs | jH | "Harness engineer" / "agent harness engineer" postings found 2026-10-26 via search (not opened individually): Remote AI Agent Engineer (Jul 2026, owns harness layer, eval frameworks, regression tests, failure taxonomies, LangGraph / Vercel AI SDK), Remote Harness Engineer (May 2026, writes agent-ready specs with acceptance criteria, reviews agent output), Nomic NYC (Jun 2026, retrieval, context assembly, evaluation), JAPAN AI Tokyo (Apr 2026, execution engine, guardrails, memory, model routing), Viktor Warsaw (Aug 2026) | the nearest real job titles | 2026-10-26 (snippets) |
| interviews | iTIsys | techinterview.org "What the agent system design interview really tests" (updated 2026-07-23; opened): coding-agent design, repeated tool call loop, MAX_STEPS, identical-call detection, idempotency after restart, schema validation, trajectory scoring | loop/stop/idempotency questions | 2026-10-26 |
| interviews | iAV, iCl, iCa, iTI | carried from agentic-ai-15h (2026-10-16/20) | evals, injection, cost, loop design | carried |
| questions | qGH | GitHub issue search counts today (gh API): anthropics/claude-code "infinite loop agent" 382 issues, "goal loop stuck" 64; openai/codex "loop runaway cost" 50, "goal" 3,232 (broad word); recent Codex goal bugs above | what breaks in real loops: premature completion, runaway goal turns, stuck loops | 2026-10-26 |

Eight kinds (docs, writing, code, paper, course, book, certification, jobs, interviews, questions). Concept ranking: 5+ source kinds: stop conditions/budgets, verification (verifier, evals), persistent state, tool loop, security/permissions, cost. 3-4: scheduling/triggers, worktree isolation, subagents/maker-checker, skills, observability. 1-2: goal/Ralph outer loop (but central to the topic), comprehension debt, loop experiments.

**What developers actually build (D6, D16, D17):** (1) overnight/CI-triggered coding loops: fix failing tests, migrate an API until every call site compiles (Claude Code `/goal` doc examples); (2) daily heartbeat triage: read CI failures and issues, write findings to a state file, one worktree + sub-agent per finding, second sub-agent reviews, open PR (Osmani worked example); (3) PR babysitter loop (`/loop check CI and address review comments`); (4) product agents with outer verify-and-retry loops, caps and escalation (support/ticket triage, research agents; Rubrik, Coinbase "agent verification", LaunchDarkly AgentControl postings); (5) agent eval/verification platforms. Suggested reference architecture for the capstone: trigger (cron/GitHub event) -> loop controller (goal, iteration/token/spend caps, repeated-call detector) -> worker agent in worktree/sandbox with least-privilege tools -> deterministic verifier (tests, lint, schema) + separate checker agent -> state spine (JSON feature list + progress file + git) -> traces and cost log -> human escalation queue -> eval suite in CI.

**Interview-critical / implement (rules 20, 26):** bounded agent loop with MAX_STEPS and budget (implement, iTIsys, iCl, iAV); stop-condition/four-exit design (done, stuck, over budget, hand off); repeated-call detection (iTIsys); idempotent tool calls and durable state (iTIsys, iCl); verifier design and eval gate in CI (iCa, iCl); injection and least privilege; cost cap/rate limiting (iCa); tracing a multi-step run (iTI). Library per mechanism: `claude_agent_sdk` (official, 0.2.174; hooks, max_turns, max_budget_usd), `agents` from `openai-agents` 0.24.0, `langgraph` 1.2.17 (checkpointer, interrupt), `pydantic` (schemas), `pytest` (deterministic verifier), `tenacity` (retries), OpenTelemetry + `langfuse` 5.0.4 (traces), `deepeval` 4.3.1 (judge/evals), `git worktree` (isolation).

## 5c. Example data

Reused from agentic-ai-15h 5c (2026-10-20; generated data needs no re-check) and adapted: a loop course needs a **checkable goal**, so the main data is generated.

| Kind | Candidate | License / source | Size | Why it fits |
|---|---|---|---|---|
| Support-desk tables | Generated mock CRM in SQLite (customers, orders, tickets, refunds, audit_log; ~200 customers, ~400 orders, ~60 tickets; seed script; `name@example.com`) | generated; may copy `topics/agentic-ai-15h/data` generator | <1 MB | Basic/Intermediate loops (read tools, one gated refund tool) |
| Policy text | Own one-page "Brightside returns policy" (agrees with the FTC 30-day rule); optional FTC business guide excerpt (US federal work; page has no licence statement, say so in SOURCES.md) | generated / ftc.gov | 1 page | Short grounding for the agent without a RAG detour |
| Coding-loop target | A tiny generated Python repo "pocket-cart": 6 small modules, a pytest suite with ~12 failing tests and a spec list (`fix_plan.md`, `feature_list.json`) | generated | <50 KB | A Ralph/`/goal`-style loop with a mechanical stop (pytest exit 0), reproducible failures, revertible with git; no download |
| Golden set | 25-30 tasks with expected end-states + 20 injection cases + 10 "loop trap" tasks (impossible goal, flaky tool, contradictory spec) to test caps and no-progress detection | generated | <100 KB | Evals as loop gates |
| Scripted fake model | deterministic scripted responses (tool call sequences incl. a runaway repeat) | generated | tiny | Tests caps/retries with no key |
| Recordings | cassettes of the few live calls | recorded via `llm_replay` | small | Replay with no key |

Nothing else opened. No real downloadable dataset is needed; say "generated" in `datasets`.

---

## 5d. Platforms, benchmarks and recency

**Platforms (loop runtimes).** Competing agent products and SDKs, with the same mechanism under different names (service map for the course, sourced as noted):

| Concept | Claude Code / Agent SDK | OpenAI Codex / Agents SDK | Vercel AI SDK | Framework |
|---|---|---|---|---|
| In-session goal loop | `/goal`, Stop hook | `/goal` (unverified from official docs; open bugs) | `ralph-loop-agent` `verifyCompletion` | LangGraph conditional edge back to the worker node |
| Time/event trigger | `/loop`, cloud routines (>=1 h), Desktop tasks, GitHub Actions | Automations tab + Triage inbox (OpenAI Academy 2026-04-23) | cron + serverless | any scheduler / Temporal |
| Caps | `max_turns`, `max_budget_usd` | per-product limits | `iterationCountIs`, `tokenCountIs`, `costIs` | `recursion_limit` |
| Isolation | `git worktree`, `isolation: worktree` on subagents | worktree per thread | n/a | n/a |
| Capabilities | SKILL.md, MCP, plugins, `.claude/agents/` | SKILL.md, MCP, `.codex/agents/` TOML | tools | tools / MCP |
| Memory/state | `AGENTS.md`/`CLAUDE.md`, progress files, sessions + `session_store` | same | files | checkpointer |
(Source: Osmani table 2026-06-07, Claude Code docs, ralph-loop-agent README, all opened 2026-10-26.) Model vendor and cloud shares from the shared sample: OpenAI 33.9%, Claude 21.3% of postings; AWS 19.5, GCP 14.6, Azure 10.1; LangChain 10.8, LangGraph 10.5 (jP, n=446). Verdict: vendor-neutral loop core written against the official Anthropic/OpenAI/Gemini SDK message formats and one hand-written loop ("under the hood", interview), then Claude Agent SDK as the primary loop runtime (it is the only vendor SDK with `max_budget_usd`, hooks and compaction documented in one page), LangGraph as the framework, a one-lesson comparison with Codex and the AI SDK. Product features (`/goal`, `/loop`) are Claude Code-specific and fast-moving: teach the concept with the portable Stop-hook / outer-loop version and treat the slash commands as one example.

**Benchmarks (practitioner).** No Coursera/DeepLearning.AI/Udemy course on "loop engineering" itself exists yet (search 2026-10-26). Nearest by standing: DeepLearning.AI Agentic AI (Ng; carried), DeepLearning.AI Agent Skills with Anthropic (official vendor short course, 10 lessons, updated 2026-07-17), Microsoft AI Agents for Beginners (18 lessons, 77.5k stars), Hugging Face Agents Course, Chip Huyen AI Engineering (best-selling O'Reilly book), AWS AIP-C01 (official certification), AI Builder Club Mastering AI Agents (50 lessons, self-published; no rating shown; closest content match, treat as topic map not as a standing benchmark). Item lists: `coverage_matrix.json` `benchmark_items`. Other 2026 courses found but not practitioner-benchmarks: IISc CCE "Agentic AI coding" (6 weekends, from 2026-09-05), IDA Copenhagen coding agents and context engineering (2 days, 2026-09-15), Stanford CS146S, University at Buffalo CSE410 (academic: not used).

**Recency (last 12 months; dates and sources).**
- 2025-11-26: Anthropic "Effective harnesses for long-running agents" (initializer + progress file + JSON feature list).
- 2026-01-17: Huntley "loop" write-up of the Ralph technique (first demo June 2025).
- 2026-06-07 / 06-22: Osmani "Loop engineering" (term spreads); 2026-06-30 Anthropic "getting started with loops"; 2026-07-14 Build Fast with AI; 2026-07-17 IBM Think.
- Claude Code: `/goal` (v2.1.234-2.1.269 added check-ins, retries; idle check-ins capped from v2.1.246), `/loop` dynamic intervals (Bedrock/Foundry need v2.1.248+), 7-day expiry for recurring session tasks, background sessions, cloud routines; current v2.1.310 (2026-10-23).
- Codex: Automations (April 2026), `/goal` with open bugs Oct 2026; current rust-v0.164.0 (2026-10-23).
- 2026-08-22 (rev. 2026-10-22): first academic paper on loop engineering; accepted JAWs@ASE 2026 (Munich, Oct 12-16).
- Versions verified on PyPI 2026-10-26: claude-agent-sdk 0.2.174 (2026-10-24), langgraph 1.2.17 (2026-10-24), openai-agents 0.24.0 (2026-10-15), anthropic 2.3.0 (2026-10-23), google-genai 2.33.0, langfuse 5.0.4, deepeval 4.3.1, pydantic-ai 2.61.0. Note: earlier agentic-ai-15h research recorded anthropic 1.15.0; PyPI today says 2.3.0 (major bump) - the core part should recheck and the 15h agentic course's pins differ.
- Shared recency (carried from agentic-ai-15h, 2026-10-20): Gemini 4 Argon GA 2026-10-13; Claude Haiku 5.5 2026-10-07; OpenAI Assistants API shut down 2026-08-26; temperature/top_p not settable on newest models.

## 5e. Design topics

Not a design topic (`profile` default). Machine-coding style items that appear: the bounded agent loop (MAX_STEPS, budget), repeated-call detector, outer verify-retry loop, token-bucket/cost limiter, idempotency-key wrapper, eval harness (golden set + pass rate).

## 5g (1). Where next (also in extras.json)

- Harness engineering (discipline, growing): building the execution environment around a model (tools, guardrails, memory, routing, evals). Evidence: 5 harness-engineer postings Apr-Aug 2026 (JAPAN AI, Nomic, Viktor, two remote), IBM Think, Anthropic harness post.
- Agent evaluation and verification platforms (technology, growing): Coinbase "Agent Verification", LaunchDarkly AgentControl, Datadog agent observability postings (Oct 2026).
- Context engineering (discipline, growing): 6.5% of postings (jP); IBM lists it as a loop component; Anthropic harness post.
- AI platform / agent infrastructure engineer (role, established-growing): gateways, durable execution, multi-tenant runtimes: Okta Agent Gateway, Rubrik, Zscaler, Stripe postings (2026-09/10).
- Forward deployed engineer (role, established): carried from agentic-ai evidence (Databricks, Stripe).
- Agentic software engineering as a practice (discipline, emerging): arXiv 2509.06216 roadmap; no postings use "loop engineer"; say so plainly.

## 6. Runs on a laptop? (per capability; tags from NOTEBOOK_RULES)

Reused from agentic-ai-15h section 6 (2026-10-20); loop rows are new.

| Capability | Local, no account? | How | Tags |
|---|---|---|---|
| Model calls | Replay only; live needs a provider key | `llm_replay` (vcrpy; re-check 9.2.0 vs 8.3.0, section 1) ; scripted fake model | `needs-llm` |
| Hand-written loop, tool registry, caps, no-progress detector, retry/backoff, token bucket, HITL gate, eval harness, state file | Yes | stdlib + pydantic + pytest | none |
| Coding loop (Ralph-style) on the pocket-cart repo | Yes with a scripted fake model; live with a key | subprocess pytest as the verifier, git in a temp repo/worktree | none / `needs-llm` |
| Claude Agent SDK loop (`max_turns`, `max_budget_usd`, hooks, permission modes) | Replay/read-along; live needs `ANTHROPIC_API_KEY` (bundled binary; no claude.ai login) | one recorded run; hooks demonstrable offline only partly | `needs-llm` |
| `/goal`, `/loop`, `/schedule` (Claude Code), Codex automations | No (product features, need subscriptions/cloud; `/schedule` is cloud) | walkthrough/screenshots; do not run in notebooks | `needs-cloud` (not run) |
| Task budgets (beta) | Live key + beta header only | recorded call; show the request shape | `needs-llm` |
| LangGraph recursion limit, `RemainingSteps`, checkpointer, interrupt | Yes | in-memory + SQLite checkpointer, fake model | none |
| OpenAI Agents SDK `max_turns` / error handlers | Replay; live needs key | recorded | `needs-llm` |
| Scheduled loop | Yes | `cron`-style in-process scheduler or a lock-file + `systemd`/`cron` description; GitHub Actions only described | none |
| Durable execution kill drill | SQLite checkpoint: yes. Temporal: Docker Compose (multi-service local cluster possible) | Temporal dev server | `needs-docker` |
| Tracing and dashboards | Yes | OTel SDK with JSON-lines exporter; Phoenix local (`pip install arize-phoenix`) | optional `slow` |
| Serving | Yes | FastAPI + uvicorn; Docker only for the image step | `needs-docker` |
| Managed runtimes | No | service map only | `needs-cloud` (not run) |
| Local models | Yes | Ollama (tools capability) | `needs-download` |

Local multi-node: Docker Compose for Temporal + OTel collector + Phoenix is possible (agentic-ai-15h F5/F6); no Kubernetes labs.

---

## 7. Production practice (L5) (loop-specific; stable items reused from topics/agentic-ai-15h/RESEARCH.md section 7, 2026-10-20; new items researched 2026-10-26)

Design stance for the course: a loop is production-grade when it has (1) a deterministic stop test, (2) three independent caps (turns, spend, wall-clock) plus no-progress detection, (3) a verifier that is not the maker, (4) external state so a killed run resumes, (5) a trace per iteration, (6) a human escalation exit.

### 7.1 Testing and evals as loop gates
- Two different things: (a) the loop's INTERNAL gate (verification step that decides "done" each iteration: tests, linter, type checker, Lighthouse score, schema check; model-as-judge only when no deterministic check exists; `/goal` uses a separate small evaluator model) and (b) the loop's OWN regression suite (does the loop, as a system, still converge on a golden task set after a prompt/tool/model change). Teach both.
- Internal gate rules from sources: deterministic verifiers preferred over self-grading (MLM); separate writer from checker (Osmani; Anthropic blog recommends a fresh-context reviewer e.g. `/code-review`); "done is a claim, not a proof". Reward-hacking test to include: loop that can edit the tests must be blocked from editing the verifier (deny rule / PreToolUse hook on test paths).
- Loop-level evals (reused, agentic-ai-15h s7.1-7.3): 30-100 golden tasks; deterministic end-state checks first, judge second; metrics for loops: success rate, pass^k over k=3-5 (tau-bench reliability metric), iterations-to-converge (median, p95), cost per success, no-progress rate, false-"done" rate (verifier said pass, hidden check fails). Judge calibration: label 50-100 outputs, Cohen's kappa (~0.6 minimum is blog consensus, not a standard). CI gate: plain pytest with a threshold file, or `deepeval` 4.3.1 (Task Completion, Step Efficiency, Plan Adherence, Tool Correctness, Argument Correctness), or Langfuse `langfuse/experiment-action` (raises `RegressionError`). Nightly live run through a batch API (-50%) while PR runs replay recorded model calls.
- Recorded-replay loops: deterministic tests of the CONTROL logic (stop conditions, caps, no-progress detector, escalation) with a scripted-but-real recorded model transcript; never fake model output in lessons (factory rule).
- 2026-05-08 paper: log analysis necessary for credible agent evaluation (arXiv 2605.08545, from agentic-ai-15h; not opened here) -> read the trajectory, not just the final score.
- Go deeper: tau3-bench, Inspect AI sandboxes, hill-climbing loops (analyse traces, propose harness change, re-run evals: LangChain layering above).

### 7.2 Observability and tracing of loops
- Claude Agent SDK (opened 2026-10-26, https://code.claude.com/docs/en/agent-sdk/observability): SDK has no telemetry of its own; the bundled Claude Code CLI subprocess exports OTLP. Enable: `CLAUDE_CODE_ENABLE_TELEMETRY=1` + exporters `OTEL_TRACES_EXPORTER=otlp`, `OTEL_METRICS_EXPORTER=otlp`, `OTEL_LOGS_EXPORTER=otlp`, `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`, `OTEL_EXPORTER_OTLP_ENDPOINT`; traces additionally need `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1` (traces are beta; names may change). Do NOT use the `console` exporter in the SDK (stdout is the message channel). Export defaults: metrics 60 s, traces/logs 5 s (`OTEL_*_EXPORT_INTERVAL`, lower to 1000 ms for short runs; killed process loses the buffer). Export errors fail silently unless `CLAUDE_CODE_OTEL_DIAG_STDERR=1` (Claude Code >= 2.1.179).
- Span names: `claude_code.interaction` (one turn) > `claude_code.llm_request` (model, latency, tokens), `claude_code.tool` (> `.tool.blocked_on_user`, `.tool.execution`), `claude_code.hook`. Subagent spans nest under parent's `claude_code.tool`. `session.id` attribute ties many `query()` calls into one timeline; W3C `TRACEPARENT`/`TRACESTATE` auto-injected so the agent run nests inside your app's trace. Tag: `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES="enduser.id=...,tenant.id=..."` (percent-encode values). Audit events: `claude_code.tool_decision`, `tool_result`, `safety_event` (>= 2.1.307), `mcp_server_connection`, `permission_mode_changed`. Content is OFF by default; opt-in `OTEL_LOG_USER_PROMPTS=1`, `OTEL_LOG_TOOL_DETAILS=1`, `OTEL_LOG_TOOL_CONTENT=1` (60 KB default truncation, `CLAUDE_CODE_OTEL_CONTENT_MAX_LENGTH`), `OTEL_LOG_RAW_API_BODIES`.
- Vendor-neutral side (reused, agentic-ai-15h s7.4): OpenTelemetry GenAI conventions (`github.com/open-telemetry/semantic-conventions-genai`, status Development; pin versions): `invoke_agent` > `chat` > `execute_tool`, `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.conversation.id`, `gen_ai.usage.input_tokens/output_tokens`, cache-aware `gen_ai.usage.cache_read.input_tokens`. Local UI: Phoenix (`arize-phoenix` 20.23.0). A hand-written loop must create its own spans: recommended loop-specific span/attribute set (course convention, not a standard): one span per iteration with `loop.iteration`, `loop.stop_reason`, `loop.verifier.result`, `loop.budget.remaining_usd`, `loop.no_progress_count`.
- Loop-specific signals to chart: iterations per run (histogram), stop-reason mix (success / max_turns / max_budget / no_progress / escalated / crashed), cost per run and per success, verifier pass rate by iteration number, tokens per iteration (context growth), compaction events (`compact_boundary`), time blocked on a human.
- Cost from the stream without a backend: every `ResultMessage` subtype carries `total_cost_usd`, `usage`, `num_turns`, `session_id`; `usage` covers only the main loop, use `model_usage` for whole-tree accounting incl. subagents (agent-loop docs, opened).

### 7.3 Security and guardrails for loops
- Why loops raise risk: unattended, repeated, often with write tools, and each iteration re-reads untrusted output (tool results, web pages, repo files). Reused framework (agentic-ai-15h s7): OWASP LLM Top 10 (2025; LLM10 Unbounded Consumption is the loop-cost risk), OWASP Agentic Top 10 2026 (2025-12-09; ASI08 Cascading Failures, ASI10 Rogue Agents, ASI01 Goal Hijack, ASI05 Unexpected Code Execution), Willison lethal trifecta (2025-06-16), Meta Rule of Two (2025-10-31), "The Attacker Moves Second" (2025-10-10: classifiers are noise filters not boundaries).
- Claude Agent SDK controls (opened, agent-loop docs): `allowed_tools` (auto-approve list), `disallowed_tools` (hard block), `permission_mode` in {`default`, `acceptEdits`, `plan`, `dontAsk` (headless: deny whatever would prompt), `auto` (model classifier reviews actions), `bypassPermissions` (CI/containers only; not as root; TS also needs `allowDangerouslySkipPermissions: true`)}, scoped rules like `Bash(npm *)`, `canUseTool` callback, hooks `PreToolUse` / `PostToolUse` / `UserPromptSubmit` / `Stop` / `SubagentStart` / `SubagentStop` / `PreCompact` (hooks run in your process, cost no context; a rejecting PreToolUse returns the rejection message to the model). Teaching point: unattended loops should run `dontAsk` or `acceptEdits` + allowlist inside a sandbox, never `bypassPermissions` on a dev laptop.
- Secure deployment (opened https://code.claude.com/docs/en/agent-sdk/secure-deployment): isolation ladder sandbox-runtime (bubblewrap / sandbox-exec; `@anthropic-ai/sandbox-runtime`, same-host kernel, no TLS inspection so domain fronting is possible) < Docker (`--cap-drop ALL --security-opt no-new-privileges --read-only --network none --memory 2g --cpus 2 --pids-limit 100 --user 1000:1000`, code mounted `:ro`, proxy over a mounted Unix socket) < gVisor `--runtime=runsc` (CPU-bound ~0% overhead, simple syscalls ~2x slower, heavy file I/O 10-200x slower) < Firecracker microVM (boot < 125 ms, < 5 MiB overhead, vsock to host proxy). Credential proxy pattern: agent never sees secrets; proxy (Envoy `credential_injector`, mitmproxy, Squid, LiteLLM) injects keys, enforces domain allowlist, logs; `ANTHROPIC_BASE_URL` for model calls, `HTTP(S)_PROXY` for others. Do not mount `.env`, `~/.aws`, `~/.ssh`, `.git-credentials`.
- Loop-specific guardrails to teach: (1) deterministic policy at the tool boundary (a 500-unit refund blocked in plain Python), (2) verifier files read-only to the maker, (3) approval gate for irreversible actions with real arguments shown, (4) egress allowlist, (5) kill switch checked every iteration, (6) injection set in CI measuring attack-success-rate, (7) no auto-merge: loop opens a PR, human merges (Osmani: stay the reviewer; Stripe Minions human-reviewed).
- Go deeper: CaMeL, garak 0.17, PyRIT 1.1, NeMo Guardrails, AgentDojo (versions from agentic-ai-15h; not re-verified here).

### 7.4 Reliability and recovery
- Termination design (MLM + Anthropic blog + SDK docs): testable goal; explicit exits success / failure / escalate; hard iteration cap; token or wall-clock budget; no-progress detection (same tool call + same error N times, or verifier score not improving for K iterations); recoverable error vs hard blocker classification; resume after cap ("Hit turn limit. Resume session <id> to continue" pattern in SDK docs).
- SDK mechanics (opened): `max_turns` counts tool-use turns only, default no limit; `max_budget_usd` default no limit, stop reported as ResultMessage subtype `error_max_turns` / `error_max_budget_usd`; also `success`, `error_during_execution`, `error_max_structured_output_retries`. Single-shot `query()` RAISES after yielding an error result (wrap in try). Budget is checked AFTER a response arrives so spend can overshoot by one response plus still-running subagents: leave headroom; budget includes subagents (needs Claude Code >= 2.1.217). Crash: final `error_during_execution` with possibly zeroed cost fields, `stop_reason` null; recover totals per cost-tracking docs. No top-level session wall-clock timeout and no per-subagent deadline: enforce your own (`asyncio.timeout`, `CLAUDE_ASYNC_AGENT_STALL_TIMEOUT_MS` is a stall watchdog only). Sessions: resume by `session_id`, fork; `session_store`/`SessionStore` adapter mirrors JSONL transcripts to your backend (best effort: `mirror_error` system message; transcripts only, not CLAUDE.md memory or working-dir files).
- Context failure: context accumulates; auto-compaction summarises older turns (`compact_boundary` message; `PreCompact` hook archives transcript); persistent rules belong in CLAUDE.md (re-injected each request), not the first prompt. State outside the conversation (progress file, Linear board, git) is the loop pattern's answer.
- Provider-level (reused s7.5): retry 429/5xx with backoff + jitter and `Retry-After`; per-call timeout; fallback model chain; idempotency key on every write tool; circuit breaker; tell the model when a tool failed; fault-injecting stub provider test.
- Lesson candidates: kill the process mid-loop and resume from the state file; double-apply test (idempotency); no-progress detector unit test.

### 7.5 Deployment of loops
- Self-hosting the Claude Agent SDK (opened https://code.claude.com/docs/en/agent-sdk/hosting): the SDK spawns a `claude` CLI subprocess per session that owns shell, cwd, JSONL transcripts; 1 session = 1 subprocess. Four session patterns: ephemeral (container per task, `TASK_PROMPT` env, exits; good for one-shot loops), long-running (many sessions per container, `ClaudeSDKClient` / TS `streamInput()`, pre-warm with `startup()`/`prewarm()`), hybrid (ephemeral container + `SessionStore` + `resume=session_id`), multi-agent container. Starting size 1 GiB RAM, 5 GiB disk, 1 CPU per agent; agents per host = (host RAM - overhead) / per-session peak RSS (measure it); pin sessions to a container by consistent hashing on `sessionId`. Python 3.10+ / Node 18+; native binary bundled and pinned to SDK version (semver; review changelog before minors). Outbound HTTPS to `api.anthropic.com` or Bedrock/Google endpoint; put auth at a gateway in front. Known limits: memory growth in long sessions (recycle subprocesses), wide parallel-subagent fanouts hit rate limits (batch them).
- Scheduled / event-driven loops: Claude Code `/loop` (local, stops when turned off), `/schedule` cloud routines (research preview), Codex app Automations tab (results to triage inbox; per MLM), Managed Agents scheduled deployments (cron). Generic fallback that works on a laptop: cron or systemd timer or GitHub Actions `schedule:`/event trigger running a one-shot loop with a state file and a lockfile (prevent overlapping runs).
- Managed option: Claude Managed Agents (beta header `managed-agents-2026-04-01`; opened https://platform.claude.com/docs/en/managed-agents/overview): agent (model, prompt, tools, MCP, skills) + environment (Anthropic cloud sandbox or self-hosted sandbox) + session + events over SSE; event history server-side; steer/interrupt by sending events; scheduled deployments; also on Claude Platform on AWS and Claude Models on Google Cloud. NOT eligible for Zero Data Retention or HIPAA BAA (stateful by design); sessions deletable via API. MCP tunnels and "dreaming" are limited research previews.

### 7.6 Cost and budgets per loop run
- Numbers (Claude docs, opened): token cost typically dominates container cost by an order of magnitude or more; a minimal container ~ $0.05/hour vs a single long agent session that can spend dollars in tokens (hosting page). Anthropic agents ~4x and multi-agent ~15x chat tokens; token usage explained 80% of BrowseComp variance (reused from agentic-ai-15h s6).
- Levers ranked (Anthropic loops blog + SDK docs): (1) model and `effort` ("among the biggest levers"; levels `low`, `medium`, `high`, `xhigh`, `max`; per-subagent override on `AgentDefinition`), (2) route routines to smaller faster models, expensive model for judgment, (3) scripts for deterministic work instead of reasoning again, (4) prompt caching of stable prefix (system prompt, tool defs, CLAUDE.md are cached automatically), (5) MCP tool search defers schemas (a few servers with many tools otherwise eat context every request), (6) subagents keep main context lean but multiply tokens, (7) cap turns and USD, (8) pilot dynamic workflows on a small slice ("can spawn hundreds of agents"), (9) batch API -50% for offline eval loops (doesn't stack with cache; reused).
- Monitoring: `/usage` (by skill, subagent, MCP), `/goal` shows turns and tokens, `/workflows` per-agent tokens (Anthropic blog); API-side `total_cost_usd` per run, `model_usage` per model.
- Course worked example to build (label as arithmetic): budget per run B; expected cost = iterations x (input tokens x price_in x (1 - cached share x 0.9) + output tokens x price_out); show how a no-progress loop of 30 iterations costs 30x one iteration and why caps matter. Use current prices re-verified on the lesson day (agentic-ai-15h cheap models: Gemini 3.5 Flash-Lite $0.30/$2.50 per MTok, `claude-haiku-5-5`; check again).
- Verifier cost: verification adds latency and cost; spend it where quality matters (MLM, Osmani).

### 7.7 Claude Code `/goal` and Stop hooks as the built-in verification loop (opened https://code.claude.com/docs/en/goal, 2026-10-26)
- `/goal <condition>` = a session-scoped wrapper around a prompt-based Stop hook: after every turn a small fast model (`ANTHROPIC_DEFAULT_HAIKU_MODEL`, billed on the small model, "typically negligible") reads the condition + conversation and returns Not-yet-met / Met / Impossible with a reason. The evaluator does NOT run commands or read files: the condition must be demonstrable from Claude's own output (e.g. "`npm test` exits 0"). Condition up to 4,000 characters; put a bound inside it ("or stop after 20 turns"). One goal per session; `/goal` shows condition, runtime, turns evaluated, token spend, last reason; `/goal clear` (aliases stop/off/reset/none/cancel). Headless: `claude -p "/goal ..."` runs to completion; use `--output-format stream-json --verbose` or it looks stuck. Auto mode removes per-tool prompts; `/goal` removes per-turn prompts; they are complementary.
- Built-in loop safety: no tool use for several consecutive turns -> loop stops, goal stays set; goal is cleared on errors you must fix (auth failure, exhausted credits, context overflow that auto-compaction cannot clear, model unavailable); transient errors retry up to 3 times then pause; rate limit / usage limit -> pause. Background work defers evaluation; check-ins after 30 min, then 1 h, then every 2 h (`CLAUDE_CODE_GOAL_CHECKIN_MINUTES`, 0 disables check-ins and auto-retry); at most 3 idle check-ins per goal. Goal restored on resume with turn count/timer/token baseline reset. Unavailable if `disableAllHooks` or `allowManagedHooksOnly`.
- Compare approaches table (docs): `/goal` (next turn when previous finishes; stops on evaluator verdict), `/loop` (time interval; stops when you stop it or Claude decides done), Stop hook (settings-file scope, script for deterministic checks or prompt for model checks, your logic decides).
- Production pattern from Spotify (7.8): verifiers run from the Stop hook before a PR opens; deterministic first, LLM judge second.

### 7.8 Case evidence for loop gates (opened)
- Spotify background coding agent, Part 3, 2025-12-09 (https://engineering.atspotify.com/2025/12/feedback-loops-background-coding-agents-part-3): three failure modes (no PR; PR fails CI; PR passes CI but functionally wrong = worst). Independent verifiers triggered by repo contents (Maven verifier on `pom.xml`), exposed through an MCP tool so the agent does not know the build system, regex-trimmed errors to protect context, run before PR opens (Claude Code Stop hook). LLM judge compares diff with the original prompt (catches scope creep: refactors, disabling flaky tests): vetoes ~25% of sessions, agent course-corrects ~50% of those; Spotify has no evals for the judge yet. Container: limited permissions, few binaries, almost no outside access; pushing code and Slack handled by surrounding infrastructure. No retry/turn limits stated.
- Anthropic "Effective harnesses for long-running agents", 2025-11-26 (https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents): initializer agent + coding agent per session; `claude-progress.txt` + git history as cross-session memory; JSON feature list (200+ features for a claude.ai clone) with `passes` field only editable by the agent ("unacceptable to remove or edit tests"), chosen over Markdown because models corrupt JSON less; `init.sh` starts the server; one feature per session; start-of-session ritual (read git log + progress, run a basic e2e test); end with clean mergeable commit; agents marked features done after unit tests/curl only, so browser automation (Puppeteer MCP) end-to-end testing was required. Open question: one general agent vs specialised multi-agent.
- LangChain "The Art of Loop Engineering", 2026-06-16, Sydney Runkle (https://www.langchain.com/blog/the-art-of-loop-engineering): four loops: agent (`create_agent`), verification (Deep Agents `RubricMiddleware` or `after_agent` hook; deterministic or LLM grader), event-driven (LangSmith Deployment cron + webhooks, Fleet channels), hill-climbing (LangSmith Engine analyses production traces, rewrites harness config, files issues). Gives no numbers, caps or budgets; keep humans approving sensitive calls and harness changes. Related: "Improving Deep Agents with harness engineering" 2026-02-17: harness-only changes moved coding agent from Top 30 to Top 5 on Terminal Bench 2.0 (search-result claim; the 52.8% -> 66.5% figures are from a secondary site, unverified).

## 8. Enterprise and scale (L6) (stable parts reused from topics/agentic-ai-15h/RESEARCH.md s8, 2026-10-12..20; loop-specific parts researched 2026-10-26)

Framing: for loop engineering "enterprise" means running MANY loops (hundreds of repos, tickets, tenants) unattended and safely: a scheduler/trigger layer, a worker fleet, per-run isolation and state, a verification layer, budgets, and governance. Local multi-node is possible with Docker Compose (Docker 27.5.1, Compose v5.2.0 on the VM; from agentic-ai-15h). No Kubernetes labs (pointer only; Anthropic hosting cookbook ships Docker, Modal and Kubernetes examples).

1. **Distributed architecture internals.** Loop runtime = trigger -> queue -> worker (one loop run) -> sandbox -> verifier -> state store -> trace sink. Four durability styles (reused, comparison table): A deterministic replay (Temporal: frontend, history, matching, worker, Postgres, UI; warn at 10,240 events, terminate above 51,200 -> Continue-As-New; `temporalio` 1.34.0 verified on PyPI 2026-10-26); B step checkpoints (LangGraph `thread_id` checkpointers, `langgraph` 1.2.17); C append-only session log + stateless harness (Anthropic Managed Agents; Claude Agent SDK `SessionStore`); D files + git as coordination (Anthropic progress file + feature JSON; Osmani "the agent forgets, the repo doesn't"). Agent SDK specific: 1 session = 1 `claude` CLI subprocess owning shell, cwd and JSONL transcript; state on local disk is lost on restart unless mirrored. OpenAI Agents SDK (2026-04-15 update; `openai-agents` 0.24.0): harness separated from sandbox, saved sandbox state can be resumed, several sandboxes per harness in parallel (secondary-source summaries; primary page returned 403).
2. **Cluster operations, hands-on (Compose).** Queue (Redis or Postgres `SKIP LOCKED`) + N worker containers (`docker compose up --scale worker=N`) each running ephemeral loop runs; one git worktree or container per run (Osmani worktrees); lockfile/lease so a schedule tick never overlaps a still-running run; `cwd` per session; Phoenix (`arize-phoenix` 20.26.1) for traces; LiteLLM proxy (`litellm` 1.106.4) for keys/budgets. Image tags: pin at build (not researched here). Per-agent starting size 1 GiB RAM / 5 GiB disk / 1 CPU; agents per host = (RAM - overhead) / peak RSS.
3. **Failure and recovery drill.** Kill a worker mid-iteration: lease expires, another worker resumes from the state file/`session_id`/checkpoint; Temporal alternative: kill the worker, workflow replays. Inject provider 429/503, a hung tool, a verifier that always fails (no-progress detector must stop it), a loop that deletes its own tests (verifier path read-only). Measure: stop-reason mix, cost inflation from retries, time to resume, duplicate side effects (idempotency keys). SDK facts to use: `error_during_execution` after crash with zeroed cost fields; `mirror_error` when the store write fails; budget overshoot by one response.
4. **Extreme scale.** What breaks first at 10x/100x/1000x loops: provider RPM/TPM, spend (loop = iterations x context), verifier/CI capacity (Spotify runs verifiers on existing CI; Linux x86 only so far), sandbox start time, trace volume, human review bandwidth (the real ceiling: Stripe human-reviews 1,000+ PRs/week; Osmani "comprehension debt"). Levers: batch for offline loops, route by model/effort, cache stable prefix, shrink verifier output, MCP tool search, tail-sample traces, queue back-pressure, break wide subagent fan-out into batches (hosting docs: wide fan-out hits rate limits). Managed-platform numbers (reused): AgentCore Runtime 5,000 active sessions/account, 8 h max session; Anthropic Managed Agents scheduled deployments max 1,000 per organisation, jitter up to 15% of interval (min 5 s, max 9 min). Lesson: capacity model (concurrency = runs/hour x run duration; tokens/hour vs TPM).
5. **Deployment options.** (a) your container: ephemeral per task (`TASK_PROMPT`), long-running multi-session with consistent hashing on `sessionId`, hybrid with `SessionStore`; (b) scheduler: cron / systemd / GitHub Actions / Temporal schedules / LangSmith Deployment cron + webhooks; (c) managed: Claude Managed Agents (beta, `managed-agents-2026-04-01`, cloud or self-hosted sandbox, scheduled deployments with cron `expression` + IANA `timezone`, DST literal wall-clock so avoid 1-3 AM or use UTC, pause/unpause/archive, `deployment_run` records with error types such as `session_rate_limited_error`, webhooks), Google/AWS/Microsoft runtimes (reused list in agentic-ai-15h s8.5); Claude Code `/schedule` cloud routines (research preview). Open-source vs paid: SDK, Temporal OSS, LangGraph OSS, Phoenix OSS, LiteLLM OSS vs Managed Agents / LangSmith / Temporal Cloud paid. Helm/operator = pointer only.
6. **Performance engineering.** Metrics: iterations to converge p50/p95, wall-clock per run, time blocked on verifier, tokens/iteration growth, sandbox cold start (Firecracker < 125 ms boot claim; gVisor file-I/O up to 10-200x slower), first-token latency irrelevant for headless loops. Tools: Locust/k6 against the trigger API with a stub model of configurable latency; recorded-replay benchmark of the loop's control code. No independent published loop benchmarks found.
7. **HA/DR.** Stateless workers + durable external state (Postgres/object store `SessionStore`, git remote, Temporal history); RPO = last committed state/checkpoint, RTO = lease expiry + restart; transcripts only are mirrored (CLAUDE.md memory and working-dir artifacts need a volume or object-store sync); Managed Agents sessions persist server-side but are not ZDR/HIPAA-BAA eligible; unpause does not backfill missed triggers (design catch-up explicitly); provider fallback never across regions for regulated data (reused). Walkthrough + one restore drill.
8. **Zero-downtime change.** Version prompt + tool schemas + model id + verifier + caps together (one config bundle); shadow mode (loop runs, output discarded, compare), canary on 5% of triggers, rainbow deployment (in-flight runs keep old version; Anthropic), eval gate in CI, kill switch checked each iteration; SDK pins CLI binary to package version (semver, read changelog before minors; `claude-agent-sdk` 0.2.174 released 2026-10-24: pre-1.0, so pin exact); Temporal worker versioning (Go deeper); Managed Agents agent `version` in deployment_run records; model deprecation churn (Gemini 3.5/3.7 Flash deprecated 2026-10-08: never hardcode ids). Hill-climbing loop (LangChain) as a controlled self-change with human review before deploy.
9. **Multi-tenancy.** Agent SDK shared-container isolation recipe (hosting docs): `setting_sources=[]`, `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`, per-tenant `CLAUDE_CONFIG_DIR`, per-tenant `cwd` on every `query()`, per-tenant egress rules at the proxy; `OTEL_RESOURCE_ATTRIBUTES` with `enduser.id` and `tenant.id` for attribution; per-tenant budgets via `max_budget_usd` and LiteLLM virtual keys (reused); Managed Agents deployment `budget.max_list_cost` is PER RUN (a "2000" cap = about $20 per run, not a cumulative ceiling); tenant id in cache keys (reused ASI06). Noisy neighbour: rate-limit trigger rate per tenant and cap concurrent runs per tenant.
10. **Security and compliance at org scale.** Isolation ladder and credential proxy (7.3); agent identity per run (reused Uber SPIRE SVID, STS short-lived per-hop JWTs, STS p99 < 40 ms); audit events with actor chain (`tool_decision`, `tool_result`, `safety_event`) forwarded to SIEM; managed settings (`allowManagedHooksOnly`, `disableAllHooks` interplay with `/goal`); PII redaction (content capture off by default); deletion (Managed Agents session delete API; trace erasure); permission rules by organisation policy; EU AI Act timeline and ISO/IEC 42001 / NIST AI RMF (reused, secondary-sourced: concept only, "ask counsel").
11. **Cost engineering (FinOps).** Levers ranked in 7.6; per-run cap + per-tenant cap + org cap at the gateway; budget check overshoots by one response; container cost ~$0.05/h vs tokens in dollars/session (Anthropic hosting docs); cost per successful run = total spend / successes (failed loops are the hidden cost); verifier/judge tokens are small (Claude `/goal` evaluator "typically negligible") but sub-agent verifiers are not; Anthropic ~4x/15x token multipliers.
12. **Platform and organisation patterns.** Golden-path loop template (caps + verifier + tracing + policy + state file preconfigured); shared verifier library exposed over MCP (Spotify); shared tool gateway/registry (Uber MCP Gateway, 800+ servers / 5,000+ tools, reused); a triage inbox for unresolved loop output (Osmani, Codex Automations); SLOs: success rate, iterations p95, cost per success, human-escalation rate; ownership: every scheduled loop has an owner, a kill switch and an expiry date; hill-climbing loop run by the platform team (LangChain loop 4).
13. **Frontier:** see section 9.
14. **Case studies (all opened 2026-10-26 unless noted):**
    - Spotify Honk background coding agent (verification loops, judge vetoes ~25%, course-correct ~50%): https://engineering.atspotify.com/2025/12/feedback-loops-background-coding-agents-part-3 . Volume: Part 1 title "1,500+ PRs later" (https://engineering.atspotify.com/2025/11/spotifys-background-coding-agent-part-1, title from search; not opened); later figures only via secondary sources (InfoQ, ZenML) that disagree: cite 1,500+ merged PRs only.
    - Stripe Minions (reused, opened 2026-10-20; post 2026-02-09): 1,000+ merged PRs/week, human-reviewed, devboxes ready in ~10 s with no production/internet access, deterministic steps interleaved (lint on push < 5 s, at most two CI rounds): https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents
    - Anthropic long-running harness (200+ feature JSON, progress file + git): https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
    - Anthropic multi-agent research system (2025-06-13, reused): +90.2% vs single agent, ~15x tokens, rainbow deployments: https://www.anthropic.com/engineering/multi-agent-research-system
    - LangChain docs-writing agent as a four-loop system (Slack-triggered, opens PRs after verification): https://www.langchain.com/blog/the-art-of-loop-engineering (no numbers published).
    - Uber MCP Gateway (reused): https://www.uber.com/us/en/blog/designing-mcp-gateway/
- Checklist items N/A: only "Kubernetes deployment hands-on" is N/A per LEVELS item 5 (pointer to the hosting cookbook's Kubernetes manifests). Item 4 "billions of items" maps to "thousands of concurrent loop runs and tokens/hour"; there is no storage-engine or sharding internals content, so item 1's "storage engine / write and read path" is replaced by "state store and event log". All 14 items otherwise apply.

### 8.x L6 lesson details for lessons 26a-30 (researched 2026-10-27; official pages opened, image tags checked on Docker Hub API and PyPI the same day)

**26a Durable resume (LangGraph + SQLite).**
- Packages in topic venv: `langgraph` 1.2.17, `langgraph-checkpoint` 4.3.0, `langgraph-checkpoint-sqlite` 3.1.2 (separate install). `SqliteSaver(sqlite3.connect("checkpoint.db"))` or `SqliteSaver.from_conn_string(...)`; methods present: `setup`, `get_tuple`, `list`, `put`, `put_writes`, `delete_thread`, `prune`/`aprune`, `copy_thread`. Docs recommend `SqliteSaver` for local dev and `PostgresSaver` (`langgraph-checkpoint-postgres`, `PostgresSaver.from_conn_string("postgresql://...")` then `.setup()`) for production; `MemorySaver`/`InMemorySaver` lose state on restart. Source: https://docs.langchain.com/oss/python/langgraph/checkpointers.md , https://docs.langchain.com/oss/python/langgraph/persistence
- Resume key: `{"configurable": {"thread_id": "..."}}` on every `invoke`/`stream`; with `PostgresSaver` keep `thread_id` under 255 chars (docs suggest `str(uuid7())[:255]`). Use the run id as thread_id.
- Durability: `graph.stream(..., durability="sync"|"async"|"exit")` (verified in the installed package: `Durability = Literal['sync','async','exit']`). `sync` writes each checkpoint before the next step (safest, slower); `async` (default) writes while the next step runs, small risk of losing the last checkpoint on a crash; `exit` writes only at exit/error/interrupt, so a mid-run crash loses everything. For the crash drill use `sync`. Added in langgraph 0.6.0, replaces `checkpoint_during`. Sources: checkpointers page above; mode semantics confirmed by search summary of https://docs.langchain.com/oss/python/langgraph/durable-execution (the page itself, when opened, only links to checkpointers; flag as secondary for the 0.6.0 rename).
- Pending writes: if a node fails mid-super-step, writes from nodes that finished in that step are kept and not re-run on resume. On replay, nodes after the last checkpoint re-execute, including LLM calls, API requests and interrupts: side effects need idempotency keys (the lesson's drill: count duplicate refunds = 0). `@task` exists in `langgraph.func` (verified importable); its docs page was not retrievable, so teach it only as "wrap a side effect so its result is saved" if the writer verifies in code.
- Encryption of state at rest: `EncryptedSerializer.from_pycryptodome_aes()` reads `LANGGRAPH_AES_KEY`; pass as `serde=`. Checkpoints grow unbounded: prune or set retention (`prune`).
- Deployment size: SQLite is single-writer, so one file per host/volume is fine for a lab; a fleet of workers on several hosts needs `PostgresSaver` (note, not taught hands-on).

**26b Kill switch and lease expiry (Postgres or SQLite queue).**
- Lease claim in Postgres: `SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1` inside a transaction (PostgreSQL 18.6 docs: skipped rows give "an inconsistent view of the data, so this is not suitable for general purpose work, but can be used to avoid lock contention with multiple consumers accessing a queue-like table"; applies only to row-level locks). Lease = row columns `owner`, `lease_expires_at`, `attempt`; a reaper (or the claim query itself) takes rows where `lease_expires_at < now()`. Worker renews every N s (heartbeat); lease TTL > 3x heartbeat. Source: https://www.postgresql.org/docs/current/sql-select.html . For a laptop-only lab SQLite with `BEGIN IMMEDIATE` and an `UPDATE ... WHERE lease_expires_at < ?` claim does the same (own-code, lesson `why` reason).
- Kill switch: one row/flag (`kill_all`, or per tenant/loop) read at the top of every iteration, plus `docker compose kill` of workers for the hard stop. Each scheduled loop: owner, kill switch, expiry date (section 8.12). Fail closed: if the flag store is unreachable, stop.
- Claude Agent SDK / Managed Agents numbers reused from the lite items above (session persistence, scheduled deployment jitter, unpause does not backfill).

**27 Observability and cost (OpenTelemetry + Phoenix).**
- Packages: `opentelemetry-sdk` 1.45.1 (in requirements). GenAI semantic conventions are status **Development** (experimental); only `error.type`, `server.address`, `server.port` are Stable on GenAI spans. As of v1.42.0 (2026-06-12) they live in the separate repo `open-telemetry/semantic-conventions-genai` (the old opentelemetry.io spec page is a redirect notice; repo has no tagged release, targets schema `gen-ai/1.42.0`). Source for the move: https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/ and https://github.com/open-telemetry/semantic-conventions-genai . Teach: pin your instrumentation library and record the schema you target.
- Names (SECONDARY source: Dash0 explainer, last updated 2026-09-14, https://www.dash0.com/knowledge/opentelemetry-genai-semantic-conventions-explained ; the repo's own agent-spans page could not be fetched, so the lesson should print the names it uses and say they may change): span names `invoke_agent {agent.name}`, `execute_tool {tool.name}`, `chat {model}`, `invoke_workflow {workflow.name}`, `plan {agent.name}`; `gen_ai.operation.name` in {`chat`, `invoke_agent`, `execute_tool`, `invoke_workflow`, `plan`, ...}; agent attributes `gen_ai.agent.name|id|version`; usage `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.usage.cache_read.input_tokens`; `gen_ai.conversation.id`. Prompt and completion content is opt-in (event `gen_ai.client.inference.operation.details`; env name varies by library, e.g. `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`; `OTEL_SEMCONV_STABILITY_OPT_IN` is required by newer shapes, value library-specific). Custom attributes the course adds (`loop.iteration`, `loop.stop_reason`, `tenant.id`) are ours, not in the spec: name them so.
- Run = one root span, one child span per iteration (`loop.iteration`), tool and model calls beneath. Backend: Phoenix `arizephoenix/phoenix:20.26.1` (tags `20`, `20.26`, `20.26.1` exist 2026-10-25; ports 6006 UI/OTLP HTTP, 4317 gRPC per Phoenix docs, not re-opened); or `otel/opentelemetry-collector-contrib:0.164.0` as a tail-sampling collector (tag exists 2026-10-27). In-process `InMemorySpanExporter` keeps the notebook offline.
- Cost per success = total spend / successful runs (failed loops are the hidden cost); compute from `gen_ai.usage.*` summed over spans. Gemini prices: use the section already in this file ("Gemini API prices used in lesson 02").

**28b Worker fleet in Compose.**
- Tool versions on the VM: Docker 27.5.1, Compose v5.2.0. `docker compose up --scale worker=3 --wait` (CLI value overrides the file's `scale`; `--wait` waits for running/healthy and implies detached; `--no-recreate` keeps existing containers). Source: https://docs.docker.com/reference/cli/docker/compose/up/ . Do not publish a fixed host port on a scaled service (collision): leave workers port-less.
- Image tags (Docker Hub API 2026-10-27): `postgres:18-alpine` (docs are PG 18.6; LiteLLM's own compose uses `postgres:16`, so either works; use one for both), `redis:8.8.4-alpine` (only if Redis is chosen; Postgres alone is enough for queue + leases + LangGraph checkpoints), `arizephoenix/phoenix:20.26.1`, `otel/opentelemetry-collector-contrib:0.164.0`. Workers are built from the course's own Dockerfile (`python:3.12-slim`, not tag-checked here).
- Skeleton: services `db` (healthcheck `pg_isready`), `worker` (scaled, `depends_on: db: condition: service_healthy`, env `DATABASE_URL`, `LEASE_TTL_S`, `HEARTBEAT_S`, `MAX_CONCURRENT_RUNS`, `LLM_RPM`), `api` (FastAPI, port 8000), optional `phoenix`. Drill: `docker compose kill worker` on one replica (or `docker kill <name>`), watch lease expiry, another replica claims the row. All values in `.env`; compose reads them via `env_file`/`${VAR}` (privacy rule).
- Rate limits: Gemini API limits are per **project**, not per key, across RPM, TPM (input) and RPD (daily, resets midnight Pacific); exceeding any one gives a rate-limit error (spend-based limits give `429 RESOURCE_EXHAUSTED` explicitly); tiers: Free; Tier 1 = billing linked; Tier 2 = $100 paid + 3 days; Tier 3 = $1,000 paid + 30 days; spend caps on a rolling 10-minute window (Tier 1 $10, Tier 2 $50, Tier 3 $200). Per-model RPM/TPM values are NOT on the public page: read them in AI Studio for the project (do not hardcode). Source: https://ai.google.dev/gemini-api/docs/rate-limits . Consequence for the lab: N workers share one project quota, so the 429 appears first; fleet-wide limiter (token bucket in Postgres/Redis or at the gateway) + retry with jitter. Concurrency model: runs in flight = runs/hour x duration; tokens/hour must stay under TPM x 60. The lab uses a stub model with configurable latency and a fake limit so no key is spent.

**29a Tenancy and budgets (LiteLLM proxy gateway).**
- `litellm` 1.106.4 (PyPI 2026-10-27). Image `docker.litellm.ai/berriai/litellm:main-stable` (what its own compose file uses; a pinned release tag should be read from the release page before the lab). Port 4000. Env: `LITELLM_MASTER_KEY` (proxy refuses to start without it; root credential), `LITELLM_SALT_KEY` (encrypts stored provider keys; changing it breaks them), `DATABASE_URL` (Postgres, e.g. `postgresql://user@db:5432/litellm`), `STORE_MODEL_IN_DB="True"`; healthcheck `GET /health/liveliness`; optional `--config /app/config.yaml`. Sources: https://docs.litellm.ai/docs/proxy/docker_quick_start , https://raw.githubusercontent.com/BerriAI/litellm/main/docker-compose.yml (compose file there hardcodes a DB password: ours must use `.env`).
- **Budgets need Postgres**: without a DB budgets do not cap spend ("No connected db."). Config: `litellm_settings: max_budget` (USD global), `budget_duration` (`30s|30m|30h|30d`), `max_internal_user_budget`, `internal_user_budget_duration`, `max_end_user_budget_id` (the old `max_end_user_budget` is no longer enforced). Source: https://docs.litellm.ai/docs/proxy/users
- Virtual key: `POST /key/generate` (Bearer master key) body `team_id`, `max_budget`, `budget_duration`, `tpm_limit`, `rpm_limit`, `max_parallel_requests`; several windows: `budget_limits: [{"budget_duration":"24h","max_budget":10},{"budget_duration":"30d","max_budget":100}]`; per-model `model_rpm_limit`/`model_tpm_limit` maps; per-model budget `model_max_budget` is Enterprise-only. Team: `POST /team/new` (`team_alias`, `max_budget`, `budget_duration`, `rpm_limit`, `tpm_limit`, `max_parallel_requests`); `POST /team/member_add` with `max_budget_in_team`; user: `POST /user/new`; customer budgets: `POST /budget/new` + `"user"` field in requests. Over budget returns `ExceededTokenBudget` (HTTP auth error). If a key has `team_id`, only team and team-member budgets are enforced, not the owner's personal budget. Zero-cost models (explicit 0 prices) bypass budget checks.
- Safety flags in `general_settings`: `fail_closed_budget_enforcement: true` (503 if spend cannot be verified), `fail_closed_rate_limit_enforcement: true` (503 if Redis counters unreachable), `token_rate_limit_type: input|output|total`, `disable_budget_reservation` (mitigation only; allows overspend under concurrency), `default_estimated_output_tokens` (size near p95 of observed output).
- Trap to teach: budget is checked before/after a response so a cap overshoots by one response (SDK `max_budget_usd` too; reused fact); Managed Agents `budget.max_list_cost` is per run, not cumulative (reused above). Offline fallback: a stub gateway in the notebook with the same semantics (the key/budget REST calls need `needs-docker`).

**29b Identity, audit, rollout.**
- Identity per run: attach `agent.id`/`gen_ai.agent.id` + `tenant.id` + `run_id` as span/audit attributes and as the gateway key's metadata; short-lived credentials per run (reused Uber SPIRE SVID, STS short-lived JWTs). Audit event schema (ours): `ts, run_id, tenant, actor_chain, tool, decision, result_hash, version_bundle`; append-only table; no content by default.
- Rollout: version bundle = prompt + tool schemas + model id + verifier + caps; shadow (run, discard output, compare against golden set), canary by hash of `run_id` mod 100 < 5, auto-rollback on eval-gate or stop-reason regression, in-flight runs keep their old bundle (rainbow, Anthropic). Sources reused in the lite item 8 above. Model ids from config, never hardcoded (Gemini 3.5/3.7 Flash deprecations 2026-10-08).

**30 Capstone.** Needs no new facts: composes 26a-29b. Acceptance items map to: kill drill (26b), overshoot capped (29a), injected instruction blocked (section 7), eval gate fail (section 7 / lesson 17).

**Case study key numbers (all previously opened; no new claims):** Spotify Honk 1,500+ merged PRs (Part 1 title), judge vetoes ~25%, course-correct ~50% of vetoes; Stripe Minions 1,000+ merged PRs/week, devbox ~10 s, lint < 5 s, at most 2 CI rounds; Anthropic multi-agent research +90.2% vs single agent at ~15x tokens; Managed Agents scheduled deployments max 1,000 per org, jitter up to 15% of interval (5 s min, 9 min max); AgentCore Runtime 5,000 active sessions/account, 8 h max session; Temporal warns at 10,240 history events, terminates above 51,200.

**Not verified (do not state as fact in lessons):** per-model Gemini RPM/TPM (project-specific, in AI Studio); LiteLLM pinned release tag; Phoenix port numbers; `@task` semantics; exact OTel agent-span required/recommended attribute lists (primary page not retrievable).


## 9. Frontier (last ~12 months; dated) (new items 2026-10-26; older items reused from agentic-ai-15h s9)

Loop and harness tooling
- 2025-11-26 Anthropic "Effective harnesses for long-running agents" (initializer + coding agent, feature-list JSON, progress file): the pattern most later "loop engineering" posts descend from. (opened)
- 2025-12-09 Spotify Part 3: independent verifiers + LLM judge as a stop gate. (opened)
- 2026-02-17 LangChain "Improving Deep Agents with harness engineering" (harness-only gains on Terminal Bench 2.0; numbers partly unverified). (search result)
- 2026-04-08 Anthropic Managed Agents (beta header `managed-agents-2026-04-01`); since then: scheduled deployments with per-run budgets and deployment runs/webhooks, self-hosted sandboxes, vaults, memory stores, MCP tunnels and "dreaming" (research preview). (opened overview + scheduled deployments)
- 2026-04-15 OpenAI "next evolution of the Agents SDK": model-native harness + native sandbox execution, resumable sandbox state, parallel sandboxes; Python first. (secondary coverage only; primary 403; `openai-agents` 0.24.0 on 2026-10-15)
- 2026-06-07/08 "Loop engineering" named by Steinberger and Osmani; 2026-06-16 LangChain "The Art of Loop Engineering" (agent, verification, event-driven, hill-climbing loops); 2026-06-30 Anthropic "Loop engineering: getting started with loops" (turn-based, goal-based `/goal`, time-based `/loop` and `/schedule`, proactive). (opened) Maturity: emerging practice vocabulary, no standard; sources define layers slightly differently.
- Claude Code `/goal` (evaluator-gated Stop hook, headless `-p` support, check-ins, auto-pause on rate limits) and Agent SDK additions: `max_budget_usd` that also bounds subagents (needs Claude Code >= 2.1.217), `effort` levels incl. `xhigh`, `permission_mode` `auto` and `dontAsk`, MCP tool search deferring schemas, `SessionStore` adapters (Python SDK >= 0.2.140 / TS >= 0.3.234 for `CLAUDE_CODE_PROJECT_DIR_NAME`), OTEL traces (beta, `claude_code.*` spans) with W3C trace-context propagation, `safety_event` audit events (>= 2.1.307). (opened, docs are undated: dates are the version numbers)
- Hill-climbing loops: LangSmith Engine analyses traces and files issues / rewrites harness config; extension toward RL fine-tuning for open-weight models is stated as a direction, not shipped. (LangChain post)

Durable execution
- 2026-03-23 Temporal + OpenAI Agents SDK integration GA (`temporalio-openai-agents` 1.1.0 on 2026-10-01 per agentic-ai-15h); 2026-07-16 Temporal LangGraph plugin public preview (graph = Workflow, node checkpoint, nodes as Activities via `"execute_in": "activity"` + `start_to_close_timeout`, `interrupt()` waits durably for days at no cost, Continue-As-New; needs `temporalio` >= 1.27.0, Python 3.11+ for Functional API). (opened Temporal blog; GA date from search snippet)
- Direction: durable execution becoming default for long-running loops (framework plugins for LangGraph, OpenAI Agents SDK, ADK, Pydantic AI, Mastra, Strands per Temporal's listing).

Security and governance (reused; all dated in agentic-ai-15h s9): "Attacker Moves Second" (2025-10-10), Rule of Two (2025-10-31), OWASP Agentic Top 10 (2025-12-09), EU AI Omnibus (2026-07-24), MCP spec 2026-07-28, A2A 1.0 (2026-03-12), AG-UI 1.0 (2026-09-17).

Where the field is heading (with honest confidence)
- Loops move from developer laptops (`/loop`) to scheduled/event-driven cloud runs with per-run budgets (Managed Agents, LangSmith Deployment, `/schedule`): established direction.
- Separation of maker and verifier (judge or deterministic) as the standard gate; judge calibration still immature (Spotify has no judge evals): growing.
- Trace-driven self-improvement ("hill climbing") of harnesses: emerging, mostly vendor posts.
- Human review bandwidth, not generation, is the bottleneck ("comprehension debt", "cognitive surrender"): widely stated, qualitative.
- Terminology and boundaries between harness, context and loop engineering are unsettled; teach the mechanisms (caps, verifier, state, schedule, trace), not the label.
- Do not build labs on preview features (Managed Agents beta, `/schedule`, OTEL traces beta, Temporal LangGraph plugin preview): concept lessons with Go deeper links; labs use Agent SDK / LangGraph / plain Python with recorded model calls.

## 10. Interview questions and loops (market part)

Shared market research reused: `topics/agentic-ai-6-production-v2/RESEARCH.cache-ai-engineering.md` (2026-10-16, 10 days old) and `topics/agentic-ai-15h/RESEARCH.md` section 10 (2026-10-20/26 checked). **`research_cache/ai-engineering.md` could not be written: the folder is owned by user jupyter (mode 755) and this session runs as another user.** The caller should run `cp topics/agentic-ai-6-production-v2/RESEARCH.cache-ai-engineering.md research_cache/ai-engineering.md` (it is dated 2026-10-16 inside, valid until 2027-01-14).

**Question set for this 15 h course** (loop-specific first; sources in brackets):
1. Your agent keeps calling the same tool in a loop: why, and how do you stop it? Step cap, identical-call detection, reprompt-or-bail, spend cap (iTIsys, iTI, iCl).
2. Draw the loop and its four exits: done, stuck, over budget, hand off to a human; what each does with state (secondary guides, 2026; qGH).
3. How do you know a loop is "done"? Machine-checkable goal; deterministic verifier before LLM judge; why a model grading its own work fails; how an agent can game a test (delete the assertion) and how to stop it (Osmani, IBM, Build Fast; reward hacking).
4. Design a coding agent that reads a repo, runs tests and opens a PR (iTIsys, Meta/Anthropic loops).
5. A restarted long-running loop double-charges / double-posts: idempotency keys, durable state, resume from checkpoint (iTIsys).
6. Where does loop state live and why not in the context window: progress file, JSON feature list, git, checkpointer (eHarness, Osmani).
7. Cost control for unattended loops: per-iteration and per-run budgets, cheaper model for the checker, caching, piloting on a slice (gAnthLoops, iCa).
8. Evaluate an agent trajectory, not just the answer; regression gate in CI for prompt/model changes; shadow/canary/rollback (iTIsys, iCa, iCl).
9. Prompt injection through tool output in an unattended loop; least privilege, sandbox, permission modes, approval for irreversible actions (iCl, iCa).
10. Parallel agents collide: worktrees, locks, one task per agent, merge strategy; when multi-agent is worth the cost (iAV Q27, Osmani).
11. Context growth in long loops: compaction, fresh context per iteration (Ralph) vs one long session; trade-offs (iTIsys, Agent SDK docs).
12. Observability: what to trace and log without raw PII (iAV, iTI).
13. Staff: roll out agent loops across 200 teams: gateway, identity, audit log, quotas, evals as a service, on-call for agents, comprehension debt and review bandwidth (cache section 1, Osmani).
14. Workflow vs agent vs loop: when not to build a loop (gOAI, eBEA, gAnthLoops "start with the simplest solution").
15. Behavioural: a time an automated system made a costly mistake and what you changed (STAR).
Code-yourself: bounded loop with MAX_STEPS and spend cap; validate tool args against a schema and return errors as observations; repeated-call detector; retry with backoff; mocked-tool test of the loop (iTIsys, secondary guides).
Misconceptions: a bigger model fixes an unreliable loop; "done" from the model is proof; a loop makes a weak model reliable (Build Fast with AI); more sub-agents is better; temperature 0 is deterministic; loops need a framework; retry every error.

**Interview loops by tier** (carried from the shared cache, 2026-10-16, with today's addition). Confidence: medium FAANG/labs, low-medium product companies, low GCCs.
- FAANG / AI labs: Anthropic 4-5 rounds (hiring manager 45-60; AI-collaborative coding 60-75 with Claude allowed, graded on prompt clarity, verification, decomposition; system design 60; values 45-60; reports of 8-9 rounds elsewhere); OpenAI recruiter, screen, 4-6 onsite rounds, applied design covers conversation state, moderation, token billing; Meta AI-assisted coding (60 min) plus an agentic design round ("triage tickets"); Google DeepMind mostly no AI; Amazon LeetCode plus cosine similarity (techinterview.org updated 2026-07-13, candidate reports). Today: agent system-design questions listed above come from techinterview.org (updated 2026-07-23): a one-hour discussion probing failure modes, model treated as an unreliable component.
- Top product companies / AI startups: recruiter 30; phone screen 45-60 often a live LLM-API coding exercise (implement a tool-calling loop, parse structured output); take-home 2-4 h (AI usually allowed); live debugging of "an agent that loops forever"; design around a model you do not control; behavioural (careery.pro 2026-02, techinterview.org 2026-07).
- GCCs / India: no first-hand write-up found (unverified). Planning assumption: project deep dive, one Python round that includes LLM API calls, one design round, manager and HR; LangChain/LangGraph/CrewAI named more than in US postings.

## 11. Suggested running example

**Recommended: one thread, two faces, "Brightside Outfitters" support desk (inner loop) plus "pocket-cart" repo (autonomous coding loop).**
- Why two: loop engineering is mostly seen in coding loops (Ralph, `/goal`, PR babysitting) but the broadest applied-developer audience also builds ticket/ops agents. Both start tiny, have a **mechanical success check** (order state / pytest exit 0), and scale to enterprise (tenants, budgets, schedules, approvals).
- Basic: 10-line loop on the desk (`get_order`, `calculator`), caps (turns, tokens, dollars, wall-clock), stop reasons, tool errors as observations, no-progress detector, first golden set. Pocket-cart: run tests as the verifier by hand.
- Intermediate: retries/backoff/idempotent refund, HITL approval gate, checkpoint + resume, context compaction and progress file, Ralph loop on pocket-cart (scripted model, then one live recording), maker/checker evaluator, LangGraph version with `recursion_limit`/`RemainingSteps`, Agent SDK hooks.
- Advanced/enterprise: scheduled and event-triggered loops with leases and a kill switch, durable run + kill drill (Temporal or SQLite), evals as CI gate with loop metrics, OTel traces + cost dashboards, per-tenant budgets, permission policy and injection tests, FastAPI + Docker service, managed-runtime service map, change management for model retirements.
- Alternatives: (b) research assistant (good for context/compaction, weak for side effects); (c) a "dependency upgrade bot" only on pocket-cart (great for goal loops, narrow). Pros of recommended: deterministic checks, no download, refunds make idempotency/approvals tangible. Cons: two codebases to maintain; mitigate by sharing the loop core.
- App requirement: `app/` FastAPI + UI grows v1 chat + run with caps, v2 approvals + resume, v3 traces + cost meter + tenant budgets.

---

## 12. Proposed requirements.txt and infrastructure

`>=` bounds are PyPI versions of 2026-10-26. Python 3.12.

```
anthropic>=2.3.0        # NEW MAJOR since agentic-ai-15h; read migration-2026-10-21 first
openai>=3.38.0
google-genai>=2.33.0
ollama>=0.6.3
pydantic>=2.14.1
tenacity>=9.2.1          # if pip cannot resolve with google-genai, fall back to 9.1.4 as agentic-ai-15h did
python-dotenv>=1.2.4     # not re-queried
pytest>=9.1.1
vcrpy>=8.3.0             # 9.2.0 exists (needs Python>=3.11); verify httpx2 patching before raising the bound
tiktoken>=0.14.0
numpy>=2.5.4
langgraph>=1.2.17
langgraph-checkpoint-sqlite>=3.1.2
langchain>=1.4.7
openai-agents>=0.24.0
claude-agent-sdk>=0.2.174
mcp>=2.3.0
fastapi>=0.162.0
uvicorn>=0.54.0
httpx>=0.28.1
opentelemetry-sdk>=1.45.1
ipykernel>=7.4.0         # not re-queried
rich>=15.0.0
# optional (separate files / tagged cells)
# temporalio>=1.34.0 ; arize-phoenix>=20.26.1 (Python 3.11-3.14) ; deepeval>=4.3.1 ; inspect-ai>=0.3.285
# google-adk>=2.13.0 (Python>=3.11) ; litellm>=1.106.4 ; pydantic-ai>=2.61.0 (Python>=3.11)
```
Infrastructure: Temporal dev server / Compose and OTel collector + Phoenix (reused agentic-ai-15h F5/F6; image tags not queried; researched just in time before the Advanced lessons). Git and `pytest` on PATH for the coding-loop lessons. Not needed: vector DB, Kubernetes.

---

## Suggested tracks

None: this is one 15-hour course (rule 29), not a roadmap. Do not split. Concepts owned elsewhere by the agentic-ai course (RAG, MCP/A2A internals, deep multi-agent) are Go deeper or one-line pointers here; the course owns termination, budgets, retries/recovery, HITL, harness/long-running state, evals as loop gates, coding loops, and running loops in production.

## Versions verified on PyPI JSON 2026-10-26

claude-agent-sdk 0.2.174 (2026-10-24, py>=3.10); openai-agents 0.24.0 (2026-10-15, >=3.10); langgraph 1.2.17 (2026-10-24, >=3.10); temporalio 1.34.0 (2026-09-30, >=3.10); deepeval 4.3.1 (2026-10-16, >=3.9,<4.0); litellm 1.106.4 (2026-10-25, >=3.10,<3.15); arize-phoenix 20.26.1 (2026-10-25, >=3.11,<3.15); langfuse 5.0.4 (2026-10-21, >=3.11,<4.0); opentelemetry-sdk 1.45.1 (2026-10-06, >=3.10).

## Warnings

1. `anthropic` jumped to 2.x on 2026-10-21 with breaking API/SDK changes (sampling params removed, Bearer auth, `MessageParam` union); agentic-ai-15h lessons were built on 1.15. Anything copied from there must be re-run.
2. "Loop engineering" is a 2026-06 term from blogs and vendor posts; there is no spec. Teach definitions with sources and say so (maturity `growing`).
3. OpenAI "Harness engineering" post could not be opened (HTTP 403); only snippets seen. `/goal`, `/loop`, `/schedule` are product features (research preview in places); do not build lessons that depend on running them.
4. Task budgets are beta and advisory; session budgets are Managed Agents only; Claude Code does not support task budgets.
5. Stale prior text: agentic-ai-15h RESEARCH contains scrubbed placeholders for Gemini model ids; read the model id from `.env`.
6. Not covered here (other parts): triangulation/coverage matrix, benchmarks, interview loops, enterprise lite, frontier.

- Loop-engineering terminology and its June 2026 origin story come from blogs; the course should define terms itself and cite the Anthropic / LangChain primary posts.
- Agent SDK docs pages are undated; where dates are given they are Claude Code / SDK version numbers.
- Spotify PR counts differ across secondary sources; only Part 3 (opened) is primary. OpenAI Agents SDK 2026-04-15 post could not be opened (403).
- Anthropic's SDK `max_turns` and `max_budget_usd` default to NO limit: lessons must always set them.
- Managed Agents is not ZDR/HIPAA-BAA eligible: matters for regulated-data lessons.

## 13. Sources

## Notes added while writing lessons

### Lesson 02
## Gemini API prices used in lesson 02 (checked 2026-10-27)
Source: https://ai.google.dev/gemini-api/docs/pricing (opened 2026-10-27). Standard paid tier, USD per 1M text tokens: gemini-2.5-flash-lite input 0.10, output 0.40 (not listed as deprecated; no shutdown date on the page). gemini-3.1-flash-lite 0.25 / 1.50; the course model setting (TUT_LLM_MODEL) 0.30 / 2.50. The page lists the course model setting (TUT_LLM_MODEL_LARGE) first among Flash models ($0.75 / $3.75 through 2026-12-31). Audio input costs more. The lesson uses gemini-2.5-flash-lite (llm_setup DEFAULT_MODELS) and a larger model price in Try it.

### Lesson 04
## Lesson 04 additions (checked 2026-10-27)
- Anthropic tool use, "Handle tool calls" (https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls, opened 2026-10-27): a failed client tool call is sent back as a `tool_result` with `"is_error": true`; for invalid calls (missing parameters) the doc says Claude retries 2-3 times with corrections before apologizing. Used in lesson 04 At work.

### Lesson 07
## Lesson 07 checks (2026-10-27, run in the topic venv)
- pytest 9.1.1: `pytest.ExitCode` names: 0 OK, 1 TESTS_FAILED, 4 USAGE_ERROR (a test path that does not exist returns 4). Source: the installed package.
- Use `--color=no` when parsing pytest output from a notebook kernel: the kernel forces colour codes, which hide the `FAILED` prefix.
- The notebook kernel reports a relative `sys.executable` (`./.venv/bin/python`); resolve it with `os.path.abspath`, not `Path.resolve()` (the venv is a symlink, and resolve drops the venv).
- google-genai 2.33.0: `google.genai.types.FinishReason.STOP` exists (normal end of a reply). anthropic: `Message` has a `stop_reason` field. Source: installed packages.
- Evaluation facts used in lesson 07 are already in RESEARCH.md section 7 (Spotify Part 3; Anthropic long-running harnesses; pass^k over k=3-5; CI regression gate).

### Lesson 09
## Lesson 09 checks (2026-10-27)
- Anthropic, "Loop engineering: getting started with loops" (claude.com/blog/getting-started-with-loops, published 2026-06-30, opened 2026-10-27): names four loop types, turn-based, goal-based (`/goal`, stop on "Goal achieved OR maximum number of turns reached"), time-based (`/loop` and `/schedule`) and proactive (routines from an event or schedule, no human in real time). The article says "A reviewer with fresh context is less biased", about a separate reviewer agent; it does not describe fresh context per loop iteration. Fresh context per iteration is the Ralph pattern (Geoffrey Huntley, ghuntley.com/ralph, 2026-01-17).
- pocket-cart (data/pocket-cart, generated, no outside source): 18 tests, 6 passed and 12 failing at start; the three modules money, pricing and tax have 9 tests, 6 failing.
- Recorded run (2026-10-27, default Gemini model via llm_setup): one prompt on three modules passed 9/9 with input 852 tokens; an outer loop with one fresh-context turn per module passed 9/9 with 306 to 318 input tokens per turn; one prompt on six modules passed 18/18 with input 1,785 tokens. One sample each: a single prompt passed on this model and repo.

### Lesson 10
## Lesson 10 checks (2026-10-27, opened the official docs)
- Claude Code hooks, Stop (https://code.claude.com/docs/en/hooks, opened 2026-10-27): Stop runs when the main agent has finished responding; not on a user interrupt (API errors fire StopFailure). Stop input adds `stop_hook_active`, `last_assistant_message`, `background_tasks`, `session_crons` to the common fields (`session_id`, `transcript_path`, `cwd`, `permission_mode`, `hook_event_name`). `stop_hook_active` is true when Claude Code is already continuing because of a stop hook; the docs say to check it to avoid blocking on a condition that never resolves.
- Stop decision: exit code 2 blocks (stderr is the reason Claude receives); or stdout JSON `{"decision": "block", "reason": "..."}`; omit `decision` to allow the stop. Other exit codes other than 0 or 2 without JSON are non-blocking errors (the stop goes ahead).
- Cap: after stop hooks have continued the turn eight times in a row, Claude Code overrides the next block and ends the turn; the count resets when Claude calls a tool; `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` raises it.
- Hook config shape used in lesson 10: `{"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "${CLAUDE_PROJECT_DIR}/..."}]}]}}`; `${CLAUDE_PROJECT_DIR}` appears in the docs' examples.
- `/goal` is a built-in shortcut for a session-scoped prompt-based Stop hook (docs TIP in the Stop section).
- Claude Agent SDK, Python reference (https://code.claude.com/docs/en/agent-sdk/python, opened 2026-10-27): `ClaudeAgentOptions.max_turns` (int or None, default None; "maximum agentic turns (tool-use round trips)"); `max_budget_usd` (float or None, default None; USD; client-side estimate that "can pass this value, so leave headroom"). `ResultMessage.subtype` values: success, error_during_execution, error_max_turns, error_max_budget_usd, error_max_structured_output_retries. On error_* subtypes `is_error` is True and `result` is None; `errors` holds loop-level messages. `total_cost_usd` is a client-side estimate.
- Lesson 10 is not built on the Agent SDK at run time: `claude_agent_sdk` is not installed in the topic venv; the SDK code is shown as a walkthrough with no call.

### Lesson 13
## Lesson 13 checks (2026-10-27, opened the sources; run in the topic venv)

- Stripe, idempotent requests (https://docs.stripe.com/api/idempotent_requests, opened 2026-10-27): the API saves the status and body of the first request with a given key once endpoint execution begins; retries with the same key return the saved response (including 500s). Keys can be removed automatically after they are at least 24 hours old; a reused key whose parameters differ is an error. Keys up to 255 characters; avoid personal data in keys; random V4 UUIDs suggested for the client. Applies to all POST requests in v1.
- Gemini API troubleshooting (https://ai.google.dev/gemini-api/docs/troubleshooting, opened 2026-10-27): retry only transient errors (429, 408, 5xx; 503 is UNAVAILABLE); do not retry 400, 402, 403; start near 1 s and roughly double; add random jitter; define a maximum number of attempts. The official Python SDK retries transient errors automatically, up to four times, with delays capped near 60 s.
- AWS Architecture Blog, "Exponential Backoff And Jitter" (https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/; published 2015-03-04, updated May 2023): Full Jitter is one variant evaluated; with 100 contending clients the jittered approach reduced the call count by more than half. Formula is in an image; lesson 13 states it as a random wait between 0 and min(cap, base * 2^attempt).
- tenacity: the venv has 9.1.4, which requirements.txt pins (>=9.1.4,<9.2) because of the google-genai resolver note; wait_exponential_jitter(initial=1, max=..., exp_base=2, jitter=1) and retry(retry=retry_if_exception_type, stop=stop_after_attempt, wait=..., before_sleep=..., reraise=True) verified by introspection; RetryCallState.next_action.sleep is available inside before_sleep.
- langchain-core Runnable.with_retry(retry_if_exception_type, wait_exponential_jitter, stop_after_attempt=3) and Runnable.with_fallbacks(fallbacks, exceptions_to_handle) exist (verified by introspection, langchain-core in the venv). langchain-google-genai 4.4.2 ChatGoogleGenerativeAI has fields `timeout` and `max_retries` (verified by introspection).

## Lesson 13 fix checks (2026-10-27, re-checked the official pages and the pinned packages in the topic venv)

- Stripe, idempotent requests (https://docs.stripe.com/api/idempotent_requests): "you can remove keys from the system automatically after they're at least 24 hours old"; "The idempotency layer compares incoming parameters to those of the original request and errors if they're not the same". The header is `Idempotency-Key`. Lesson 13 now says Stripe "may delete a key once it is at least 24 hours old" and "returns an error when a reused key comes with different parameters".
- AWS Architecture Blog, "Exponential Backoff And Jitter" (https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/): the page names "Full Jitter" and says "In the case with 100 contending clients, we've reduced our call count by more than half." The formula itself is in an image; the lesson states it in words (random wait between 0 and the capped exponential step). The "2015, updated 2023" dates were dropped from the lesson.
- Gemini API troubleshooting (https://ai.google.dev/gemini-api/docs/troubleshooting): retry transient errors (429, 408, 5xx), not 400/402/403; exponential backoff; first retry about 1 s; add jitter; the official SDKs retry automatically. The docs summary for the Python SDK says "up to four times"; the pinned client disagrees (see next item), so the lesson does not state the number of SDK retries.
- Pinned `langchain-google-genai` 4.4.2 (verified in the venv source, `chat_models.py` and `_common.py`): `ChatGoogleGenerativeAI.max_retries` defaults to 6 (alias `retries`) and is passed as `HttpRetryOptions(attempts=max_retries)`. Setting `max_retries=1` disables retries (the source says `0` means the SDK default, 5 retries).
- `google-genai` 2.33.0 (`types.py`): `HttpRetryOptions.attempts` is "Maximum number of attempts, including the original request." So the client's `max_retries` of 6 means six attempts in total, and 4 tenacity tries x 6 client attempts can send up to 24 requests for one failed step. Lesson 13 prints `max_retries` in step 5 (6 in the recorded run).
- tenacity 9.1.4 (verified in the venv source): `wait_exponential_jitter` waits `min(initial * exp_base**(n-1) + random.uniform(0, jitter), max)`. With the lesson's settings (initial 0.2, jitter 0.2) the waits are about 0.2, 0.4, 0.8 s plus up to 0.2 s. The recorded run printed 0.25, 0.54 and 0.94 s. This is a different rule from the AWS "Full Jitter" formula.

### Lesson 15
## Lesson 15 checks (2026-10-27, run in the topic venv and the recorded run)
- langchain-core 1.7.0: `trim_messages(messages, *, max_tokens, token_counter, strategy="last", allow_partial=False, end_on=None, start_on=None, include_system=False, ...)`; `token_counter` takes a callable, a model, or "approximate". `count_tokens_approximately` is in `langchain_core.messages.utils` (chars / 4 plus a per-message allowance). Source: installed package.
- langchain-google-genai 4.4.2: the reply's `usage_metadata` carries `input_tokens`, `output_tokens` and `input_token_details={"cache_read": n}` (n from `cached_content_token_count`). Source: installed package, chat_models.py.
- `langchain.agents.middleware` (summarization) is not in the topic venv: the umbrella `langchain` package is not installed, so compaction is hand-written in lesson 15 (`hand_code: topic`).
- Recorded run (2026-10-27, gemini-2.5-flash-lite via get_llm, 5 model calls): input tokens 376 (turn 1), 739 (turn 2), 1,106 (turn 3, full chat), 814 (compaction call), 411 (turn 3 after compaction). Cache reads 0 in all five. One sample only.
- In the same recording the model's compaction summary said the money tests still failed; pytest showed them passing after turn 1. Summaries are claims and need the verifier.
- Claude Haiku 5.5 cache-read price used in At work: 0.01 per MTok against 0.10 input (RESEARCH.md section 1, pricing line; not re-opened today).
## Lesson 15 caching fixes (2026-10-27, official docs opened)
- Gemini implicit caching: "enabled by default for all Gemini 2.5 and newer models"; no configuration. Minimum input tokens listed: 2,048 for Gemini 2.5 Flash and 2.5 Pro (4,096 for Gemini 3.x and 4 Argon). Hits reported in `usage.total_cached_tokens`. Source: https://ai.google.dev/gemini-api/docs/caching
- Claude prompt caching: enable with a `cache_control` marker: automatic (top-level `cache_control: {"type": "ephemeral"}`) or explicit breakpoints on content blocks. Prefix order: tools, system, messages, up to the marked block; hits need 100% identical segments. Minimum cacheable length 512 tokens for Haiku 5.5. `input_tokens` excludes cache reads: total = `cache_read_input_tokens` + `cache_creation_input_tokens` + `input_tokens`. Changing any block at or before the breakpoint breaks the hit. Default lifetime 5 minutes. Source: https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- LangChain (langchain-google-genai in the topic venv): Gemini `cache_read` = `cached_content_token_count`, reported in `input_token_details` and not added to `input_tokens` (so it sits inside the prompt count). Source: installed package, chat_models.py.
- Lesson 15 recording: 0 cache reads in 5 calls; prompts 376 to 1,106 tokens, below the 2,048 minimum listed for 2.5 Flash/Pro (the lesson's model is gemini-2.5-flash-lite; its minimum is not listed on the page read).

### Lesson 17
## Lesson 17 checks (2026-10-27, run in the topic venv)
- pytest 9.1.1: `pytest.ExitCode` names used by the notebook (TESTS_FAILED for exit 1). Source: installed package.
- pytest: `-p no:cacheprovider` keeps the gate from writing `.pytest_cache`; `--rootdir` pins the rootdir when the test runs from another folder. Source: installed package (pytest 9.1.1).
- llm_replay: `cassette_dir()` is relative to the process cwd (`cwd.parent / data / llm_cassettes`) unless `TUT_CASSETTE_DIR` is set. A test run in a subfolder must set it to an absolute path (learned in this build).
- pass^k (tau-bench reliability metric): per task with n runs and c passes, C(c,k)/C(n,k); averaged over tasks. Source: RESEARCH.md section 7.1 (tau-bench).

### Lesson 16
## Lesson 16 checks (2026-10-27, opened the official docs; run in the topic venv)
- Agent SDK hooks (code.claude.com/docs/en/agent-sdk/hooks, opened 2026-10-27): `ClaudeAgentOptions(hooks={"PreToolUse": [HookMatcher(matcher=..., hooks=[cb])]})`; callback `(input_data, tool_use_id, context)`; input has `hook_event_name`, `tool_name`, `tool_input`; deny is `hookSpecificOutput` with `hookEventName`, `permissionDecision: "deny"`, `permissionDecisionReason`; `{}` allows. Matchers match the tool name only; for MCP tools the name is `mcp__<server>__<action>`. Hooks may not fire when `max_turns` ends the session.
- Agent SDK skills (code.claude.com/docs/en/agent-sdk/skills, opened 2026-10-27): `.claude/skills/<name>/SKILL.md`; loaded through `setting_sources` (`"project"`, `"user"`); metadata at startup, full content when invoked; `skills="all"` or a list of names; `allowed_tools` for pre-approval.
- claude-agent-sdk 0.2.174 (PyPI JSON, 2026-10-27): requires Python >=3.10. Installed in the topic venv under the lock. Exports `create_sdk_mcp_server`, `tool`, `HookMatcher`, `ClaudeAgentOptions` (fields `max_turns`, `max_budget_usd`, `hooks`, `skills`, `setting_sources`, `mcp_servers`). Constructing the options needs no key.

### Lesson 18
## Lesson 18 checks (2026-10-27, run in the topic venv)
- google-genai `APIError` carries an integer `code` (the HTTP status). The loop's retry predicate reads `code` for 429, 500, 502, 503 and 504. Source: installed package google-genai (APIError signature `code: int`).
- tenacity `retry_if_exception`, `stop_after_attempt`, `wait_exponential_jitter`, `reraise=True`: as used in lesson 13. Source: installed package tenacity 9.1.1.
- pytest `-p no:cacheprovider`, `--color=no`, `-rf` summary lines `FAILED <node> - <reason>`: as used in lessons 11 and 17. Source: pytest 9.1.1 in the topic venv.

### Lesson 22
## Lesson 22 checks (2026-10-27, run in the topic venv with langgraph 1.2.17 and langgraph-checkpoint-sqlite 3.1.2)
- `interrupt()` re-runs its node from the first line on resume: a probe graph showed the paused node executing once more on each `Command(resume=...)`, while the node before it did not run again. Sources: the executed lesson 22 notebook; section 8 "26a Durable resume" notes on pending writes (LangGraph persistence docs).
- A new `SqliteSaver` connection and a new compiled graph resume the same `thread_id` from the same file (lesson 22, step 4). Source: executed notebook.
- `recursion_limit` is a top-level config key. At limit 8 the run stops with `GraphRecursionError: Recursion limit of 8 reached without hitting a stop condition`. A run that resumes after an interrupt starts its step count again; holds are capped by a counter in state, not by `recursion_limit`. Source: executed notebook and probe.
- Resuming without `thread_id` raises `ValueError: Checkpointer requires one or more of the following 'configurable' keys: thread_id, checkpoint_ns, checkpoint_id`. Source: executed notebook.
- `RemainingSteps` (from `langgraph.managed`) is read in a node through a `TypedDict` field of that type; the give-up route ran at 6 polls with `recursion_limit=8` and a check at fewer than 3 steps left. Source: executed notebook.

### Lesson 23
## Lesson 23 checks (2026-10-27, Meta Rule of Two opened; run in the topic venv)
- Meta, "Practical AI agent security" (https://ai.meta.com/blog/practical-ai-agent-security/, dated 2025-10-31): Rule of Two. Until prompt injection can be reliably detected and refused, an agent should hold no more than two of: (A) processing untrusted input, (B) accessing sensitive systems or private data, (C) changing state or communicating externally. If a task needs all three: a fresh session or supervision such as human approval.
- Recorded run (langchain-core 1.7.0, langchain-google-genai 4.4.2, Gemini via llm_setup): the model followed a planted "SYSTEM NOTICE" in a note and asked for a 500 USD refund on a 120 USD order when every tool was bound; with only the read tool bound it still asked for issue_refund (with the key `amount`), which the grant check denied. 4 model calls in total.

### Lesson 26a
## Lesson 26a checks (2026-10-27, installed langgraph 1.2.17 and langgraph-checkpoint-sqlite 3.1.2 in the topic venv; run in the notebook)
- `durability` is accepted by `invoke` and `stream`; its values are `sync`, `async`, `exit` (`langgraph.types.Durability`). The default is `"async"` (langgraph/pregel/main.py, docstring: "defaults to `"async"`"). Lesson 26a passes `durability="sync"` in the worker.
- `InMemorySaver` (`langgraph.checkpoint.memory`) keeps state only in the process: a new instance sees no thread (`{}`). Lesson 26a prints this.
- A worker killed with SIGKILL after its ledger write exits with code -9; the checkpoint still names `refund` as the next node; a new process with the same `thread_id` resumes from it, and `check` does not run again (executed notebook, 26a).
- `insert or ignore` with a unique key returns rowcount 0 on the repeat; the resumed `refund` node then writes nothing (executed notebook, 26a). Without a key (uuid per try) the same drill writes two refunds, 240 USD (executed notebook, Common mistakes cell).
- `get_state_history(config)` lists checkpoints newest first with `metadata["step"]` and `next`; `invoke(None, {**snapshot.config, "recursion_limit": 10})` replays from that checkpoint (executed notebook, 26a).
- Sources: https://docs.langchain.com/oss/python/langgraph/checkpointers.md and https://docs.langchain.com/oss/python/langgraph/persistence (RESEARCH section 8, 26a); Stripe idempotent requests (see the lesson 13 checks above).

### Lesson 26b
## Lesson 26b checks (2026-10-27, Gemini rate-limit page opened; run in the topic venv with the recorded model calls)
- Gemini API rate limits (https://ai.google.dev/gemini-api/docs/rate-limits): limits apply per project, not per API key. The page says a spend-based limit returns `429 RESOURCE_EXHAUSTED`; exceeding RPM, TPM or RPD "will trigger a rate limit error" (the page does not tie the 429 code to RPM/TPM/RPD). Lesson 26b says only this.
- Lease and kill-switch timings in lesson 26b (TTL 2.0 s, heartbeat 0.5 s, iteration pause 0.2 s, cap 12 iterations) are lab settings of our own worker, not provider or library numbers.
- PostgreSQL SKIP LOCKED caveat (inconsistent view; queue-like tables only): taken from RESEARCH section 8.x (26b), already quoted from https://www.postgresql.org/docs/current/sql-select.html; not re-opened in this lesson run.
- Managed Agents does not backfill missed triggers on unpause: RESEARCH section 8 item 7 (reused).
- Lesson 26b drill results (executed, replay): C-21 cancel stopped it at its next check; the global switch stopped C-30 with 0 further iterations after the read; the lease expired after the SIGKILL; one takeover as attempt 2; one refund (120 USD); the stale attempt-1 write was refused; a switch read once ran 10 iterations (raises as the Common mistakes cell shows).

## Lesson 25 checks (2026-10-28, opened the Anthropic multi-agent research page twice; run in the topic venv)
- Quote, verbatim, same sentence (section "Benefits of a multi-agent system"): "For instance, most coding tasks involve fewer truly parallelizable tasks than research, and LLM agents are not yet great at coordinating and delegating to other agents in real time." Used in lesson 25 as "most coding tasks involve fewer truly parallelizable tasks than research" and "not yet great at coordinating and delegating to other agents in real time".
- Also verbatim on the same page: "agents typically use about 4× more tokens than chat interactions"; "multi-agent systems use about 15× more tokens than chats"; "outperformed single-agent Claude Opus 4 by 90.2% on our internal research eval".
- Also on the page: "some domains that require all agents to share the same context or involve many dependencies between agents are not a good fit for multi-agent systems today" (not quoted in lesson 25).
- Source: https://www.anthropic.com/engineering/multi-agent-research-system

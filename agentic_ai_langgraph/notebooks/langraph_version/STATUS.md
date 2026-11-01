# LangGraph version: status

All 38 lessons and the six track overviews are built. Each lesson was checked three ways:

- **Replay:** the notebook runs offline with no key, from its recording (or with no model calls at all).
- **Live:** lessons that call the model were recorded with the key in `.env`, using the course's model.
- **Quality:** no text fallbacks (every flowchart renders), no unexpected error cells (deliberate errors are caught and print only their message), and the privacy check passes.

Last full check: **44 of 44 notebooks pass offline**; **76 flowcharts and figures** render; **0 text fallbacks**; the privacy check passes on 90 files.

Versions: langgraph 1.2.16, langchain-core 1.6.12, mcp 2.3.0, fastmcp 4.1.1, a2a-sdk 1.2.3, langchain-google-genai 4.4.2.

| Lesson | Notebook (folder) | Model calls | Figures | Notes |
|---|---|---|---|---|
| Overview 01 Foundations | 01_foundations/00_overview | 0 | 1 | |
| 01 Why agentic AI | 01_foundations/01_why-agentic-ai | 3 | 4 | |
| 02 First model call | 01_foundations/02_first-model-call | 2 | 1 | the recording's request URL holds the model name |
| 03 Tokens, context, sampling | 01_foundations/03_tokens-context-sampling | 2 | 2 | |
| 04 Structured output and tools | 01_foundations/04_structured-output-and-tools | 4 | 3 | |
| Overview 02 Single agent | 02_single_agent/00_overview | 0 | 1 | |
| 05 Agent loop by hand | 02_single_agent/05_agent-loop-by-hand | 4 | 2 | |
| 06 Tools that work | 02_single_agent/06_tools-that-work | 2 | 2 | |
| 07 Eval and safety | 02_single_agent/07_eval-and-safety | 2 | 3 | the scripted baseline scores 12 of 30 |
| 08 Checkpoint: order assistant | 02_single_agent/08_checkpoint-order-assistant | 2 | 2 | four checks |
| 09 Memory | 02_single_agent/09_memory | 2 | 2 | the store refuses card numbers |
| 10 RAG and agentic RAG | 02_single_agent/10_rag-and-agentic-rag | 3 | 4 | one chunk per embedding request |
| 11 Why a graph | 02_single_agent/11_why-a-graph | 3 | 2 | the loop loses its messages; the graph resumes |
| 12 Choosing a framework | 02_single_agent/12_choosing-a-framework | 6 | 3 | calls counted by the recorder |
| 13 Human approval gate | 02_single_agent/13_human-approval-gate | 1 | 1 | moved from the earlier variant |
| 14 Checkpoint: single desk | 02_single_agent/14_checkpoint-single-desk | 3 | 2 | five checks, all pass |
| Overview 03 Design patterns | 03_design_patterns/00_overview | 0 | 1 | |
| 15 Chaining and routing | 03_design_patterns/15_chaining-and-routing | 5 | 3 | the chain's check misses an invented claim; kept as a teaching example |
| 16 Parallelization | 03_design_patterns/16_parallelization | 3 | 2 | verdicts are pass or fail only |
| 17 Orchestrator and evaluator | 03_design_patterns/17_orchestrator-and-evaluator | 8 | 1 | moved from the earlier variant |
| 18 Control patterns | 03_design_patterns/18_control-patterns | 5 | 2 | moved from the earlier variant |
| Overview 04 Agents and protocols | 04_agents_and_protocols/00_overview | 0 | 1 | |
| 19 Agent as a service | 04_agents_and_protocols/19_agent-as-a-service | 1 | 1 | |
| 20 Agent discovery | 04_agents_and_protocols/20_agent-discovery | 0 | 1 | |
| 21 Agent registry | 04_agents_and_protocols/21_agent-registry | 0 | 1 | |
| 22 MCP: server, client, LangGraph | 04_agents_and_protocols/22_mcp-server-and-client | 2 | 2 | the bridge to LangChain is written in the lesson |
| 23 MCP discovery | 04_agents_and_protocols/23_mcp-discovery | 2 | 1 | the descriptions alone do not decide the choice |
| 24 MCP registry, gateway, auth | 04_agents_and_protocols/24_mcp-registry-gateway-auth | 0 | 2 | a poisoned description is flagged |
| 25 A2A: serve an agent | 04_agents_and_protocols/25_a2a-serve-agent | 0 | 2 | local server in a background thread |
| 26 A2A discovery | 04_agents_and_protocols/26_a2a-discovery | 0 | 1 | |
| 27 A2A registry and delegation | 04_agents_and_protocols/27_a2a-registry-delegation | 0 | 2 | names the gaps |
| 28 A2A task lifecycle | 04_agents_and_protocols/28_a2a-task-lifecycle | 0 | 1 | input-required, failed, canceled |
| Overview 05 Multi-agent | 05_multi_agent/00_overview | 0 | 1 | |
| 29 Why multi-agent | 05_multi_agent/29_why-multi-agent | 8 | 1 | one agent 2 calls; router plus specialists 6 |
| 30 Supervisor and hand-offs | 05_multi_agent/30_supervisor-and-handoffs | 7 | 2 | |
| 31 Failure modes and guards | 05_multi_agent/31_failure-modes-and-guards | 0 | 1 | scripted: the guards stop the loop |
| Overview 06 Production | 06_production/00_overview | 0 | 1 | |
| 32 Evals in CI | 06_production/32_evals-in-ci | 0 | 1 | pytest gate: exit 0, 1, then 0 |
| 33 Observability | 06_production/33_observability | 2 | 3 | trace table and flowchart from spans |
| 34 Security and guardrails | 06_production/34_security-and-guardrails | 2 | 1 | 10 of 10 refund attempts blocked |
| 35 Reliability and durable runs | 06_production/35_reliability-and-durable-runs | 0 | 1 | kill drill: exit 3, then paid once |
| 36 Cost and latency | 06_production/36_cost-and-latency | 2 | 1 | cache, route, cap |
| 37 Serving and enterprise map | 06_production/37_serving-and-enterprise | 0 | 2 | three replicas, canary |
| 38 Capstone: the desk in production | 06_production/38_capstone-support-desk | 3 | 2 | seven release checks; release approved |

## Open items

1. **MCP adapter.** `langchain-mcp-adapters` 0.3.2 needs `mcp` below 2.0, and the course uses `mcp` 2.3.0. No adapter release supports `mcp` 2.x. Lesson 22 bridges the tools to LangChain in about ten lines. Revisit when the adapter supports `mcp` 2.x.
2. **`scripts/` is read-only for this user** (owned by another user). Needed:
   - `build_notebook.py`: write `src/langraph_version/<track>/x.py` to `notebooks/langraph_version/<track>/x.ipynb`. The lessons are built next to their source and moved.
   - `run_notebook.py` and `check_lesson.py`: find recordings for lessons in track folders. The track recordings are in `notebooks/langraph_version/data/llm_cassettes/`, where the kernel looks.
3. **Model-name check.** The original course notebooks and their earlier recordings still contain the model name, which the privacy check flags. The new notebooks are clean, apart from the request URL inside lesson 02's recording.
4. **Earlier `_langraph` variants.** The variants of old lessons 12, 13 and 14 now live in the track folders as lessons 17, 18 and 13. The three variant files in `notebooks/` are kept as they were.
5. **Localhost services.** Lessons 22 to 28 and 37 start servers on localhost. Each starts on a free port and is stopped at the end of its lesson.

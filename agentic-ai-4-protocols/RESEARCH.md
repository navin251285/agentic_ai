# Research — Agentic AI 4: Protocols — MCP, A2A, AG-UI

Slug `agentic-ai-4-protocols`. Researched 2026-10-11. Everything below was read on an official page, PyPI/npm/GitHub API, or checked by running code on this VM (Python 3.12.13, scratch venvs). Items I could not confirm are marked **UNVERIFIED**. Where sources disagree it is said in the text.

Sections: 1 Snapshot · 2 Docs map · 3 Core concepts · 4 Current vs deprecated · 5 Ecosystem · 6 Runs on a laptop (incl. record/replay findings) · 7 Production (L5) · 8 Enterprise (L6) · 9 Frontier · 10 Interview questions · 11 Running example · 12 requirements + infra · 13 Sources · 14 **Source syllabus check**.

---

## 1. Snapshot

**Installed in `.venv` (2026-10-11, Python 3.12.13):** mcp 2.3.0 · fastmcp 4.1.0 · a2a-sdk 1.2.2 · ag-ui-protocol 1.0.0 · ag-ui-langgraph 0.0.47 · langchain 1.4.4 (`langchain.mcp` beta) · langchain-google-genai 4.4.1 · langgraph 1.2.14 · openai-agents 0.23.1 · Authlib 1.8.0 · PyJWT 2.15.1 · uvicorn 0.54.0 · httpx 0.28.1 · vcrpy 8.3.0. Node v26.4.0 for the Inspector. `llm_replay.py` here sets `ignore_localhost=True`.

**Re-check 2026-10-12 (one day after the Snapshot): no spec revision, major version or package change.** PyPI/npm/GitHub re-queried: mcp 2.3.0, fastmcp 4.1.0, a2a-sdk 1.2.2, ag-ui-protocol 1.0.0, ag-ui-langgraph 0.0.47, langchain 1.4.4, langgraph 1.2.14, langchain-google-genai 4.4.1, anthropic 1.13.0, openai 3.29.0 (2026-10-11), openai-agents 0.23.1, google-genai 2.29.0, Inspector 2.10.1, @ag-ui/core 1.0.2, @a2a-js/sdk 1.3.0 are all unchanged. MCP spec repo: latest tag still 2026-07-28; commits since 10-07 are docs only (Governance WG charter 10-08, Inspector `mcpdo` docs, Linux listed for Claude Desktop, TS quickstart `serveStdio`). MCP blog newest post is the roadmap (2026-08-22); roadmap still "Last updated 2026-08-22". A2A newest GitHub release v1.0.1 (2026-05-28). Keycloak 26.8.0 (2026-10-01) is latest. AG-UI integration packages published 2026-10-09..12: `@ag-ui/aws-strands` 1.0.0, `ag_ui_adk` 0.9.0, `@ag-ui/mastra` 2.0.0 (moved to AG-UI 1.0: interrupts only via `RUN_FINISHED` interrupt outcome and `RunAgentInput.resume`). Sources: PyPI/npm/GitHub APIs, https://modelcontextprotocol.io/development/roadmap, https://www.keycloak.org/securing-apps/mcp-authz-server.

### 1.1 Protocol revisions and governance

| Thing | Current | Date | Source |
|---|---|---|---|
| MCP spec | **2026-07-28** ("Current"); previous Final: 2025-11-25, 2025-06-18, 2025-03-26, 2024-11-05; a `draft` also exists | released 2026-07-28 | modelcontextprotocol.io/specification/versioning; blog.modelcontextprotocol.io/posts/2026-07-28/ |
| MCP roadmap | "Last updated 2026-08-22" | | modelcontextprotocol.io/development/roadmap |
| A2A spec | **1.0.0** (earlier 0.3.0, 0.2.6, 0.1.0); GitHub release **v1.0.0 = 12 Mar 2026**, **v1.0.1 = 26/28 May 2026** (header says 28 May, changelog says 2026-05-26) | | github.com/a2aproject/A2A/releases |
| AG-UI spec | **1.0** (docs have `spec/1.0` and `spec/draft`); `ag-ui-protocol` 1.0.0 on PyPI 2026-09-17; `@ag-ui/core` 1.0.2 | | docs.ag-ui.com/llms.txt; PyPI; npm |
| AP2 | **v0.2.0** released 28 Apr 2026; v0.1.0 = 2025-09-16 | | github.com/google-agentic-commerce/AP2/releases |
| Agent Skills | open format, no version number on the pages read | | agentskills.io/specification |
| AGENTS.md | living format, no versioned spec | | agents.md |

Governance (read carefully, it changed):
- **Agentic AI Foundation (AAIF)**, a Linux Foundation directed fund, announced **2025-12-09** with founding projects MCP (Anthropic), goose (Block), AGENTS.md (OpenAI). Platinum: AWS, Anthropic, Block, Bloomberg, Cloudflare, Google, Microsoft, OpenAI (LF press release). aaif.io/projects lists six projects today: **MCP, goose, AGENTS.md, agentgateway, A2A, Agent Router**.
- **A2A**: donated by Google to the Linux Foundation 2025-06-23 (Google Open Source Blog, 2026-04-16); **joined AAIF as a Growth Stage project on 2026-08-27** (a2a-protocol.org blog). A Technical Steering Committee with AWS, Cisco, Google, IBM Research, Microsoft, Salesforce, SAP, ServiceNow maintains it. "150+ organisations" is from the LF press release of 2026-04-09; the Google blog of 2026-04-16 says "over 100 technology companies" (sources differ; quote the LF number with its date).
- **MCP**: "Model Context Protocol a Series of LF Projects, LLC"; Lead Maintainers David Soria Parra and Den Delimarsky; Core Maintainers Peter Alexander, Caitie McCaffrey, Kurtis Van Gent, Clare Liguori, Paul Carleton, Nick Cooper; membership is per person, not per company (modelcontextprotocol.io/community/governance). AAIF Technical Committee chair is David Soria Parra.
- **AG-UI**: MIT, born from CopilotKit's partnership with LangChain and CrewAI, bi-weekly working group run via CopilotKit; **not** listed in AAIF projects; no formal governance model on the pages read (github.com/ag-ui-protocol/ag-ui, 16.5k stars).
- **AP2**: Google donated AP2 to the **FIDO Alliance** on 2026-04-28 together with Mastercard's Verifiable Intent; FIDO formed an Agentic Authentication TWG (chairs CVS Health, Google, OpenAI) and a Payments TWG (chairs Mastercard, Visa) (fidoalliance.org).
- **AGNTCY**: Cisco donated to the Linux Foundation 2025-07-29 (The Register / Outshift); site says "a Series of LF Projects, LLC" with TSC from Cisco, Dell, Google, Oracle, Red Hat. Outshift says it became "a foundational component" of AAIF in Dec 2025, but aaif.io/projects does not list it (conflict, **UNVERIFIED**).
- **Agent Skills**: originally developed by Anthropic, released as an open standard (agentskills.io), GitHub `agentskills/agentskills`; not on the AAIF project list.

### 1.2 Packages (PyPI JSON API / npm, queried 2026-10-11)

| Package | Version | Released | Python / Node | Notes |
|---|---|---|---|---|
| `mcp` (official SDK) | **2.3.0** (v2.0.0 = 2026-07-28; 2.1.0 08-24; 2.2.0 09-07; 2.3.0 10-02). `mcp` 1.30.0 = 1.x maintenance (security fixes only) | 2026-10-02 | >=3.10 | `pip install mcp` now gives 2.x. Pin `mcp>=1.28,<2` to stay on v1. Depends on new `mcp-types` 2.3.0 and `httpx2` |
| `fastmcp` | **4.1.0** (metapackage → `fastmcp-slim[client,server]==4.1.0`) | 2026-10-08 | >=3.10 | standalone project (gofastmcp.com); requires `mcp>=2,<3` and `httpx2` |
| `a2a-sdk` | **1.2.2** | 2026-10-05 | >=3.10 | implements A2A 1.0 with a 0.3 compat mode; extras `http-server fastapi grpc telemetry encryption postgresql mysql sqlite sql all` |
| `ag-ui-protocol` | **1.0.0** | 2026-09-17 | >=3.9 | import as `ag_ui.core`, `ag_ui.encoder` |
| `ag-ui-langgraph` | 0.0.47 | 2026-10-08 | >=3.10,<3.15 | needs `langgraph<2`, `langchain>=1.2` |
| `copilotkit` (Python) | 0.1.96 | 2026-08-26 | >=3.10,<3.15 | optional |
| `langchain-mcp-adapters` | 0.3.2 (2026-08-06) — **ARCHIVED 2026-09-17, caps `mcp<2`, do not teach** | | | replaced by `langchain.mcp` (below) |
| `langchain` | **1.4.4** (`langchain[mcp]` extra → `fastmcp>=4.0.11,<5`) | 2026-10-08 | >=3.10 | `langchain.mcp.MCPAdapter` is **beta** (emits `LangChainBetaWarning`), needs `langchain[mcp]>=1.4.0` |
| `langgraph` | 1.2.14 | 2026-10-06 | >=3.10 | |
| `langchain-google-genai` | **4.4.1** | 2026-10-10 | >=3.10 | Gemini via LangChain |
| `google-genai` | 2.29.0 | 2026-10-07 | >=3.10 | Vertex client init is now `genai.Client(enterprise=True, project=..., location=...)` per README ("Gemini Enterprise Agent Platform"); `vertexai=True` + api_key still works (used by `llm_setup.py`, tested today) |
| `anthropic` | 1.13.0 | 2026-10-09 | >=3.10 | `anthropic.lib.tools.mcp` helpers (`mcp_tool`, `async_mcp_tool`, `mcp_message`, …) work with mcp v1 and v2; extra `anthropic[mcp]`; depends on `httpx2` |
| `openai` | 3.29.0 | 2026-10-11 | >=3.10 | |
| `openai-agents` | 0.23.1 | 2026-10-02 | >=3.10 | supports `mcp>=1.19,<3`; with v2, `params["auth"]`/`httpx_client_factory` take `httpx2` types |
| `vcrpy` | **8.3.0** | 2026-07-04 | >=3.10 | patches httpx **and httpx2** (verified, 6.2) |
| `httpx2` | 2.13.1 | | | Pydantic's fork "next generation HTTP client"; used by mcp v2, fastmcp 4, anthropic, openai |
| `uvicorn` / `starlette` / `fastapi` | 0.54.0 / 1.7.0 / 0.143.0 | | >=3.10 | |
| `authlib` / `pyjwt` | 1.8.0 / 2.15.1 | | | for a dev authorization server / token verification |
| `agntcy-app-sdk` | 0.5.5 | 2026-04-09 | **>=3.12** | optional, AGNTCY |
| `a2a-inspector` (PyPI) | 0.1.0 | 2025-07-10 | >=3.13 | stale on PyPI; repo `a2aproject/a2a-inspector` **UNVERIFIED** |
| `@modelcontextprotocol/inspector` (npm) | **2.10.1** | 2026-10-08 | **Node >=22.19.0** | VM has Node 26.4 |
| `@modelcontextprotocol/sdk` (npm) | 1.32.1 | | | TypeScript SDK |
| `@a2a-js/sdk` | 1.3.0 | | | |
| MCP Registry (GitHub) | v1.8.1 | 2026-08-06 | | **preview**; "not designed for self-hosting" |
| agentgateway | v1.6.0 | 2026-10-02 | | LF/AAIF; Apache-2.0 |
| kind / helm | v0.33.0 / v4.3.0 | 2026-08-26 / 2026-09-09 | | VM has `docker`, `kubectl`, `node`, `npx`; **no `kind`, no `helm`** |
| Keycloak image | `quay.io/keycloak/keycloak:26.8.0` (tags 26.8, 26.8.0, 26.7.5 …) | | | see 8.10 |

Minimum Python: 3.10 for every package above; use **3.12** (kit venvs are 3.12.13; `agntcy-app-sdk` needs >=3.12, `a2a-inspector` PyPI wheel >=3.13).

**Co-install test (done):** one venv with `mcp==2.3.0 a2a-sdk==1.2.2 ag-ui-protocol==1.0.0 vcrpy==8.3.0 "langchain[mcp]==1.4.4" langchain-google-genai==4.4.1 langgraph==1.2.14 anthropic==1.13.0 openai==3.29.0 openai-agents==0.23.1 fastapi uvicorn python-dotenv` resolved with no conflicts (fastmcp 4.1.0, google-genai 2.29.0, httpx2 2.13.1). `langchain-mcp-adapters==0.3.2` + `mcp==2.3.0` does **not** resolve (`ResolutionImpossible`).

### 1.3 LLM-centric snapshot (model ids, prices, SDK support)

Model ids and prices are those already checked on 2026-10-11 in `topics/agentic-ai-7-advanced-agents/RESEARCH.md` §1.3 (same day; I did not re-open the pricing pages). The kit's `llm_setup.py` CATALOG matches. **Verified by me today:** `init_chat_model("gemini-3.1-flash-lite", model_provider="google_genai", vertexai=True, api_key=$GOOGLE_CLOUD_API_KEY)` makes real tool-calling and streaming calls.

| Provider | Lesson model | $ in / out per 1M | Alternates |
|---|---|---|---|
| Google (default, Vertex via `GOOGLE_CLOUD_API_KEY`) | `gemini-3.1-flash-lite` | 0.25 / 1.50 | `gemini-3.5-flash-lite` 0.30/2.50; `gemini-3.8-flash` 0.75/3.75 until 2026-12-31 then 1.50/7.50 |
| Anthropic | `claude-haiku-5-5` | from 0.10 / 0.50 | `claude-sonnet-5-5` 2/10 (no `temperature` on current Claude) |
| OpenAI | `gpt-6-luna` | 0.10 / 0.50 | `gpt-6.1-sol` 2/10 |
| Ollama | `qwen2.5:7b` | free | tool calling quality is modest |

SDK support for what this track needs (all verified by running or by official docs):
- **Tool calling / structured output / streaming:** `langchain-google-genai` 4.4.1 (`bind_tools`, `astream` verified); Anthropic and OpenAI SDKs all support the three.
- **MCP tools → LangChain model:** `langchain.mcp.MCPAdapter` (beta) — verified end to end (6.1).
- **MCP → vendor SDKs:**
  - Anthropic: (a) client-side helpers `anthropic.lib.tools.mcp.async_mcp_tool(tool, session)` for `tool_runner`; (b) **MCP connector** in the Messages API (beta header `mcp-client-2025-11-20`; `mcp_servers=[{type:"url", url, name, authorization_token}]` + `tools=[{"type":"mcp_toolset","mcp_server_name":...}]`; server must be publicly reachable over HTTP (Streamable HTTP or SSE), local stdio not supported; tools only; the older `mcp-client-2025-04-04` is deprecated) — platform.claude.com/docs/en/agents-and-tools/mcp-connector.
  - OpenAI: Responses API `tools=[{"type":"mcp","server_label","server_url","require_approval","allowed_tools","authorization","tunnel_id","defer_loading"}]`; approval items `mcp_approval_request` → `mcp_approval_response`; Streamable HTTP or SSE; local servers need "Secure MCP Tunnel"; `connector_id` deprecated for models released after 2026-09-01. Agents SDK: `MCPServerStdio`, `MCPServerStreamableHttp`, `MCPServerSse` (deprecated transport), `HostedMCPTool`, `create_static_tool_filter`, `cache_tools_list`, `require_approval`.
  - Google: Gemini API docs show remote MCP via the Interactions API (`client.interactions.create(..., tools=[{"type":"mcp_server","name":..,"url":..}])`, Streamable HTTP only, no hyphen in server names). The SDK pattern `GenerateContentConfig(tools=[mcp_client_session])` is documented as **experimental** and **FAILED in my test** with google-genai 2.29.0 on both `mcp` 1.30 and 2.3.0: `TypeError: cannot pickle '_asyncio.Task/Future'` from `config.model_copy(deep=True)` in `models.generate_content` (Vertex express-key client). Do not teach it; use LangChain `bind_tools` (6.1) or hand-convert MCP tools to function declarations.

---

## 2. Official docs map (coverage checklist)

### 2.1 MCP — modelcontextprotocol.io (versioned: docs/ and specification/ for 2026-07-28, 2025-11-25, 2025-06-18, 2025-03-26, 2024-11-05, draft)

Docs (2026-07-28) `/docs/2026-07-28/…`:
- getting-started/intro — What is MCP
- learn/architecture · learn/server-concepts · learn/client-concepts · learn/versioning
- develop/connect-local-servers · develop/connect-remote-servers · develop/build-with-agent-skills · develop/build-server · develop/build-client · develop/clients/client-best-practices · sdk
- tutorials/security/authorization · tutorials/security/security_best_practices · tutorials/security/local-server-security (new)
- tools/inspector (+ inspector/web, cli, tui, mcpdo, configuration, authorization, protocol-eras, recipes, security) · tools/debugging
- examples (Example Servers)

Specification (2026-07-28) `/specification/2026-07-28/…`:
- index · changelog ("Key Changes") · deprecated (registry of deprecated features) · architecture/index
- basic/index (overview, `_meta`, error codes) · basic/versioning
- basic/patterns: index · **mrtr** (Multi Round-Trip Requests) · **subscriptions** · cancellation · progress
- basic/transports: index · stdio · streamable-http
- basic/authorization: index · authorization-server-discovery · client-registration · security-considerations
- client: roots · sampling · elicitation (the first two Deprecated)
- server: index · **discover** · prompts · resources · tools · utilities/caching · completion · logging (Deprecated) · pagination
- schema (reference)

Extensions `/extensions/…`: overview · client-matrix · apps/overview · apps/build · auth/overview · auth/oauth-client-credentials · auth/enterprise-managed-authorization · tasks/overview · skills/overview.
Registry `/registry/…`: about · quickstart · faq · package-types · remote-servers · authentication · versioning · github-actions · moderation-policy · registry-aggregators · terms-of-service.
SEPs `/seps/…` (index of ~50; the ones this track needs: 414 OTel trace context, 985 PRM/RFC 9728, 990 enterprise IdP policy, 991 CIMD, 1024 local server install security, 1036 URL elicitation, 1046 client credentials, 1577 sampling with tools, 1686 → 2663 Tasks, 1865 MCP Apps, 2106 JSON Schema 2020-12, 2127 Server Cards (Final, Extensions track), 2133 Extensions, 2207 refresh tokens, 2243 HTTP headers, 2322 MRTR, 2468 `iss`, 2549 TTL, 2567 sessionless, 2575 stateless, 2577 deprecate Roots/Sampling/Logging, 2596 lifecycle policy, 2640 Skills ext).
Community `/community/…`: governance, contributor-ladder, sep-guidelines, feature-lifecycle, sdk-tiers, security, working groups (agents, file-uploads, filesystems, governance, infrastructure, inspector-v2, interceptors, registry, sdk, server-card, skills-over-mcp, transports, triggers-events) and interest groups (auth, enterprise, enterprise-managed-authorization, financial-services, primitive-grouping, scientific-computing, security, tool-annotations). Roadmap: `/development/roadmap`.
Python SDK docs `py.sdk.modelcontextprotocol.io`: Get started (installation, first-steps, real-host, testing) · Servers (tools, structured output, resources, URI templates, prompts, completions, media, handling errors) · Inside your handler (Context, Dependencies, Lifespan, Elicitation, Multi-round-trip, Sampling and roots, Progress, Cancellation, Logging, Subscriptions) · Running (ASGI mount, Deploy & scale, Authorization, OpenTelemetry, Legacy clients) · Clients (callbacks, transports, OAuth, identity assertion, session groups, subscriptions, caching) · Protocol versions · Deprecated · Advanced (low-level Server, pagination, middleware, header parameters, extensions, MCP Apps, skills) · Troubleshooting · Migration guide · API ref (`mcp`, `mcp_types`).
FastMCP docs gofastmcp.com: Getting started, Servers, Clients, Apps, `llms.txt`.

### 2.2 A2A — a2a-protocol.org/latest
- Home (key features, MCP relationship, non-goals, governance, Apache-2.0)
- Documentation: `/topics/what-is-a2a/` · `a2a-and-mcp` · `key-concepts` · `life-of-a-task` · `agent-discovery` · `enterprise-ready` · `streaming-and-async` · `multi-tenancy`
- Extensions: `/topics/extensions/` · `custom-protocol-bindings` · `extension-and-binding-governance`
- Specification: `/specification/` (data model in `spec/a2a.proto`; §4 objects, §4.5 security schemes, §7 security, §8 Agent Card incl. 8.2 discovery, 8.4 signing, 8.6 caching, §9 JSON-RPC, §10 gRPC, §11 HTTP+JSON, §12 custom bindings, §13 security considerations) · `/whats-new-v1/` · `/definitions/`
- Resources: `/sdk/` (Python API ref `/sdk/python/api/`; repos a2a-python, a2a-go, a2a-java, a2a-js, a2a-dotnet, a2a-rs) · Tutorials `/tutorials/python/1-introduction … 8-next-steps` (setup, agent skills & card, agent executor, start server, interact, streaming & multi-turn) · DeepLearning.AI course
- Community: `/community/`, `/roadmap/`, `/partners/` · Blog (2026-08-27 AAIF post; 2026-10-01 A2A CLI `github.com/a2aproject/a2a-cli`)
- Samples: `github.com/a2aproject/a2a-samples` (helloworld, langgraph currency agent)
- **Warning:** tutorial step 7 still shows the old `A2AStarletteApplication` API while step 5 uses `create_agent_card_routes` + `create_jsonrpc_routes` — the docs are internally inconsistent; follow step 5/6 (and my verified code in 6.2).

### 2.3 AG-UI — docs.ag-ui.com (index at /llms.txt)
- Overview/introduction · MCP, A2A and AG-UI (`agentic-protocols`) · Migrating to 1.0 · Production support · Integrations · Support
- Quickstart: applications · introduction (new integrations) · server · middleware · clients
- Concepts: architecture · events · agents · middleware · messages · metadata · reasoning · state · **interrupts** · serialization · tools · subagents · capabilities · generative-ui-specs
- Drafts: overview · generative UI · meta events
- Development: What's New · Roadmap · Contributing · Tutorials (Cursor, Debugging)
- **Specification 1.0** (`/spec/1.0/…`): index · changelog · architecture · basic (event model, run-input, metadata, capabilities, patterns: streaming / snapshots / interrupt-resume, transports: **HTTP+SSE**, **HTTP+Protobuf**, processing model, versioning) · events (lifecycle, text-messages, tool-calls, reasoning, state, activity, subagents, passthrough) · schema-files · schema; parallel `/spec/draft/`
- SDKs: TypeScript (core, client: AbstractAgent/HttpAgent/middleware/subscriber/compaction, `@ag-ui/encoder`, `@ag-ui/proto`) · **Python** (core overview/types/multimodal/events; encoder overview) · .NET (abstractions, client, hosting). Other languages listed on the README: Kotlin, Go, Dart, Java, Rust, Ruby, C++.
- External: AG-UI Dojo (dojo.ag-ui.com), A2UI (generative-UI spec that works with AG-UI).

### 2.4 Others
- AP2 (ap2-protocol.org; repo google-agentic-commerce/AP2) — roles, Checkout/Payment mandates (open/closed), Human-Present/Not-Present flows, A2A/MCP extension, UCP integration guide.
- AGENTS.md (agents.md) — format, nesting rule, supported tools list.
- Agent Skills (agentskills.io): overview, specification, quickstart, client showcase, `skills-ref validate`.
- AGNTCY (agntcy.org): Agent Directory, OASF, Identity, SLIM, Observability SDK, Evaluation SDK, Secure Runtime, AgentBridge (A2A).
- agentgateway (agentgateway.dev: standalone + Kubernetes docs).

---

## 3. Core concepts (complete-course checklist)

**Why protocols / the three interfaces**
- M×N integration problem; MCP = agent↔tools/data (vertical), A2A = agent↔agent (horizontal, opaque peers), AG-UI = agent↔user app; A2UI/MCP Apps = what the UI renders.
- Tool vs agent decision: expose as MCP tool when it is a deterministic, schema'd function you control; as A2A agent when it plans, takes minutes, needs multi-turn clarification, or belongs to another team/vendor and must stay opaque.
- JSON-RPC 2.0 basics: requests, notifications, results, errors, ids; why a protocol rather than function calling.

**MCP core**
- Roles: host, client (one per server), server; model-controlled tools vs app-controlled resources vs user-controlled prompts.
- Stateless protocol (2026-07-28): no `initialize`, no `Mcp-Session-Id`; each request carries `_meta` keys `io.modelcontextprotocol/protocolVersion`, `…/clientInfo`, `…/clientCapabilities`, `…/logLevel`; result `_meta` `…/serverInfo`; `resultType` ("complete" | "input_required" | "task"); `server/discover` (mandatory for servers); `UnsupportedProtocolVersionError`; protocol eras (legacy handshake ≤2025-11-25 vs modern).
- Primitives: tools (name rules 1–128 chars `[A-Za-z0-9_.-]`, `title`, `description`, `inputSchema`/`outputSchema` JSON Schema 2020-12 default, `annotations` — **untrusted unless server trusted**, `icons`, `structuredContent`, `isError`, protocol error vs tool-execution error), resources (URIs, templates RFC 6570, subscriptions, annotations audience/priority), prompts, completion, pagination (cursor), caching (`ttlMs`, `cacheScope` public|private on list/read results), deterministic tool ordering.
- Server→client needs: **elicitation** (form + URL mode), sampling, roots — now delivered by **Multi Round-Trip Requests**: server returns `InputRequiredResult{resultType:"input_required", inputRequests, requestState}`; client retries with new JSON-RPC id plus `inputResponses` and echoed `requestState`; `requestState` is attacker-controlled → MUST be integrity-protected (HMAC/AEAD) if it influences authz/business logic; supported only on `tools/call`, `resources/read`, `prompts/get`.
- Subscriptions: `subscriptions/listen` (one long-lived POST response stream; opt-in `toolsListChanged`, `promptsListChanged`, `resourcesListChanged`, `resourceSubscriptions`; ack + `io.modelcontextprotocol/subscriptionId`).
- Progress, cancellation (close the SSE stream = cancel on HTTP; `notifications/cancelled` only on stdio), logging (deprecated; stderr / OpenTelemetry instead), OTel trace context in `_meta` (`traceparent`, `tracestate`, `baggage`, SEP-414).
- Transports: stdio (newline-delimited JSON-RPC; credentials from env, not OAuth), **Streamable HTTP** (single endpoint, POST only; `Accept: application/json, text/event-stream`; `MCP-Protocol-Version`, `Mcp-Method`, `Mcp-Name` headers must match body → `HeaderMismatch` -32020; `x-mcp-header` → `Mcp-Param-*`; Origin validation MUST → 403; bind localhost; SSE not resumable; `X-Accel-Buffering: no`; GET/DELETE → 405), HTTP+SSE (deprecated), error-code allocation (-32020…-32099 reserved for spec).
- Extensions framework (SEP-2133): `{vendor-prefix}/{name}` ids, `extensions` in capabilities, off by default, graceful degradation, `ext-*` and `experimental-ext-*` repos. Official: **Tasks** (`io.modelcontextprotocol/tasks`: `CreateTaskResult{taskId,status,ttlMs,pollIntervalMs}`, `tasks/get`, `tasks/update`, `tasks/cancel`, states working / input_required / completed / failed / cancelled, `notifications/tasks` over `subscriptions/listen`; `tasks/list` and blocking `tasks/result` removed), **MCP Apps** (`io.modelcontextprotocol/ui`; tool `_meta.ui.resourceUri` → `ui://` resource, mime `text/html;profile=mcp-app`, sandboxed iframe + postMessage JSON-RPC `ui/…`, `_meta.ui.csp`/`permissions`; spec 2026-01-26; supported by Claude, Claude Desktop, VS Code Copilot, M365 Copilot, goose, Postman, MCPJam, Archestra), **OAuth client credentials**, **Enterprise-Managed Authorization** (ID-JAG), **Skills over MCP**; Server Cards (SEP-2127 Final; card at `<streamable-http-url>/server-card`, AI Catalog at `/.well-known/ai-catalog.json`; no tools in the card).
- Registry: `server.json`, reverse-DNS names (`io.github.user/server`, `com.example/server`), DNS/GitHub verification, package types, remote servers, aggregators, moderation; **public servers only** (private → run your own registry implementing the OpenAPI); in **preview**.
- Tooling: Inspector 2.x (web / `--cli` / `--tui` / `mcpdo`), `mcp dev server.py`, in-memory `Client(server)`, conformance suite, SDK tiers (Tier 1: TypeScript, Python, Go, C#; Rust beta).

**MCP authorization (Enterprise item 10 core)**
- MCP server = OAuth 2.1 resource server; client = OAuth 2.1 client; AS separate or co-hosted. Auth OPTIONAL; HTTP only; stdio uses environment credentials.
- Normative building blocks: OAuth 2.1 draft-13, RFC 6750 bearer, RFC 8414 AS metadata (+OIDC discovery), **RFC 9728 Protected Resource Metadata (servers MUST)**, **RFC 8707 resource indicators (clients MUST send `resource` in authorize AND token requests)**, PKCE S256 (client MUST refuse if `code_challenge_methods_supported` absent), **Client ID Metadata Documents** (HTTPS-URL `client_id`; SHOULD) > pre-registration; **DCR (RFC 7591) now Deprecated**, RFC 9207 `iss` validation MUST, `application_type` in DCR, credentials bound to issuer.
- Flow: POST without token → `401` + `WWW-Authenticate: Bearer resource_metadata="…", scope="…"` → fetch PRM → pick AS → AS metadata → client registration → authorization code + PKCE + `resource` → token → `Authorization: Bearer` on **every** request (never in the query string).
- Scopes: challenge `scope` is authoritative; fallback `scopes_supported`; runtime `403 insufficient_scope` + `scope=` + `resource_metadata`; step-up = union of old and new scopes; retry limits; scope minimization (no `*`/`all`; don't publish every scope in `scopes_supported`).
- Server MUST validate audience (token issued for this server), MUST NOT accept or pass through other tokens (token passthrough forbidden); for upstream APIs the server is a separate OAuth client with its own token.
- Refresh tokens: public clients MUST rotate; `offline_access` guidance (SEP-2207); short-lived access tokens.
- Attacks: confused deputy (proxy + static client id + DCR + consent cookie → per-client consent, exact redirect-URI match, `__Host-` cookies, state single-use ≤10 min), token passthrough, SSRF during discovery (block 10/8, 172.16/12, 192.168/16, 127/8, 169.254/16, fc00::/7, fe80::/10; egress proxy e.g. Smokescreen; DNS pinning), state-handle hijacking (sessionless MCP: bind handle to verified user), local server compromise (consent + sandbox for one-click installs), OAuth authorization-URL injection (`javascript:` etc.), stdio proxy escalation, mix-up (RFC 9207), localhost redirect impersonation with CIMD, scope inflation.
- Enterprise-managed authorization (ID-JAG): client logs in to enterprise IdP, exchanges ID token for an **Identity Assertion JWT Authorization Grant**, presents it to the MCP AS for an access token — no per-server consent screen; central policy and revocation.
- Roadmap: DPoP, workload identity federation (SEP-1933), RFC 8693 token exchange, IETF WIMSE, Agent Identity WG (forming).

**A2A core (v1.0)**
- Opaque agents; Agent Card (identity, `supportedInterfaces[]` {url, protocolBinding JSONRPC | GRPC | HTTP+JSON, protocolVersion, tenant}, `capabilities` {streaming, pushNotifications, extendedAgentCard}, skills {id,name,description,tags,examples,inputModes,outputModes}, `securitySchemes`/`security`, `signatures`), discovery at `/.well-known/agent-card.json` (RFC 8615), registries (no standard registry API), direct config; ETag/Cache-Control; **extended (authenticated) card** via `GetExtendedAgentCard`.
- **Signed cards:** JWS (RFC 7515) over RFC 8785 JSON canonicalization, `signatures` excluded from the canonical form; SDK helpers `a2a.utils.signing.create_agent_card_signer` / `create_signature_verifier(key_provider, algorithms)`; `A2ACardResolver.get_agent_card(signature_verifier=…)`.
- Operations (identical names in JSON-RPC and gRPC): `SendMessage`, `SendStreamingMessage`, `GetTask`, `ListTasks` (cursor, pageSize 1–100), `CancelTask`, `SubscribeToTask`, `Create/Get/List/DeleteTaskPushNotificationConfig`, `GetExtendedAgentCard`. REST paths without `/v1` (e.g. `POST /message:send`).
- Task states (`TaskState`): `TASK_STATE_UNSPECIFIED, SUBMITTED, WORKING, COMPLETED, FAILED, CANCELED, REJECTED, INPUT_REQUIRED, AUTH_REQUIRED` (terminal: completed, failed, canceled, rejected; interrupted: input_required, auth_required). Verified in the SDK enum.
- Message (`messageId, contextId, taskId, role ROLE_USER|ROLE_AGENT, parts, referenceTaskIds`), `Part` (one of `text | raw | url | data`, `mediaType`, `filename`; no `kind`), Artifact (results go in artifacts, not messages), `contextId` groups turns, `returnImmediately`, `historyLength`.
- Streaming `StreamResponse` = one of task | message | statusUpdate | artifactUpdate; push notifications (webhook gets StreamResponse; SSRF validation exists in SDK `push_url_validator`); multi-tenancy `tenant`; versioning header `A2A-Version`, extensions header `A2A-Extensions`; errors via `google.rpc.Status`+`ErrorInfo` (`domain: a2a-protocol.org`); OAuth flows: auth-code (PKCE), client-credentials, device-code (implicit/password removed); mTLS, API key, HTTP, OIDC schemes.
- Python SDK 1.x mental model: types are **protobuf messages** (`a2a_pb2.AgentCard`); `AgentExecutor.execute/cancel(context: RequestContext, event_queue: EventQueue)`; `TaskUpdater`; `DefaultRequestHandler(agent_executor, task_store, agent_card, extended_agent_card)`; `InMemoryTaskStore` (and DB stores, `a2a/server/cluster/` for multi-replica); routes `create_agent_card_routes`, `create_jsonrpc_routes`, `create_rest_routes`, FastAPI routes; client `create_client(agent=card, client_config=ClientConfig(streaming=…))`, `client.send_message(SendMessageRequest(...))` async iterator; helpers `a2a.helpers.new_text_message / new_text_part / new_task_from_user_message / get_message_text`; client auth interceptors in `a2a.client.auth`.

**AG-UI core (1.0)**
- Event-based, transport-agnostic; HTTP+SSE reference binding (POST `RunAgentInput` → `text/event-stream`; no resumption, no `Last-Event-ID`, retry = new run; errors before stream = HTTP status, errors after = `RUN_ERROR`, never infer success from 200) and HTTP+Protobuf binding.
- Events: lifecycle `RUN_STARTED, RUN_FINISHED(outcome success|interrupt, result), RUN_ERROR, STEP_STARTED, STEP_FINISHED`; text `TEXT_MESSAGE_START/CONTENT/END/CHUNK`; tools `TOOL_CALL_START/ARGS/END/RESULT/CHUNK`; state `STATE_SNAPSHOT, STATE_DELTA (JSON Patch), MESSAGES_SNAPSHOT`; activity `ACTIVITY_SNAPSHOT/DELTA`; subagents `SUBAGENT_STARTED/FINISHED/ERROR`; reasoning `REASONING_START/MESSAGE_START/MESSAGE_CONTENT/MESSAGE_END/MESSAGE_CHUNK/END/ENCRYPTED_VALUE` (the 0.x `THINKING_*` removed in 1.0.0); `RAW`, `CUSTOM`; draft `META_EVENT`. Wire type strings are UPPER_SNAKE_CASE; docs headings use PascalCase. Python classes verified: `RunStartedEvent … SubagentStartedEvent …`.
- **Interrupts / human approval:** `RUN_FINISHED{outcome:{type:"interrupt", interrupts:[{id, reason: tool_call|input_required|confirmation, message, toolCallId, responseSchema, expiresAt}]}}`; client resumes on the same `threadId` with `resume:[{interruptId, status: resolved|cancelled, payload}]`; partial resumes unsupported; replay of resume must be safe; LangGraph opt-in via `emit_interrupt_outcome`.
- Frontend tools, shared state, capabilities, middleware, serialization/compaction, `RunAgentInput{threadId, runId, state, messages, tools, context, forwardedProps, resume?}`, `protocolVersion` declared on `RUN_STARTED`, A2UI/MCP Apps for generative UI. Clients: CopilotKit, terminal, Slack/Teams, React Native.

**Neighbours**
- AGENTS.md (nearest file wins; chat prompt overrides; 60k+ repos), Agent Skills (`SKILL.md` frontmatter: `name` ≤64 `[a-z0-9-]` = dir name, `description` ≤1024, optional `license`, `compatibility` ≤500, `metadata`, experimental `allowed-tools`; progressive disclosure ≈100 tokens metadata → <5000 tokens body (<500 lines) → on-demand `scripts/ references/ assets/`; `skills-ref validate`), Skills over MCP extension.
- AP2: user→agent delegation via signed **mandates** (Checkout Mandate, Payment Mandate; each "open" = constraints, "closed" = specific authorization), Human-Present vs Human-Not-Present, credential provider, merchant; extension of A2A and MCP; FIDO TWGs; "60+ payments orgs" (LF release).
- AGNTCY: Agent Directory + OASF (agent descriptions), identity, SLIM (secure low-latency messaging), observability/evaluation SDKs, AgentBridge.
- Gateways/registries for governance: agentgateway (LF/AAIF; MCP federation, A2A, JWT/API-key/OAuth, CEL RBAC, OpenTelemetry; standalone or Kubernetes Gateway API), Agent Router (AAIF, Envoy based), AWS "MCP Gateway & Registry" (Apache-2.0, 2026-06-17), Uber MCP Gateway, Cloudflare Workers.

---

## 4. Current APIs vs deprecated / renamed

| Old way | Current way | Since | Source |
|---|---|---|---|
| `initialize` / `notifications/initialized` handshake, `Mcp-Session-Id` | per-request `_meta` (version, capabilities, clientInfo); `server/discover` | spec 2026-07-28 | spec changelog (SEP-2575/2567) |
| Server→client requests (`elicitation/create`, `sampling/createMessage`, `roots/list`) | MRTR: `InputRequiredResult` + retry with `inputResponses`/`requestState` | 2026-07-28 | changelog (SEP-2322) |
| GET stream, `resources/subscribe`/`unsubscribe` | `subscriptions/listen` | 2026-07-28 | changelog |
| `ping`, `logging/setLevel`, `notifications/roots/list_changed` | removed; `io.modelcontextprotocol/logLevel` in `_meta`; stderr/OTel | 2026-07-28 | changelog |
| Roots, Sampling, Logging | **Deprecated** (≥12 months): tool params / resource URIs; call the LLM provider directly; stderr/OTel | 2026-07-28 | SEP-2577, deprecated registry |
| SSE `Last-Event-ID` resumability | removed; re-issue request with new id | 2026-07-28 | changelog |
| HTTP+SSE transport (2024-11-05) | Streamable HTTP | deprecated since 2025-03-26; Deprecated state 2026-07-28 | SEP-2596 |
| Experimental Tasks in core (`tasks/result`, `tasks/list`) | `io.modelcontextprotocol/tasks` extension: `tasks/get`, `tasks/update`, `tasks/cancel`, unsolicited handles | 2026-07-28 | SEP-2663 |
| Dynamic Client Registration (RFC 7591) | Client ID Metadata Documents (HTTPS URL client_id) | 2026-07-28 (DCR deprecated) | auth spec, PR #2858 |
| no `iss` check | validate RFC 9207 `iss` before redeeming code | 2026-07-28 | SEP-2468 |
| resource-not-found `-32002` | `-32602` | 2026-07-28 | changelog |
| `HeaderMismatch -32001` etc. | `-32020…` allocation (-32021 MissingRequiredClientCapability, -32022 UnsupportedProtocolVersion) | 2026-07-28 | changelog |
| Python `from mcp.server.fastmcp import FastMCP` | `from mcp.server import MCPServer` (module `mcp.server.mcpserver`) | mcp 2.0.0 (2026-07-28) | py.sdk migration guide; verified import |
| `ClientSession` + `streamablehttp_client` + `initialize()` | `async with Client(url \| StdioServerParameters \| server_obj)`; `streamable_http_client(url, http_client=httpx2.AsyncClient(...))` | mcp 2.0 | migration guide / transports page |
| `McpError`, `e.error.message` | `MCPError`, `e.message` | mcp 2.0 | migration guide |
| `inputSchema`/`isError` field names in Python | snake_case (`input_schema`, `is_error`); wire stays camelCase (`by_alias=True`) | mcp 2.0 | migration guide |
| `ctx.elicit()` in tool body | `Annotated[T, Resolve(fn)]` + `Elicit(...)` (works on all eras); `ctx.elicit` only on legacy connections | mcp 2.0 | py.sdk elicitation page |
| `mcp.get_context()`, `ctx.fastmcp` | `ctx: Context` injection, `ctx.mcp_server` | mcp 2.0 | migration guide |
| `FastMCP("X", port=…)` constructor transport args, `mcp.settings.port`, `MCP_*` env vars, `mount_path` | `mcp.run("streamable-http", host=…, port=…)` / `streamable_http_app()`; env not read | mcp 2.0 | migration guide |
| `@server.call_tool()` decorators (low-level) | `Server("x", on_call_tool=handler)` constructor handlers | mcp 2.0 | migration guide |
| `create_connected_server_and_client_session` | `Client(server_obj)` in-memory | mcp 2.0 | testing page |
| WebSocket transport, experimental Tasks API, `RFC7523OAuthClientProvider`, `Context.client_id` | removed (`get_access_token().client_id`) | mcp 2.0 | whats-new / releases |
| `session_id` / stateful HTTP | any worker serves any request; `stateless_http=True` affects legacy path only | mcp 2.0 | deploy page |
| `langchain-mcp-adapters` `MultiServerMCPClient`, `convert_mcp_tool_to_langchain_tool` | `langchain.mcp.MCPAdapter` (async ctx mgr, `list_tools()`), `as_langchain_tool` (coroutine); config `{"mcpServers":{…}}` | langchain 1.4.0 (beta); adapters archived 2026-09-17 | docs.langchain.com migrate page; adapters issue #578 |
| Anthropic MCP connector beta `mcp-client-2025-04-04` | `mcp-client-2025-11-20` with `mcp_toolset` | 2025-11 | Claude docs |
| OpenAI `connector_id` (legacy connectors) | `server_url` / Secure MCP Tunnel | models after 2026-09-01 | OpenAI docs |
| A2A 0.3: `message/send`, `message/stream`, `tasks/get`, `tasks/cancel`, `tasks/resubscribe`, `agent/getAuthenticatedExtendedCard` | `SendMessage`, `SendStreamingMessage`, `GetTask`, `CancelTask`, `SubscribeToTask`, `GetExtendedAgentCard` (+ `ListTasks`) | A2A 1.0 (2026-03-12) | whats-new-v1 |
| A2A 0.3 states `"completed"`, role `"user"` | `TASK_STATE_COMPLETED`, `ROLE_USER` (SCREAMING_SNAKE, `CANCELED` US spelling) | 1.0 | whats-new-v1 |
| `kind` discriminator; `TextPart/FilePart/DataPart`; `mimeType`; `file.fileWithUri/Bytes` | single `Part` oneof `text|raw|url|data`; `mediaType`; `url`/`raw` | 1.0 | whats-new-v1 |
| Card `url`, `preferredTransport`, `additionalInterfaces`, `protocolVersion`, `supportsAuthenticatedExtendedCard` | `supportedInterfaces[]`, `capabilities.extendedAgentCard` | 1.0 | whats-new-v1 |
| stream `final` boolean | wrapped `statusUpdate`/`artifactUpdate`; terminal state closes stream | 1.0 | whats-new-v1 |
| page-based list; `/v1` REST prefix; `application/problem+json` | cursor (`pageToken`,`pageSize`,`nextPageToken`); no `/v1`; `google.rpc.Status` | 1.0 | whats-new-v1 |
| a2a-sdk 0.3 `A2AStarletteApplication(...).build()`, `A2AClient`/`ClientFactory` | `create_*_routes(...)` + `Starlette(routes=…)`; `create_client(agent=card, client_config=ClientConfig(…))`; **protobuf** types | a2a-sdk 1.0 | tutorials steps 5–6; verified |
| OAuth implicit/password flows in A2A cards | removed; device code (RFC 8628) added; `pkceRequired` | 1.0 | whats-new-v1 |
| AG-UI `THINKING_*` events | `REASONING_*` | removed in 1.0.0 | docs.ag-ui.com/concepts/events |
| AG-UI null fields, `SubAgentInfo/subAgents`, `BinaryInputContent`, `MetadataMixin` | omit absent fields (ag-ui-protocol ≥0.1.20); `SubagentInfo/subagents`; removed | 1.0 | migrating-to-1-0 |
| AG-UI framework adapters on pre-1.0 interrupt events (custom interrupt events / tool-call-based resume) | interrupt outcome on `RUN_FINISHED` + `RunAgentInput.resume` only (`@ag-ui/mastra` 2.0.0, 2026-10-12) | AG-UI 1.0 adapters, Oct 2026 | github.com/ag-ui-protocol/ag-ui/releases |
| LangGraph interrupt invisible to AG-UI client | `emit_interrupt_outcome` → `RUN_FINISHED.outcome.interrupt` | AG-UI 1.0 | interrupts page |

---

## 5. Ecosystem and alternatives

| Tool | When chosen | Source |
|---|---|---|
| Plain function/tool calling in a vendor SDK | one app, tools in-process, no reuse across clients | track 3 |
| **MCP** | reusable tool/data servers shared by many clients (IDEs, chat apps, agents) | spec |
| **A2A** | delegate to an independent, opaque agent (other team/vendor/framework), long tasks, multi-turn clarification | a2a-protocol.org |
| **AG-UI** | stream an agent's text/tool/state events to a front end; human approvals | docs.ag-ui.com |
| MCP Apps / MCP-UI / A2UI / Open JSON UI | rich UI inside a host chat / generative UI specs | extensions, AG-UI docs |
| FastMCP 4 (standalone) vs official `mcp` 2 `MCPServer` | FastMCP: richer server/client/auth/Apps/"Code Mode" features, requires mcp>=2; official: smallest dependency, conformance reference | gofastmcp.com, PyPI |
| Vendor hosted MCP (Anthropic connector, OpenAI `type:"mcp"`, Gemini Interactions `mcp_server`) | model provider calls your public HTTPS server so you run no client; no stdio | vendor docs |
| `langchain.mcp.MCPAdapter` / OpenAI Agents SDK `MCPServer*` / Anthropic `async_mcp_tool` | you run the MCP client in your process and loop yourself | vendor docs |
| OpenAPI→MCP / REST adapters (FastMCP `from_openapi`, agentgateway OpenAPI integration, Uber AutoCrawler) | wrapping existing APIs fast | FastMCP/agentgateway/Uber |
| MCP gateways: agentgateway (OSS, LF), AWS MCP Gateway & Registry (OSS), Kong, Zuplo, Obot, Cloudflare, Prefect Horizon (FastMCP's paid gateway), Docker MCP Gateway **UNVERIFIED** | central authn/authz, rate limits, audit, registry | agentgateway README, AWS blog, Kong/Zuplo search results (not opened) |
| Private MCP registry (own implementation of the registry OpenAPI) | internal servers; public registry rejects private ones | registry/about |
| AGNTCY (Directory/OASF, SLIM, Identity) | cross-org agent discovery + identity + secure messaging beyond A2A | agntcy.org |
| AP2 (+ Visa/Mastercard programs, x402 appears in AP2 samples) | agent-initiated payments | ap2-protocol.org |
| AGENTS.md vs Agent Skills vs Skills-over-MCP | AGENTS.md = per-repo instructions; Skills = reusable procedures loaded on demand; Skills-over-MCP = distribute skills from a server | agents.md, agentskills.io, MCP extensions |
| Older/competing: ACP (IBM), ANP — **UNVERIFIED current status**, not opened; LangGraph Platform / ADK expose A2A natively **UNVERIFIED** | | |

---

## 6. Runs on a laptop?

### 6.1 Verified experiments (all 2026-10-11, scratch venv Python 3.12.13, versions as in 1.2)

1. **MCP v2 server + LangChain + real Gemini, end to end.** `MCPServer("Tracker")` with one `@mcp.tool()`; `async with MCPAdapter({"mcpServers":{"t":{"command":sys.executable,"args":["srv.py"]}}}) as ad: tools = await ad.list_tools()`; `llm.bind_tools(tools)`; Gemini returned `tool_calls=[{'name':'count_open','args':{'team':'web'},...}]`; `await tool.ainvoke(tool_call_dict)` returns a **`ToolMessage`** (calling with bare args returns a list of content blocks); second call produced "The web team currently has 5 open issues." Two model calls total. `AIMessage.content` is a list of blocks for Gemini in langchain 1.x → use `.text`.
   - `MCPAdapter` target may be a `{"mcpServers":…}` dict (stdio or `{"url":…}`), a URL string, a `Path`, a `fastmcp.Client`, a `FastMCP`/**`MCPServer` instance (in-process, no subprocess, no HTTP)**, a transport, or a `ClientGroup`. Auth is configured on the underlying `fastmcp.Client`.
2. **MCP over local Streamable HTTP**: `mcp.run("streamable-http", host="127.0.0.1", port=8765)` works; requests are `POST /mcp` with `server/discover`, `tools/list`, `tools/call`, each carrying `_meta` (confirmed in the cassette body) and `mcp-method` header. No session, no handshake.
3. **Auth wiring**: `MCPServer("Tracker", token_verifier=DevVerifier(), auth=AuthSettings(issuer_url=…, resource_server_url="http://127.0.0.1:8766/mcp", required_scopes=["issues:read"]))` with `class DevVerifier(TokenVerifier): async def verify_token(self, token) -> AccessToken | None`. Unauthenticated POST → `401` with `www-authenticate: Bearer error="invalid_token", error_description="Authentication required", resource_metadata="http://127.0.0.1:8766/.well-known/oauth-protected-resource/mcp"`; `GET /.well-known/oauth-protected-resource/mcp` → `{"resource":…,"authorization_servers":[…],"scopes_supported":["issues:read"],"bearer_methods_supported":["header"]}`. `get_access_token()` inside a tool returns the caller's token. (`validate_token_resource` defaults off with a warning; docs say 3.0 will default it on — turn it on in lessons.)
4. **A2A server + client with a real LLM behind the executor** (a2a-sdk 1.2.2): an `AgentExecutor` that calls `llm.ainvoke(...)`, `DefaultRequestHandler` + `InMemoryTaskStore`, `Starlette(routes=[*create_agent_card_routes(card), *create_jsonrpc_routes(handler,"/")])`, uvicorn started in a daemon thread in the same process; client `A2ACardResolver(...).get_agent_card()` then `create_client(agent=card, client_config=ClientConfig(streaming=False))` and `async for chunk in client.send_message(SendMessageRequest(message=new_text_message("…", role=Role.ROLE_USER)))` returned a Task with artifact text "Bug" and state COMPLETED. Chunks print as protobuf text (not dict); use `MessageToDict` for display.
5. **AG-UI endpoint with a real streaming LLM**: FastAPI `POST /agent` taking `RunAgentInput`, `EventEncoder(accept=…)`, emitting `RunStarted → TextMessageStart → TextMessageContent… → TextMessageEnd → RunFinished` while iterating `llm.astream(...)`; `StreamingResponse(…, media_type=enc.get_content_type())` gives `text/event-stream`. **Recorded once, then replayed with `GOOGLE_CLOUD_API_KEY` empty: identical event sequence** (only the random `messageId` uuid differs).
6. **vcrpy interaction findings** (drive the `llm_replay` guidance below):
   - **stdio MCP servers are invisible to vcrpy**: 0 requests recorded for a stdio run.
   - **Local HTTP is intercepted by default** (MCP via fastmcp/httpx2: 3 requests recorded). Replay then worked with *no server running* and played all 3 — so a cassette can silently stand in for the server and mask server bugs; the cassette matches by `method+scheme+host+port+path` (as `llm_replay` configures) so repeated `POST /mcp` are replayed purely by order.
   - **Fix verified**: `vcr.use_cassette(..., ignore_localhost=True)` (or `ignore_hosts=[…]`): local MCP/A2A/AG-UI traffic stays live, only model calls (and Google auth metadata calls) are cassetted; with no server running the call fails with a real connection error, as it should.
   - vcrpy 8.3.0 does patch `httpx2` (needed: mcp v2, fastmcp 4, anthropic 1.13, openai 3.x all use httpx2; a2a-sdk uses httpx).
   - **An LLM called from inside a subprocess** (stdio server, `uvicorn` in another process) is *not* recorded/replayed and needs a live key → keep model calls in the notebook process, and run HTTP servers in a **thread in the same process** (`uvicorn.Server(Config(app,…)).run` in a daemon thread) when the server itself calls the model (A2A executor, AG-UI endpoint).
   - Streaming (SSE) model responses record and replay fine (experiment 5).
   - The cassette URI for Vertex contains the **GCP project id** (`…/projects/<id>/locations/global/…`), and GCE metadata-server calls (`169.254.169.254`, `metadata.google.internal`) are recorded; `llm_replay.py` scrubs tokens/service-account emails in bodies but I did not see a URI/project-id filter → **warning: decide whether to normalise the project id before committing cassettes** (add `before_record_request`).
   - Random ids (uuid `messageId`, A2A task/message ids, timestamps) differ between record and replay runs; lessons must not assert on them or must seed them.
   - Replay-safety budget: `llm_replay._count_call` only counts paced hosts (googleapis/anthropic/openai), so localhost protocol calls don't consume the 2-call budget.
7. **google-genai `tools=[ClientSession]` automatic function calling fails** (see 1.3). OpenAI Agents SDK and Anthropic helpers not run (no keys for those providers used).

### 6.2 Capability table

| Capability | Local, no account? | Option | Tags |
|---|---|---|---|
| MCP server (tools/resources/prompts) | yes | `MCPServer`, stdio or `127.0.0.1` HTTP; in-memory `Client(server)` for tests | none |
| MCP client + real model | yes (replay) | `langchain.mcp.MCPAdapter` + `init_chat_model(...).bind_tools` | `needs-llm` (recorded) |
| Elicitation / MRTR | yes | `Resolve`/`Elicit` in server, `Client` callback in tests | none |
| Tasks extension | partly | fastmcp 4 ships task utilities; official `mcp` 2.3 has only `mcp_types` models for the extension — **UNVERIFIED** server/client support, check at build time; fall back to hand-written JSON-RPC with `httpx` against a server that returns `CreateTaskResult` | none / `slow` |
| MCP Apps | partly | serve a `ui://` HTML resource from a tool; rendering needs a host (Claude Desktop, VS Code, MCPJam, basic-host from ext-apps) | `needs-download` (Node) |
| Inspector | yes | `npx @modelcontextprotocol/inspector` (Node ≥22.19; web UI prints a tokenised URL), `--cli --method tools/list` for scripted output | `needs-download` |
| OAuth resource server (PRM, 401 challenge, scope check) | yes | `TokenVerifier` + `AuthSettings` | none |
| Authorization server | yes (two ways) | (a) tiny in-process AS with Authlib 1.8 (**not built yet**; to prove in the build) or `client_credentials`/pre-minted JWT signed with PyJWT; (b) **Keycloak** `quay.io/keycloak/keycloak:26.8.0 start-dev --features=cimd` | none / `needs-docker` |
| Browser authorization-code flow | needs a human/browser | headless: client_credentials extension, or script the redirect with httpx against the dev AS | `needs-download`? no; mark interactive cells `skip-in-ci` |
| Enterprise-managed auth (ID-JAG) | read-along + dev IdP | Keycloak 26.7/26.8 supports EMA as resource AS (experimental); not as IdP (issue #48818) | `needs-docker` |
| Vendor-hosted MCP (Anthropic connector, OpenAI `mcp` tool, Gemini `mcp_server`) | no (needs public HTTPS) | local stand-in: client-side loop; tunnels (OpenAI "Secure MCP Tunnel", ngrok) are read-along | `needs-cloud` |
| MCP Registry | read: yes (public REST); publish: no | `mcp-publisher`, GitHub/DNS auth; official codebase not self-hostable → read-along + local fake index | `needs-cloud` |
| A2A server/client | yes | `a2a-sdk` + Starlette/uvicorn thread; JSON-RPC and REST bindings; gRPC needs extra `grpc` | none |
| A2A signed cards | yes | `create_agent_card_signer` / `create_signature_verifier` with a local ES256 key | none |
| A2A push notifications | yes | local webhook receiver on another port (SDK validates push URLs, may block localhost — check) | none |
| AG-UI endpoint + client | yes | FastAPI + `EventEncoder`; consume with `httpx` stream; CopilotKit/React front end optional | none / `needs-download` |
| AP2 | read-along | spec + samples | — |
| AGNTCY | read-along (optional `agntcy-app-sdk`, Python ≥3.12) | | — |
| AGENTS.md / Agent Skills | yes | write files; validate with `skills-ref validate` | none |
| Gateway (agentgateway) | yes (binary or Docker) / K8s | standalone quickstart; K8s via kind (VM lacks kind/helm: install first) | `needs-docker`, `needs-k8s` |
| Load testing a stateless MCP endpoint | yes | `uvicorn --workers 4` + `hey`/`locust`/`httpx` loop | `slow` |

Notebook cell guidance: start local servers in-process (thread) or stdio; call `llm_replay` with `ignore_localhost` semantics; never put a model call inside a subprocess server; each example ≤2 model calls (tool-selection call + final-answer call fits MCP; A2A example = 1 call in the remote agent + 1 in the orchestrator).

---

## 7. Production practice (L5)

**Testing**
- In-memory: `async with Client(mcp, raise_exceptions=True) as c:` with pytest+anyio (`anyio_backend` fixture), `inline-snapshot` optional; `Client(mcp)` probes era; pin `mode="legacy"` to test elicitation/sampling push (py.sdk testing page).
- Conformance: SEP-2484 requires conformance tests for Standards-Track SEPs to be Final; SDK tiers doc (`/community/sdk-tiers#conformance-testing`); Python SDK `examples/servers/everything-server` is the cross-SDK conformance target.
- CLI in CI: `npx @modelcontextprotocol/inspector --cli https://…/mcp --transport http --method tools/list --format json | jq` (exit codes documented).
- Tool-selection evals with recorded model calls (the kit's replay) — does the model pick the right tool/args for N prompts; keep tool descriptions in version control and snapshot `tools/list` (deterministic order helps).
- A2A: card validation, round trip with `a2a-inspector` (**UNVERIFIED current**) or `a2a-cli` (blog 2026-10-01).

**Observability**
- OpenTelemetry: `_meta` carries `traceparent/tracestate/baggage` (SEP-414); Python SDK has an OTel middleware page; `a2a-sdk[telemetry]`; propagate one trace across AG-UI → agent → MCP → upstream API.
- Log tool usage for audit (spec tools §Security); for stdio log to stderr (MCP logging deprecated).
- Gateway metrics keyed on `Mcp-Method` / `Mcp-Name` headers without parsing bodies (Cloudflare post).

**Security (summary; detail in 8.10)** — validate inputs, access control, rate limit tool calls, sanitize outputs (spec tools §Security MUST list); `TransportSecuritySettings(allowed_hosts, allowed_origins)` — default accepts localhost only (421/403 otherwise); Origin check MUST; bind 127.0.0.1 locally; confirm destructive tools; request bodies >4 MiB → 413 (Python SDK 2.0).

**Reliability**
- Stateless ⇒ any worker serves any request; scale with `uvicorn server:app --workers 4`; no sticky sessions on 2026-07-28 (legacy 2025-11-25 clients need stickiness or `stateless_http=True`, losing callbacks and resumability).
- MRTR across workers: all instances need the same `RequestStateSecurity(keys=[…])` and server name/audience, otherwise "Invalid or expired requestState".
- Change notifications across replicas: share a `SubscriptionBus` implemented on your pub/sub (SDK ships in-process only); streams not resumable, clients re-listen.
- Timeouts: Python `Client` URL transport 30 s connect/write/pool, 300 s read; `httpx2` default is 5 s if you build your own client without a timeout; SSE event limit 1 MiB (`max_sse_event_size`). Long work → Tasks extension (poll with `pollIntervalMs`, persist task ids), not long-held connections.
- Cancellation = close the response stream; handlers must stop work.
- Caching: honour `ttlMs`/`cacheScope`; deterministic tool order keeps LLM prompt caches warm.
- A2A: `InMemoryTaskStore` loses state on restart → DB task stores (`a2a-sdk[postgresql|mysql|sqlite]`), `a2a/server/cluster` for multi-replica streams; card caching via ETag/Cache-Control; version negotiation `A2A-Version` and SDK compat mode for 0.3 peers.
- AG-UI: no resume → client retries as a new run with new `runId`; keep-alive comment lines; `X-Accel-Buffering: no` behind nginx.

**Deployment**: ASGI behind a TLS-terminating proxy needs `--proxy-headers --forwarded-allow-ips`; add a health route with `custom_route`; mount into FastAPI/Starlette (`/run/asgi/`); Cloudflare Workers / serverless possible because stateless (Cloudflare "billions of tool calls since February", "thousands of requests per second", blog `mcp-v2`); dual-protocol migration: run strict stateless route beside sessionful route, drain, remove (≥12-month deprecation floor).

**Cost / context**: tool schemas are paid tokens on every model call; Uber saw context bloat/cost at hundreds of servers → Response Projection, Code Mode, 4-tool incremental discovery (`discover_server`, `discover_tools`, `get_tool_schema`, `invoke_tool`); MCP roadmap lists "progressive discovery". Keep tools few, descriptions short, outputs trimmed (`structuredContent` with `outputSchema`), cache `tools/list`.

---

## 8. Enterprise and scale (L6) — checklist from `standards/LEVELS.md`

This track owns **item 10**. Items 1, 13 and the rest belong to other tracks; for each, the protocol-specific facts a lesson in *this* track can still use are listed so L5/L6 lessons stay concrete.

### 8.1 Distributed architecture internals — **N/A in this track → agentic-ai-5-multi-agent (item 1)**
Protocol-level facts usable here: MCP 2026-07-28 removed protocol sessions so a server is an ordinary stateless HTTP service (components: client, optional gateway/proxy, server replicas, AS/IdP, registry); A2A Python `a2a/server/cluster` (`database_task_store.py`, `database_event_stream.py`) is the SDK's own multi-replica story; Uber's architecture = control plane (MCP Registry) + data plane (Proxy Gateway → Muttley mesh → HTTP/gRPC/TChannel). Contrast "sessionful/legacy" (sticky sessions, in-memory) vs "stateless" (any replica).

### 8.2 Cluster operations — **N/A → agentic-ai-6-production (item 2)**
Usable: `uvicorn --workers 4` locally; 3-replica MCP behind nginx/Docker Compose proves "no sticky sessions" and shared `RequestStateSecurity` keys; Kubernetes via kind v0.33.0 (not installed on the VM).

### 8.3 Failure and recovery — **N/A → agentic-ai-6-production (item 3)**
Usable drills: kill an MCP replica mid-`tools/call` (in-flight request lost, client must re-issue with a new id — no resumability); kill the AS/IdP (existing tokens work until expiry; PRM/AS metadata caching); expire `requestState`.

### 8.4 Extreme scale — **N/A → agentic-ai-6-production (item 4)**
Usable numbers: Uber 800+ MCP servers / 5,000+ tools; Tier-1 SDKs ≈ half a billion downloads/month, Python+TS each >1 billion total (MCP blog); context cost of tool catalogs is the first thing that breaks.

### 8.5 Kubernetes and infrastructure — **N/A → agentic-ai-6-production (item 5)**
Usable: agentgateway has a Kubernetes mode on the Gateway API (v1.6.0); AWS MCP Gateway & Registry ships Helm charts (EKS multi-AZ), Terraform for ECS Fargate, Docker Compose for laptops; exact chart names/versions **UNVERIFIED** (not opened).

### 8.6 Performance engineering — **N/A → agentic-ai-6-production (item 6)**
Usable: header-based routing (`Mcp-Method`, `Mcp-Name`, `Mcp-Param-*`) lets gateways meter per tool without parsing bodies; cacheable lists; no published MCP/A2A latency benchmarks found in this pass (**gap**).

### 8.7 HA and DR — **N/A → agentic-ai-6-production (item 7)**
Usable: stateless ⇒ multi-region active-active is a load-balancer problem; A2A task store and AG-UI runs need external state; registries are metadata (rebuildable).

### 8.8 Zero-downtime change — **N/A → agentic-ai-6-production (item 8)**
Usable: protocol version negotiation per request lets mixed-version fleets coexist (`UnsupportedProtocolVersionError`, `server/discover`); deprecation policy (Active → Deprecated ≥12 months, expedited ≥90 days → Removed, registry of deprecated features); Uber: owners review each tool-definition change as a config diff, can roll back; rug-pull defence = pin/hash tool descriptions.

### 8.9 Multi-tenancy and isolation — **N/A → agentic-ai-6-production (item 9)**
Usable: A2A `tenant` field on requests and `AgentInterface`; MCP state handles must be bound to the verified user (`<user_id>:<handle>`); Asana MCP cross-tenant leak (June 2025) as the cautionary tale; per-tenant scopes/audience.

### 8.10 Security and compliance at organisation scale — **OWNED BY THIS TRACK (item 10)**

**A. Mechanisms and exact names (2026-07-28)**
1. *Authentication topology.* Remote MCP server = resource server only. Python v2: `MCPServer(name, token_verifier=…, auth=AuthSettings(issuer_url, resource_server_url, required_scopes, validate_token_resource))`; `TokenVerifier.verify_token(token) -> AccessToken | None`; `get_access_token()`; PRM auto-served at `/.well-known/oauth-protected-resource/<path>`. FastMCP 4 has provider-based auth (docs not opened; **UNVERIFIED**).
2. *Client side.* `OAuthClientProvider(server_url, client_metadata=OAuthClientMetadata(...), storage=TokenStorage, redirect_handler, callback_handler, client_metadata_url=<CIMD URL>)` is an `httpx2.Auth`; `ClientCredentialsOAuthProvider(client_id, client_secret, scope=)` for M2M; `TokenStorage` protocol (4 async methods) — persist client info too; callbacks return `AuthorizationCodeResult`. LangChain: configure auth on the `fastmcp.Client`; keurcien reports `langchain[mcp]` works with OAuth, API-key and public remote servers (adapters issue #578, 2026-09-15).
3. *Audience & passthrough.* Validate `aud`/`resource` = your canonical URI (`https://mcp.example.com/mcp`, no fragment, no trailing slash preferred). Never forward the inbound token; exchange (RFC 8693 token exchange) or use a separate upstream credential. Uber does exactly this for third-party servers (exchanges internal token for a Jira/Google token).
4. *Scopes.* Least privilege; per-tool scope checks inside handlers (SDK `required_scopes` is server-wide); `403 insufficient_scope` with the **full set needed for the operation in one challenge**; log elevation events with correlation ids.
5. *Tool poisoning / rug pull / shadowing* (Invariant Labs, 2025-04-01): hidden instructions in tool descriptions; description change after approval; one server's description steering another's tool. Defences: show full descriptions, pin/hash `tools/list` output and alert on diffs (use `ttlMs` caching + `listChanged`), isolate servers/namespace tool names (`{server}_{tool}`; spec: server name not unique), treat `annotations` (readOnlyHint etc.) as untrusted unless server trusted, human confirmation for destructive tools, registry/gateway admission scan (AWS gateway runs Cisco AI Defense scanners on each registration; critical/high findings disable the asset).
6. *Prompt injection through tool results / lethal trifecta* (Willison 2025-06-16): private data + untrusted content + external communication in one agent = exfiltration; GitHub MCP "toxic agent flow" (Invariant, 2025-05-26; over-privileged PAT; architectural, not a server bug). Defences: split capabilities across agents/sessions, per-session repo allow-list, output sanitization/PII redaction at gateway (Uber default), confirmation gates, no guardrail-only strategy (Willison: "95% is a failing grade"). Design-pattern research (CaMeL, plan-then-execute, dual-LLM, AgentDojo) already summarised in `topics/agentic-ai-7-advanced-agents/RESEARCH.md` — cross-reference, do not redo.
7. *Confused deputy.* Proxy server + static third-party client id + DCR + consent cookie ⇒ per-client consent page owned by the MCP server, exact `redirect_uri` string match, CSRF/`state` single-use ≤10 min and set only **after** consent, `__Host-` cookies with `Secure; HttpOnly; SameSite=Lax`, `frame-ancestors`/`X-Frame-Options: DENY`.
8. *Client-side hardening.* SSRF block-list for discovery URLs, HTTPS only (loopback exception), egress proxy (Smokescreen), no shell `open`, scheme allow-list for authorization URLs, consent dialog showing the full command for one-click local servers, sandbox stdio servers.
9. *Agent identity.* Today: client credentials / `ClientCredentialsOAuthProvider`; Enterprise-Managed Authorization extension (`io.modelcontextprotocol/enterprise-managed-authorization`, ID-JAG, SEP-990; IdP policy, central revocation, audit); roadmap: DPoP, Workload Identity Federation (SEP-1933), RFC 8693, IETF WIMSE, human-presence attestation. A2A: `securitySchemes` (apiKey, http, oauth2 [authorization code+PKCE, client credentials, device code], openIdConnect, mutualTls), per-skill `security_requirements`, signed Agent Cards (JWS+JCS, `kid`/`jku`, restrict `algorithms` to avoid algorithm confusion), extended cards behind auth, "servers must return only tasks the caller is authorized to see" and must not reveal existence of unauthorised resources. AAIF has an Identity & Trust working group; FIDO Agentic Authentication TWG; AGNTCY Identity.
10. *Audit.* Per-call who/what/when/args-hash/result-size; tool-level Access Control System at gateway (Uber); AWS gateway audit log "who did what and when" (claims SOC 2/GDPR support); correlate with OTel `traceparent`; `requestState` and handle replay protection; Inspector stores OAuth tokens in OS keychain or plaintext `~/.mcp-inspector/secrets.json` on headless Linux (warning in docs).
11. *Compliance/data.* Residency and deletion obligations are deployment-level; OpenAI hosted MCP is ZDR/Data-Residency compatible but third-party servers follow their own policy; Anthropic MCP connector is **not ZDR-eligible** (feature metadata on the docs page).
12. *Local-server controls.* stdio spec guidance: credentials from env; local HTTP servers need auth token or unix socket; `mcp` v2 stdio subprocess gets a minimal env, pass secrets via `env=`.

**B. Real incidents and CVEs (sources: authzed timeline https://authzed.com/blog/timeline-mcp-breaches; The Hacker News 2026-04-20; Invariant Labs; NVD IDs as quoted by those sources — the CVE database itself was not opened)**

| Date | Product | ID / class | What / numbers |
|---|---|---|---|
| 2025-04 | WhatsApp MCP + malicious co-installed server | tool poisoning/shadowing | chat history exfiltrated; Invariant Labs 2025-04-01 write-up |
| 2025-05 | GitHub MCP official server | prompt injection via public issue + over-privileged PAT | private repo data leaked to public PR (Invariant 2025-05-26); architectural |
| 2025-06 | Asana MCP | cross-tenant access-control flaw | one org's projects/tasks visible to others |
| 2025-06 | MCP Inspector | CVE-2025-49596, CVSS 9.4 | unauthenticated RCE via inspector–proxy on localhost; fixed in 0.14.1 (SD Times via search; the Inspector's current docs describe a per-launch API token) |
| 2025-07 | mcp-remote | CVE-2025-6514, CVSS 9.6 | OS command injection from malicious `authorization_endpoint`; versions 0.0.5–0.1.15; 437,000+ downloads |
| 2025-08 | Anthropic Filesystem MCP server | CVE-2025-53109/53110 | sandbox escape via symlink/containment bypass |
| 2025-09 | "postmark-mcp" malicious package | supply chain | all mail BCC'd to attacker |
| 2025-09 | Flowise | CVE-2025-59528 | STDIO design flaw / sandbox bypass |
| 2025-10 | Smithery hosting | path traversal in `smithery.yaml` | Fly.io token leaked, 3,000+ apps controlled |
| 2025-10 | figma-developer-mcp | CVE-2025-53967 | command injection |
| 2026-01 | gemini-mcp-tool (unofficial) | CVE-2026-0755, 9.8 | unauthenticated RCE |
| 2026-02 | Fake Oura MCP (SmartLoader) | registry supply chain | StealC infostealer |
| 2026-03 | nginx-ui | CVE-2026-33032, 9.8 | auth bypass on MCP message endpoint; 2,600+ exposed instances |
| 2026-04 | STDIO "by design" (OX Security via The Hacker News 2026-04-20) | ~10 CVEs incl. CVE-2026-30623 (LiteLLM), CVE-2026-30624 (Agent Zero), CVE-2026-30615 (Windsurf), CVE-2026-40933 (Flowise, search snippet says CVSS 10) | 150M+ downloads, 7,000+ servers; Anthropic called behaviour "expected" and did not change the protocol; mitigations: sandbox, treat config as untrusted, verified sources |
| 2026 | MCPJam inspector CVE-2026-23744 (RCE ≤1.4.2), Context7 CVE-2026-75130 (prompt injection, CVSS 9), Kong Konnect CVE-2026-13341, Mobile MCP CVE-2026-35394 | from search results only — **UNVERIFIED**, verify on NVD before quoting |
OWASP Top 10 for Agentic Applications 2026 published 2025-12-09 (ASI01–ASI10; entry names not retrieved; supply chain = ASI04 per a secondary source). A separate "OWASP MCP Top 10" was referenced by a secondary source; **not confirmed**.

**C. Open source vs paid**: MCP/A2A/AG-UI/AGENTS.md/Agent Skills specs and SDKs open (Apache-2.0 for MCP and A2A, MIT for AG-UI); Keycloak, Dex, Authlib, agentgateway, AWS MCP Gateway & Registry (Apache-2.0) open; Okta/Entra/Auth0/PingFederate IdPs, Prefect Horizon, Kong/Zuplo/Obot gateways, Cisco AI Defense scanning, Cloudflare Workers OAuth Provider are commercial or platform-bound.

### 8.11 Cost engineering — **N/A → agentic-ai-6-production (item 11)**
Usable: tool-catalog token cost, Response Projection, Code Mode, tool-list caching, deterministic order for prompt-cache hits (see section 7).

### 8.12 Platform and organisation patterns — **N/A as a full item → agentic-ai-6-production (item 12)**, but this track owns the protocol side: org registry (private registry implementing the MCP Registry OpenAPI; `server.json`; namespace verification), gateway + registry control plane/data plane (Uber), default-disabled discovery with owner enablement (Uber), curated approved server list and read-only vs destructive labels (Block), AAIF working groups as the standards venue, SDK Tier system, deprecation registry.

### 8.13 Frontier — **N/A → agentic-ai-9-frontier (item 13)**; protocol-side items are in section 9.

### 8.14 Case studies — **N/A as a full item → agentic-ai-6-production (item 14)**; usable write-ups for this track:
1. **Block** — goose + MCP company-wide (blog 2025-04-21): thousands of employees daily; all internal servers written in-house; curated approved servers (Snowflake, GitHub, Jira, Slack, Google Drive, internal compliance/support APIs); tools labelled read-only/destructive with confirmation; admins control which models may call which tools; OAuth with tokens in OS keychains, but "OAuth flows run inside locally run MCP servers" — a stated temporary approach. (Speakeasy secondary: ~4,000 of 10,000 employees on goose — not Block's own number.) https://goose-docs.ai/blog/2025/04/21/mcp-in-enterprise
2. **Uber** — MCP Gateway (2026-10-01): 800+ servers, 5,000+ tools; Registry (control plane) + Proxy Gateway (data plane); AutoCrawler (Cadence) converts Protobuf/Thrift IDL to MCP servers with LLM-enriched descriptions; tools start **disabled**; per-tool Access Control System policies; PII redaction on responses; Response Projection + Code Mode (now default for coding agents). https://www.uber.com/us/en/blog/designing-mcp-gateway/
3. **Cloudflare** — "The next generation of MCP" (2026): Code Mode MCP server for the whole Cloudflare API on an unofficial stateless mode, "thousands of requests per second", "billions of tool calls since February"; Workers instead of Durable Objects; Sentry and Linear as early adopters. https://blog.cloudflare.com/mcp-v2/
4. **AWS Open Source** — "Governing AI Assets at Scale with MCP Gateway and Registry" (2026-06-17): NGINX + FastAPI + MongoDB/DocumentDB, Keycloak/Entra/Okta/Auth0/Cognito/PingFederate, scanner gate, audit log, Helm on EKS, Compose on laptop; Expedia Group runs "hundreds" of MCP servers/tools/skills. https://aws.amazon.com/blogs/opensource/governing-ai-assets-at-scale-with-mcp-gateway-and-registry/
5. A2A adoption (LF 2026-04-09): Microsoft (Azure AI Foundry, Copilot Studio), AWS (Bedrock AgentCore Runtime), production in supply chain, financial services, insurance, IT ops — no counts.

---

## 9. Frontier (last ~12 months)

- **2025-12-09** AAIF formed (MCP, goose, AGENTS.md); **2025-12-09** OWASP Top 10 for Agentic Applications.
- **2026-01-26** MCP Apps spec revision; Apps shipped in Claude, VS Code Copilot, M365 Copilot, goose, Postman.
- **2026-03-12** A2A v1.0.0 (stable; signed cards; multi-tenancy; gRPC multi-tenancy; `ListTasks`); 2026-04-09 LF "150+ orgs"; 2026-04-16 Google one-year post; 2026-05 v1.0.1; **2026-08-27 A2A joins AAIF (Growth Stage)**; 2026-10-01 `a2a-cli`.
- **2026-04-20** OX Security "MCP by design" STDIO RCE disclosure (150M+ downloads affected); wave of 2026 CVEs.
- **2026-04-28** AP2 v0.2 (Human-Not-Present flows) and donation to FIDO Alliance.
- **2026-06-17** AWS open-source MCP Gateway & Registry.
- **2026-07-28** **MCP 2026-07-28**: stateless core, `server/discover`, MRTR, `subscriptions/listen`, cache hints, header routing, extensions framework, Tasks→extension, DCR deprecated→CIMD, `iss` validation, Roots/Sampling/Logging deprecated, lifecycle policy; Python SDK 2.0.0 the same day (`FastMCP`→`MCPServer`, `Client`, `httpx2`, `mcp-types`); Tier-1 SDKs TypeScript/Python/Go/C#, Rust beta.
- **2026-08-22** MCP roadmap: (1) agentic messaging primitives (Triggers & Events WG, composition of Tasks/subscriptions/progress), (2) **HTTP over stdio** (HTTP/2 multiplexing over stdin/stdout) and ETag caching, (3) **agent identity & enterprise security** (DPoP, Workload Identity Federation SEP-1933, ID-JAG, RFC 8693, WIMSE; Agent Identity WG forming), (4) improved primitives (tool-result shape redesign, **progressive discovery**, annotations may be deprecated), (5) SDK DX (spec-generated SDKs, extension contract).
- **2026-08/09** LangChain moves MCP into `langchain.mcp` (beta) on FastMCP; `langchain-mcp-adapters` archived 2026-09-17.
- **2026-09-17** AG-UI protocol/SDK 1.0 (interrupt outcome + resume, reasoning events, subagent events, capabilities, protobuf transport).
- **2026-10-01** Uber MCP Gateway write-up; **2026-10** Inspector 2.x (web/CLI/TUI/mcpdo).
- **2026-10-09..12** AG-UI adapters move to 1.0 (`@ag-ui/aws-strands` 1.0.0, `ag_ui_adk` 0.9.0 with replica-safe processed-message ledger, `@ag-ui/mastra` 2.0.0). **2026-10-08** MCP Governance Working Group charter merged (docs). Re-check 2026-10-12: nothing else new since the 10-11 Snapshot.
- Keycloak support matrix (https://www.keycloak.org/securing-apps/mcp-authz-server, nightly 26.8.0 guide): MCP 2025-03-26 "Supported"; 2025-06-18, 2025-11-25 and 2026-07-28 "Experimental". RFC 7591 DCR supported (MAY in newest MCP versions); RFC 9207 supported; RFC 8707 experimental (`--features=resource-indicators`); CIMD experimental (`--features=cimd`, client profile executor + `client-id-uri` condition); CIMD default 5 KB document limit, 5 min to 3 days cache (SPI options); ChatGPT's CIMD not supported (needs `token_endpoint_auth_methods_supported`); Claude Desktop cannot use JWT Authorization Grant against Keycloak.
- Direction: protocols converge on HTTP-native, stateless, gateway-friendly; identity (agents as first-class principals) is the next fight; registries/server cards/AI Catalog for discovery; code-mode/progressive discovery to cut tool-catalog tokens; consolidation under AAIF (MCP, A2A, AGENTS.md, agentgateway) with AG-UI, Agent Skills, AP2 (FIDO), AGNTCY elsewhere.

---

## 10. Common interview questions / misconceptions

1. MCP vs A2A: when is something an MCP tool and when an A2A agent? (opaque, autonomous, long/multi-turn → A2A; schema'd deterministic call you control → MCP.) Misconception: "they compete".
2. MCP vs plain function calling / OpenAPI? What does MCP add (discovery, uniform transport, resources/prompts, auth)? What does it not (it does not make a model good at choosing tools).
3. What does "stateless MCP" mean in 2026-07-28? What replaced `initialize`, `Mcp-Session-Id`, server→client requests and GET streams? What breaks for session-dependent servers? (Misconception: stateless = no state; state moves to explicit handles.)
4. Walk through MRTR for an elicitation inside `tools/call`. Why must `requestState` be signed? What if the retry lands on another replica?
5. Streamable HTTP vs stdio vs legacy HTTP+SSE: security and scaling differences; why Origin validation and localhost binding?
6. Design OAuth for a remote MCP server: roles, PRM, `WWW-Authenticate`, RFC 8707 `resource`, PKCE, CIMD vs DCR, scope step-up. Where does token validation live?
7. What is token passthrough, why forbidden, and what do you do when the MCP server must call GitHub as the user? (Separate upstream token via OBO/token exchange; audience validation.)
8. Confused deputy in an MCP OAuth proxy: conditions, attack, mitigations.
9. Tool poisoning, rug pull, tool shadowing, and indirect prompt injection via tool results: explain with the lethal trifecta; what can a protocol fix vs a system design fix? (Staff-level: why guardrail classifiers are not a control.)
10. Design an org-wide MCP platform for 5,000 engineers (staff/system design): gateway, registry, approval workflow, auth (EMA/ID-JAG), per-tool authz, audit, redaction, tool-catalog token budget, versioning, kill switch. Cite Uber/Block/AWS patterns.
11. Design agent identity: how does an agent authenticate to MCP servers acting for a user who is offline? (client credentials vs ID-JAG vs token exchange/DPoP; scopes; audit "on behalf of".)
12. A2A Agent Card: where is it, what is in it, how are cards signed/verified, what is an extended card, how do you prevent card spoofing?
13. A2A task lifecycle: enumerate states, which are terminal vs interrupted; how do `contextId`/`taskId` support multi-turn; message vs artifact; streaming vs push notifications vs polling.
14. A2A bindings: JSON-RPC vs gRPC vs HTTP+JSON — how are they chosen from the card? Multi-tenancy?
15. AG-UI: what problem does it solve vs just streaming tokens? Event categories; how does human approval work (interrupt outcome + resume)? Why no resumption?
16. How do MCP Tasks differ from A2A tasks? (extension-level durable handle for one tool call vs agent-level task with its own lifecycle and messages.)
17. How do you test an MCP server? (in-memory client, Inspector CLI, conformance, recorded model evals.) How do you record/replay LLM calls without recording your own local servers?
18. Why did Roots/Sampling/Logging get deprecated and what replaces them?
19. How would you roll out a breaking protocol revision (dual-stack, 12-month deprecation window, version negotiation)?
20. Misconceptions: "MCP servers are sandboxed" (stdio servers run with user privileges; ~2026 STDIO CVEs); "OAuth in MCP means the server issues tokens" (it is only the resource server); "`annotations` like readOnlyHint are enforceable" (untrusted); "A2A needs a central registry" (none defined); "AG-UI is a UI framework" (it is an event protocol).

---

## 11. Suggested running example

**A. "Team issue tracker / ops desk" ("Trackr") — recommended.** Start: SQLite or in-memory list of ~20 issues with `team`, `status`, `severity`; one MCP server (`search_issues`, `count_open`, `create_issue`, `close_issue`, resource `runbook://{team}`, prompt `triage_issue`) used by a real model. Grows: stdio → local Streamable HTTP → OAuth with scopes (`issues:read`, `issues:write`) and PRM → second client (LangChain + vendor SDK/Inspector) → Tasks (long export/bulk-close) → MRTR elicitation ("close 40 issues?") → A2A `triage-agent` (classify/prioritise) and `fix-agent` (propose patch) with an orchestrator → AG-UI chat front end with approval interrupt → org scale: many tenants (team/org as `tenant` in A2A and as token claim), private registry of per-team MCP servers, gateway with per-tool authz, ID-JAG via IdP, audit log. Matches the source's capstone (Jira/GitHub/DB, triage + fix agents, human approval). Pros: everyone knows issues; toy data is visible; every protocol feature has a natural use (destructive tool → annotations/confirmation; long job → Tasks; clarification → input-required/MRTR; approval → AG-UI interrupt); injection demo is natural (malicious text in an issue body = tool-result injection, GitHub-MCP incident analogue). Cons: very common example, low novelty; keep schemas tiny to hold tool-catalog tokens down.
**B. "Pantry / recipe desk"**: tools = pantry stock + recipe search; pros: friendly, zero-risk data; cons: weak security story (no tenants, no destructive/exfil path), A2A split is artificial.
**C. "Library / equipment booking"** (reserve rooms/laptops): pros: natural multi-tenant (branches), natural AP2-style payment/deposit extension, long-running approvals (Tasks); cons: more domain rules to explain, less obvious prompt-injection surface.

---

## 12. Proposed requirements.txt and infrastructure

```
# core protocols
mcp>=2.3.0
fastmcp>=4.1.0              # pulled by langchain[mcp]; also used directly in a few lessons
a2a-sdk>=1.2.2              # optional extras: [grpc] [sqlite] [telemetry]
ag-ui-protocol>=1.0.0
# model access (kit standard)
langchain[mcp]>=1.4.4       # langchain.mcp.MCPAdapter (beta)
langchain-google-genai>=4.4.1
langgraph>=1.2.14
vcrpy>=8.3.0
python-dotenv>=1.0
# servers / auth / tests
uvicorn>=0.54.0
starlette>=1.7.0
fastapi>=0.143.0
httpx>=0.28.1
authlib>=1.8.0
pyjwt[crypto]>=2.15.1
pytest>=9.1.1
anyio
inline-snapshot             # optional
# vendor SDK lessons (pick per track 3)
anthropic>=1.13.0
openai>=3.29.0
google-genai>=2.29.0
# optional
openai-agents>=0.23.1       # mcp<3 compatible; httpx2 types under mcp v2
ag-ui-langgraph>=0.0.47     # AG-UI + LangGraph
copilotkit>=0.1.96          # optional front-end integration
agntcy-app-sdk>=0.5.5       # optional, Python >=3.12, read-along
```
Do **not** list `langchain-mcp-adapters` (archived, `mcp<2`). Use Python 3.12. Same venv as track 7 is compatible (mcp 2.3.0 there). The co-install of everything above except the optional lines was resolved in one venv (1.2). Needs versions of `inline-snapshot`, `pytest`, `anyio` not verified here.

Infrastructure to pin (all `needs-*` tagged):
- Node ≥22.19.0 and `npx @modelcontextprotocol/inspector@2.10.1` (needs-download).
- Docker: `quay.io/keycloak/keycloak:26.8.0` (`start-dev --features=cimd`; 26.8 adds RFC 8707 support experimental; 26.7.x lacks resource indicators — realm/compose files **untested**).
- kind v0.33.0 and Helm v4.3.0 (to install; VM has docker + kubectl only) for the gateway lab; agentgateway v1.6.0 (chart/image names UNVERIFIED — open `agentgateway.dev/docs/kubernetes/latest/documentation/quickstart` at build time).
- Optional: MCP Registry (public API read-only; do not self-host), `a2a-cli`.

`llm_replay` changes the lessons will need (for the kit author; not applied): (1) pass `ignore_localhost=True` (or `ignore_hosts`) to `vcr.VCR(...)`; (2) add `before_record_request` to normalise the Vertex project id in the URI and drop GCE metadata calls; (3) document "servers that call a model run in a thread in the notebook process"; (4) the `_paced` budget already ignores localhost.

---

## 13. Sources (URLs actually opened)

MCP: https://modelcontextprotocol.io/specification/versioning · /llms.txt · /specification/2026-07-28/changelog · /specification/2026-07-28/basic/authorization/index · /basic/authorization/security-considerations · /basic/transports/streamable-http · /basic/patterns/mrtr · /server/tools · /docs/2026-07-28/tutorials/security/security_best_practices · /docs/2026-07-28/tools/inspector · /extensions/overview · /extensions/tasks/overview · /extensions/apps/overview · /extensions/auth/enterprise-managed-authorization · /registry/about · /development/roadmap · /community/governance · /seps/2127-mcp-server-cards · https://blog.modelcontextprotocol.io/posts/2026-07-28/ · https://blog.cloudflare.com/mcp-v2/
Python SDK: https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/README.md · https://github.com/modelcontextprotocol/python-sdk/releases · https://github.com/modelcontextprotocol/python-sdk/tree/main/examples · https://py.sdk.modelcontextprotocol.io/ · /whats-new/ · /migration/ · /run/authorization/ · /run/deploy/ · /get-started/testing/ · /handlers/elicitation/ · /client/oauth-clients/ · /client/transports/ · https://gofastmcp.com/
LangChain: https://docs.langchain.com/oss/python/migrate/langchain-mcp-adapters · https://github.com/langchain-ai/langchain-mcp-adapters/issues/578
Vendors: https://platform.claude.com/docs/en/agents-and-tools/mcp-connector · https://developers.openai.com/api/docs/guides/tools-connectors-mcp · https://openai.github.io/openai-agents-python/mcp/ · https://ai.google.dev/gemini-api/docs/function-calling · https://raw.githubusercontent.com/googleapis/python-genai/main/README.md
A2A: https://a2a-protocol.org/latest/ · /specification/ · /whats-new-v1/ · /topics/agent-discovery/ · /blog/archive/2026/ · /blog/2026/08/27/a-new-chapter-for-a2a-joining-the-agentic-ai-foundation/ · /tutorials/python/1-introduction/ … /7-streaming-and-multiturn/ · /sdk/ · https://github.com/a2aproject/A2A/releases · https://github.com/a2aproject/a2a-python · https://opensource.googleblog.com/2026/04/a-year-of-open-collaboration-celebrating-the-anniversary-of-a2a.html · https://www.linuxfoundation.org/press/a2a-protocol-surpasses-150-organizations-lands-in-major-cloud-platforms-and-sees-enterprise-production-use-in-first-year
AG-UI: https://docs.ag-ui.com/introduction · /llms.txt · /concepts/events · /concepts/interrupts · /migrating-to-1-0 · /sdk/python/core/overview · /sdk/python/encoder/overview · /quickstart/server · /spec/1.0/basic/transports/http-sse · /development/updates · /agentic-protocols · https://github.com/ag-ui-protocol/ag-ui
Others: https://aaif.io/ · /about/ · /projects/ · https://aaif.io/blog/using-keycloak-as-an-mcp-authorization-server · https://www.linuxfoundation.org/press/linux-foundation-announces-the-formation-of-the-agentic-ai-foundation · https://agents.md/ · https://agentskills.io/ · /specification · https://agntcy.org/ · https://ap2-protocol.org/ · https://github.com/google-agentic-commerce/AP2/releases · https://www.fidoalliance.org/fido-alliance-to-develop-standards-for-trusted-ai-agent-interactions/ · https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/ · https://github.com/agentgateway/agentgateway · https://agentgateway.dev/docs/
Security/case studies: https://authzed.com/blog/timeline-mcp-breaches · https://thehackernews.com/2026/04/anthropic-mcp-design-vulnerability.html · https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks · https://invariantlabs.ai/blog/mcp-github-vulnerability · https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/ · https://goose-docs.ai/blog/2025/04/21/mcp-in-enterprise · https://www.uber.com/us/en/blog/designing-mcp-gateway/ · https://aws.amazon.com/blogs/opensource/governing-ai-assets-at-scale-with-mcp-gateway-and-registry/
Re-check 2026-10-12: https://modelcontextprotocol.io/development/roadmap · https://blog.modelcontextprotocol.io/ · https://www.keycloak.org/securing-apps/mcp-authz-server · GitHub API releases/commits for modelcontextprotocol, A2A, ag-ui, python-sdk, a2a-python, keycloak.
Registries/APIs queried: PyPI JSON for all packages in 1.2; npm registry (inspector, sdk, @ag-ui/core, @a2a-js/sdk); GitHub API (kind, helm, agentgateway, inspector, registry releases); quay.io API (keycloak tags). Web searches (snippets only, not cited as sources): CVE-2025-6514/49596 details (JFrog/Tenable/SD Times via search), 2026 CVE list (SentinelOne, CSA, Context7, Kong), Uber/Kong/Zuplo gateway listicles, Keycloak MCP docs (keycloak.org/securing-apps/mcp-authz-server — **not opened**), Outshift AGNTCY posts, The Register AGNTCY.

---

## 14. Source syllabus check (`SOURCE_SYLLABUS.md`)

Legend: ✅ confirmed · ⚠️ changed — current fact · ❌ wrong — correction.

### 14.1 Claim by claim

| # | Claim in source | Verdict | Current fact / correction (source) |
|---|---|---|---|
| 1 | "Current spec is the 2026-07-28 revision" | ✅ | Marked "Current" at modelcontextprotocol.io/specification/versioning; released 2026-07-28 (official blog). |
| 2 | "Headline change is a stateless protocol core, so a remote MCP server runs like an ordinary HTTP service" | ✅ | No `initialize`, no `Mcp-Session-Id`, per-request `_meta`, `server/discover`, header routing (`Mcp-Method`, `Mcp-Name`), cacheable lists; any worker can serve any request (changelog; Python deploy page; Cloudflare). Caveats the course must teach: breaking change for session-dependent servers; server→client requests replaced by MRTR; SSE not resumable; legacy (≤2025-11-25) clients still need sessions/stickiness. |
| 3 | "MCP is a Linux Foundation project" | ⚠️ | More precisely "Model Context Protocol a Series of LF Projects, LLC", hosted since 2025-12-09 by the **Agentic AI Foundation** (LF-directed fund); maintainers are individuals; Lead Maintainers Soria Parra & Delimarsky. |
| 4 | "Architecture: host, client, server; JSON-RPC 2.0; capability and version negotiation" | ⚠️ | Roles and JSON-RPC unchanged, but negotiation is no longer a handshake: version + capabilities ride on every request; `server/discover` is optional for clients, mandatory for servers; `UnsupportedProtocolVersionError`. |
| 5 | "Server primitives: tools, resources, prompts" | ✅ | Plus completion, pagination, caching hints, `structuredContent`/`outputSchema`. |
| 6 | "Client primitives: sampling, elicitation, roots" | ⚠️ | **Roots, Sampling and Logging are Deprecated** (SEP-2577; ≥12-month window). Elicitation stays (form + URL mode) but is delivered through Multi Round-Trip Requests, not server-initiated requests. Teach elicitation; mention the other two as legacy. |
| 7 | "Transports: stdio for local, Streamable HTTP for remote" | ✅ ⚠️ | Correct, but Streamable HTTP is now POST-only (no GET stream, no sessions, no resumability); HTTP+SSE formally Deprecated. Roadmap: Streamable HTTP over stdio. |
| 8 | "Authorization: OAuth 2.1, protected resource metadata, scoped tokens; never pass user tokens straight through" | ✅ | Confirmed and sharper: RFC 9728 PRM MUST, RFC 8707 `resource` MUST, PKCE S256, audience validation, passthrough forbidden. **Missing from the source:** Client ID Metadata Documents replace DCR (deprecated), RFC 9207 `iss` validation, step-up via `insufficient_scope`, enterprise-managed authorization (ID-JAG). |
| 9 | "Extensions framework: Tasks (long-running) and MCP Apps (interactive UI) ship outside the core spec" | ✅ | Tasks is `io.modelcontextprotocol/tasks` (moved out of core; polling `tasks/get`, `tasks/update`); MCP Apps is `io.modelcontextprotocol/ui` (`ui://`, sandboxed iframe). Also official: OAuth client-credentials, Enterprise-Managed Authorization, Skills over MCP; extensions are opt-in. |
| 10 | "The MCP Registry for discovering servers" | ✅ ⚠️ | Official registry is in **preview**, public servers only (private → own registry implementing its OpenAPI), namespace verification via DNS/GitHub, intended for aggregators not hosts. Also new: Server Cards (SEP-2127). |
| 11 | "MCP Inspector for debugging" | ✅ | v2.10.1 (npm, Node ≥22.19): web + `--cli` + `--tui` + experimental `mcpdo`. |
| 12 | "Security: tool poisoning, prompt injection through tool results, confused-deputy, over-broad scopes" | ✅ | Plus token passthrough, SSRF in discovery, mix-up, state-handle hijacking, local server compromise, STDIO command-execution CVEs (see 8.10). |
| 13 | "A2A reached v1.0 in March 2026, its first stable release" | ✅ | GitHub tag v1.0.0 = 12 Mar 2026; v1.0.1 late May 2026. (Some secondary guides say April — wrong.) |
| 14 | "governed by the Linux Foundation with over 150 supporting organisations" | ⚠️ | LF project since 2025-06-23; **since 2026-08-27 a Growth Stage project of AAIF**. "150+" is from the LF release of 2026-04-09 (Google blog the same month says "over 100"). |
| 15 | "Agent Card published at /.well-known/agent-card.json; signed cards for identity" | ✅ | Path confirmed (a2a-protocol.org agent-discovery; SDK serves it). Signing = JWS over RFC 8785-canonical JSON; SDK helpers exist. v1.0 card shape changed (`supportedInterfaces[]`). |
| 16 | "Tasks with a lifecycle (submitted, working, input-required, completed, failed)" | ❌ (incomplete) | v1.0 enum: `TASK_STATE_SUBMITTED, WORKING, COMPLETED, FAILED, CANCELED, REJECTED, INPUT_REQUIRED, AUTH_REQUIRED` (+`UNSPECIFIED`). Terminal: completed, failed, canceled, rejected. Interrupted: input_required, auth_required. Names are prefixed/uppercase in v1.0. |
| 17 | "messages, parts and artifacts" | ✅ | Parts are now a single oneof (`text|raw|url|data`); no `kind`. |
| 18 | "Streaming over SSE, push notifications, JSON-RPC, gRPC and REST bindings" | ✅ | Plus custom bindings, `ListTasks`, `SubscribeToTask`, multi-tenancy, `A2A-Version`/`A2A-Extensions` headers. |
| 19 | "Agents stay opaque" | ✅ | "opaque agentic applications" is the official phrase. |
| 20 | "AP2 (Agent Payments Protocol) for agent-initiated payments" | ⚠️ | Now **v0.2** (28 Apr 2026, Human-Not-Present flows) and **donated to the FIDO Alliance** (same day), no longer Google-run; current site documents Checkout and Payment mandates, each open/closed. Still an A2A/MCP extension. Adoption: early pilots (secondary). |
| 21 | "AG-UI: an event stream between agent backend and front end (text deltas, tool calls, state updates, human approvals)" | ✅ | Spec **1.0** (ag-ui-protocol 1.0.0, 2026-09-17). Human approval = interrupt outcome on `RUN_FINISHED` + `resume`. Not under AAIF; CopilotKit-led, MIT. Also reasoning, activity, subagent events. |
| 22 | "AGENTS.md and Agent Skills: conventions for giving coding agents project instructions and reusable know-how" | ✅ ⚠️ | AGENTS.md is an AAIF project (donated by OpenAI), 60k+ repos. Agent Skills (`SKILL.md`) was created by Anthropic and is an open standard at agentskills.io, supported by dozens of tools; distribution over MCP via the Skills extension. Not an AAIF project per aaif.io. |
| 23 | "AGNTCY: Linux Foundation infrastructure for agent discovery, identity and observability" | ✅ ⚠️ | Cisco donated to LF 2025-07-29; components Directory/OASF, Identity, SLIM, Observability/Evaluation SDKs, Secure Runtime, AgentBridge. Whether it is part of AAIF is disputed (Outshift says yes, aaif.io project list says no). |
| 24 | "Build: MCP server with OAuth connected to two clients; wrap two agents as A2A servers" | ✅ | Feasible on a laptop (6.1). |
| 25 | Cited docs: "MCP roadmap (Aug 2026)", "A2A one-year update (Google, Apr 2026)", "Linux Foundation A2A adoption announcement" | ✅ | Roadmap last updated 2026-08-22; Google Open Source Blog 2026-04-16; LF press release 2026-04-09. |
| 26 | Parent note: "Frameworks change every few months" (implicit: use LangChain adapters) | ⚠️ | `langchain-mcp-adapters` archived; use `langchain.mcp.MCPAdapter` (beta). |

### 14.2 Important topics the source misses (add to the syllabus)
- MCP 2026-07-28 mechanics: `server/discover`, `_meta` protocol/capability keys, MRTR (`InputRequiredResult`, `requestState` signing), `subscriptions/listen`, `ttlMs`/`cacheScope`, `Mcp-Method`/`Mcp-Name`/`x-mcp-header`, error-code allocation, legacy-era compatibility and migration.
- Feature lifecycle/deprecation policy, SDK tiering, conformance.
- Python SDK v2 API: `MCPServer`, `Client`, `Resolve/Elicit`, in-memory testing, `TokenVerifier/AuthSettings`, `OAuthClientProvider`, `TransportSecuritySettings`, `RequestStateSecurity`, `SubscriptionBus`, `httpx2`; FastMCP 4.
- Connecting MCP to models: `langchain.mcp.MCPAdapter`; Anthropic MCP connector and `async_mcp_tool`; OpenAI hosted `type:"mcp"` and Agents SDK; Gemini Interactions `mcp_server`; why `GenerateContentConfig(tools=[session])` is unreliable.
- Auth depth: CIMD vs DCR, `iss`/mix-up, step-up, enterprise-managed authorization (ID-JAG), client credentials extension, DPoP/WIF roadmap, Keycloak support matrix (26.7 vs 26.8), agent identity.
- Gateways/registries/Server Cards/AI Catalog; private registries; Uber, Block, Cloudflare, AWS patterns; agentgateway.
- A2A: extended cards, `AUTH_REQUIRED`/`REJECTED`, multi-tenancy, push-notification security, `A2A-Version`, a2a-sdk 1.x protobuf types, DB task stores, a2a-cli, A2A inside AAIF.
- AG-UI: concrete event catalogue, interrupt/resume contract, protobuf transport, A2UI/MCP Apps relation, `ag-ui-langgraph`.
- Real incidents/CVEs list (8.10.B) and OWASP Agentic Top 10.
- AAIF itself (who governs what), Agent Skills spec details, Skills over MCP.
- Record/replay of protocol traffic (6.1) — a kit-specific requirement.

### Verified for lesson 01 (2026-10-11, mcp 2.3.0, raw JSON-RPC over stdio)
- `MCPServer("Trackr").run()` defaults to stdio. Requests must carry `params._meta` with `io.modelcontextprotocol/protocolVersion` and `io.modelcontextprotocol/clientCapabilities` (clientInfo optional); missing key → `-32602` "params._meta is missing the required envelope key(s): …". Missing `params` entirely → `-32602` "Invalid request parameters" and the connection is then treated as handshake era (later 2026 requests rejected with `-32600`).
- `server/discover` result: `supportedVersions`, `capabilities` (prompts/resources/tools listed by default), `resultType:"complete"`, `cacheScope`, `ttlMs`, `_meta.io.modelcontextprotocol/serverInfo`.
- `tools/call` result: `content`, `structuredContent` (`{"result": …}` for an `int` return), `isError`; bad args / unknown tool → result with `isError:true` (not a JSON-RPC error). Unknown method → `{"code":-32601,"message":"Method not found","data":"<method>"}`. Unsupported version → `-32022` "Unsupported protocol version", `data:{supported, requested}`.
- Non-JSON lines are silently ignored (no `-32700` reply); `notifications/cancelled` gets no reply; replies to pipelined requests may arrive out of order (match by `id`). Server logs (rich) go to stderr.

### Host config files (lesson 05a, confirmed 2026-10-12)
- **Claude Desktop**: file `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS), `%APPDATA%\Claude\claude_desktop_config.json` (Windows); top key `mcpServers`; stdio entries `command`, `args`, optional `env`; no `type` field in the docs' examples. Full quit and restart to load. Remote servers are added in Settings > Connectors ("Add custom connector"), not in this file. Source: modelcontextprotocol.io/docs/develop/connect-local-servers and /connect-remote-servers.
- **Claude Code**: `.mcp.json` at project root (scope `project`, shared via git); top key `mcpServers`; stdio `type` `stdio` (no type = stdio) with `command`, `args`, `env`; `http` entries `type` `http` + `url` (+ optional `headers`); `sse` deprecated. Scopes: `local` (default, in `~/.claude.json` under the project path), `project`, `user` (`~/.claude.json`). Precedence local > project > user, whole entry replaced, not merged. Approval: confirmed 2026-10-12 — Claude Code prompts for approval in interactive sessions before using project-scoped `.mcp.json` servers (reset with `claude mcp reset-project-choices`); `claude -p`, Agent SDK and cloud sessions load them without asking; approvals in untrusted folders are ignored. Source: code.claude.com/docs/en/mcp (approval and scope sections, fetched 2026-10-12). Expansion `${VAR}` and `${VAR:-default}` in command, args, env, url, headers. Source: code.claude.com/docs/en/mcp.
- **VS Code (Copilot agent mode)**: `.vscode/mcp.json` uses top key **`servers`**, not `mcpServers`. Stdio: `type` (required) `stdio`, `command`, `args`, `env`, `envFile`, `cwd`. HTTP: `type` `http` (or `sse`), `url`, `headers`, `oauth`. `inputs` array (`promptString`, `pickString`, `command`) and `${input:id}` for secrets. User-profile file via command "MCP: Open User Configuration". Source: code.visualstudio.com/docs/copilot/customization/mcp-servers and /reference/mcp-configuration.
- **Cursor**: project `.cursor/mcp.json`, global `~/.cursor/mcp.json`; top key `mcpServers`; stdio `command`, `args`, `env` (type optional in examples); remote entries use `url` (+ `headers`, optional `auth` with `CLIENT_ID`, `CLIENT_SECRET`, `scopes`); interpolation `${env:NAME}`, `${userHome}`, `${workspaceFolder}`, `${pathSeparator}`. Source: cursor.com/docs/mcp (redirect from docs.cursor.com/context/model-context-protocol).
- Teaching point: the top key and the entry shape differ by host, so one Python dict renders four files, and a validator catches the wrong key before the host does.

## 15. Lesson 06 checks (run locally, mcp 2.3.0, langchain 1.4.4)
- `MCPServer.run("streamable-http", host="127.0.0.1", port=8766, json_response=True, transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=[...], allowed_origins=[...]))` serves `POST /mcp`; `json_response=True` returns plain `application/json` replies (SDK `mcp/server/mcpserver/server.py` run overloads; confirmed with a scratch probe and by the lesson 06 run).
- POST with `Mcp-Name` that disagrees with `params.name` → HTTP 400, JSON-RPC `-32020` ("mcp-name header does not match the request body's 'name' parameter") (SDK `mcp/shared/inbound.py`, `HEADER_MISMATCH`).
- POST with an `Origin` not in `allowed_origins` → HTTP 403, plain text "Invalid Origin header"; a POST with no `Origin` header is allowed (SDK `mcp/server/transport_security.py`, "Origin can be absent").
- GET `/mcp` → 405 Method Not Allowed. `server/discover` answers with `supportedVersions: ["2026-07-28"]`.
- `MCPAdapter({"mcpServers": {"trackr": {"url": URL}}})` with one server publishes bare tool names (`count_open`); the `{server}_` prefix appears only when several servers are configured (lesson 05).

## 16. Lesson 14 checks (review fix round)
- `anthropic.lib.tools.mcp.async_mcp_tool(tool, session)` returns a `BetaAsyncFunctionTool`; `await tool.call(input)` runs the MCP tool with no model (checked in the installed `anthropic` 1.13.0 source, `lib/tools/mcp.py` and `lib/tools/_beta_functions.py`).
- Passing an MCP session in `GenerateContentConfig(tools=[session])`: the sync `generate_content` refuses it before any network call, and `aio.models.generate_content` fails with `TypeError: cannot pickle '_asyncio.Task' object` (observed locally, google-genai in the topic venv, 2026-10-12). The python-genai MCP guide describes this built-in MCP support as experimental (mirror: mintlify.com/googleapis/python-genai/guides/mcp-support). A blog post says the example is marked for the Gemini Developer API only, not Vertex; not confirmed against Google's docs.

## 17. Lesson 16 checks (OAuth client flow, run locally, mcp 2.3.0, authlib 1.8.0)
Confirmed in the installed package source (`.venv/.../mcp/client/auth/oauth2.py`, `utils.py`, `authlib/oauth2/rfc7636/challenge.py`, `authlib/oauth2/rfc9207/`), and by running the flow end to end against a local AS (Authlib + Starlette) and Trackr on 127.0.0.1:8768:
- `OAuthClientProvider(server_url, client_metadata, storage, redirect_handler, callback_handler, client_metadata_url=..., validate_resource_url=None)` is a `httpx2.Auth`. Use it as `httpx2.AsyncClient(auth=provider)`, then `Client(streamable_http_client(URL, http_client=http))`. `Client` takes a transport, not `auth=`.
- Sessions are anyio task groups: keep one `Client` per cell or per call, not across notebook cells. Tokens survive in `TokenStorage`.
- `TokenStorage` (4 async methods): `get_tokens`, `set_tokens`, `get_client_info`, `set_client_info`.
- `AuthorizationCodeResult(code, state, iss)`: the callback handler returns it; the SDK validates `iss` against the AS issuer (RFC 9207, `validate_authorization_response_iss`).
- CIMD: `client_metadata_url` must be an **https** URL with a non-root path (`is_valid_client_metadata_url`); used only if AS metadata has `client_id_metadata_document_supported: true`. The SDK does not fetch it; the AS does. The lab's AS holds a copy (no HTTPS offline).
- Step-up: a `403` with `WWW-Authenticate` `error="insufficient_scope"` makes the SDK run authorization again with the union of the previous and the challenged scopes (SEP-2350), calling `redirect_handler` a second time. Verified: second authorize `scope=issues:read issues:write`.
- Authlib 1.8 has no Starlette/ASGI authorization server. Use its primitives: `authlib.oauth2.rfc7636.challenge.create_s256_code_challenge` / `compare_s256_code_challenge` (the module path `authlib.oauth2.rfc7636` alone does not export the compare function), and `authlib.jose.jwt.encode(header, claims, key)` (returns bytes).
- Per-operation 403: the SDK's `required_scopes` only answers 403 for the server-wide scope. Lesson 16 wraps `mcp.streamable_http_app(json_response=True)` in an ASGI gate that reads the JSON-RPC body and answers 403 for `close_issue` without `issues:write`.

**Lesson 16 review fix (2026-10-12).** `authlib.jose` is deprecated (AuthlibDeprecationWarning). The lesson signs the dev JWT with joserfc instead: `from joserfc import jwt`, `from joserfc.jwk import OctKey`, `jwt.encode({"alg": "HS256"}, claims, OctKey.import_key(DEV_KEY))`, which returns a `str` (no `.decode()`). Checked by running it in the venv (joserfc 1.7.5): PyJWT verifies the token with the same key, audience and issuer. Sources: joserfc guide `github.com/authlib/joserfc/blob/master/docs/guide/jwt.rst`; migration guide `jose.authlib.org/en/migrations/pyjwt`; PyPI `pypi.org/project/joserfc/`. `authlib.oauth2.rfc7636` stays (PKCE helpers).

## 18. Lesson 27 checks (testing and Inspector, run locally, Node v26.4.0, pytest 9.1.1, anyio 4.15.1)
- Inspector CLI (docs: modelcontextprotocol.io/docs/2026-07-28/tools/inspector/cli, fetched 2026-10-12): `npx -y @modelcontextprotocol/inspector@2.10.1 --cli <command> [args] --method tools/list --format json`; HTTP uses `--server-url <url> --transport http` (or a positional URL with `--transport http`). Methods include `tools/list`, `tools/call --tool-name X --tool-arg k=v`. `--format json` prints one JSON object with no banner. Exit codes: 0 success, 1 usage/unexpected, 3 auth required, 4 unreachable, 5 tool error or tool not found, 6/7/8/9 CI gates (`--strict`, `--verify`). Non-zero exits write one JSON line to stderr (`{"error": {...}}`). `--stored-auth-only` for CI.
- Confirmed live: the command above against `apps/03/trackr_server.py` exited 0 and listed `count_open`, `search_issues`, `create_issue`, `close_issue` (about 16 s with the npm download).
- Web: `npx @modelcontextprotocol/inspector` prints a URL with a per-launch token; `MCP_AUTO_OPEN_ENABLED=false` stops the browser opening. Secrets stored in OS keychain or unencrypted `~/.mcp-inspector/secrets.json` on headless Linux.
- In-process tests: `Client(mcp, raise_exceptions=True)`; an unknown tool name returns `is_error=True` with text `Unknown tool: <name>` (no exception). `call_tool` returns a `CallToolResult` (attributes, not a dict). `model_dump(mode="json", by_alias=True)` gives the wire names (`destructiveHint`); Python attribute is `annotations.destructive_hint`.
- Pytest output in the notebook: pass `--color=no` or the FAILED lines carry ANSI codes.
- a2a-cli (repo github.com/a2aproject/a2a-cli, fetched 2026-10-12): Go binary, Apache 2.0, not a Python package. Install: `brew tap a2aproject/a2a-cli https://github.com/a2aproject/a2a-cli && brew install a2a`, `winget install a2aproject.a2acli`, `go install github.com/a2aproject/a2a-cli@latest` (binary named `a2a-cli`, rename to `a2a`), or release binaries. Commands: `a2a card get <url>`, `a2a send -a <url> "<text>"`, `a2a send -a <url> --stream "<text>"`. No card-validation command on the page. Not installed on this VM, so not run live.
- Conformance and SDK tiers: Python SDK is Tier 1 (listed in section 2 of this file, from the docs). Not run live.

## 19. Lesson 29 checks (tool poisoning, run locally, mcp 2.3.0, langchain 1.4.4)
- `MCPServer.tool(name, title, description, annotations, ...)`: passing `description=` overrides the docstring, so a server can publish a different description per version (used by the weather server's `WEATHER_VERSION` switch). Confirmed with `inspect.signature` on the installed SDK.
- `Client(StdioServerParameters(...)).list_tools()` returns a `ListToolsResult`: use `.tools`. Each Python `Tool` has `name`, `description`, `input_schema`, `annotations` (`model_dump(by_alias=True, exclude_none=True)` gives `readOnlyHint`/`destructiveHint`).
- `MCPAdapter` with two servers in `mcpServers` names tools `{server}_{tool}` (`trackr_search_issues`, `weather_get_forecast`); with one server it keeps the plain name. The adapter's LangChain tools have no `input_schema` or `annotations`, so fingerprints must come from `tools/list` through `Client`.
- A model can answer with a tool call that has no text: the defended run in lesson 29 returned a `search_issues` call and an empty `text`. Print `tool_calls` as well as `text`.
- Sources for the cases: Invariant Labs tool-poisoning write-up (2025-04-01); postmark-mcp (Koi Security / Snyk reporting, version 1.0.16, September 2025: a copy of the Postmark mail library that BCC'd every email to the attacker's server).

## 20. Lesson 30 checks (prompt injection through tool results, run locally, mcp 2.3.0, langchain 1.4.4)
- `MCPAdapter` returns a list-valued tool result as one text block with one JSON object per item and no separator (`{...}{...}`), not a JSON array. Parse it item by item (`json.JSONDecoder().raw_decode`), or read the structured payload from the ToolMessage `artifact` (`structured_content.result`). Confirmed by running the Trackr server through the adapter.
- `ToolAnnotations(openWorldHint=True)` is accepted by the installed SDK; the lesson uses it on the outbound tool to mark an external destination. Annotations are the server's claim and do not enforce anything.
- Recorded with gemini-3.1-flash-lite (6 real calls, budget 6): the model followed the hidden comment in issue 13 in the attacked run and asked for `reports_post_report` with the list (including a customer email) as the body. Another model may ignore the comment; the lesson says so.
- Sources for the case: Simon Willison, "The lethal trifecta" (2025-06-16, simonwillison.net/2025/Jun/16/the-lethal-trifecta/); Invariant Labs, GitHub MCP toxic agent flow (2025-05-26, invariantlabs.ai/blog/mcp-github-vulnerability).

## 21. Lesson 33 checks (production checkpoint, run locally, mcp 2.3.0, langchain 1.4.4, pyjwt 2.15.1, httpx 0.28.1)
- `langchain.mcp.MCPAdapter` with one server in `mcpServers` keeps plain tool names (`list_issues`, `post_report`); with two or more it prefixes them (`trackr_list_issues`). The checkpoint's reader and sender each hold one server, so their names are plain. Confirmed by running the notebook.
- `jwt.encode(payload, key, algorithm="HS256")` (PyJWT 2.15.1) returns a `str`. Lesson 16's `gate` reads the `Authorization` header, so a read-only token can be minted in code for the in-process check.
- `httpx.ASGITransport(app=...)` calls an ASGI app in process with no server and no lifespan. The gate answers `403` before the MCP app runs, so the check needs no running Trackr. The app is only ever called with a token that lacks the write scope.
- A model can ask for a tool the host did not offer (recorded with gemini-3.1-flash-lite, attack B: `reports_post_report` from the reader). The host must refuse it. The checkpoint prints `REFUSED` rather than running it.
- Recording: 5 real model calls for the checkpoint (budget 6). The syllabus entry says 8 planned; the lesson uses fewer because the protocol-only attack needs no model call.
- Sources: the MCP and OAuth details are the same as lessons 16, 29, 30 and 31 (see sections 17, 19 and 20 above); the lesson adds no new spec claim.

## Notes added while writing lessons

### Lesson 04
## 22. Lesson 04 checks (resources, templates, prompts, completion, paging; run locally, mcp 2.3.0, langchain 1.4.4)
- High-level `MCPServer` has no paging switch: `resources/list` returned every static resource in one reply. Paging was added by registering `resources/list` on `mcp._lowlevel_server.add_request_handler("resources/list", PaginatedRequestParams, handler)` (the same hook the `@mcp.completion()` decorator uses in `mcp/server/mcpserver/server.py`). Handler returns `ListResourcesResult(resources=..., next_cursor=...)`. Verified: page 1 gives 2 resources and `nextCursor "2"`, page 2 gives the third and no cursor.
- Template parameters typed with a `Literal` fail pydantic validation before the function runs and come back as `-32603` (`UnexpectedResourceError`). Typing the template parameter as `str` and raising `MCPError(code=INVALID_PARAMS)` (`-32602`) for an unknown team gives the clean invalid-params error. Source: `mcp/server/mcpserver/resources/templates.py` (`create_resource` re-raises `MCPError`).
- Prompt arguments arrive as strings on the wire (`"issue_id": "4"`); a `ValueError` raised in the prompt function comes back as `-32603`; raising `MCPError(code=INVALID_PARAMS)` gives `-32602` (verified).
- `completion/complete` params: `ref` (`{"type":"ref/prompt","name":...}` or `{"type":"ref/resource","uri":"runbook://{team}"}`), `argument` `{name, value}`; result `completion` `{values, total, hasMore}`. Types `PromptReference`, `ResourceTemplateReference`, `Completion` are in `mcp.types`.
- `INVALID_PARAMS` (-32602) and `INTERNAL_ERROR` are exported from `mcp.types`; `MCPError` is in `mcp.shared.exceptions`. No `RESOURCE_NOT_FOUND` constant exists in the SDK (2026-07-28 uses -32602 for resource not found, see section 4).
- Client-side helpers: `Client.list_resources(cursor=...)`, `list_resource_templates`, `read_resource`, `list_prompts`, `get_prompt`, `complete` (mcp/client/client.py). The notebook uses raw JSON-RPC like lesson 03.
- Sources: https://modelcontextprotocol.io/specification/2026-07-28 (server resources, prompts, completion, pagination pages); local SDK source at mcp 2.3.0 as above.

### Lesson 07a
## Lesson 07a checks (legacy era; run locally, mcp 2.3.0 in the topic venv)
- Python SDK "Serving legacy clients" page (https://py.sdk.modelcontextprotocol.io/v2/run/legacy-clients/): `Client(url, mode="legacy")` runs the `initialize` handshake; the default negotiates 2026-07-28. `mcp.streamable_http_app(stateless_http=True)` affects only the legacy leg. Legacy sessions live in a per-process dict: with more than one worker, legacy clients need sticky routing or they get HTTP 404. `ctx.elicit()` works only on legacy connections; `Resolve` works on both eras. Under `stateless_http=True` server-initiated requests raise `NoBackChannelError`. `mcp.run(...)` accepts `stateless_http` (checked in installed source).
- Installed mcp 2.3.0 source: `ConnectMode = Literal["legacy", "auto"] | str`; a version string other than 2026-07-28 passed as `mode` raises `ValueError` ("'2025-11-25' is a handshake-era version; use mode='legacy'"). The `-32022` code is the constant `mcp_types.UNSUPPORTED_PROTOCOL_VERSION`; the SDK raises it as `mcp.shared.exceptions.MCPError` (`UnsupportedProtocolVersionError` is the spec name, `mcp_types.UnsupportedProtocolVersionError` the wire model). In `mode="auto"` the probe falls back to `initialize` on any MCPError except a modern-only `-32022`.
- Observed on the lesson 03 Trackr server (apps/07a worker, mcp 2.3.0): legacy `initialize` returns 200 with `Mcp-Session-Id` (sticky) and no session id (stateless); `tools/list` with that session on another sticky worker returns 404 `Session not found` (code -32600); a sticky worker refuses a versionless request without a session with 400 `Missing session ID`; a stateless worker answers `tools/list` with the 2025-11-25 header and no session with 200; `notifications/initialized` returns 202.
- Deviation from the entry: the entry suggested an mcp 1.x side venv for a true old-era server. Not built: the v2 server's legacy leg speaks the same 2025-11-25 wire, so the lesson uses it (download avoided).

### Lesson 07b
## Lesson 07b checks (subscriptions/listen; run locally, mcp 2.3.0, httpx 0.28.1)
- SDK source (mcp 2.3.0, installed in the topic venv): `mcp/shared/subscriptions.py` (`SUBSCRIPTION_ID_META_KEY = "io.modelcontextprotocol/subscriptionId"`, event types `ToolsListChanged`, `PromptsListChanged`, `ResourcesListChanged`, `ResourceUpdated`), `mcp/server/subscriptions.py` (ack is the first frame, `notifications/subscriptions/acknowledged`; the listen request id is the subscriptionId; no replay; abrupt drop ends the stream), `mcp/client/subscriptions.py` (`listen()` raises `SubscriptionLost` on an abrupt drop; "no automatic re-listen").
- Wire: `POST /mcp` with method `subscriptions/listen`, params `notifications` (camelCase `toolsListChanged`, `resourcesListChanged`, `resourceSubscriptions`) and `_meta`. Without `text/event-stream` in Accept the server answers HTTP 406 (`streamable_http_modern.py`). The response is SSE (`data:` lines) even with `json_response=True`.
- Server side: `MCPServer` registers the listen handler by default. Inside a tool, `await ctx.notify_tools_changed()` and `await ctx.notify_resource_updated(uri)` publish events; `mcp.add_tool(fn, name=...)` adds a tool at run time.
- Observed: `resources/read` needs an `Mcp-Name` header equal to the `uri` parameter, or the server returns -32020.
- Honored filter: the server echoed back the subset it agreed to (requested `resourcesListChanged` was honored).
- Sources: local SDK files above; https://modelcontextprotocol.io/specification/2026-07-28 (subscriptions/listen, already listed in section 3 of this file).

### Lesson 09
## Lesson 09 checks (A2A task lifecycle; run locally, a2a-sdk 1.2.2, Python 3.12, Gemini via llm_setup; 2026-10-12)
- `TaskState` has 9 values: `TASK_STATE_UNSPECIFIED`, `SUBMITTED`, `WORKING`, `COMPLETED`, `FAILED`, `CANCELED`, `INPUT_REQUIRED`, `REJECTED`, `AUTH_REQUIRED`. Terminal: COMPLETED, FAILED, CANCELED, REJECTED. Interrupted: INPUT_REQUIRED, AUTH_REQUIRED (verified in SDK enum and `DefaultRequestHandler` TERMINAL_TASK_STATES).
- `TaskUpdater` methods in 1.2.2: `start_work`, `requires_input(message=)`, `requires_auth`, `add_artifact(parts, name=)`, `complete`, `failed`, `reject`, `cancel`, `update_status`, `new_agent_message(parts)`. A message with a known taskId continues the task; the task history gets the user and agent messages (`TaskManager` appends status messages to `task.history`).
- Client: `get_task(GetTaskRequest(id, history_length))`, `list_tasks(ListTasksRequest(context_id=…))` returns `.tasks`, `cancel_task(CancelTaskRequest(id))`, `subscribe(SubscribeToTaskRequest(id))` (needs `ClientConfig(streaming=True)` and a server with streaming; otherwise NotImplementedError). The first subscribe event is the task snapshot.
- Cancelling a COMPLETED task raises `TaskNotCancelableError` ("Task cannot be canceled") on the client.
- Raw JSON-RPC error for an unknown task: HTTP 200, `error.code` -32001, `message` "Task not found", `data[0]` = `@type` `type.googleapis.com/google.rpc.ErrorInfo`, `reason` `TASK_NOT_FOUND`, `domain` `a2a-protocol.org`. JSON-RPC method names are PascalCase (`GetTask`).
- An agent that uses no extension does not echo the `A2A-Extensions` header in its reply.
- **llm_replay caveat (important):** while `llm_replay` is active (record or replay), a streamed `SubscribeToTask` on a non-terminal task hangs until the client timeout (`A2AClientTimeoutError`), even with `ignore_localhost=True`. The same call works with no recorder. Lesson 09 therefore reattaches from a second process (`apps/09/resubscribe.py`). Other lessons with open-ended SSE streams under llm_replay should expect the same.
- Recording: 4 model calls (issue 4 ask, issue 4 answer, issue 9 streamed, issue 1 paused). Replay runs with `TUT_LLM_MODE=replay` and needs no key.

### Lesson 12
## Lesson 12 checks (elicitation with MRTR; run locally, mcp 2.3.0, langchain-core 1.6.9)
- Installed `mcp` 2.3.0 source: `mcp/server/mcpserver/resolve.py` defines `Resolve(fn)`, `Elicit(message, schema)`, `Sample`, `ListRoots`; a resolver may return `Elicit`; `Annotated[ElicitationResult[T], Resolve(fn)]` gives accept/decline/cancel. On 2026-07-28 the question rides `InputRequiredResult` (`input_requests` / `request_state`). Verified by running the lesson.
- `mcp/server/request_state.py`: `RequestStateSecurity(keys=[...])` (AES-256-GCM, keys[0] seals), `RequestStateSecurity.ephemeral()` (process-local key), `ttl` default 600 s; `MCPServer(..., request_state_security=...)`. A tampered token returned `-32602 "Invalid or expired requestState"` (HTTP 400) in the run.
- A modern request without `io.modelcontextprotocol/clientCapabilities` in `_meta` returned `-32602` naming the missing envelope key (run output), not `-32021`.
- Client: `Client(url, elicitation_callback=fn)`; default `mode="auto"` drives the MRTR loop; `input_required_max_rounds` default 10; `call_tool(..., input_responses=, request_state=)` for manual loops (mcp_types `InputResponses = dict[str, InputResponse]`, `InputRequests = dict[str, InputRequest]`).
- `ElicitRequestURLParams` fields: meta, mode, message, url, elicitation_id, task (serialises `elicitationId`). The server side of URL mode is not exposed through `Resolve`/`Elicit` in mcp 2.3.0 (only `Context.elicit_url`, which is the server-initiated path), so lesson 12 shows the URL request shape and does not run it.
- `langchain.mcp.MCPAdapter` answers elicitation with a LangGraph interrupt, so lesson 12 drives the model with the plain `mcp` Client and a LangChain `StructuredTool`.
- Sources: https://py.sdk.modelcontextprotocol.io/v2/handlers/elicitation/ · https://py.sdk.modelcontextprotocol.io/v2/handlers/multi-round-trip/ · https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/mrtr (listed in section 13) · installed package source.

### Lesson 13
## Lesson 13 checks (extensions, progress, cancellation; run locally, mcp 2.3.0 in the topic venv)
- Extensions: `mcp.server.extension.Extension` (set `identifier` as `vendor-prefix/name`); `MCPServer(extensions=[...])` advertises each id under `capabilities.extensions` in `server/discover`. Source: `mcp/server/extension.py`, `mcp/server/mcpserver/server.py` (`_apply_extension`). Verified: the probe server listed `example.trackr/progress-detail`.
- Client opt-in: `_meta["io.modelcontextprotocol/clientCapabilities"]["extensions"][id] = {}` on the requests that want it. Inside a tool, `ctx.client_capabilities` exposes it (`mcp/server/apps.py` reads the same field). Verified: with opt-in the progress message names the batch; without it the message is None.
- Progress: the server reads `params._meta.progressToken` (`mcp/shared/jsonrpc_dispatcher.py`, `progress_token_from_params`) and `await ctx.report_progress(n, total, message)` sends `notifications/progress` on the response stream. Verified with `json_response=False` (SSE replies).
- Cancellation over HTTP: when the client closes the response, `watch_disconnect` in `mcp/server/_streamable_http_modern.py` cancels the handler's task group, so the tool gets `CancelledError`. Verified: the handler's `finally` ran at the batch the client had reached, and the count stopped (checked twice, 2.5 s apart). `notifications/cancelled` POSTs are accepted and ignored on the 2026-07-28 HTTP path (same file, docstring).
- Caveat: with `llm_replay` active (vcrpy), streamed local responses are buffered until the body ends, so a live stream reads all events at once. The lesson calls `llm_replay.stop()` after its one model call. Verified by experiment.
- Sources: local SDK source in the topic venv (mcp 2.3.0); the 2026-07-28 spec pages already listed in section 2 of this file (basic/patterns, extensions overview).

### Lesson 19
## Lesson 19 checks (AG-UI human approval; run locally, ag-ui-protocol 1.0.0, ag-ui-langgraph 0.0.47, langgraph 1.2.14; 2026-10-12)
- Classes verified by introspection in the topic venv: `ag_ui.core` exports `RunFinishedInterruptOutcome` (type `interrupt`, `interrupts`), `Interrupt` (id, reason, message, tool_call_id, response_schema, expires_at, metadata) and `ResumeEntry` (interrupt_id, status `resolved|cancelled`, payload, metadata); `RunAgentInput.resume` takes a list of `ResumeEntry`.
- `ag_ui_langgraph` 0.0.47: `LangGraphAgent(..., emit_interrupt_outcome=True)` is the opt-in for the structured outcome (default False). `add_langgraph_fastapi_endpoint(app, agent, path)` adds `POST path` and `GET path/health`. A single resolved entry becomes `Command(resume=payload)`; a cancelled entry becomes `Command(resume={<cancelled sentinel>: True, "interrupt_id": id})`, so the node must test for an explicit approval rather than for the sentinel.
- The interrupt reason comes from the interrupt value: if the value is a dict with `reason`, it is used; otherwise the adapter writes `langgraph:interrupt`. The value's `message` and `tool_call_id` (or `toolCallId`) are copied too.
- Observed: the adapter emits `RAW`, `STEP_*`, `STATE_SNAPSHOT` and a final `MESSAGES_SNAPSHOT`. Text produced by a node with `ainvoke` (not streamed) appears only in the snapshot, not as `TEXT_MESSAGE_CONTENT`. A real model call streamed text in the run output. Tool calls showed as `TOOL_CALL_START` with the name, and the tool result appears in the snapshot.
- Observed: a resume with an id the thread does not hold, on a finished thread, returns `RUN_FINISHED` with no node run and no error (the spec only says a missing resume on a paused thread is an error).
- Spec (docs.ag-ui.com/concepts/interrupts, fetched 2026-10-12): `outcome.interrupts` non-empty; resume must cover every open interrupt (partial resumes unsupported); a `cancelled` entry is still required in the array and has no payload; an identical resume "must be safe to replay"; a resume with the same id but a different status or payload is not specified.
- Recording: 3 real model calls (run 1 picks `close_issue`, run 2 writes the answer after approval, run 3 picks `close_issue` on a second thread). Replay with `TUT_LLM_MODE=replay` passes with no key.

### Lesson 21
## Lesson 21 checks (AGENTS.md and Agent Skills; 2026-10-12)

- Agent Skills spec (https://agentskills.io/specification): `name` 1-64 chars, lowercase letters, digits and hyphens, no leading/trailing or doubled hyphens, must match the parent directory name; `description` 1-1024 chars; optional `license`, `compatibility` (1-500 chars), `metadata` (string map), `allowed-tools` (experimental). Progressive disclosure: name+description (~100 tokens) at startup, body (<5000 tokens recommended, <500 lines) on activation, `scripts/ references/ assets/` on demand. Validation via `skills-ref validate ./my-skill`.
- skills-ref on PyPI: `skills-ref` 0.1.1 ("Reference library for Agent Skills"), requires Python >=3.11; installed into the topic venv (3.12). Python API: `from skills_ref import validate, read_properties`; `validate(Path)` returns a list of error strings, empty means valid. CLI `skills-ref validate <dir>` exits 1 on errors. Source: skills-ref package source (skills_ref/validator.py, cli.py); the GitHub README says "intended for demonstration purposes only".
- Skills extension (https://modelcontextprotocol.io/extensions/skills/overview; SEP-2640 Final): id `io.modelcontextprotocol/skills`; servers MUST declare `resources` plus the extension in `server/discover` and implement `skills/list` and `skills/get`; files are served via `resources/read` at `skill://<name>/...` URIs; manifest entries carry SHA-256 digest and size per file; unknown URI returns -32602. SDK support is still being implemented per the page, so the lesson builds the listing entry by hand. mcp 2.3.0 (topic venv) has no `skills/list` handler (grep of the package).

### Lesson 24
## Lesson 24 checks (tool catalogs; run locally 2026-10-12, mcp 2.3.0, Gemini gemini-3.1-flash-lite via llm_setup, recorded)
- MCPServer.tool(name=, title=, description=, annotations=) accepts an explicit name and description (checked with inspect.signature in the topic venv). The lesson registers 5 to 60 closure-built tools this way (apps/24/catalog_server.py).
- In-process Client(server).list_tools() returns tools with input_schema. The lesson sends type-function entries (name, description, parameters) to bind_tools; the reply usage_metadata input_tokens is the model own count.
- Recorded run (4 model calls): 3 of 3 expected tool names at 5, 20 and 60 tools; input tokens 225, 708, 1972; 60 tools with long descriptions 7852. One run with three requests is not an accuracy measurement.
- A naive merge by bare name of the issues search and the runbooks search gives 6 names for 7 tools, with no error; namespaced server_tool keeps 7.
- Production claims come from RESEARCH.md section 7 (Cost / context) and section 8.12 (Uber MCP gateway, 800+ servers, 5,000+ tools).

### Lesson 13a
## Lesson 13a checks (MCP Tasks extension; run locally, mcp 2.3.0 in the topic venv, Gemini via llm_setup; 2026-10-12)
- Wire format, from the 2026-07-28 schema (`https://raw.githubusercontent.com/modelcontextprotocol/ext-tasks/main/schema/2026-07-28/schema.ts`, read 2026-10-12):
  - `Task`: `taskId`, `status` (`working` | `input_required` | `completed` | `failed` | `cancelled`), `statusMessage?`, `createdAt`, `lastUpdatedAt`, `ttlMs` (integer ms from creation; `null` = unlimited; the server may discard the task after it), `pollIntervalMs?`.
  - `CreateTaskResult` = `Result & Task & { resultType: "task" }` (flat fields, not wrapped in `task`).
  - `tasks/get` params `{ taskId }`; result `GetTaskResult` with `resultType: "complete"`; `completed` carries `result`, `failed` carries `error`, `input_required` carries `inputRequests`.
  - `tasks/cancel` params `{ taskId }`; empty result; cancellation is cooperative and eventually consistent.
  - `tasks/update` params `{ taskId, inputResponses }`; keys must match outstanding `inputRequests`.
  - `notifications/tasks` carries a full `DetailedTask`; it is opted into through `subscriptions/listen`.
  - Opt-in: `io.modelcontextprotocol/tasks` in `_meta["io.modelcontextprotocol/clientCapabilities"].extensions` per request; the server advertises it in `server/discover`; "never return a task to a client that did not declare support" (https://modelcontextprotocol.io/extensions/tasks/overview, read 2026-10-12).
- mcp 2.3.0 has the Tasks models (`mcp.types.CreateTaskResult`, `Task`, `GetTaskResult`, `CancelTaskRequestParams`, `TaskStatus` literal of the five statuses) but their aliases are the older shape (`task` wrapper, `ttl`, `pollInterval`, `statusMessage`), and there is no server-side task loop in the package (only a docstring in `mcp/server/extension.py` names `tasks/get`). The lesson therefore writes the server by hand (`apps/13a/trackr_export_server.py`, stdlib only). fastmcp 4.1.0 ships task utilities (`fastmcp/utilities/tasks.py`), not used here.
- Verified locally: with the opt-in `export_issues` returns `{resultType: task, taskId, status: working, ttlMs: 600000, pollIntervalMs: 300}`; without it the same call returns the CSV after the whole 3-second export; `tasks/get` moves working → completed with `result`; `tasks/cancel` returns `{}` and the status becomes `cancelled` with the batch where it stopped.
- Recorded: 2 model calls (tool choice `export_issues` with `{format: csv, team: web}`; one-sentence summary). The local JSON-RPC calls are in the same cassette because `llm_replay` records every HTTP call; the notebook makes them in one fixed order so replay matches.
- Review fix round (2026-10-12), checked against the official spec:
  - Spec pages: https://github.com/modelcontextprotocol/ext-tasks (schema `schema/2026-07-28/schema.ts`, SEP-2663) and https://modelcontextprotocol.io/extensions/tasks/overview (read 2026-10-12).
  - `Task` fields: `taskId`, `status`, `createdAt`, `lastUpdatedAt`, `ttlMs` (number or null, required); `statusMessage?` and `pollIntervalMs?` optional. The lesson's field names match.
  - `tasks/get` result is `GetTaskResult` = `DetailedTask & { resultType: "complete" }`; `completed` carries `result`, `failed` carries `error`.
  - `tasks/cancel` result is `CancelTaskResult` = `Result & { resultType: "complete" }`, an empty acknowledgement. The lesson's server now returns `{"resultType": "complete"}` (it returned `{}` before). `tasks/update` params are `{taskId, inputResponses}`; the lesson does not run it.
  - The spec defines `resultType: "complete"` on plain results too, so the plain `export_issues` reply now carries it.
  - `mcp` 2.3 `mcp_types`: `CreateTaskResult` has a `task` wrapper; `Task` uses `ttl` and `poll_interval`; there are `GetTaskPayloadRequest` and `ListTasksRequest`. These are the older experimental shape, so the lesson does not use them.
  - Not in the spec, lesson choices: the `export_issues` tool and its schema, batch count and status texts, and the internal `cancel` flag (never on the wire).

### Lesson 23a
## Lesson 23a checks (retries, idempotency and deadlines; run locally 2026-10-12, mcp 2.3.0, a2a-sdk 1.2.2, ag-ui-protocol 1.0.0, Gemini via llm_setup, recorded: 4 model calls)

- MCP stdio: when the client's call is cancelled (asyncio timeout around `call_tool`), the stdio transport sends the cancel and the server handler gets `CancelledError`. Verified: a 30 s tool under a 1.5 s client timeout logged `CANCELLED` on the server.
- A2A SDK 1.2.2 does not deduplicate on `Message.messageId`: `grep` of the `a2a/server` package finds no dedupe logic. An agent that must not repeat work stores its answer under the incoming `messageId` itself.
- A2A `ClientConfig` has `httpx_client`; the default client timeout is shorter than a 10 s deadline plus grace. Pass an `httpx.AsyncClient(timeout=60)` for deadline demos (verified: a 5 s `A2AClientTimeoutError` before the fix).
- A2A request metadata: `SendMessageRequest.metadata` is a protobuf `Struct` (`request.metadata.update({...})`); the agent reads it as `context.metadata` (dict).
- AG-UI `RunAgentInput` field `forwarded_props` (alias `forwardedProps`) carries app-level values such as an operation id and a deadline.
- llm_replay caveat: vcr records and replays every httpx request, including requests to the notebook's own localhost servers. In replay, the servers do not run, so state kept in a server process (counters, log files) is not reproduced. The lesson prints only results that come back in responses or from the stdio Trackr process.
- Stripe API idempotency (fetched 2026-10-12, https://docs.stripe.com/api/idempotent_requests): the `Idempotency-Key` header on POST requests; the first request's status and body are saved; keys can be pruned after at least 24 hours; the server compares incoming parameters and errors if a reused key has different ones.

## Checks added in the 23a fix round (2026-10-12)

- a2a-sdk dedupe check (installed a2a-sdk 1.2.2 in this topic's .venv, `.venv/lib/python3.12/site-packages/a2a`): `grep -i message_id` over `a2a/server/request_handlers/`, `a2a/server/tasks/` and `a2a/server/routes/` finds no messageId dedupe. The only `message_id` hits are `TaskUpdater` generating ids for its own outgoing messages. Conclusion: the SDK does not dedupe on an incoming `Message.messageId`; the lesson's agent stores its own answers (`ANSWERS`).
- Stripe idempotency, re-fetched 2026-10-12 from https://docs.stripe.com/api/idempotent_requests:
  - `Idempotency-Key` header: all POST requests accept it (API v1); GET and DELETE should not send it.
  - Keys can be removed automatically after they are at least 24 hours old ("we can remove keys from the system automatically after they're at least 24 hours old"). A reused key after pruning is treated as a new request.
  - The idempotency layer compares incoming parameters to the original and errors if they differ.
  - For API v1 Stripe saves the status code and body of the first request made with the key, after endpoint execution begins; retries with the same key return the saved response.

### Lesson 27a
## Lesson 27a checks (tool-selection evals; run locally 2026-10-12, mcp 2.3.0, vcrpy 8.3.0, langchain-core via langchain-google-genai, Gemini gemini-3.1-flash-lite via llm_setup, recorded: 2 model calls)
- `MCPServer.tool(name=, description=)` takes the description from a file (apps/27a/eval_server.py). Argument validation is on: a string for an integer argument returns `is_error=True` with a pydantic validation message and no structured content.
- `vcr.use_cassette(path, ignore_localhost=True)` (vcrpy 8.3.0) lets a localhost request go live and saves 0 requests; with the option off the same request is saved (1 request). Checked with a local `ThreadingHTTPServer` on 127.0.0.1:9270, with and without an active `llm_replay` recorder: nesting works.
- The topic's `llm_replay.py` does not pass `ignore_localhost` to `vcr.VCR(...)` (the line-11 note in section 1 of this file says it does; the file was not changed). Lesson 27a does not depend on the flag: its eval server runs in process with no HTTP.
- `convert_to_openai_tool(<mcp Tool>)` raises `ValueError: Unsupported function`: the model needs the dict form `{"type": "function", "function": {...}}`.
- Recorded run: v1 descriptions 8 of 8 right, 428 input tokens; v2 (close_issue and archive_issue texts swapped, a copy-paste slip) 6 of 8 right (requests 4 and 6 answered with the other tool), 335 input tokens. A merged-description rewrite ("Change an issue's state." for close, reopen and archive) still scored 8 of 8 in a live probe, so it was not used.

### Lesson 31b
## Lesson 31b checks (AG-UI endpoint security; 2026-10-12)
- AG-UI Run Input spec 1.0 (https://docs.ag-ui.com/spec/1.0/basic/run-input.md): `state` is "the consumer's last agreed value"; "An absent `state` means the empty object". `tools` are "frontend tools": "The application executes them, not the agent." `forwardedProps` is "An application-specific channel passed through to the agent untouched. The protocol attaches no meaning to the payload." The page has no statement on authentication, authorization, CORS or endpoint security, so the endpoint must provide them.
- AG-UI Python types page (https://docs.ag-ui.com/sdk/python/core/types): RunAgentInput fields thread_id, run_id, parent_run_id, state, messages, tools, context, forwarded_props (alias forwardedProps), resume. "Backend-defined tools should stay in the backend agent or framework configuration." Message roles include developer, system, assistant, user, tool, activity, reasoning, so a client can send system messages unless the server refuses them.
- Observed (ag-ui-protocol 1.0.0, FastAPI 0.143, pyjwt 2.15.1, run in the topic venv): a `text/plain` body with JSON content to a RunAgentInput route returns 422 in FastAPI; the same body as application/json returns 200 with the forged state, the system role and the smuggled tool echoed. PyJWT `jwt.decode(token, key, algorithms=["HS256"])` on a token that has an `aud` claim raises InvalidAudienceError "Invalid audience"; with a wrong audience argument it raises "Audience doesn't match".
- Starlette CORSMiddleware (starlette 1.7.0): CORS headers only; a disallowed origin gets no Access-Control-Allow-Origin header on a preflight, so the browser blocks reading the reply. It does not reject the request, so the server-side Origin check is separate.
- Quote check (lesson 31b, 2026-10-12): the lesson now paraphrases the AG-UI spec in its own words instead of quoting it; the source remains https://docs.ag-ui.com/spec/1.0/basic/run-input.md.

### Lesson 32a
## Lesson 32a checks (protocol and description releases; run locally 2026-10-12, mcp 2.3.0, a2a-sdk 1.2.2, Gemini gemini-3.1-flash-lite via llm_setup, recorded: 4 model calls)
- Feature lifecycle: a Deprecated feature stays deprecated for at least twelve months (measured from the revision that marks it Deprecated) before it is eligible for removal; the expedited path needs an active security risk, Core Maintainer approval and still gives at least ninety days. Trackr adopts the twelve-month floor as its own policy. Source: https://modelcontextprotocol.io/community/feature-lifecycle (read 2026-10-12).
- `Deprecation` header (RFC 9745, Standards Track, March 2025): an Item Structured Header holding a Date, example `Deprecation: @1688169599`; it is the date the resource was or will be deprecated. `Sunset` (RFC 8594) is optional, gives the date the resource stops responding, uses HTTP-date format and must not be earlier than `Deprecation`. Verified by the run: `Deprecation: @1791763200`, `Sunset: Tue, 12 Oct 2027 00:00:00 GMT`. Source: https://www.rfc-editor.org/rfc/rfc9745.html (read 2026-10-12).
- A2A-Version: a missing header is read as 0.3. Source: a2a-sdk 1.2.2 `a2a/utils/version_validator.py` (`validate_version`: "If the header is missing or empty, it is interpreted as PROTOCOL_VERSION_0_3"). The A2A "what's new in v1" page does not define the default, so it is not cited for it. A version with a different major number is refused with error -32009 `VERSION_NOT_SUPPORTED` (ErrorInfo reason). Verified by the run.
- `enable_v0_3_compat=True` on `a2a.server.routes.create_jsonrpc_routes` answers `message/send` on the same endpoint as `SendMessage`; without it the 0.3 method returns -32601 "Method not found". Verified by the run.
- `RequestStateSecurity(keys=[...])` (mcp 2.3.0, `mcp/server/request_state.py`): `keys[0]` seals, every key unseals; the docstring gives the rotation order `[old, new]`, then `[new, old]`, then `[new]` after one TTL; default ttl 600 s. A token sealed with an unknown key raises `InvalidRequestState: unknown key` in the codec. Verified by the run.
- Release endpoint: one `/mcp` route serves both eras (`Client(url, mode="legacy")` negotiates 2025-11-25, `Client(url)` negotiates 2026-07-28, same six tools). The middleware adds the headers to legacy replies (request `MCP-Protocol-Version: 2025-11-25`, or a reply that creates an `Mcp-Session-Id`).
- Sources for the 27a descriptions reused here: `apps/27a/descriptions_v1.json` and `descriptions_v2.json` (27a recording: v2 scored 6 of 8).

### Lesson 29a
## Lesson 29a checks (sandboxing stdio servers; run locally 2026-10-12, Docker 27.5.1 on Debian 12, python:3.12-slim-bookworm, mcp 2.3.0 in the image)
- Docker flags used: `--network none`, `--read-only`, `--tmpfs /tmp`, `--cap-drop ALL`, `--security-opt no-new-privileges`, `--pids-limit`, `--memory`, `-v <file>:/app/server.py:ro`, no `-e`. The image runs as uid 10001 (`USER` in the Dockerfile). Checked by running the lesson's cells.
- The notebook's `--read-only` check: `open('/app/x.txt','w')` in a read-only root fails with a non-zero exit (run in the build loop).
- CVE and incident facts in lesson 29a's At work section are taken from RESEARCH.md §8.10.B (secondary sources, NVD not opened). Phrase them as "reported".

### Lesson 34
## Lesson 34 checks (Keycloak 26.8.0 in Docker, run locally 2026-10-12; mcp 2.3.0, joserfc, PyJWT 2.15.1, cryptography 50.0.2)
- Image `quay.io/keycloak/keycloak:26.8.0` pulled and run with `start-dev --features=cimd,resource-indicators --import-realm --hostname=http://127.0.0.1:8340`. The log warns that both features are experimental. Discovery at `/realms/<realm>/.well-known/openid-configuration` lists `client_id_metadata_document_supported: true` and `code_challenge_methods_supported: [plain, S256]`.
- Resource indicators: `resource` is accepted only if a client has the attribute `resource_url` with that value and the realm allows it; otherwise the token step answers `invalid_target`. A token requested with `resource=` has `aud` = that one URL. Without `resource` the audience comes from the Audience mappers (`aud` = client ids).
- CIMD executor configuration keys (read from `keycloak-services-26.8.0.jar`, the `ClientIdMetadataDocumentExecutor` classes): `cimd-allow-http-scheme`, `cimd-allow-permitted-domains`, `cimd-restrict-same-domain`, `cimd-resource-indicator-allow-list`, `only-allow-confidential-client`, `accept-public-client-with-confidential-client-only-grant`. The condition `client-id-uri` uses `client-id-uri-scheme` and `client-id-uri-allow-permitted-domains`. Without the policy the client ID is refused as `client_not_found` and the document is never fetched.
- The Keycloak server fetches the document only if the client ID's host is trusted and the redirect URI's host is trusted too (`not trusted domain` otherwise). The document's `client_id` must equal the URL exactly; its `grant_types` must include `refresh_token`, or Keycloak issues no refresh token (`use.refresh.tokens` false). Scopes requested must be in the document's `scope` or in the realm's default optional scopes.
- A CIMD login may show a consent page (required action `OAUTH_GRANT`) the first time; a repeat login with the same scopes goes straight to the redirect.
- The realm import accepts `clientProfiles`, `clientPolicies`, `defaultOptionalClientScopes`, `accessTokenLifespan` (300 s used), `revokeRefreshToken: true`, `refreshTokenMaxReuse: 0`. A reused refresh token answers 400 `invalid_grant` ("Maximum allowed refresh token reuse exceeded").
- Keycloak sets its login cookies `Secure`; Python's cookie jar does not send them to `http://127.0.0.1`. The lesson keeps the cookies itself.
- MCP SDK `OAuthClientProvider` accepts only https client-ID URLs (`is_valid_client_metadata_url`); the lab's http document therefore runs with a small client written in the notebook (PKCE, `resource`, `iss` check, refresh rotation).
- Refresh token lifetime in the lab: 1800 s (`refresh_expires_in`), access token 300 s.
- Sources: https://www.keycloak.org/securing-apps/mcp-authz-server (features, resource indicators, CIMD client profile, Audience mapper; read 2026-10-12); the Keycloak 26.8.0 image's own `kc.sh build --help` (feature names); the classes named above.

## Lesson 34 fix round (2026-10-12): sources checked
- Keycloak MCP authorization server guide (https://www.keycloak.org/securing-apps/mcp-authz-server, read 2026-10-12): CIMD is "an experimental feature" and resource indicators are "an experimental feature" (both may change in later versions). The client ID URL "MUST have an `https` scheme (unless Allow http scheme is enabled)"; that option "must be OFF in a production environment". The page does not say whether `plain` PKCE is refused, so the lesson says only that Keycloak still advertises `plain` and a production realm must force S256.
- PyJWT API docs (https://pyjwt.readthedocs.io/en/stable/api.html, PyJWKClient): the whole key set is cached by default (`cache_jwk_set=True`, `lifespan` 300 s). Per-key caching (`cache_keys`) is off by default. An unknown `kid` forces one refetch, but only after `cooldown_duration` (default 30 s); "a newly rotated key may therefore wait for the cooldown period".
- Keycloak server administration guide, "Configuring realm keys > Rotating keys" (https://www.keycloak.org/docs/latest/server_admin/index.html): add a new key pair with a higher priority, keep the old one passive so it can verify earlier signatures, remove it once nothing uses it; suggests new keys every 3 to 6 months and deleting old ones 1 to 2 months later. Whether old keys stay in the JWKS during rotation is not stated in the part read.

### Lesson 28
## Lesson 28 checks (observability; run locally 2026-10-12, mcp 2.3.0, a2a-sdk 1.2.2, opentelemetry-sdk 1.45.1, Gemini gemini-3.1-flash-lite via llm_setup)

- **MCP trace context (spec).** `_meta` reserved keys `traceparent`, `tracestate`, `baggage`, values in W3C Trace Context and W3C Baggage formats, "for compatibility with OpenTelemetry semantic conventions for MCP"; non-normative example with `"traceparent": "00-0af7…-00f0…-01"` in `tools/call`. Source: https://modelcontextprotocol.io/specification/2026-07-28/basic/index (fetched 2026-10-12, section "General fields / _meta").
- **MCP SDK does it automatically.** `mcp/shared/_otel.py` (`inject_trace_context`, `extract_trace_context`), `mcp/shared/jsonrpc_dispatcher.py` (outbound span `MCP send <method>` injects into `_meta`), `mcp/server/_otel.py` (`OpenTelemetryMiddleware`: server span per inbound message, parent from `_meta`). Verified: a Streamable HTTP `tools/call` shows client and server spans with the same trace id (lesson 28 run).
- **a2a-sdk telemetry.** `a2a/utils/telemetry.py`: spans on decorated handlers, enabled by default when OpenTelemetry is installed; disable with `OTEL_INSTRUMENTATION_A2A_SDK_ENABLED=false` (any value other than 'true' disables). A2A does not inject `traceparent` into HTTP headers itself: lesson 28 adds an httpx request hook and an ASGI middleware (source: a2a-sdk 1.2.2 package, `a2a/utils/telemetry.py`; verified in the lesson run).
- **Streamable HTTP app in-process.** `mcp.streamable_http_app(json_response=True)` needs its lifespan running (`app.router.lifespan_context(app)`); without it a POST fails with "Task group is not initialized". Lesson 28 holds the lifespan open in a task (verified).
- **llm_replay recorder and local calls (finding).** vcrpy 8.x patches `handle_async_request` of httpx and httpx2 `ASGITransport` as well as the socket transports (`vcr/patch.py` lines 99–137). Local ASGI calls are therefore recorded unless the lesson calls the saved original method (the lesson 22 `SocketTransport` pattern). A recording attempt without this stored every local call ("not in cassette, sending to real server"). Lesson 28 uses `LocalASGI`/`LocalASGI2` for this.
- **Lesson 22 orchestrator gate (finding for reviewers).** `apps/22/orchestrator.py` `gate()` reads `tool_calls[0]` and then `call['args']['issue_id']`. When a model reply holds `classify_issues` and `close_issue` together, the gate reads the classify call and raises `KeyError: 'issue_id'`. Lesson 28's question asks for the close alone in its own reply. Lesson 22's own question should say the same.

## Lesson 28 record note (2026-10-12)
- Lesson 28's approval question now says: step 1 classify_issues alone in its reply; step 2 close_issue as ONE tool call alone in its own reply. The record run with this wording passed R1-R8 (3 model calls, cassette `data/llm_cassettes/28_observability.yaml`).
- Reviewer: lesson 22's own question should use the same "close alone" wording (its gate reads tool_calls[0]); not changed here (lesson 22 file).

## Lesson 32 checks (deploying protocol services; run locally 2026-10-12, Docker 27.5.1 with Compose v5.2.0, nginx 1.27.5-alpine, python:3.12-slim-bookworm, a2a-sdk 1.2.2, mcp 2.3.0, Gemini gemini-3.1-flash-lite via llm_setup, recorded: 1 model call)
- **a2a-sdk 1.2.2 has no task TTL.** `DatabaseTaskStore` (`a2a/server/tasks/database_task_store.py`) has save/get/list/delete and nothing that expires tasks. Lesson 32 runs its own sweep on `TaskModel` (`a2a/server/models.py`: `id`, `status` JSON, `last_updated` DateTime) and deletes only terminal states.
- **Multi-replica streaming in the SDK:** `a2a.server.cluster` exports `VersionedDatabaseTaskStore(engine)` and `DatabaseTaskEventStream(engine)` (`a2a/server/cluster/database_task_store.py`, `database_event_stream.py`; both create their tables with `initialize()`). `DefaultRequestHandler` is `DefaultRequestHandlerV2` in 1.2.2 and warns when a `VersionedTaskStore` has no `event_stream`, so the lesson passes both. The event stream is polled, which is how a replica streams a task another replica runs.
- `TaskUpdater.update_status(state, message=...)`, `add_artifact(parts, name=...)`, `complete()`; `create_agent_card_routes(card)`, `create_jsonrpc_routes(handler, "/")` (checked with `inspect.signature`).
- **mcp 2.3.0:** `MCPServer(name, version=..., log_level=...)` (the default INFO logs flood the notebook); `streamable_http_app(json_response=True, transport_security=TransportSecuritySettings(allowed_hosts=[...], allowed_origins=[...]))`; the lesson lists `host:*` patterns next to the bare hosts. Health and MCP mount under one FastAPI app; the mounted apps' lifespans are run from the parent lifespan (`mcp.router.lifespan_context(mcp)`), and the database tables are created there too.
- **Finding for reviewers: llm_replay intercepts every HTTP call of its own process.** In replay mode, a local `httpx.get` and a `urllib` request to `127.0.0.1` both raise `CannotOverwriteExistingCassetteException`, because `llm_replay.start` has no localhost exemption (checked on the topic's `llm_replay.py`). Lesson 32 therefore makes all of its own local calls in `apps/32/probe.py` (a child process), and its replicas are uvicorn processes that record and replay their own model call. Any lesson that calls its own servers from the notebook process in replay mode will hit this.
- **Docker:** `docker compose up -d` returns before the apps listen; nginx answers 502 for a replica that is still starting. The lesson polls each replica's published port, then the proxy, and again after `restart trackr-b`.
- **Measured (median of 200 `GET /healthz`, two runs):** direct to a replica 3.1–3.4 ms; through nginx 4.0–4.3 ms; added 0.6–0.9 ms. Round-robin: both replicas answer through the proxy.
- **Stream across a replica restart (run locally, process path):** a stream on replica a shows SUBMITTED, WORKING, COMPLETED while replica b is stopped and started; replica b then reads the completed task from the shared SQLite file (`classified by: model`).
- Image: `python:3.12-slim-bookworm` plus `mcp==2.3.0`, `a2a-sdk[http-server,sqlite]==1.2.2`, `fastapi==0.143.0`, `uvicorn==0.54.0`; the container runs as root because it writes the bind-mounted SQLite file (lab only, noted in `infra/32/Dockerfile`).
- Sources: the installed packages in `topics/agentic-ai-4-protocols/.venv/lib/python3.12/site-packages/` (a2a-sdk 1.2.2, mcp 2.3.0); the local `llm_replay.py`; Docker Hub `nginx:1.27.5-alpine` and `python:3.12-slim-bookworm` (pulled here).

### Lesson 35
## Lesson 35 checks (agent identity: client credentials and token exchange; 2026-10-12)

- MCP extension `io.modelcontextprotocol/oauth-client-credentials`: client credentials for machine-to-machine MCP access; client secret or RFC 7523 JWT assertion; the client sends the bearer token on each request; prefer JWT assertions; secrets must be rotated and scoped. Source: https://modelcontextprotocol.io/extensions/auth/oauth-client-credentials (opened 2026-10-12).
- SDK (mcp 2.3.0 installed in the topic venv): `mcp.client.auth.extensions.client_credentials.ClientCredentialsOAuthProvider(server_url, storage, client_id, client_secret, token_endpoint_auth_method="client_secret_basic", scope=None, issuer=None)`. The parameter is `scope`; the public docs example uses `scopes`, which the installed 2.3.0 code does not take. `issuer` is deprecated when omitted (MCPDeprecationWarning, required in 3.0). Source: installed `client_credentials.py`.
- RFC 8693 token exchange: `grant_type=urn:ietf:params:oauth:grant-type:token-exchange`; `subject_token` and `subject_token_type` required; `actor_token` with `actor_token_type` optional; `resource`, `audience`, `scope`, `requested_token_type` optional. Response: `issued_token_type` (required), `access_token`, `token_type`, `expires_in` (recommended), `scope` when applicable. `act` claim (section 4.1) names the actor and nests for prior actors. Source: https://www.rfc-editor.org/rfc/rfc8693.html (opened 2026-10-12).
- The lesson uses a local stand-in authorization server (no Docker, no Keycloak): Keycloak's token-exchange support was not verified for this lesson, so it was not used.

### Lesson 37
## Lesson 37 checks (securing A2A; run locally 2026-10-12, a2a-sdk 1.2.2, PyJWT 2.15.1, cryptography, Python 3.12)
- `a2a.utils.signing`: `create_agent_card_signer(signing_key, protected_header, header=None)` returns a function that appends one `AgentCardSignature` to the card; `create_signature_verifier(key_provider, algorithms)` returns a function that raises `NoSignatureError` (no signatures) or `InvalidSignaturesError` (no valid signature). The key provider is called as `key_provider(kid, jku)` inside the verifier's PyJWT `try`, so raising `jwt.InvalidKeyError` for an unknown kid makes that signature count as invalid (verified).
- Signed content is the RFC 8785 canonical JSON of the card with `signatures` removed and empty values cleaned. Changing any field after signing (checked: the URL) fails with `InvalidSignaturesError`.
- Forgeries refused (verified): unsigned card (`NoSignatureError`); tampered signed card, look-alike signed with another key under the same kid, unknown kid, HS256 header with the pinned key (all `InvalidSignaturesError`).
- PyJWT 2.15.1 refuses to use a PEM public key as an HMAC secret (`InvalidKeyError: ... should not be used as an HMAC secret`), at signing and at verification. So the HS256 key-confusion forgery fails in the library; the algorithm allow-list is still the policy control.
- Card types (protobuf): `SecurityScheme(oauth2_security_scheme=OAuth2SecurityScheme(flows=OAuthFlows(client_credentials=ClientCredentialsOAuthFlow(token_url, refresh_url, scopes))))`; `AgentCard.security_schemes` is a map (set with `.CopyFrom`); `security_requirements` is a list of `SecurityRequirement(schemes={name: StringList(list=[...])})`; `AgentSkill.security_requirements` exists; `AgentCapabilities.extended_agent_card`.
- Server: `DefaultRequestHandler(..., extended_agent_card=, extended_card_modifier=async (card, ServerCallContext) -> AgentCard)`. The SDK does not check credentials itself; the context carries `state["headers"]` (lowercase keys) from the HTTP request. Auth is the application's job (the lesson wraps the ASGI app).
- Client: `create_client(agent, client_config, interceptors=[AuthInterceptor(store)])`; `InMemoryContextCredentialStore.set_credentials(session_id, scheme_name, credential)`; the call passes `ClientCallContext(state={"sessionId": ...})`. `AuthInterceptor` adds `Authorization: Bearer` for an `http` bearer or OAuth2/OIDC scheme found in the card's `security_requirements`. `Client.get_extended_agent_card(GetExtendedAgentCardRequest(), context=..., signature_verifier=...)`.
- `A2ACardResolver.get_agent_card(signature_verifier=...)` raises the verifier's error to the caller.

### Lesson 38
## Lesson 38 checks (multi-tenant MCP servers and A2A agents; run locally 2026-10-12, a2a-sdk 1.2.2, mcp 2.3.0, Gemini gemini-3.1-flash-lite via llm_setup, recorded: 4 model calls)
- A2A tenant field (installed a2a-sdk 1.2.2): `AgentInterface.tenant` and `SendMessageRequest.tenant` exist. The JSON-RPC dispatcher copies the body's tenant into `call_context.tenant` (`a2a/server/routes/jsonrpc_dispatcher.py`, line ~311); `RequestContext.tenant` exposes it to an executor. On the client, `TenantTransportDecorator` fills an empty request tenant from the chosen interface and keeps an explicit one (`a2a/client/transports/tenant_decorator.py`). Verified: a request whose tenant is `api` with a `web` token is refused by the executor (TASK_STATE_FAILED).
- The executor reads headers from `context.call_context.state["headers"]` (lowercase keys). `TaskUpdater.failed(message)` takes a pb Message.
- MCP (mcp 2.3.0): a tool result has `is_error`; `Tool.input_schema` lists the parameters. A tool called with an extra argument (`tenant`) ignores it: the tool still uses the token's tenant (verified). A `ToolError` reaches the client as `Error executing tool <name>: <message>`.
- Measured once on this machine (40 concurrent calls from one tenant, 20 sequential calls from another, 2 worker slots, 30 ms each): quotas on: 2 ran, 38 refused, other tenant median 49 ms, worst 259 ms; quotas off: 40 ran, median 50 ms, worst 804 ms. Numbers vary by run; the lesson reports them as measured.
- Sources: installed SDK source above; RESEARCH.md section 8.9 (Asana MCP cross-tenant flaw, June 2025, and A2A `tenant` field usage); RESEARCH.md section 8.14 (Uber MCP Gateway, 800+ servers, 5,000+ tools, tools start disabled).

### Lesson 38a
## Lesson 38a checks (multi-hop delegation; run locally 2026-10-12, a2a-sdk 1.2.2, mcp 2.3.0, PyJWT 2.15.1, joserfc 1.7.5, httpx2 2.13.1)
- A2A server request headers: `a2a/server/routes/common.py` stores `state['headers'] = dict(request.headers)` on the call context, so an AgentExecutor reads the caller's bearer token from `context.call_context.state["headers"]` (lowercase keys). Checked in the installed package.
- A2A client: `ClientConfig(httpx_client=httpx.AsyncClient(headers={"Authorization": ...}))` sends the token on every request of that client; one client per hop. Checked in the installed package signature (`ClientConfig.httpx_client: httpx.AsyncClient | None`).
- RFC 8693 section 4.1: the new token's `act` names the current actor and nests the previous `act` inside it, so a three-hop token carries `act.sub` for the newest actor and `act.act.sub` for the one before. Source: https://www.rfc-editor.org/rfc/rfc8693.html (opened 2026-10-12, same source as lesson 35).
- RFC 8693 section 4.1 (fixes round, 2026-10-12, opened https://www.rfc-editor.org/rfc/rfc8693.html): "The outermost `act` claim represents the current actor while nested `act` claims represent prior actors." Access control: a resource MUST only consider the token's top-level claims and the party identified as the current actor; "Prior actors identified by any nested `act` claims are informational only." Section 4.1 sets no maximum length or depth for the nested chain.
- RESEARCH.md section 8 (Enterprise and scale, L6), item 3 "Audience & passthrough": never forward the inbound token; exchange it (RFC 8693) for the next audience. Cited in the 38a At real scale bullets.

### Lesson 39
## Lesson 39 checks (organisation-wide authorization checkpoint; run locally 2026-10-12, Docker 27.5.1, Keycloak 26.8.0 image, mcp 2.3.0, a2a-sdk 1.2.2, joserfc, PyJWT 2.15.1, httpx2 2.13.1, Gemini gemini-3.1-flash-lite via llm_setup, recorded: 2 model calls)
- Keycloak standard token exchange (docs, read 2026-10-12: https://www.keycloak.org/securing-apps/token-exchange): feature `token-exchange-standard:v2` (on by default in 26.8); the calling client must be confidential with the "Standard token exchange" switch on (attribute `standard.token.exchange.enabled`). Standard V2 takes `grant_type`, `subject_token`, `subject_token_type`, `requested_token_type`, `scope`, `audience`. It does NOT take `resource` ("does not yet have support for the `resource` parameter"). It does not describe an `act` claim or nested actor chains; delegation (`actor_token`, `may_act`) is preview and needs FGAP v2. Public clients and subject impersonation are not supported in V2.
- Live behaviour of the realm in `infra/39/` (Keycloak 26.8.0, run 2026-10-12): the exchange is refused with `403 access_denied, "Client is not within the token audience"` when the subject token's `aud` does not name the caller; refused with `400 invalid_request, "Requested audience not available: <client>"` when no requested scope maps to the target audience; refused with `400 invalid_scope, "Invalid scopes: ..."` for a scope the caller does not hold (the client's default or optional scopes). The subject's scope is not checked against the requested scope in this build: a hop may request a scope the subject token lacks if the caller holds it, so the scope limit is the caller's list, not the subject's grant.
- Audience mapper: a client scope with protocol mapper `oidc-audience-mapper` and `included.client.audience` = a client id adds that client id to `aud` when the scope is requested. Keycloak sends a single string when there is one audience.
- `sub` comes from the `basic` client scope (`oidc-sub-mapper`). A realm import that lists its own client scopes must include `basic` in the client's default scopes, or the password-grant token has no `sub`.
- Group membership mapper (`oidc-group-membership-mapper`, full.path false) gives the teams claim; realm role mapper (`oidc-usermodel-realm-role-mapper`) gives roles; `oidc-usermodel-property-mapper` gives `preferred_username`.
- Client secrets for confidential clients can be set after import with `PUT /admin/realms/<realm>/clients/<id>` with `secret` (HTTP 204), so no secret sits in the realm file.
- Password grant (`directAccessGrantsEnabled` on a public client): used in lesson 39 only as a short lab sign-in; a wrong password gives `400 invalid_grant`.
- Sources: https://www.keycloak.org/securing-apps/token-exchange (read 2026-10-12); https://www.keycloak.org/securing-apps/mcp-authz-server (lesson 34, resource indicators and CIMD, experimental); lesson 34 and lesson 35 notes in this file.
- Replay note (llm_replay/vcr): during a recording window, httpx calls to local servers (Keycloak, Trackr, the A2A agent) are recorded and replayed too, as in lesson 38a. Lesson 39 keeps its live checks (matrix, step-up, refusals, ship check) outside the window.

## Lesson 39 fix round (2026-10-12): realm isolation source
- Keycloak server administration guide, "Configuring realms" and "Core concepts and terms" (https://www.keycloak.org/docs/latest/server_admin/index.html, read 2026-10-12): "A realm is a space where you manage objects, including users, applications, roles, and groups." "One Keycloak deployment can define, store, and manage as many realms as there is space for in the database." "Realms are isolated from one another and can only manage and authenticate the users that they control." "A user belongs to and logs into a realm." The page does not say whether a user of one realm can log in to another; the lesson relies only on the isolation sentence.
- The lab realm's `accessTokenLifespan` is 300 s (infra/39/realm-ops-org.json), so a team change reaches Trackr's decisions within 300 s of the next token issue. This is the window the Decision guide quotes.
- The RFC 8693 §4.1 nested `act` statement is in lesson 38a's checks above; lesson 39 cites it only for the nested form, not for Keycloak's output.

# Agentic AI 4: Protocols — MCP, A2A, AG-UI — source syllabus

Track 4 of the roadmap in `topics/agentic-ai/ROADMAP.md` (parent: `topics/agentic-ai/SOURCE_SYLLABUS.md`, Level 4). Enterprise checklist items owned by this track: 10 (security: OAuth, scopes, tool poisoning, agent identity). Item 1 is "N/A — covered in track agentic-ai-5-multi-agent", item 13 "N/A — covered in track agentic-ai-9-frontier", and every other item "N/A — covered in track agentic-ai-6-production".

Prerequisites: tracks 1–3 (LLM foundations and the agent loop; agent patterns, memory and RAG; frameworks — LangGraph + one vendor SDK).

User decision for this track: LLM-based throughout. A real model drives every example where an agent or model acts, core and basic lessons included; no scripted dummy models. Calls are recorded with llm_replay so lessons run without a key. Low cost: at most 2 model calls per example.

Course-wide notes from the parent:
Prerequisites: basic Python (functions, classes, async), JSON and HTTP, Git. No ML theory is needed until Level 7.
Rule of thumb: build every pattern by hand once before using a framework for it. Frameworks change every few months; the loop underneath does not.

Level 4: Protocols — MCP, A2A, AG-UI
Goal: understand the three interfaces of an enterprise agent. MCP connects an agent to tools and data, A2A connects an agent to other agents, and AG-UI connects an agent to the user's screen.
MCP and A2A are complementary, not rivals: an agent uses MCP to call tools it controls, and A2A to hand work to another agent it does not control.
MCP (Model Context Protocol)
The current spec is the 2026-07-28 revision. Its headline change is a stateless protocol core, so a remote MCP server now runs like any ordinary HTTP service. MCP is a Linux Foundation project.
• Architecture: host app, MCP client, MCP server; JSON-RPC 2.0 messages; capability and version negotiation
• Server primitives: tools (actions), resources (readable data), prompts (templates)
• Client primitives: sampling (server asks the model), elicitation (server asks the user), roots
• Transports: stdio for local servers, Streamable HTTP for remote ones
• Authorization: OAuth 2.1, protected resource metadata, scoped tokens; never pass user tokens straight through
• Extensions framework: opt-in features such as Tasks (long-running work) and MCP Apps (interactive UI) that ship outside the core spec
• The MCP Registry for discovering servers; the MCP Inspector for debugging
• Security: tool poisoning, prompt injection through tool results, confused-deputy attacks, over-broad scopes
A2A (Agent2Agent)
A2A reached v1.0 in March 2026, its first stable release, and is governed by the Linux Foundation with over 150 supporting organisations.
• Agent Card: a JSON description of an agent's skills, endpoint and auth, published at /.well-known/agent-card.json; signed cards for identity
• Tasks with a lifecycle (submitted, working, input-required, completed, failed), messages, parts and artifacts
• Streaming over SSE, push notifications for long tasks, JSON-RPC, gRPC and REST bindings
• Agents stay opaque: they share results, not their internal memory or tools
• Related: AP2 (Agent Payments Protocol) for agent-initiated payments
AG-UI and the rest
• AG-UI: an event stream between an agent backend and a front end (text deltas, tool calls, state updates, human approvals)
• AGENTS.md and Agent Skills: conventions for giving coding agents project instructions and reusable know-how
• AGNTCY: Linux Foundation infrastructure for agent discovery, identity and observability
Build: an MCP server for a real system you use (a database, GitHub, or a SaaS API) with OAuth, connected to two different clients. Then wrap two of your agents as A2A servers and have one delegate a task to the other.
Exit test: explain on a whiteboard when to expose a capability as an MCP tool versus as an A2A agent.

Related capstone (grown in track 9, previewed here):
1. Enterprise ops copilot: MCP servers for Jira, GitHub and a database; an orchestrator delegating over A2A to a triage agent and a fix agent; human approval before any change.

Protocol specs named by the source: MCP specification 2026-07-28 and release notes; MCP roadmap (Aug 2026); A2A specification; A2A one-year update (Google, Apr 2026); Linux Foundation A2A adoption announcement.

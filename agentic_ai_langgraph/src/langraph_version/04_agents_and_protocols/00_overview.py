# %% [markdown]
# # Track 4 · Agents, discovery and protocols
# *Lessons 19 to 28 · about three hours · reading and running this page needs no API key.*

# %%
import sys; sys.path.insert(0, "../../..")  # the topic folder: graph_view.py and a2a_server.py live there

from graph_view import lesson_cards, show_mermaid, track_banner

track_banner(
    "Track 4 of 6 · LangGraph version",
    "Agents, discovery and protocols",
    "An agent that other code can use has to be described, found and trusted. This track gives an agent a card, teaches how callers "
    "find it, and then runs the same three steps for the two protocols: MCP for tools and A2A for agents.",
    start="#134e4a", end="#0f766e")

# %% [markdown]
# ## Three parts, one rhythm
# **Part A** is the idea: an agent as a service, discovery and a registry. **Part B** is MCP: build a server, discover its tools, register and gate
# them. **Part C** is A2A: serve an agent, discover its card, delegate through a registry, and follow the task states. Each protocol uses the same
# five steps: build, discover, registry, secure, use inside a graph.

# %%
MAP = """
flowchart LR
  subgraph A["Part A · agents"]
    A1["19 agent as a service<br/>the card"] --> A2["20 discovery<br/>find it without a hard-coded address"] --> A3["21 registry<br/>catalogue, health, allow-list"]
  end
  subgraph B["Part B · MCP: tools"]
    B1["22 build a server<br/>and a client"] --> B2["23 discovery<br/>tools, resources, prompts"] --> B3["24 registry, gateway, auth"]
  end
  subgraph C["Part C · A2A: agents"]
    C1["25 serve an agent"] --> C2["26 card discovery"] --> C3["27 registry and delegation"] --> C4["28 task states"]
  end
  A --> B --> C
  classDef step fill:#f0fdfa,stroke:#0f766e
  class A1,A2,A3,B1,B2,B3,C1,C2,C3,C4 step
"""
show_mermaid(MAP)

# %% [markdown]
# ## The lessons

# %%
lesson_cards([
    ("19", "An agent as a service", "The card: name, skills, inputs and refusals, generated from the agent's own tools."),
    ("20", "Agent discovery", "Three ways to find an agent: hard-coded, from config, and by its card at a well-known path."),
    ("21", "Agent registry", "A catalogue with versions, owners, health checks and an allow-list; search by skill."),
    ("22", "MCP: server, client, LangGraph", "Expose order tools over MCP and call them from a LangGraph agent through a bridge."),
    ("23", "MCP discovery", "List what the server offers on connect; the model chooses from names, descriptions and questions."),
    ("24", "MCP registry, gateway and auth", "A gateway checks the token, the server's approved version and the tool's allow-list; a poisoned description is flagged."),
    ("25", "A2A: serve an agent", "Publish a card, accept a task, run a LangGraph graph in an executor, and return an artifact with its state."),
    ("26", "A2A discovery", "Resolve each card, check it is complete and points back to its base, then match a skill."),
    ("27", "A2A registry and delegation", "A supervisor splits a question, delegates each part as a task, and names the gaps."),
    ("28", "A2A task lifecycle", "Input required, completed, failed and canceled: each state tells the caller what to do next."),
], accent="#0f766e")

# %% [markdown]
# ## What you can do after this track
# - Give an agent a card that other teams can read, and find an agent by the skill a caller needs.
# - Expose tools over MCP, gate them, and check their descriptions before the model reads them.
# - Serve an agent over A2A, delegate work to other agents, and read every task state.
#
# **Next:** Track 5 puts several agents in one graph, and shows how they hand off and fail.

# %% [markdown]
# # Track 4 · Multi-agent systems
# *Lessons 20 to 23 · about ninety minutes · reading and running this page needs no API key.*

# %%
import sys; sys.path.insert(0, "../../..")  # the topic folder: graph_view.py lives there

from graph_view import lesson_cards, show_mermaid, track_banner

track_banner(
    "Track 4 of 5 · LangGraph version",
    "Multi-agent systems",
    "Several agents, each with its own tools and instructions, and a supervisor that routes work between them. "
    "A second agent costs more calls and can loop, so you add one only when it pays. Then you guard the hand-offs.",
    start="#4c1d95", end="#7c3aed")

# %% [markdown]
# ## How the agents work together
# The supervisor is the only one that decides where the work goes. Each agent returns to it. A guard counts the hand-offs and
# stops a loop. A remote agent is reached through a card that describes what it can do.

# %%
MAP = """
flowchart LR
  U(["Customer"]) --> S["Supervisor<br/>routes the request"]
  S --> O["Orders agent<br/>status and delivery"]
  S --> P["Policy agent<br/>returns and refunds"]
  O --> S
  P --> S
  S --> G{"Guard<br/>hand-offs and visits"}
  G -->|within limits| S
  G -->|over the limit| H["Person takes over"]
  subgraph A2A["Agent-to-agent: a remote agent"]
    C["Agent card<br/>what it can do"] --> T["Task sent"] --> R["Task states:<br/>working, done, failed"]
  end
  S -. "delegates to" .-> C
  classDef agent fill:#f5f3ff,stroke:#7c3aed
  classDef guard fill:#fde68a,stroke:#b45309
  class S,O,P,T,R,C agent
  class G guard
"""
show_mermaid(MAP)

# %% [markdown]
# ## The lessons

# %%
lesson_cards([
    ("20", "Why multi-agent, and when one agent is better",
     "Measure what a second agent costs in calls and tokens, and use one only when isolation or parallel work pays."),
    ("21", "Supervisor and hand-offs",
     "A supervisor routes to an orders agent or a policy agent; each one returns control with its result."),
    ("22", "Failure modes and guards",
     "Reproduce a loop between two agents, then stop it with a visit counter, a hand-off limit and a shared-state check."),
    ("23", "Agent-to-agent protocol (A2A)",
     "Read an agent card, send a task to another agent, and follow the task through its states."),
], accent="#7c3aed")

# %% [markdown]
# ## What you can do after this track
# - Decide, with numbers, whether a second agent is worth its cost.
# - Build a supervisor that routes between specialists, with each one's tools kept separate.
# - Find and stop the loops and lost context that appear between agents.
# - Hand a task to a remote agent and handle the states it can end in.
#
# **Next:** Track 5 makes all of this production-ready: evals in CI, traces, security, reliability, cost and serving.

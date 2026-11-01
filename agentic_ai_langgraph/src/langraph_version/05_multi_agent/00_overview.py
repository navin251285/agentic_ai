# %% [markdown]
# # Track 5 · Multi-agent systems
# *Lessons 29 to 31 · about ninety minutes · reading and running this page needs no API key.*

# %%
import sys; sys.path.insert(0, "../../..")  # the topic folder: graph_view.py lives there

from graph_view import lesson_cards, show_mermaid, track_banner

track_banner(
    "Track 5 of 6 · LangGraph version",
    "Multi-agent systems",
    "Several agents, each with its own tools and instructions, and a supervisor that routes work between them. A second agent costs "
    "more calls and can loop, so you add one only when it pays. Then you guard the hand-offs.",
    start="#4c1d95", end="#7c3aed")

# %% [markdown]
# ## How the agents work together
# The supervisor decides where the work goes. Each specialist returns control to it. A guard counts the hand-offs and stops a loop.

# %%
MAP = """
flowchart LR
  U(["customer"]) --> S["Supervisor<br/>decides the next step"]
  S --> O["Orders specialist<br/>order tools"]
  S --> P["Policy specialist<br/>policy tools"]
  O -->|hand back with a result| S
  P -->|hand back with a result| S
  S --> G{"Guard<br/>visits and hand-offs"}
  G -->|over the limit| H["stop with a reason"]
  S -->|finish| E(["reply"])
  classDef agent fill:#f5f3ff,stroke:#7c3aed
  classDef guard fill:#fde68a,stroke:#b45309
  class S,O,P agent
  class G guard
"""
show_mermaid(MAP)

# %% [markdown]
# ## The lessons

# %%
lesson_cards([
    ("29", "Why multi-agent, and when one agent is better",
     "Measure the calls, tokens and tool choices of one agent against a router with two specialists, on the same question."),
    ("30", "Supervisor and hand-offs",
     "A supervisor decides each step; specialists return control with Command; a hop limit ends the run."),
    ("31", "Failure modes and guards",
     "Two agents that hand work back and forth; a visit limit, a hand-off limit and a shared-state check stop them with a reason."),
], accent="#7c3aed")

# %% [markdown]
# ## What you can do after this track
# - Decide, with numbers, whether a second agent is worth its cost.
# - Build a supervisor that routes between specialists, with the path visible.
# - Find and stop the loops and lost context that appear between agents.
#
# **Next:** Track 6 makes the agent production-ready: evals in CI, traces, security, reliability, cost, serving and a capstone.

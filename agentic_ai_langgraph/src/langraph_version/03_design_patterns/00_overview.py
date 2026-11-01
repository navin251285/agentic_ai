# %% [markdown]
# # Track 3 · Agentic AI design patterns
# *Lessons 15 to 18 · about ninety minutes · reading and running this page needs no API key.*

# %%
import sys; sys.path.insert(0, "../../..")  # the topic folder: graph_view.py lives there

from graph_view import lesson_cards, show_mermaid, track_banner

track_banner(
    "Track 3 of 6 · LangGraph version",
    "Agentic AI design patterns",
    "Five shapes that most agent systems are built from. Each one is a small graph with a clear place for the model's "
    "decision, a cost you can count, and a failure you can name. Pick the simplest shape that solves the task.",
    start="#7c2d12", end="#c2410c")

# %% [markdown]
# ## The five patterns at a glance
# The model decides only where a diamond is. Every other step is code. Read the diamonds first: they are where the cost and the risk come from.

# %%
MAP = """
flowchart LR
  subgraph P1["1 · Prompt chaining · lesson 15"]
    a1["Draft"] --> a2["Check"] --> a3["Polish"]
  end
  subgraph P2["2 · Routing · lesson 15"]
    b1["Classify"] --> b2["Refund branch"]
    b1 --> b3["Order branch"]
  end
  subgraph P3["3 · Parallelization · lesson 16"]
    c1["Split"] --> c2["Reviewer A"]
    c1 --> c3["Reviewer B"]
    c2 --> c4["Join"]
    c3 --> c4
  end
  subgraph P4["4 · Orchestrator-workers · lesson 17"]
    d1["Plan"] --> d2["Worker"]
    d1 --> d3["Worker"]
    d2 --> d4["Combine"]
    d3 --> d4
  end
  subgraph P5["5 · Evaluator-optimizer · lesson 17"]
    e1["Draft"] --> e2{"Judge"}
    e2 -->|fail, rounds left| e1
    e2 -->|pass| e3["Send"]
  end
  classDef step fill:#fff7ed,stroke:#c2410c
  classDef decide fill:#fde68a,stroke:#b45309
  class a1,a2,a3,b1,b2,b3,c1,c2,c3,c4,d1,d2,d3,d4,e1,e3 step
  class e2 decide
"""
show_mermaid(MAP)

# %% [markdown]
# ## The lessons

# %%
lesson_cards([
    ("15", "Chaining and routing", "Patterns 1 and 2: a fixed chain with a check between steps, and a classifier that picks one branch."),
    ("16", "Parallelization", "Pattern 3: independent reviewers run at once with Send; a rule combines their votes."),
    ("17", "Orchestrator-workers and evaluator-optimizer",
     "Patterns 4 and 5: a planner hands out work; a judge checks the draft and sends it back once, with a stop rule."),
    ("18", "Choosing a control pattern",
     "ReAct, plan-and-execute and reflection side by side, with the calls, tokens and dollars each one costs."),
], accent="#c2410c")

# %% [markdown]
# ## What you can do after this track
# - Name the pattern a task needs, and say why a simpler one is not enough.
# - Build each pattern as a LangGraph graph, with the model's decision in one visible place.
# - Put a stop rule on every loop, and send an unresolved case to a person.
# - Price a pattern from its call count before you build it.
#
# **Next:** Track 4 gives agents a way to be found, and shows MCP for tools and A2A for agents.

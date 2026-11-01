# %% [markdown]
# # Track 2 · The single agent
# *Lessons 05 to 14 · about four hours · reading and running this page needs no API key.*

# %%
import sys; sys.path.insert(0, "../../..")  # the topic folder: graph_view.py lives there

from graph_view import lesson_cards, show_mermaid, track_banner

track_banner(
    "Track 2 of 6 · LangGraph version",
    "The single agent",
    "One model, one loop, one set of tools. You build the loop yourself once, then let LangGraph run it: with tests, memory, "
    "retrieval, a human approval step and a checkpoint for the whole support desk.",
    start="#1e3a8a", end="#2563eb")

# %% [markdown]
# ## How the lessons fit
# Three stages. First the loop and its tools, with tests and safety. Then the context the agent needs: memory and knowledge. Then the
# checkpoint that brings the parts together, with a human approval step.

# %%
MAP = """
flowchart TB
  subgraph LOOP["Stage 1 · the loop and its tools"]
    L05["05 Agent loop by hand<br/>step and cost caps"] --> L06["06 Tools that work<br/>names, schemas, errors"]
    L06 --> L07["07 Eval and safety<br/>golden set, injection, gate"]
    L07 --> L08["08 Checkpoint: order assistant"]
  end
  subgraph CTX["Stage 2 · context"]
    L09["09 Memory<br/>short and long term"] --> L10["10 RAG and agentic RAG<br/>retrieval with citations"]
    L10 --> L11["11 Why a graph<br/>state, steps, resume"]
  end
  subgraph DESK["Stage 3 · the desk"]
    L12["12 Choosing a framework"] --> L13["13 Approval gate<br/>interrupt and resume"]
    L13 --> L14["14 Checkpoint: single desk"]
  end
  L08 --> L09
  L11 --> L12
  classDef lesson fill:#eff6ff,stroke:#1d4ed8
  class L05,L06,L07,L08,L09,L10,L11,L12,L13,L14 lesson
"""
show_mermaid(MAP)

# %% [markdown]
# ## The lessons

# %%
lesson_cards([
    ("05", "Agent loop by hand", "Write the think-act-observe loop with a step cap, a spend cap and repeated-call detection."),
    ("06", "Tools that work", "Functions the model uses correctly, and errors it can recover from inside a graph."),
    ("07", "Eval and safety", "A golden set and a scripted harness with Send; a refund gate that refuses an injected write."),
    ("08", "Checkpoint: order assistant", "The first agent you can ship: tools, caps, a gate, a saved thread and a score, with four checks."),
    ("09", "Memory", "Trim the conversation by tokens; keep customer facts in a store, with a rule that refuses card numbers."),
    ("10", "RAG and agentic RAG", "Ingest, retrieve by keyword and vector fused, cite the chunk; let the agent search again."),
    ("11", "Why a graph", "The loop loses its messages on a failed tool; the graph resumes from its last checkpoint."),
    ("12", "Choosing a framework", "A hand loop, a graph and create_agent on one question: the calls, and what each build still needs."),
    ("13", "Approval gate", "Pause a refund for a person, resume the same run, and pay exactly once under its key."),
    ("14", "Checkpoint: single desk", "Memory, retrieval, approval and pay-once in one desk graph, with five checks that must pass."),
], accent="#1d4ed8")

# %% [markdown]
# ## What you can do after this track
# - Build an agent loop with caps, and know what each cap stops.
# - Write tools and tests the model can use without guessing, and keep the agent safe from text it reads.
# - Give the agent memory and knowledge, and cite where an answer came from.
# - Run the agent as a graph with a saved pause, so a person can approve a refund and the run survives a restart.
#
# **Next:** Track 3 shows five design patterns, each as a flowchart you can reuse.

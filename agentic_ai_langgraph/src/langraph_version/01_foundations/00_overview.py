# %% [markdown]
# # Track 1 · Foundations
# *Lessons 01 to 04 · about one hour · reading and running this page needs no API key.*

# %%
import sys; sys.path.insert(0, "../../..")  # the topic folder: graph_view.py lives there

from graph_view import lesson_cards, show_mermaid, track_banner

track_banner(
    "Track 1 of 6 · LangGraph version",
    "Foundations",
    "Before an agent can act, it has to answer well and ask for a tool correctly. This track builds that: one model call, "
    "the numbers that drive its cost, structured answers you can check, and the tool-call round trip.",
    start="#0f766e", end="#1d4ed8")

# %% [markdown]
# ## How the lessons fit
# Each lesson adds one piece to the last. The flowchart shows the order. Lesson 04 ends with a model that can ask for a
# tool, which is the first step of an agent.

# %%
MAP = """
flowchart LR
  A["01 Why agentic AI<br/>chatbot, workflow or agent?"] --> B["02 First model call<br/>get_llm, usage, streaming"]
  B --> C["03 Tokens and sampling<br/>counting, price, temperature"]
  C --> D["04 Structured output<br/>and the tool-call round trip"]
  D --> E(["Track 2: the single agent"])
  classDef lesson fill:#ecfdf5,stroke:#0f766e
  class A,B,C,D lesson
"""
show_mermaid(MAP)

# %% [markdown]
# ## The lessons

# %%
lesson_cards([
    ("01", "Why agentic AI", "Tell a chatbot, a fixed workflow and an agent apart, and say when not to build an agent."),
    ("02", "First model call", "One call with get_llm().invoke(): read the text, the usage and the cost, then stream the answer."),
    ("03", "Tokens and sampling", "Count tokens with the model's own counter, price a call, and see what temperature and thinking change."),
    ("04", "Structured output and tool calls",
     "Get checked JSON with a retry, then run the tool-call round trip the model expects."),
], accent="#0f766e")

# %% [markdown]
# ## What you can do after this track
# - Call a model from Python and read its text, its token usage and its cost.
# - Ask for validated, structured answers, and retry when one is wrong.
# - Declare a tool, let the model request it, run it in your code and send the result back.
# - Explain why a workflow comes before an agent, which the rest of the course relies on.
#
# **Next:** Track 2 builds one agent with a loop, tools, tests, memory and retrieval.

# %% [markdown]
# # Track 5 · Production
# *Lessons 24 to 30 · about two hours · reading and running this page needs no API key.*

# %%
import sys; sys.path.insert(0, "../../..")  # the topic folder: graph_view.py lives there

from graph_view import lesson_cards, show_mermaid, track_banner

track_banner(
    "Track 5 of 5 · LangGraph version",
    "Production",
    "The same agent, made ready for real users: a regression gate that blocks a bad change, traces you can read, "
    "defences against injected text, retries that cannot pay twice, cost caps, and a deployable service.",
    start="#134e4a", end="#0f766e")

# %% [markdown]
# ## The path to production
# Each step adds one thing a team needs before release. The capstone runs them all on the support desk: the eval gate
# blocks a bad change, and a kill drill checks that a refund is paid once.

# %%
MAP = """
flowchart LR
  E["24 Evals<br/>golden set, judge, CI gate"] --> O["25 Observability<br/>traces and a dashboard"]
  O --> S["26 Security<br/>injection, guardrails, audit"]
  S --> R["27 Reliability<br/>retries, idempotency, durable runs"]
  R --> C["28 Cost and latency<br/>caps, cache, routing"]
  C --> V["29 Serving<br/>API, fleet, enterprise map"]
  V --> K(["30 Capstone<br/>the desk in production"])
  E -. "a failing eval blocks the release" .-> K
  classDef step fill:#f0fdfa,stroke:#0f766e
  class E,O,S,R,C,V step
"""
show_mermaid(MAP)

# %% [markdown]
# ## The lessons

# %%
lesson_cards([
    ("24", "Evals: depth and the CI gate",
     "Find which component fails with error analysis, grade free text with a judge, and fail the build on a drop."),
    ("25", "Observability", "Trace every model and tool call as a span, log only what is safe, and read a dashboard."),
    ("26", "Security, guardrails and MCP auth",
     "Attack the agent with injected tickets, check every tool call against policy, and keep an audit log of who did what."),
    ("27", "Reliability and durable runs",
     "Retry with backoff and idempotency keys, then kill the worker mid-run and check the refund is paid once."),
    ("28", "Cost and latency", "Cap spend per ticket, cache the stable prefix, route easy work to a cheaper model."),
    ("29", "Serving and the enterprise map",
     "Serve the agent as an API in a container, load-test three replicas, and place it in an organisation with tenancy and DR."),
    ("30", "Capstone: the desk in production",
     "Ship the support desk as a tested, traced, budget-capped service with an eval gate and a drill."),
], accent="#0f766e")

# %% [markdown]
# ## What you can do after this track
# - Stop a bad change from reaching users with a test in CI, and roll a new model out safely.
# - Read a trace to find where a run spent its time and money.
# - Defend the agent against text it reads, and show who approved what.
# - Keep a refund correct when the server restarts or a request is retried.
#
# **You have finished the course.** The capstone is the place to start building your own agent.

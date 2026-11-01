# %% [markdown]
# # Track 6 · Production
# *Lessons 32 to 38 · about three hours · reading and running this page needs no API key.*

# %%
import sys; sys.path.insert(0, "../../..")  # the topic folder: graph_view.py lives there

from graph_view import lesson_cards, show_mermaid, track_banner

track_banner(
    "Track 6 of 6 · LangGraph version",
    "Production",
    "The same agent, made ready for real users: a regression gate that blocks a bad change, traces you can read, defences against "
    "injected text, retries that cannot pay twice, cost caps, a deployable service, and a capstone that checks it all.",
    start="#134e4a", end="#0f766e")

# %% [markdown]
# ## The path to production
# Each step adds one thing a team needs before release. The capstone runs them together on the support desk.

# %%
MAP = """
flowchart LR
  E["32 Evals in CI<br/>golden set, baseline, gate"] --> O["33 Observability<br/>traces and what to log"]
  O --> S["34 Security<br/>injection, identity, audit"]
  S --> R["35 Reliability<br/>retries, keys, kill drill"]
  R --> C["36 Cost and latency<br/>cache, route, cap"]
  C --> V["37 Serving<br/>API, replicas, canary"]
  V --> K(["38 Capstone<br/>the desk, with its release checks"])
  E -. "a failing gate blocks the release" .-> K
  classDef step fill:#f0fdfa,stroke:#0f766e
  class E,O,S,R,C,V step
"""
show_mermaid(MAP)

# %% [markdown]
# ## The lessons

# %%
lesson_cards([
    ("32", "Evals in CI", "A golden set with a saved baseline and a release test that blocks a worse candidate."),
    ("33", "Observability", "A callback writes a span per call; a trace as a table and a flowchart; log decisions, never text."),
    ("34", "Security and guardrails", "Injected tickets, a gate in code, an identity scope and an audit log with no customer text."),
    ("35", "Reliability and durable runs", "Retry policies, an idempotency key, and a kill drill where the money moves once."),
    ("36", "Cost and latency", "Price a ticket, cache a deterministic step, route easy work to a cheaper setting, cap the spend."),
    ("37", "Serving and the enterprise map", "FastAPI replicas, a load test on p50 and p95, a canary with a written promotion rule."),
    ("38", "Capstone: the desk in production", "One graph with a capped model step, a keyed refund, an audit and a release checklist of seven checks."),
], accent="#0f766e")

# %% [markdown]
# ## What you can do after this track
# - Stop a bad change from reaching users with a test in CI, and roll a new version out safely.
# - Read a trace to find where a run spent its time and money.
# - Defend the agent against text it reads, and show who approved what.
# - Keep a refund correct when the server restarts or a request is retried.
#
# **You have finished the course.** The capstone is the place to start building your own agent.

# %% [markdown]
# # 21 · From proof of concept to production: what changes
#
# Level L5 · Part 3 · core · ~25 min · builds on 17, 20
#
# Concept lesson. No keys, no Docker, no model calls. The one code cell reads the saved output of lesson 20's run (`../data/recorded/20.json`), so the numbers are real. Nothing here needs the network.

# %% [markdown]
# ## Goal
#
# By the end you can list what a proof of concept leaves out for Basket Bazaar, and judge a published case study by its numbers only: what the number is compared with, over what period, and who measured it.

# %% [markdown]
# ## Why it matters
#
# Your proof of concept worked in the demo. The customer's ops lead asks: "When is it live?" Without a plan for production you answer with a date you cannot keep.
#
# - **Without this lesson:** the POC runs on your laptop, with the key in `.env`, on 224 lines of one CSV. Its first real failure is a 2 a.m. page with no runbook. The team learns the gap by paying for it.
# - **With it:** you name the gap before you promise a date, and you know which gaps the customer must close and which you close.
# - **When you don't need it:** a POC that answers one question and is thrown away. Anything a customer will depend on needs the gap closed.

# %% [markdown]
# ## The idea
#
# A **proof of concept (POC)** answers one question on real data: can this work at all? **Production** means a customer depends on it every day, so it must handle bad data, failing systems, secrets, audits, cost and handover. A POC is easy to mistake for the whole job.
#
# Think of a prototype car and a car you sell. The prototype proves the engine works. The sold car needs crash tests, a service manual, spare parts and a warranty process. Nobody buys a car for its engine alone.

# %% [markdown]
# ## Picture
#
# The POC proves one path. Production closes the gaps on the right.

# %% [markdown]
# ```mermaid
# flowchart LR
#     POC[POC: one CSV, laptop, demo] --> G{Gaps}
#     G --> D[Data: live feed, bad rows]
#     G --> S[Secrets and access]
#     G --> N[Customer network]
#     G --> F[Failures: timeouts, retries]
#     G --> Q[Evals as a release gate]
#     G --> V[Logs, traces, alerts]
#     G --> O[Runbook and restore drill]
#     G --> C[Cost per customer]
#     G --> H[Handover to the customer team]
#     D & S & N & F & Q & V & O & C & H --> P[Production: customer depends on it]
# ```

# %% [markdown]
# ## Already know this?
#
# This is the first lesson of Part 3 (Production, handover and delivery). The rest of the Part covers the same ground, from handover to end-to-end delivery. Answer these five. If you can answer all of them, skip to lesson 31 and come back when a question stumps you.
#
# 1. How do you change a running service without taking customers offline? (lesson 24)
# 2. What must a handover pack contain for the customer's team to run the service alone? (lesson 22)
# 3. One customer asks for a feature. When does it go into the shared product, and when does it stay custom? (lesson 25)
# 4. How do you turn one customer's logs into cost per customer per month? (lesson 29)
# 5. A customer asks for something outside the agreed scope. What do you write back? (lesson 30)

# %% [markdown]
# ## Explained

# %% [markdown]
# ### What the POC leaves out
#
# Production needs more than the POC, and each row below names the lesson that teaches it.
#
# | Area | Proof of concept | Production | Lesson |
# | --- | --- | --- | --- |
# | Data | one CSV of 224 lines, checked by eye | live feed; duplicates, mixed units, schema changes | 05 |
# | Secrets | one `.env` file on a laptop | the customer's secret store, rotation, least privilege | 13 |
# | Network | your laptop, open internet | the customer's VPC, egress proxy, allow-list | 14, 15 |
# | Failure | works while the API is up | timeouts, retries, idempotency, a fallback | 04, 28 |
# | Quality | a few test messages, checked by hand | an eval gate before every release, with real failures added | 11, 12, 20 |
# | Visibility | print statements | logs, traces, metrics and alerts | 16 |
# | Operations | the builder is the on-call | runbook, restore drill, on-call handover | 17, 22 |
# | Cost | "it was cheap in the demo" | a budget per customer per month | 18, 29 |
#

# %% [markdown]
# ### The reference architecture
#
# A **reference architecture** is the standard set of parts a solution needs and how they connect. You reuse it for each customer. For an enterprise AI system the parts are: the customer's data source, a connector that reads it, an agent or model service with its tools, evals and guardrails, an API or UI, the deployment in the customer's cloud or VPC, and the runbook and handover. In a system design interview, draw these boxes and say where each risk sits.

# %% [markdown]
# ### What a number needs before you can use it
#
# A figure is only a comparison when four things are known: the **baseline** (the value before), the **after** value, the **period** (over what time), and **who measured** it, with what scope. A vendor's customer story often gives the after value and leaves one of the others out. Then you cannot compare it with your own project.

# %% [markdown]
# ## Worked example
#
# ### Example 1: the POC's own numbers
#
# Lesson 20 ran the triage service on a laptop, with its real trace and metric saved. Read them: where does the time go? One slow request is a symptom. The trace says where the time is spent, so the production fix is aimed at the right owner.

# %%
import json
from pathlib import Path

REC = json.loads(Path("../data/recorded/20.json").read_text())  # the real output of lesson 20's run
spans = json.loads(REC["trace"])
total = next(s["ms"] for s in spans if s["span"].startswith("GET /triage"))
customer_call = next(s["ms"] for s in spans if s["span"] == "GET" and "/orders" in s["url"])
print(f"one triage request: {total:.0f} ms; the Basket Bazaar orders API call inside it: {customer_call:.0f} ms ({customer_call / total:.0%})")
metric = json.loads(REC["metric"])
print(f"metric: {metric['over_1s']:.0f} of {metric['requests']:.0f} requests took over 1 s")

# %% [markdown]
# The triage code is not the slow part. Almost all of the time is the Basket Bazaar orders API. A production plan therefore starts with that API's owner and a timeout on the call, not with a faster model. The POC could not show this; it had no trace.

# %% [markdown]
# ### Example 2: three published case studies, numbers only
#
# Vendors publish customer stories with numbers. The table below uses three customer stories on claude.com. They are Anthropic's own customer stories: vendor-authored, not independently measured. Each figure in the table is a quote from that page, not a verified measurement. The pages show no publication date, and they were read on 2026-10-24. Re-check each live page before you quote it in a customer deck.
#
# For each figure, the table records the **after** value, the **baseline** (the value before), the **period**, and **who measured** it. None of the quotes says who measured. The last column only confirms that the key phrase was copied correctly from the quote. It does not show that the claim is true.

# %%
SOURCES = {
    "Jakala": "https://claude.com/customers/jakala",
    "Athena": "https://claude.com/customers/athena",
    "AirOps": "https://claude.com/customers/airops",
}
CASES = [
    {"case": "Jakala", "quote": "JAKALA's first production agent took about a quarter to go from design to live client deployment.",
     "after": "about a quarter", "baseline": "none stated", "period": "not stated", "measured": "not stated", "check": "about a quarter"},
    {"case": "Jakala", "quote": "The second was half that.",
     "after": "half that", "baseline": "first agent: about a quarter", "period": "not stated", "measured": "not stated", "check": "half that"},
    {"case": "Jakala", "quote": "Under 24-hour campaign-optimization cycles on accounts running the hybrid agent model, down from 5–7 working days.",
     "after": "Under 24-hour cycles (hybrid-agent accounts only)", "baseline": "5–7 working days", "period": "not stated", "measured": "not stated", "check": "Under 24-hour"},
    {"case": "Athena", "quote": "Deploys production enterprise workflows in 4–8 weeks, compared to the 6–12 month industry standard",
     "after": "4–8 weeks", "baseline": "6–12 month industry standard", "period": "not stated", "measured": "not stated", "check": "4–8 weeks"},
    {"case": "AirOps", "quote": "Time to quality went from 60 hours to 5 hours.",
     "after": "5 hours", "baseline": "60 hours", "period": "not stated", "measured": "not stated", "check": "5 hours"},
    {"case": "AirOps", "quote": "2x productivity across the team, with individual employees reporting 20 to 40 hours saved per week",
     "after": "2x productivity", "baseline": "none stated", "period": "not stated", "measured": "not stated", "check": "2x productivity"},
]

# %% [markdown]
# Print the sources and the table. Read each row with the four questions in mind: after, baseline, period, who measured.

# %%
print("Sources (vendor's own customer stories, read 2026-10-24):")
for name, url in SOURCES.items():
    print(f"  {name}: {url}")
print()
print(f"{'case':<9}{'after':<46}{'baseline':<32}{'period':<12}{'who measured':<14}{'key phrase in quote'}")
for c in CASES:
    print(f"{c['case']:<9}{c['after']:<46}{c['baseline']:<32}{c['period']:<12}{c['measured']:<14}{c['check'] in c['quote']}")

# %% [markdown]
# Read the table as a reviewer. The Jakala "5–7 working days" row is the most useful one, because it has a before and an after on what the vendor calls the same task ("down from"). Check the scope, though: "under 24 hours" holds only for accounts on the hybrid agent model. The two Jakala agent rows ("about a quarter", "half that") compare one team's first and second agent, but they have no period and no scope. Not stated: how many people, which client, what "live" meant. "4–8 weeks" is set against an industry claim, not against the customer's own before. "2x productivity" has no before, so you cannot plan with it. No row says who measured its figure. The FDE's habit: ask the vendor who measured it, over what period and on what scope, or measure your own customer, before you quote a number.

# %% [markdown]
# ## At work
#
# - **Evals are the release gate.** Teams start with 20 to 50 tasks drawn from real failures. Graders come in three types: code (fast, brittle), model (flexible) and human (gold, slow) (Anthropic's eval guidance, RESEARCH section 7.1). → lesson 11, lesson 12.
# - **Customers review your design before go-live.** Common practice, not a sourced standard: the review asks for a data-flow diagram, subprocessors, SOC 2 evidence and SSO and audit logs. → lesson 27.
# - **Runbooks and on-call handover to the customer team are standard practice.** A system without them is found broken at 2 a.m. (RESEARCH section 7.5). → lesson 17, lesson 22.
# - **Vendor numbers are marketing until you check the baseline.** Quote a number only with its baseline and period, and check it on your own customer first. Go deeper: the business case, lesson 30.

# %% [markdown]
# ## Common misconceptions
#
# - **"The POC works, so we are nearly done."** The POC answered one question. The gaps in the table are the rest of the job, and they often take more work than the POC (field experience, not a measured figure).
# - **"A vendor's '4 weeks' is a benchmark we can promise."** The story does not say what the work included, who did it, or how many people. Without that it is a sales claim, not a plan.
# - **"Handover is a README written on the last day."** Lesson 22 builds the handover pack.

# %% [markdown]
# ## Production checklist
#
# Before you tell a customer "live", every line should be true:
#
# - [ ] Every number in the handover says measured, recorded or not measured (lesson 20).
# - [ ] Every alert has an owner and a runbook with a verify step (lesson 17).
# - [ ] Secrets are in the customer's secret store, with a tested rotation (lesson 13).
# - [ ] The eval gate runs before each release, and real failures are added to the set (lessons 11, 20).
# - [ ] A trace shows where the time goes for a slow request (lesson 16).
# - [ ] The cost per customer per month is known and has a budget (lesson 18).
# - [ ] A restore drill met the recovery target (lesson 17).
# - [ ] The customer's team has run the system once, with the handover pack (lesson 22).

# %% [markdown]
# ## Check yourself
#
# Answer each question in one or two sentences, then open the hidden answer.
#
# 1. The demo used 224 lines. The customer's file has 40,000 rows, two currencies and blank item names. What breaks first, and what do you check before you change any model prompt?
# 2. A customer says: "Athena deploys production workflows in 4–8 weeks, so ours will take four weeks." What do you ask before you agree?
# 3. Lesson 20's trace shows 98% of the slow request inside the Basket Bazaar orders API. Who fixes it, and what do you hand over?
# 4. Which is more useful to plan with: "2x productivity" or "60 hours to 5 hours"? Why?
# 5. Your POC keeps its key in `.env`. The customer's security review is next week. Name the production change and the lesson that teaches it.

# %% [markdown] tags=["solution"]
# **Answers** (hidden until opened)
#
# 1. The data layer breaks first: duplicates and mixed units give wrong totals, and blank names fail the parser or match nothing. Check the data (lesson 05) and count the bad rows before you touch the prompt. A prompt cannot fix bad input.
# 2. The baseline and the scope: what work was included, how many people, what the team had already built, and whether the 4–8 weeks covers the first workflow or every one. Ask for the numbers, not the headline. The quote does not say who measured the time, so ask that too.
# 3. The Basket Bazaar orders API team fixes it: it is outside your code. You hand over the trace id, the span times (1,508 ms of 1,539 ms) and a timeout on your side with a clear error (lessons 16, 17). Do not restart the triage service; it does not help.

# %% [markdown] tags=["solution"]
# **Answers, continued**
#
# 4. "60 hours to 5 hours" is more useful, and it is still only a claim to verify. It has a before and an after, so the ratio is about 12x. But "time to quality" is not defined, and the task, scope, period and who measured it are not stated. "2x productivity" has no before, so you cannot plan with it at all. Ask the vendor for the task, the period and the measurement method behind the 60-hour figure.
# 5. Move the secret to the customer's secret store and rotate it, with the service account scoped to read only (lesson 13). The review will look for this first.

# %% [markdown]
# ## Recap
#
# - A POC proves one path on one dataset. Production adds data, secrets, network, failure handling, quality gates, visibility, operations and cost.
# - The reference architecture is the same set of parts for each customer; the risks sit in the boxes.
# - A number is comparable only with its baseline, its period and who measured it.
# - Words to keep: **proof of concept**, **reference architecture**, **baseline** (all in the glossary).
#
# %% [markdown]
# **Common mistake:** promising a date from the POC's demo. Plan from the gap list instead.

# %% [markdown]
# **Interview:** "A prototype works on the customer's sample. What do you need before it goes live?" Strong answer: "I list the gaps by area: real data and bad rows, secrets and the customer's network, timeouts and retries, an eval gate, traces and alerts, a runbook and restore drill, cost per customer, and a handover the customer's team has rehearsed. I quote a date only after the gap list is closed."

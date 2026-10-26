# %% [markdown]
# # 01 · Why forward deployed engineering, and when you don't need it
#
# Level L1 · Part 1 · core · ~25 min · builds on nothing (course opener)

# %% [markdown]
# ## Goal
#
# After this lesson you can say what a forward deployed engineer (FDE) does, how the role differs from a software engineer, a solutions architect and a consultant, and name the cases where a product alone is enough.

# %% [markdown]
# ## Why it matters
#
# Basket Bazaar is a fictional grocery delivery app, and it is our customer. Its orders live in its own systems: a store system that our product cannot read, and a delivery-message export of customer complaints. Deliveries go wrong: wrong items, late orders, missing items. Basket Bazaar's ops lead raises a ticket. Our support team cannot see the store system, so the ticket goes to engineering, which adds it to the product backlog (the ordered list of work the product team has agreed to build). Meanwhile the ops lead is stuck.
#
# Without someone working inside the customer's world, each fix waits for the product's release cycle (the schedule of planned product releases). The cell below shows the shape of that wait. The day counts are invented for illustration, not measured; real queues differ by company.

# %% [markdown]
# **Illustrative days (invented for this lesson, not measured).** Without an FDE, the ticket moves through our queues. With an FDE, the same problem is seen on site. The FDE timeline leaves out the ticket and triage steps on purpose: an FDE works on site, so there is no queue to show.

# %%
# Illustrative numbers, invented for this lesson, not measured.
waits = [
    ("Ticket triaged: support cannot see the store system", 2),
    ("Feature waits in the product backlog", 30),
    ("Fix ships in the next scheduled release", 30),
]
fde_waits = [
    ("FDE reads the delivery-message export on site", 1),
    ("FDE writes and tests a fix with the ops lead", 3),
]

for name, steps in [("Without an FDE", waits), ("With an FDE", fde_waits)]:
    day = 0
    print(f"{name} (illustrative days)")
    for stage, wait in steps:
        day += wait
        print(f"  day {day:>3}: {stage}")

# %% [markdown]
# Each wait is added to the day before, so the fix ships on day 62 versus day 4 with an FDE. These are invented day counts that show the shape of the wait, not a measurement.
#
# Our product team was not slow or careless. The fix needed access and context that only Basket Bazaar's side has, and a release cycle is built for changes that help every customer.
#
# **What it makes easy:** an engineer with access to the customer's data and a sponsor (the customer-side person who backs the project) can go from complaint to working fix in days, and can tell the product team what to build next.
#
# **When you don't need one:** the customer can set the product up alone through a standard API or a self-serve setup, the need is one simple integration, or the product is cheap to change. Check that before you staff an engineer for each customer.

# %% [markdown]
# ## The idea
#
# A forward deployed engineer is a software engineer who works inside the customer's environment: their systems, their data and their people. The FDE owns an outcome from first discovery to go-live (the day the customer's real work runs on the service), writes production code, and sends repeatable patterns back to the product team. Think of a field technician who repairs the machine on the customer's site, then tells the factory why it keeps breaking. The product team builds for everyone. The FDE makes it work for this customer now.

# %% [markdown]
# ## Picture
#
# Two views of the same Basket Bazaar problem. The first has no one on site.
#
# ### Without an FDE

# %% [markdown]
# ```mermaid
# flowchart LR
#     OPS["Basket Bazaar ops lead"] -->|ticket| SUP["Our support team"]
#     SUP -->|cannot see store system| ENG["Our engineering"]
#     ENG -->|feature request| BL["Product backlog"]
#     BL -->|next release| PROD["Our product"]
#     PROD -.->|no access to store data| STORE["Basket Bazaar store system"]
#     OPS -.->|manual workaround| OPS
# ```

# %% [markdown]
# ### With an FDE
#
# The second view has an engineer who sits between the customer and the product team.

# %% [markdown]
# ```mermaid
# flowchart LR
#     subgraph CUST["Basket Bazaar environment"]
#         OPS["Ops lead"]
#         STORE["Store system and delivery-message export"]
#         FDE["Forward deployed engineer"]
#     end
#     subgraph VEND["Our company"]
#         PROD["Product team"]
#         PAT["Shared connectors and patterns"]
#     end
#     FDE -->|reads and fixes| STORE
#     FDE -->|working fix, tested with| OPS
#     FDE -->|repeatable pattern| PAT
#     PAT --> PROD
# ```

# %% [markdown]
# ## How it simplifies the architecture
#
# The FDE does not remove the product or the release process. It removes the handoffs between the customer's systems and the people who can change them.
#
# | | Without an FDE | With an FDE |
# |---|---|---|
# | Parties between the customer and a fix | support, engineering, backlog, release | one engineer, on site |
# | Glue code (code that connects two systems) for this customer | written later, if at all; workarounds pile up | written in the customer's environment, reviewed, then shared if it repeats |
# | Information lost on each handoff | the ops lead's real problem | little; the FDE sees the data |
# | Failure points | a ticket nobody owns; a manual workaround that becomes permanent | one person is a single point of knowledge; the handover (passing the running service to the customer's team) must be planned (lesson 22) |
#
# %% [markdown]
# The trade-off is real. One FDE serves a few customers at a time, and a custom fix can split the product into many forks. Lesson 25 covers how to keep field work from splitting the product.

# %% [markdown]
# ## Already know this?
#
# These five questions preview Part 1 (lessons 01 to 09). This is a preview of Part 1. Skip only if you can answer all five. It is not a prerequisite for lesson 01.
#
# 1. A customer says "our deliveries are bad". What would you ask first so you can measure something?
# 2. A customer order API times out after you sent a write. Why can a retry create a duplicate, and what stops it?
# 3. A delivery-message export lists the same message twice. What happens to the label counts, and how do you dedupe? (The answer is the dedupe idea in lesson 05.)
# 4. Name two things a proof of concept's scope (a small, working test on real data that answers one question) should leave out on purpose.
# 5. How would you show progress to an operations lead who does not write code?

# %% [markdown] tags=["solution"]
# **Answers** (hidden until opened)
#
# 1. Ask for the failure: which messages, which label (missing, wrong, late), how often, and what the customer did next. That gives a baseline you can compare against after the fix.
# 2. The first request may have been applied. A retry without an idempotency key can write the same record twice. Send a key with the write and reuse it on retries (lesson 04).
# 3. The label counts count the message twice, so one issue looks like two. Dedupe by a stable key, not by the whole raw row. Lesson 05 does this for order lines: trim and fix case first, then keep one row per cleaned line.
# 4. Any two of: new integrations, production hosting, every store's data, a permanent UI, sign-off on service levels (lesson 03).
# 5. Show a working result on the customer's real data, one number they care about, and say what is not done yet (lesson 07).

# %% [markdown]
# ## Explained
#
# The role sits between a product team and a customer. These definitions are the common pattern in job postings and public write-ups. Companies differ, so read each posting.
#
# | Role | Main job | Writes production code? | Owns the outcome at the customer? |
# |---|---|---|---|
# | Software engineer (product team) | builds the product for many customers | yes, in the product repo | no; ships the product, not one customer's outcome |
# | Solutions architect | designs the fit before and during the sale | prototypes, usually not production | no; hands over |
# | Consultant | advises and recommends | rarely | no; leaves after the report |
# | Forward deployed engineer | makes the product work in the customer's environment | yes, in the customer's environment and the shared patterns | yes, through go-live and handover |
#
# %% [markdown]
# An FDE usually moves through the same cycle. The steps map to the Parts of this course:
#
# 1. **Discover** the real problem (Basic).
# 2. **Scope** a proof of concept with success criteria (Basic).
# 3. **Build** against the customer's systems and data (Basic).
# 4. **Evaluate, secure, deploy and observe** the service (Intermediate).
# 5. **Go live, hand over and codify** the pattern (Advanced).

# %% [markdown]
# ## Worked example
#
# Here is one invented first week, to show the steps.
#
# Basket Bazaar's support agents read every delivery message (wrong, late or missing items) by hand and sort it into a label. The ops lead wants that faster. In plain steps:
#
# - **Day 1, on site:** the FDE sits with two support agents and reads three recent messages with them. The pattern: a customer writes "only two of the four bananas came", and the agents label it by hand as missing, while wrong and late are mixed up on busy days. The FDE asks for the delivery-message export. The stand-in order data is built in lesson 05. The delivery-message export is the triage project's stand-in (lessons 20 and 31).
# - **Day 2, data:** the FDE finds duplicate rows and two date formats in the export. They write down an assumption, that the same message can arrive twice from a retry, and mark it for testing.
# %% [markdown]
# - **Day 3, scope:** the FDE writes a one-page scope. Problem: agents cannot sort delivery messages into missing, wrong, late or damaged items fast enough. Goal: a triage that labels each message. Non-goal: changing Basket Bazaar's store or order system, refunds, or a customer-facing app. Success measure: the triage labels at least 90% of the labelled messages correctly (a target to agree with the ops lead, not a measured number yet).
# - **Day 5, demo:** a rough prototype labels last week's messages. The ops lead says which labels were wrong. The FDE fixes the rule, and the product team hears about the date problem the same day.
#
# Notice what the FDE did not do: rebuild the product, or promise a feature for next quarter. The fix lives with the customer, and the pattern goes back to the product.

# %% [markdown]
# ## What it does not solve, and the alternatives
#
# An FDE does not scale linearly. Every embedded engineer costs time, and the customer depends on one person. Marty Cagan (SVPG, 17 September 2025, https://www.svpg.com/forward-deployed-engineers/) warns that without a platform team that generalises what FDEs learn, you end up with "thousands of large, bespoke solutions" to maintain. This course's answer is shared connectors, an eval harness (a repeatable script that scores outputs against a test set), templates and a handover playbook (lessons 25 and 22).
#
# Alternatives, when an FDE is the wrong answer:
#
# - **Better self-serve onboarding and documentation** when most customers can follow a guide.
# - **Standard integration platforms or connectors** when a ready-made connector exists for the customer's system.
# - **A solutions architect plus a product team** when the customer needs advice and a design, not code in their systems.
# - **A consultant** when the work is a one-time assessment with no build.

# %% [markdown]
# ## Where the course goes
#
# The course follows one running example, Basket Bazaar's delivery issues, and grows it one step per part:
#
# | Part | Lessons | What you build |
# |---|---|---|
# | Basic: the customer problem and a proof of concept | 01 to 09 | discovery, scope, an API call with retries, a messy export cleaned, a checked triage label, a demo |
# | Intermediate: evaluate, secure, deploy and observe | 10 to 20 | evals from real failures, auth and secrets, a Docker Compose deployment, a restricted network, logs and traces, runbooks, cost; checkpoint 20 deploys the proof of concept |
# | Advanced: production, handoff, productizing and delivery | 21 to 32 | production gaps, handover, per-store tenancy (multi-tenancy: one product serving many stores, with each store's data kept apart), zero-downtime change, field reports, security evidence, a failure drill, unit economics, the delivery drill |
#
# %% [markdown]
# Out of scope, with pointers: Kubernetes is its own course, and this course runs the same service with Compose (lesson 14). Fine-tuning models is a research job, not covered here.

# %% [markdown]
# ## At work
#
# - Anthropic's Forward Deployed Engineer job posting asks engineers to "identify and codify repeatable deployment patterns". Field work that is never turned into a shared pattern becomes one-off code → lesson 25.
# - Engagements often start when a customer's deal stalls on deployment (paraform's write-up on FDE roles, a recruiting-platform blog, secondary source). Discovery and scope decide what gets built first → lessons 02 and 03.
# - Postings in bloomberry's analysis of 1,000 FDE job postings (published 2025-11-18, updated 2026-01-25) mostly ask for a builder: production code, tests and a deployment. Start in the proof of concept → lesson 09; the gap to production → lesson 21.
# - A consultant's report ends the engagement; an FDE's handover must leave the customer's team able to run the service without them → lesson 22.
#
# Go deeper: the Kubernetes course covers customer clusters, which this course does not.

# %% [markdown]
# ## Common misconceptions
#
# - **"An FDE is a consultant who leaves a slide deck."** A consultant recommends and leaves. An FDE writes production code in the customer's environment and stays through go-live.
# - **"An FDE is a demo person."** bloomberry's analysis of 1,000 FDE job postings (published 2025-11-18, updated 2026-01-25) finds that, of those 1,000 postings, 60% are "builder", 30% "sales-engineer-plus" and 10% internal-tools roles. That describes postings, not every FDE's day.
# - **"Every customer needs an FDE."** The role pays off when deployment into the customer's systems is the bottleneck. When the product installs and works alone, a second engineer adds cost and fork risk.

# %% [markdown]
# ## Check yourself
#
# Answer each question in one or two sentences, then open the hidden answer.
#
# 1. A product team says, "We already have support. Why embed an engineer?" What would you say?
# 2. A Basket Bazaar security team will not let our product call its systems over the public internet. Which role owns that fix, and what is the first step?
# 3. You are offered an FDE job where every customer asks for a custom feature. What is the main risk, and what would you do in your first month?
# 4. Which of these is not a typical FDE task: (a) build a proof of concept on the customer's data, (b) sell a licence alone, (c) write the runbook for the customer team?
# 5. Give one case where you would not hire an FDE.

# %% [markdown] tags=["solution"]
# **Answers** (hidden until opened)
#
# 1. Support can file tickets, but without access to the customer's systems it cannot see the cause. An embedded engineer can read the data, find or rule out the cause in days, and tell the product team what to change.
# 2. The FDE, with Basket Bazaar's network and security team. First, agree the constraints and a private network path, such as a private link or an egress proxy (lesson 15).
# 3. The risk is a fork: many custom copies of the product. In month one, find the repeated requests, make them shared components, and say no to out-of-scope asks in writing (lessons 25 and 30).
# 4. (b). Selling a licence is a sales task. (a) and (c) are FDE work.
# 5. Any one of: the customer can self-serve through a standard API; the need is a single simple integration; the product is cheap to change for everyone.

# %% [markdown]
# ## Recap
#
# - A forward deployed engineer works inside the customer's environment, owns the outcome to go-live, and feeds patterns back to the product.
# - Without that role, fixes wait in queues and workarounds become permanent; with it, the handoffs shrink.
# - The role does not scale linearly. The fix is a shared platform, shared patterns and a handover plan.
# - You don't need one when the customer can set the product up alone, the need is simple, or the product is cheap to change.
# - Words to keep: **forward deployed engineer (FDE)**, **handover**, **codify** (all in the glossary, GLOSSARY.md).
#
# %% [markdown]
# **Common mistake:** treating the FDE as a consultant or a demo role. The role ships production code.
#
# %% [markdown]
# **Interview:** "What does a forward deployed engineer do that a software engineer on a product team does not?" Strong answer: "They work in the customer's environment to get the product into production, own the outcome to go-live, and turn repeated fixes into patterns for the product, while watching the cost of bespoke work."

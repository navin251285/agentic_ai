# %% [markdown]
# # 03 · Scoping a proof of concept and a two-week sprint
#
# Level L1 · Part 1 · core · ~25 min · builds on lesson 02

# %% [markdown]
# ## Goal
#
# By the end of this lesson you can turn the lesson 02 findings into one proof-of-concept question about Basket Bazaar's delivery triage, write success criteria with a baseline, a target and a test, fit the work into a two-week sprint with a cut line, and say in writing what the proof of concept will not do.

# %% [markdown]
# ## Why it matters
#
# Basket Bazaar's ops lead wants labels before an agent opens each message. Lesson 02 turned that into testable problems. Someone still has to decide what a two-week **proof of concept (POC)** builds: a small working test on real data that answers one question.
#
# The cell below shows an unscoped plan. The day counts are **invented estimates**.
#
# - **Without it:** seven wishes need 21 days, the sprint has 9, and the loudest voice picks the list.
# - **With it:** one question, success criteria and a cut line. Each sprint item answers the question.
# - **When you don't need it:** when the customer has already named one measurable question with a test.

# %%
# Wishes from the first planning call. Days are invented estimates.
wishes = [("Dashboard for support leads", 4), ("Late-delivery alerts from the timestamps", 2),
          ("Customer reply drafts for each label", 3), ("Retry queue for failed label writes", 3),
          ("Live connection to the support tool", 5), ("Login and roles for support agents", 2),
          ("Early list of likely refunds", 2)]
SPRINT_DAYS = 9  # invented: 10 working days minus 1 day for access requests

total = sum(days for _, days in wishes)
print(f"wishes: {len(wishes)}, estimated days: {total}, sprint days: {SPRINT_DAYS}")
print("fits the sprint?", total <= SPRINT_DAYS)
print("success criteria written: 0")

# %% [markdown]
# ## The idea
#
# A **sprint** is a fixed period of work. Here it is two weeks, or 10 working days. The **time box** is that fixed end date: the date does not move, the scope does. A **success criterion** is a number the POC must reach. It has five parts: the observable (what you count), the **baseline** (the value today), the **target** (the value the POC must reach), the test (how you measure it) and an owner.

# %% [markdown]
# A **non-goal** says what the POC will not do. The **cut line** is the point where the time runs out. Work above it is in the sprint; work below it goes to the **backlog** (the ordered list of work for later). Think of a fixed-length meeting: the end time does not move, so you decide the agenda first, and the line is where the time runs out.

# %% [markdown]
# ## Picture
#
# The lesson 02 findings become one question. The question sets the criteria. The criteria decide which work sits above the cut line.

# %% [markdown]
# ```mermaid
# flowchart TD
#     F["Lesson 02 findings: testable problems"] --> Q["One POC question"]
#     Q --> C["Success criteria: observable, baseline, target, test"]
#     C --> W["Candidate work with estimated days"]
#     W --> CUT{"Cut line at sprint capacity"}
#     CUT -->|above the line| IN["In the sprint"]
#     CUT -->|below the line| BL["Backlog"]
#     IN --> D["Day 10: check each criterion, decide"]
# ```

# %% [markdown]
# ## Step by step
#
# **The sprint at a glance.** Criteria C1 to C4 come in Step 2. Day 1: agree the 90% target with the ops lead. Day 3: the reviewed-label export and the message export arrive, or the POC stops. Day 5: set the target for hand-labelled messages per week (C4, Step 2). Day 10: check each criterion and decide.

# %% [markdown]
# ### Step 1: pick the one question
#
# Lesson 02 left three testable problems. Only one matches the ops lead's own words: missing and wrong items filed by hand. The other two are real, but they are a different need (timing, and queue routing). They are not dropped for good: they go to the backlog. The wishes that do not serve the one question (login, live connection, dashboard) are dropped now.

# %%
# The three testable problems from lesson 02, with a verdict for this POC.
problems = [("Missing and wrong items filed by hand", "serves the need"),
            ("Late deliveries reported days later", "backlog"),
            ("Damaged items sent to the wrong queue", "backlog")]
print('Need: "the label before an agent opens the message, so the easy ones go out the same day."')
for problem, verdict in problems:
    print(f"- {problem}: {verdict}")

# %% [markdown]
# The POC question is: **can a triage step label each delivery message with the right issue type for at least 90% of messages that an agent has already labelled?** It needs a **message export** (one row per message, with its text and time) and a **reviewed-label export** (the same messages with the label the agent chose, from the support tool). We have neither in full yet. The sample from lesson 02 has four unique messages, which is far too few to score anything.

# %% [markdown]
# So the first task of the sprint is to ask the support team for the reviewed-label export. If it is not sent by day 3, the POC stops (Step 5).

# %% [markdown]
# Every plan rests on **assumptions**: things we believe without proof yet. Write them down, so each one gets tested or dropped. Each label says where a value is invented.

# %%
# Assumptions to test (or drop) by day 3. "invented" marks the made-up parts.
assumptions = [
    "A1. The reviewed-label export exists and arrives by day 3 (invented: nobody has confirmed it)",
    "A2. The agents' labels are right often enough to test against (invented: no one has checked a sample)",
    "A3. The ops lead's 12-a-week figure of missing-item messages is a guess, not a count (from one interview)",
]
print("\n".join(assumptions))

# %% [markdown]
# ### Step 2: write the success criteria
#
# Each criterion has the five parts from The idea. C1 is the 90% target named as the success measure in lesson 01. Where nobody has measured a value, mark it as not measured or invented. Targets are invented starting points to agree with the ops lead on day 1. C4 is left unfinished on purpose: its target is not known yet.

# %%
REQUIRED = ("observable", "baseline", "target", "test", "owner")

criteria = [
    {"id": "C1", "observable": "share of reviewed messages the triage labels the same as the agent did",
     "baseline": "no automatic label exists, so 0%", "target": "90% (invented, to agree on day 1)",
     "test": "run the triage on a held-out set of reviewed messages the rule was never written from; correct = same label as the agent",
     "owner": "ops lead"},
    {"id": "C2", "observable": "share of messages the triage leaves with no label for an agent",
     "baseline": "not measured", "target": "at most 10% (invented)",
     "test": "count the messages with no label in the same run as C1",
     "owner": "ops lead"},
    {"id": "C3", "observable": "share of messages labelled within 5 minutes of received_at",
     "baseline": "not measured", "target": "95% of messages (invented)",
     "test": "compare received_at with the label time in the run log",
     "owner": "support lead"},
    {"id": "C4", "observable": "hand-labelled delivery messages per week",
     "baseline": "not measured", "target": "",
     "test": "count hand-labelled messages in week 1",
     "owner": "support lead"},
]

for c in criteria:
    gaps = [key for key in REQUIRED if not c.get(key)]
    print(c["id"], "ready" if not gaps else "not ready, missing: " + ", ".join(gaps))

# %% [markdown]
# C4 is not ready: it has no target yet. Week 1 measures its baseline, and the target is set on day 5. Until then C4 is context, not a pass or fail test. The reviewed-label export is the ground truth for C1: the real answer you compare the triage against. The rule-based triage (candidate item 4 in Step 3) is written only after that export arrives, so this lesson does not score one.

# %% [markdown]
# ### Step 3: fit the work with a cut line
#
# First the capacity. Ten working days minus one day for access requests leaves 9 days (invented). The demo and handoff notes always go in, so they reserve 1 day. What is left is 8 days for candidate work.
#
# Each candidate names the criterion it serves (or none) and its estimated days (invented). The order matters: items that serve a criterion come first, then the shortest first. Walk down the list and add days. A **strict** cut line stops at the first item that does not fit. It does not skip ahead to a smaller item, because the order is the decision.

# %%
RESERVED = {"Demo script and handoff notes": 1}  # always in the sprint

# (work item, criterion it serves or None, estimated days). Days are invented.
candidates = [
    ("Read the message export and check its columns", "C1", 1),
    ("Get and read the reviewed-label export", "C1", 1),
    ("Hold out a test set the rule never sees", "C1", 1),
    ("Write the rule-based triage", "C1", 1),
    ("Run the triage on the held-out set and score it", "C1", 1),
    ("Count unlabelled messages and label times (C2, C3)", "C2", 1),
    ("Count hand-labelled messages per week", "C4", 1),
    ("Fix the three most common wrong labels, then rerun", "C1", 1),
    ("Login and roles for support agents", None, 2),
    ("Customer reply drafts for each label", None, 3),
    ("Store manager dashboard", None, 4),
]

# %% [markdown]
# The cut is one function. It sorts the candidates, then walks down the list and adds days until the next item would not fit.

# %%
def cut_line(items, capacity):
    # False sorts before True, so items serving a criterion come first, then the shortest.
    ordered = sorted(items, key=lambda item: (item[1] is None, item[2]))
    used, inside, below = 0, [], []
    for item in ordered:
        # Once anything is below the line, everything after goes below too.
        if not below and used + item[2] <= capacity:
            inside.append(item)
            used += item[2]
        else:
            below.append(item)
    return inside, below, used

# %% [markdown]
# Run the cut with this sprint's capacity. Each list prints on one line, so nothing is cut off.

# %%
capacity = SPRINT_DAYS - sum(RESERVED.values())
inside, below, used = cut_line(candidates, capacity)

print(f"IN the sprint ({used} of {capacity} days):",
      "; ".join(f"{name} ({days}d)" for name, _, days in inside))
print(f"BELOW the cut line, backlog ({len(below)}):",
      "; ".join(f"{name} ({days}d)" for name, _, days in below))

# %% [markdown]
# The sprint is full with zero slack. Below the line are the login and roles, the customer reply drafts and the store manager dashboard. Any surprise in the reviewed-label export moves another item below the line. That is why real plans keep some slack, and why the Try it asks you to change the capacity.

# %% [markdown]
# ### Step 3a: draw the POC data flow
#
# **Solution architecture** is the plan for how data moves through the POC. Draw it before any code. The diagram shows the customer two inputs, the one place where they meet (our triage and scoring), and one output: a label file for the agent queue. It writes nothing back to the support tool, and nothing connects live to it.

# %% [markdown]
# ```mermaid
# flowchart LR
#     ME["Message export (CSV, support tool)"] --> T["Triage: rule labels each message"]
#     RL["Reviewed-label export (CSV, support tool)"] --> S["Score: triage label vs agent label"]
#     T --> S
#     T --> OUT["Label file (CSV) for the agent queue"]
#     S --> R["Day 10 results: C1, C2, C3"]
# ```

# %% [markdown]
# ### Step 4: write what the POC will not do
#
# A non-goal is a sentence that says what the POC will not do, and where that work goes. Write them as soon as the cut line is drawn. Each one needs a reason and a place to go. This list stops the customer from assuming the POC is the product.

# %%
# (what the POC will not do, why, where that work goes)
non_goals = [
    ("No live connection to the support tool", "only CSV exports in scope", "API integration is taught in lesson 04"),
    ("No customer reply drafts", "a different need; below the line", "backlog, 3 days (invented)"),
    ("No late-delivery alerts", "a different need (timing)", "backlog, 2 days (invented)"),
    ("No dashboard, login or roles", "no criterion needs them", "decide after day 10"),
    ("No change to the agents' queue or refund process", "the POC informs; it does not change process", "ops lead decides"),
    ("No production hosting", "the sprint tests on the customer's files", "lesson 21"),
]

for what, why, where in non_goals:
    print(f"- {what}. Why: {why}. Where: {where}.")

# %% [markdown]
# ### Step 5: set the kill criterion and decide on day 10
#
# A **kill criterion** is a rule, agreed before the work starts, that stops the POC early. Ours: if the reviewed-label export or the message export is not sent by day 3, stop and rescope. On day 10, check each criterion against its test. Then choose one of three outcomes: go on to production scoping, change the question, or stop.
#
# The results below are **invented** to show the decision. They are not measurements.

# %%
# Invented results on day 10. Targets come from Step 2.
results = {"C1": 0.86, "C2": 0.08, "C3": 0.96}
targets = {"C1": 0.90, "C2": 0.10, "C3": 0.95}  # C2: lower is better


def decide(results, targets, files_by_day3):
    if not files_by_day3:
        return "stop: a file was missing on day 3 (reviewed-label export or message export); rescope"
    met = {"C1": results["C1"] >= targets["C1"], "C2": results["C2"] <= targets["C2"],
           "C3": results["C3"] >= targets["C3"]}
    print({name: ("met" if ok else "not met") for name, ok in met.items()})
    return "go on to production scoping" if all(met.values()) else "change the question or rescope; do not ship"


print("decision:", decide(results, targets, files_by_day3=True))

# %% [markdown]
# C1 missed its target: the triage matched the agents on 86% of reviewed messages, not 90%. That is a useful answer. A POC can say no, and a clear no is cheaper than a wrong yes.

# %% [markdown]
# ## At work
#
# - Teams write a one-page scope with non-goals and acceptance tests before the build starts (Educative FDE course). → lesson 08 covers timelines and risk for a customer engagement.
# - A POC often works on demo data and fails on the customer's real files. → lesson 05 ingests real files, and lesson 09 is the POC checkpoint.
# - Anthropic's engineering post on agent evals suggests 20 to 50 tasks drawn from real failures, the same habit as turning a criterion into a test. → lesson 11 builds the eval set.
#
# Go deeper: the gap between a POC and production is in lesson 21.

# %% [markdown]
# ## Common mistakes
#
# - **A criterion with no number.** "The labels are good" cannot be tested. Comparing a number with a word fails loudly:

# %% tags=["raises-exception"]
# A criterion written as an adjective, not a number.
target = "good"
measured = 0.86

print(measured >= target)

# %% [markdown]
# The fix is a number, a baseline and a test, as in Step 2.
#
# - **Sorting by effort only.** The cheapest items fill the sprint, and the criterion that proves the need falls below the line. Keep the "serves a criterion" sort key.
# - **Forgetting the non-goals.** If nobody writes down what the POC will not do, the customer will assume it does everything.

# %% [markdown]
# ## Try it
#
# The ops lead adds a wish: "Store managers see the labels on their phone" (2 days, serves no criterion). An IT freeze on day 8 takes one working day, so 9 becomes 8. Change `sprint_days_try` to the freeze value, run the cut, and say in one sentence what the POC gives up.

# %%
# your code here
new_wish = ("Store managers see the labels on their phone", None, 2)
sprint_days_try = None  # change this to the freeze value (the sprint days after the freeze)

if sprint_days_try is None:
    print("Set sprint_days_try to the freeze value, then run this cell again.")
else:
    inside, below, used = cut_line(candidates + [new_wish], sprint_days_try - sum(RESERVED.values()))
    print("IN:", [name for name, _, _ in inside])
    print("BELOW:", [name for name, _, _ in below])

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
new_wish = ("Store managers see the labels on their phone", None, 2)
sprint_days_try = 8  # the freeze takes one day

inside, below, used = cut_line(candidates + [new_wish], sprint_days_try - sum(RESERVED.values()))
print("IN:", [name for name, _, _ in inside])
print("BELOW:", [name for name, _, _ in below])
print(f"used {used} of {sprint_days_try - sum(RESERVED.values())} days")

# %% [markdown]
# With 8 sprint days the candidate capacity is 7. The seven items before the cut keep C1, C2, C3 and C4 measured, but the second pass on the wrong labels falls below the line. The POC then tests C1 once, with no fix, and the phone view stays in the backlog. Say so to the ops lead on day 1, not on day 10.

# %% [markdown]
# ## Recap
#
# - Turn the findings into one question: can triage label messages as well as agents, at 90%+?
# - Give each criterion an observable, baseline, target, test and owner; mark invented numbers.
# - Fit work with a strict cut line, ordered by criterion served, then by days.
# - Write non-goals with a reason and a place to go; set a kill criterion before day 1.
# - **proof of concept**, **sprint**, **success criterion**, **baseline**, **non-goal**, **cut line**, **kill criterion**
#
# **Interview:** "You have two weeks and a customer who wants everything. What do you build?" Strong answer: "I pick the one question tied to the stated need, set testable criteria, cut at capacity, write non-goals."

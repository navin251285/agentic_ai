# %% [markdown]
# # 08 · Timelines, risk and success metrics for a customer engagement
#
# Level L1 · Part 1 · professional · ~25 min · builds on lesson 03

# %% [markdown]
# ## Goal
#
# By the end of this lesson you can turn the lesson 03 plan into a day-by-day sprint timeline in a CSV file, write a risk register with a score, an owner, a mitigation and a trigger for each risk, and draft success metrics that the ops lead and the support lead can check and sign.

# %% [markdown]
# ## Why it matters
#
# Lesson 03 gave Basket Bazaar a plan: one question, four success criteria, a cut line and non-goals. A slide does not say which day a task starts, who waits for whom, or what happens when the reviewed-label export is late.
#
# - **Without it:** the timeline lives in someone's head. The export arrives on day 6, nobody notices until day 9, and the decision on day 10 has no data to decide on.
# - **With it:** one table with a start day and an end day for every task, a risk list with an owner for each risk, and metrics the ops lead has agreed in writing.
# - **When you don't need it:** a one-day fixed-price task with one owner and no outside inputs.
#
# The day counts, scores and targets in this lesson are **invented** for teaching. Basket Bazaar must replace them with its own numbers.

# %% [markdown]
# ## The idea
#
# A **timeline** is an ordered list of tasks with a start day and an end day. Like a train timetable, one late task delays every task after it. A **milestone** is a point in time with no work of its own, such as a decision. A **risk** might happen and hurt the plan. The **risk register** lists every risk with a **likelihood** and an **impact** (both 1 to 5); its **score** is likelihood times impact. Each risk also needs a **mitigation** (what we do now to lower it) and a **trigger** (the sign that it is happening). The **time box** is the fixed length of the sprint: here 10 working days (two weeks). The work must fit inside it; the time box does not stretch.

# %% [markdown]
# ## Picture
#
# The lesson 03 plan becomes three files: a timeline, a risk register and a metrics list. The ops lead checks the metrics before the first day of work.

# %% [markdown]
# ```mermaid
# flowchart LR
#     P["Lesson 03 plan: criteria, candidate work, cut line"] --> T["sprint_timeline.csv: start and end day per task"]
#     P --> R["risk_register.csv: score, owner, mitigation, trigger"]
#     P --> M["success_metrics.csv: baseline, target, test, owner"]
#     T --> K{"Check: fits the 10-day time box? kill check on day 3?"}
#     R --> K
#     M --> S["Ops lead agrees and signs before day 1"]
# ```

# %% [markdown]
# ## Step by step

# %% [markdown]
# ### Step 1: load the lesson 03 plan
#
# This notebook does not import lesson 03. The plan is copied below as data, so the notebook runs on its own. The days are **invented estimates**, and the criteria match lesson 03 (C1 to C4). The message export is asked for to arrive by day 2 (invented); the reviewed-label export is due by day 3 and is the one the kill check waits for. Each plan row carries its own **owner** and a **needs_files** flag (True when the task cannot start until the customer's exports are in hand). The checks read these flags, not the task wording. Nothing below the cut line is in this plan: every row is work we have agreed to do.

# %%
from pathlib import Path
import csv

OUT = Path("../data/08")  # run-time files for this lesson only
OUT.mkdir(parents=True, exist_ok=True)


def save_csv(name, rows):  # rows: dicts with the same keys, written to ../data/08/<name>
    with open(OUT / name, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

SPRINT_DAYS = 10  # the time box: two weeks of working days (fixed)

# The work above the cut line, in order: (task, criterion, days, owner, needs_files). Days are invented.
plan = [
    ("Read the message export and check its columns", "C1", 1, "FDE", False),
    ("Get and read the reviewed-label export", "C1", 1, "FDE", False),
    ("Hold out a test set the rule never sees", "C1", 1, "FDE", True),
    ("Write the rule-based triage", "C1", 1, "FDE", False),
    ("Run the triage on the held-out set and score it", "C1", 1, "FDE", True),
    ("Count unlabelled messages and label times (C2, C3)", "C2", 1, "FDE", True),
    ("Count hand-labelled messages per week", "C4", 1, "support lead", False),
    ("Fix the three most common wrong labels, then rerun", "C1", 1, "FDE", True),
]
KILL_TASK = "Get and read the reviewed-label export"  # the kill check (Step 2) follows this task
print("plan items:", len(plan), "| work days:", sum(p[2] for p in plan))

# %% [markdown]
# ### Step 2: build the sprint timeline
#
# The function places each task one after another. This is a **strict** order: each task starts only when the one before it has finished, so nothing jumps ahead. Day 1 is access requests and agreeing the 90% target with the ops lead. The last row is the demo script and handoff notes, a one-day slot the plan always reserves for showing the result to the store.

# %%
def build_timeline(plan, access_days=1, demo_days=1):
    rows, day = [], 1
    rows.append({"task": "Access requests; agree targets with the ops lead", "kind": "task",
                 "criterion": "-", "owner": "FDE and ops lead", "needs_files": False,
                 "start_day": day, "end_day": day + access_days - 1})
    day += access_days
    for task, criterion, days, owner, needs_files in plan:
        rows.append({"task": task, "kind": "task", "criterion": criterion, "owner": owner,
                     "needs_files": needs_files, "start_day": day, "end_day": day + days - 1})
        day += days
    rows.append({"task": "Demo script and handoff notes", "kind": "task", "criterion": "-",
                 "owner": "FDE", "needs_files": False,
                 "start_day": day, "end_day": day + demo_days - 1})
    return rows

rows = build_timeline(plan)
print(*(f"day {r['start_day']:>2}-{r['end_day']:<2} {r['task']}" for r in rows), sep="\n")

# %% [markdown]
# The timeline has no milestones yet. Add two: the **kill check** on the last day both exports may arrive (day 3, as in lesson 03), and the **decision** on day 10. A kill check is the day-3 rule that stops the POC if a file is missing. Milestones have `kind` set to `kill check` or `decision`, so the checks can find them.

# %%
def add_milestones(rows):
    out = []
    for row in rows:
        out.append(row)
        if row["task"] == KILL_TASK:
            out.append({"task": "KILL CHECK: both exports in hand, or stop and rescope", "kind": "kill check",
                        "criterion": "-", "owner": "ops lead", "needs_files": False,
                        "start_day": row["end_day"], "end_day": row["end_day"]})
    last = out[-1]["end_day"]
    out.append({"task": "DECISION: check M1 to M3 against their tests", "kind": "decision", "criterion": "M1-M3",
                "owner": "ops lead and FDE", "needs_files": False, "start_day": last, "end_day": last})
    return out

timeline = add_milestones(rows)
print("milestones:", [r["task"] for r in timeline if r["kind"] != "task"])

# %% [markdown]
# ### Step 3: check the timeline and save it
#
# Two checks decide whether the plan is real. It must end inside the time box. And every row flagged `needs_files` must start after the kill check. The file is written to `../data/08/sprint_timeline.csv`, then read back so you see what a reviewer would see.

# %%
def check_timeline(rows, sprint_days):
    end = max(r["end_day"] for r in rows)
    problems = [f"ends on day {end}, after the {sprint_days}-day time box"] if end > sprint_days else []
    kill_day = next(r["end_day"] for r in rows if r["kind"] == "kill check")
    for r in rows:
        if r["needs_files"] and r["start_day"] <= kill_day:
            problems.append(f"'{r['task']}' starts on day {r['start_day']}, before the kill check on day {kill_day}")
    return problems

print("problems:", check_timeline(timeline, SPRINT_DAYS) or "none")

save_csv("sprint_timeline.csv", timeline)
print(*(OUT / "sprint_timeline.csv").read_text(encoding="utf-8").splitlines(), sep="\n")  # read back: what a reviewer sees

# %% [markdown]
# ### Step 4: write the risk register
#
# Each risk gets a score (likelihood times impact). Sort by score, so the riskiest item is read first. Rule of thumb: **act first on scores of 12 or more**. Every row needs an owner, a mitigation and a trigger. A risk without an owner is a risk nobody watches. The scores are **invented**: the team agrees them with the ops lead on day 1.

# %%
risks = [
    {"id": "R1", "risk": "Reviewed-label export not sent by day 3", "likelihood": 3, "impact": 5, "owner": "support team lead", "mitigation": "request the file in writing on day 1; kill check on day 3", "trigger": "no file by the end of day 2"},
    {"id": "R2", "risk": "Rule overfits the few messages it was written from, so the score looks too high", "likelihood": 4, "impact": 3, "owner": "FDE", "mitigation": "write the rule before the held-out set is opened; score only on the held-out set", "trigger": "held-out score far below the score on the rule's own messages"},
    {"id": "R3", "risk": "Message export columns differ from the lesson 02 sample", "likelihood": 3, "impact": 3, "owner": "FDE", "mitigation": "read the header the day the export arrives (day 2) and map the columns before joining", "trigger": "a column is missing or renamed"},
    {"id": "R4", "risk": "IT freeze on day 8 cuts the sprint by one day", "likelihood": 2, "impact": 4, "owner": "ops lead", "mitigation": "know the freeze date on day 1; if it cuts a day, cut the least useful item from the plan", "trigger": "freeze date announced"},
    {"id": "R5", "risk": "Store managers ask for extra features mid-sprint, such as a shopper app (unpaid scope)", "likelihood": 4, "impact": 2, "owner": "FDE", "mitigation": "send each ask to the backlog or a written change request", "trigger": "a new request in the team channel"},
    {"id": "R6", "risk": "Message export holds customer details beyond what the triage needs", "likelihood": 2, "impact": 5, "owner": "customer data owner", "mitigation": "export only the needed columns; keep no copies outside the agreed folder", "trigger": "a file with names, phone numbers or card numbers"},
    {"id": "R7", "risk": "Store IT access takes more than one day", "likelihood": 3, "impact": 3, "owner": "ops lead", "mitigation": "file the access request on day 0 (before the sprint starts)","trigger": "no confirmation by the end of day 1"},
]
for r in risks:
    r["score"] = r["likelihood"] * r["impact"]

problems = [r["id"] for r in risks if not (r["owner"] and r["mitigation"] and r["trigger"])]
print("risks without owner, mitigation or trigger:", problems or "none")

save_csv("risk_register.csv", risks)
for r in sorted(risks, key=lambda r: r["score"], reverse=True):
    print(f"{r['id']} score {r['score']:>2}  owner: {r['owner']:<22} {r['risk']}" + ("  <- act first" if r["score"] >= 12 else ""))

# %% [markdown]
# ### Step 5: agree the success metrics with the ops lead
#
# A **success metric** is a number the customer can check, with a baseline (today's value), a target and a test. It measures what the store gets, not what we build: "features shipped" is not one. M1 is the accuracy measure that lesson 03 calls C1 (the 90% target): the share of labelled delivery messages that the triage labels correctly, on messages held out from the rule and taken from the reviewed-label export. M2 to M4 mirror lesson 03's C2 to C4. Targets are **invented starting points** for the ops lead to agree on day 1.
#
# The notebook can check that a metric is complete, not that the customer agrees. `signed_by` stays empty until the customer fills it. M4's target is set on day 5.

# %%
metrics = [
    {"id": "M1", "metric": "Share of labelled delivery messages the triage labels correctly (held out from the rule, from the reviewed-label export)",
     "baseline": "0% (no triage labels exist yet)", "target": "90% (invented, to agree)",
     "test": "run the triage on the held-out messages from the reviewed-label export and compare each label with the expected label; correct = same label", "owner": "ops lead", "signed_by": ""},
    {"id": "M2", "metric": "Share of messages the triage leaves with no label for an agent",
     "baseline": "not measured", "target": "at most 10% (invented, to agree)",
     "test": "count the messages with no label in the same run as M1", "owner": "ops lead", "signed_by": ""},
    {"id": "M3", "metric": "Share of messages labelled within 5 minutes of received_at",
     "baseline": "not measured", "target": "95% of messages (invented, to agree)",
     "test": "compare received_at with the label time in the run log", "owner": "support lead", "signed_by": ""},
    {"id": "M4", "metric": "Hand-labelled delivery messages per week",
     "baseline": "not measured (the ops lead guesses about 12 a week; a guess, not a count)", "target": "",
     "test": "count hand-labelled messages in week 1", "owner": "support lead", "signed_by": ""},
]

for m in metrics:
    gaps = [k for k in ("baseline", "target", "test", "owner", "signed_by") if not m[k]] + (["measured baseline"] if "not measured" in m["baseline"] else [])
    print(m["id"], "ready to sign" if not gaps else "not ready, missing: " + ", ".join(gaps))

save_csv("success_metrics.csv", metrics)

# %% [markdown]
# No metric is ready to sign yet. That is the honest answer on day 1. M1 has every field filled except the signature. M1's "0%" baseline counts as measured, because no triage labels exist yet, so the current share of correct labels really is zero. M2 and M3 also need a measured baseline, and M4 needs a measured baseline and a target. Week 1 measures these baselines. The C4 target is set on day 5 (lesson 03). In the timeline, that day-5 target is a note, not a task row.

# %% [markdown]
# ## At work
#
# - Field teams judge success by the customer outcome (the go-live date, the missing-item rate), not by feature count. → lesson 09 is the POC checkpoint that reads these metrics.
# - Metrics are checked against held-out real messages, never the rule's own examples. → lesson 11: building the eval set from real failures.
# - Risks sit next to the assumptions log in the scoping notes and are reviewed with the plan. → lesson 21: the risks that a POC does not carry into production.
# - A one-page scope (statement of work) with non-goals and acceptance tests stops mid-sprint asks from becoming unpaid work. → lesson 22: handing over the timeline, risk register and agreed metrics.
#
# Go deeper: the course's Educative reference covers scoping and the POC sprint in its module "From Problem to POC Sprint".

# %% [markdown]
# ## Common mistakes
#
# - **A task that starts before its input.** A held-out test set built on day 2, before the reviewed-label export is due on day 3, plans work that cannot be done. The demo copies the timeline, moves the held-out row to start on day 2 and end on day 3, then runs the same `check_timeline` check from Step 3 on the copy. The check raises the error, so you see the real message:

# %% tags=["raises-exception"]
# The held-out set is built before the labels arrive, so the plan is wrong. This cell stops the notebook with the check's own message.
wrong = [dict(r) for r in timeline]  # copy the rows; the real timeline is unchanged
held_out = next(r for r in wrong if r["needs_files"])  # the first row that needs the files
held_out["start_day"], held_out["end_day"] = 2, 3
raise ValueError(check_timeline(wrong, SPRINT_DAYS)[0])

# %% [markdown]
# The fix is to move the start day after the kill check, or to cut a task.
#
# - **A risk with no owner.** A row that says "data quality" and nothing else will never be watched. Every row needs a name or a role.
# - **A metric with no test.** "The labels are good" cannot be checked. Write the test next to the target.
# - **Extra work with no signed change request.** A change request adds or changes work after the plan is agreed. Extra work is **billable** only once the customer agrees to it in writing; otherwise the team quietly absorbs it.

# %% [markdown]
# ## Try it
#
# The store's IT contact says the access request takes two days, not one. Set `access_days` in the cell below, build the timeline, and check whether it still fits the 10-day time box. Say in one sentence what you would tell the ops lead.

# %%
# your code here
access_days = None  # change this to 2, then run the cell again

if access_days is None:
    print("Set access_days, then run this cell again.")
else:
    tried = add_milestones(build_timeline(plan, access_days=access_days))
    print("problems:", check_timeline(tried, SPRINT_DAYS) or "none")
    print("last day used:", max(r["end_day"] for r in tried))

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
access_days = 2
tried = add_milestones(build_timeline(plan, access_days=access_days))
print("problems:", check_timeline(tried, SPRINT_DAYS) or "none")
print("last day used:", max(r["end_day"] for r in tried))

# The cut: drop the last item of the plan (lesson 03's cut line), then check again.
cut = [p for p in plan if p[0] != "Fix the three most common wrong labels, then rerun"]
t2 = add_milestones(build_timeline(cut, access_days=2))
print("after the cut:", check_timeline(t2, SPRINT_DAYS) or "none", "| last day:", max(r["end_day"] for r in t2),
      "| kill check on day:", next(r["end_day"] for r in t2 if r["kind"] == "kill check"))

# %% [markdown]
# With two access days the plan ends on day 11, one day past the time box. The fix is a decision, not a silent overrun. Cut the item that comes last in the plan, "Fix the three most common wrong labels, then rerun" (lesson 03's cut line): the output above shows the plan then fits on day 10, and the kill check moves to day 4 because the access request took the extra day. The POC tests C1 once, with no second pass. R7 in the risk register already covers this. Its trigger (no confirmation by the end of day 1) fired, so tell the ops lead now, and record the 2-day access time in the day-1 plan.

# %% [markdown]
# ## Recap
#
# - A timeline gives every task a start day and an end day. A milestone, such as the kill check, has no work of its own.
# - A risk register scores each risk (likelihood times impact) and gives every row an owner, a mitigation and a trigger. Act first on scores of 12 or more.
# - Success metrics need a baseline, a target, a test, an owner and the customer's signature.
# - Extra work without a signed change request is unpaid. Send it to the backlog.
# - Terms: **timeline**, **milestone**, **risk register**, **trigger**, **success metric** (GLOSSARY.md).
#
# **Interview:** "The reviewed-label export arrives late and the sprint is full. What do you do?" Strong answer: "I check the kill criterion first. A missing export on the agreed day means stop and rescope, in writing. If it is late but still in time, I move the dependent tasks, cut the lowest-value item from the plan, and log the slip as a risk."

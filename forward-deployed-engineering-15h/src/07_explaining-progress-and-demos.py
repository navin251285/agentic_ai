# %% [markdown]
# # 07 · Explaining progress to non-engineers and running a live demo
#
# Level L1 · Part 1 · core · ~20 min · builds on lesson 03

# %% [markdown]
# ## Goal
#
# By the end of this lesson you can write a one-page **status update** for a non-engineer, say what a **live demo** of the lesson 03 proof of concept shows and does not show, and answer an unanswered question with a **holding answer** that names an owner and a due date.

# %% [markdown]
# ## Why it matters
#
# Basket Bazaar's ops lead is about to start a two-week sprint on delivery triage (lesson 03). Without a plain update, the ops lead reads "C1 target 90%" as "the triage already labels 90% of messages correctly", and a demo on invented data, unlabelled, gets a rollout approved by mistake. The cell below prints a raw update with no owner, day or decision; the 90% target is invented.
#
# - **Without it:** one line of jargon the ops lead cannot act on.
# - **With it:** a page with where we are, what we know, what we need and by when.
# - **When you don't need it:** a short chat with a sponsor who already knows the work.

# %% [markdown]
# **Recap of lesson 03: three sprint terms used below**
#
# - **C1**: success criterion; the share of messages the triage labels like the agent. Target 90% (invented, agreed day 1).
# - **Kill criterion**: a rule that stops the test early. Here: if the reviewed-label export or the message export is not sent by day 3, the test stops and we rescope.
# - **Cut line**: splits the work into items **IN** the sprint and items **BELOW** the cut line, which go to the backlog.

# %%
# A raw update, as an engineer might post it. The 90% target is from lesson 03
# (an invented starting point, not a result). No result is shown here yet.
raw = "C1 target 90%, reviewed-label export pending, schema TBD, kill criterion armed."
print(raw)
print("words:", len(raw.split()))

# %% [markdown]
# ## The idea
#
# A **status update** answers four questions for a non-engineer: where are we, what do we know, what do you need to decide and by when, and what could go wrong. Every number carries a label: **measured**, **guess** or **invented**. A **demo script** is a written plan for a live demo: the steps in order, what each should show, and what it must not claim. A **holding answer** replies to a question you cannot answer yet: what you know, who finds out and by which day. It never guesses.
#
# A site visit to a building under repair works the same way: the engineer shows what is built, what is only on paper and what needs sign-off, each with a date.

# %% [markdown]
# ## Picture
#
# One update, one demo and one question log feed the same reader. The status page carries the decision. The demo carries the proof and its limits. The question log carries the open items.

# %% [markdown]
# ```mermaid
# flowchart LR
#     S["Status page: where we are, what we know, decision, risks"] --> R["Ops lead reads it"]
#     D["Demo script: shows and does not show"] --> R
#     R --> Q{"Unanswered question?"}
#     Q -->|yes| H["Holding answer: owner and due day"]
#     H --> LOG["Question log, reviewed each update"]
#     Q -->|no| OK["Decision made, next update"]
# ```

# %% [markdown]
# ## Step by step
#
# ### Step 1: check the numbers before you write them
#
# The only message data we have yet is the lesson 02 sample: a tiny file of fictional Basket Bazaar delivery messages, with no real customer data. Lesson 02's Step 4 writes it to `../data/02/`. Its rows have a `message_id`, a `label` and the message text. Peek at it first, then count from the file, not from memory.
#
# Row `M-2004` appears twice on purpose: a retry in the export. A duplicated row must not count twice, so count unique `message_id` values, not rows.
#
# Lesson 02 is optional here. If you skipped it, the cell below writes the same five rows to `../data/07/`, so this lesson still runs.

# %%
import csv
from pathlib import Path

CSV_TEXT = """message_id,order_id,store,received_at,label,message
M-2001,BB-1001,Store 12,2026-10-20 18:40,missing_item,Order BB-1001: 6 eggs ordered and 4 came. Two eggs are missing.
M-2002,BB-1002,Store 12,2026-10-20 19:05,late,Order BB-1002: the driver came 50 minutes after the slot.
M-2003,BB-1003,Store 07,2026-10-20 19:30,damaged,Order BB-1003: the bread arrived squashed flat.
M-2004,BB-1004,Store 07,2026-10-21 09:50,wrong_item,Order BB-1004: I got oat milk and I ordered whole milk.
M-2004,BB-1004,Store 07,2026-10-21 09:50,wrong_item,Order BB-1004: I got oat milk and I ordered whole milk.
"""

SAMPLE = Path("../data/02/delivery_messages_sample.csv")
if not SAMPLE.exists():  # fallback: the same invented rows, written to ../data/07/ (not the lesson 02 file)
    SAMPLE = Path("../data/07/delivery_messages_sample.csv")
    SAMPLE.parent.mkdir(parents=True, exist_ok=True)
    SAMPLE.write_text(CSV_TEXT)
print("file:", SAMPLE)

with SAMPLE.open(newline="") as f:
    rows = list(csv.DictReader(f))
for r in rows[:2]:
    print(r["message_id"], r["label"], "|", r["message"][:60])
unique_ids = {r["message_id"] for r in rows}
print("rows in the file:", len(rows), "| unique messages:", len(unique_ids))

# %% [markdown]
# The file has five rows and four unique messages. Four messages are far too few to score C1 (the lesson 03 criterion: the share of messages the triage labels the same as the agent). So the status update says so, in a number with its label.

# %% [markdown]
# ### Step 2: write the one-page status update
#
# This update is for **day 1** of the sprint, the day the scope is agreed. What has run so far: the scope (lesson 03), the data flow drawn, and a read of the lesson 02 sample. No result is measured yet. Read the page the way the ops lead will: top to bottom, in under two minutes. The decision sits on its own line, near the top, with an owner and a day.

# %%
# The status update for day 1. Each number carries its label.
status = {
    "headline": "Day 1 of a two-week test: can a triage step label delivery messages as well as our agents do?",
    "decision": {"ask": "Confirm the support team sends the reviewed-label export and the message export",
                 "owner": "ops lead", "due": "day 3"},
    "where_we_are": ["Scope agreed: one question, four success criteria (C1 to C4 in lesson 03), a cut line (lesson 03)",
                     "Data flow drawn: two CSV exports in, one label file out, nothing written back",
                     "C1 target: 90% (invented; we agree it with you today)"],
    "what_we_know": [f"{len(unique_ids)} unique messages in the lesson 02 sample (measured from the file; too few to score C1)",
                     "Missing-item messages filed by hand: about 12 a week (guess from one interview in lesson 02, not counted)"],
    "risks": ["Kill criterion: if either export is not sent by day 3, the test stops and we agree the next step together"],
    "open_question": {"question": "Should agents see the triage label on the same screen as the message?",
                      "owner": "FDE", "due": "day 5"},
}

# %% [markdown]
# The render function turns the dictionary into the page the ops lead reads. The decision is the third line, so it shows even in a short preview.

# %%
def render(s):
    d = s["decision"]
    lines = [s["headline"], "", f"Decision needed: {d['ask']}. Owner: {d['owner']}. By: {d['due']}.", ""]
    for title, key in [("Where we are", "where_we_are"), ("What we know", "what_we_know")]:
        lines.append(title + ":")
        lines += ["  - " + item for item in s[key]]
    lines.append("Risks:")
    lines += ["  - " + risk for risk in s["risks"]]
    q = s["open_question"]
    lines.append(f"Open question: {q['question']} Owner: {q['owner']}. By: {q['due']}.")
    return "\n".join(lines)


page = render(status)
print(page)

# %% [markdown]
# **What you should see:** a headline, the decision on the third line with an owner and a day, two short lists, one risk and one open question. Nothing in it needs a glossary.

# %% [markdown]
# ### Step 3: check the page before you send it
#
# Three checks catch most problems: the page fits on one sheet, the decision has an owner and a day, and every figure in "where we are" and "what we know" carries a label. The label check reads both sections. It skips references such as "day 3", "lesson 02" and the criterion id "C1", because those are not figures.

# %%
import re

words = len(page.split())
labels = ("measured", "guess", "invented")


def figures(item):
    # "day 3", "lesson 02" and "C1" name a day, a lesson or a criterion. They are not figures.
    # The regex strips only those three prefixes before the digit check. It is a simple check
    # and will miss cases, such as a figure written in words ("twelve") or another reference label.
    return re.sub(r"\b(day|lesson|C)\s?\d+", "", item)


checks = {
    "one page (under 200 words)": words < 200,
    "decision has an owner and a day": all(status["decision"].get(k) for k in ("owner", "due")),
    "every figure is labelled": all(any(lab in item for lab in labels)
                                    for key in ("where_we_are", "what_we_know")
                                    for item in status[key]
                                    if any(ch.isdigit() for ch in figures(item))),
}
print(f"words: {words}")
for name, ok in checks.items():
    print("pass" if ok else "FAIL", "-", name)

# %% [markdown]
# **What you should see:** `words` well under 200 and three `pass` lines. A `FAIL` means the page goes back to you before it goes to the ops lead.

# %% [markdown]
# ### Step 4: run the live demo from a script
#
# The demo shows the lesson 03 work: the scope, the cut line, the data flow, the C1 success criterion and the kill criterion. The table below is the demo script. Rehearse it once against a 15-minute slot (invented; ask the ops lead for the real length). The real proof-of-concept demo, on the real exports, comes in lesson 09; this script is the frame you will reuse there.

# %%
# The demo script: what to show, what you should see, and what it does not show.
demo = [
    ("Scope on one page", "the IN and BELOW lists of the cut line", "real labels; no result is measured yet"),
    ("Data flow", "two CSV exports in, one label file out, no write-back", "any live link to the support tool"),
    ("Success criterion C1", "a baseline (none today), a target (90%) and a test on held-out reviewed messages (lesson 03)","whether 90% is the right bar; it is an invented starting point"),
    ("Kill criterion", "the test stops on day 3 if an export is missing", "how well the triage would work on a real Saturday"),
]
for step, (show, sees, not_shown) in enumerate(demo, 1):
    print(f"{step}. Show: {show}")
    print(f"   You should see: {sees}")
    print(f"   Does not show: {not_shown}")

# %% [markdown]
# Before the demo, list each input with its label. Say the label aloud before the number.

# %%
# Numbers keep their labels in the room.
demo_inputs = {"message sample (4 unique messages)": "measured, too few to score",
               "C1 target 90%": "invented, to agree today",
               "kill criterion: export by day 3": "agreed (lesson 03)",
               "about 12 a week": "guess, from one interview in lesson 02"}
for name, label in demo_inputs.items():
    print(f"{name}: {label}")

# %% [markdown]
# **What you should see:** four steps, each with what it shows and what it does not. The demo never claims accuracy on real messages, because the real exports have not arrived. Say that on the first slide, not at the end.

# %% [markdown]
# ### Step 5: handle a question you cannot answer yet
#
# The ops lead asks something the team has not measured. Do not guess. Give a **holding answer**: what you know, who finds out, and the day they will reply. Then log the question, so it is reviewed at the next update. The function below builds the reply and the log entry, and it needs an owner and a due day.

# %%
question_log = []


def holding_answer(question, owner, due):
    # Says what we know, who finds out and when. It never guesses.
    entry = next((q for q in question_log if q["question"] == question), None)
    if entry is None:
        question_log.append({"question": question, "owner": owner, "due": due, "status": "open"})
    else:  # asked again: update the open entry instead of adding a second one
        entry.update(owner=owner, due=due)
    return f"We do not know yet. {owner} will find out by {due} and reply to you."


print(holding_answer("Can the triage tell us which messages agents will still need to read by hand?", "support lead", "day 5"))
print(question_log[-1])

# %% [markdown]
# **What you should see:** one reply that names an owner and a day, and a log entry with `status: open`.
#
# **Limit:** the function checks only that `owner` and `due` are passed. It does not check that the owner agreed or that the day is real. Asking the same question again updates its entry, so the log keeps one line per question. The log lives in memory and is gone when the notebook restarts.

# %% [markdown]
# ## At work
#
# - Interview loops include a live demo to executives (RESEARCH §10 item 13) and behavioural/STAR stories (item 14); we advise saying what the demo does not prove. → lesson 09 holds the proof-of-concept checkpoint.
# - A demo shows one good run; a rate needs an eval set, usually 20 to 50 tasks from real failures (RESEARCH §7.1: Anthropic, "Demystifying evals for AI agents", 9 Jan 2026). → lesson 11 builds that set.
# - A POC that works in the demo can fail on real customer data (RESEARCH §10 item 11: "a POC worked in demo but fails on real customer data: diagnose"); the "Does not show" column names that gap early. → lesson 08 covers engagement risk.
#
# Go deeper: what happens after the POC, when the demo becomes a real release, is in lesson 21.
#
# %% [markdown]
# ## Optional: a STAR story for behavioural rounds
#
# This is optional, for behavioural rounds. **STAR** means Situation, Task, Action, Result. Build one story from your own work. The sample below is **invented** and shows the shape only.

# %% [markdown]
# | Part | Invented example |
# |---|---|
# | Situation | A grocery customer's ops lead wanted a delivery-triage demo the week before a sign-off. |
# | Task | Show progress without implying the labels were final. |
# | Action | Wrote a one-page update, labelled every number, and rehearsed a demo script with what it does not show. |
# | Result | The ops lead approved the test and set the export deadline on the spot. (Invented outcome.) |

# %% [markdown]
# ## Common mistakes
#
# - **A guess dressed as an answer.** "Yes, it will work on Saturdays" is a claim nobody has tested. Say what you know, who finds out and when.
# - **A holding answer with no owner or day.** A reply with no owner is a promise nobody keeps. The function refuses to run without `due`:

# %% tags=["raises-exception"]
# A holding answer that forgets the due day.
print(holding_answer("Will the triage work on Saturdays?", "FDE"))

# %% [markdown]
# The fix: give a name and a day, as in Step 5.
#
# - **A demo that hides its inputs.** If the room thinks the numbers are measured, the decision rests on invented data. Show the labels, as in Step 4.

# %% [markdown]
# ## Try it
#
# The ops lead asks: "Will the triage also label the Saturday rush messages correctly?" Nobody has measured it yet. Write the holding answer. Fill in `owner` and `due`, then run the cell. Running it twice updates the same log entry, it does not add a second one.

# %%
# your code here
saturday_q = "Will the triage also label the Saturday rush messages correctly?"
owner = None  # who finds out
due = None    # the day they reply

if owner and due:
    print(holding_answer(saturday_q, owner, due))
else:
    print("Fill in owner and due, then run this cell again.")

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
saturday_q = "Will the triage also label the Saturday rush messages correctly?"
owner = "support lead"  # the person who can pull last Saturday's messages and their reviewed labels
due = "day 6"

print(holding_answer(saturday_q, owner, due))
print(question_log[-1])

# %% [markdown]
# The reply admits the gap, names who closes it and gives a day. The log keeps the question open until someone answers it.

# %% [markdown]
# ## Recap
#
# - A status update has four parts: where we are, what we know, the decision (owner and day, near the top) and the risks.
# - Label every number as measured, guess or invented. Say the label aloud in the demo.
# - A live demo shows the work and its scope, and says what it does not show. Put that on the first slide.
# - When you cannot answer, give a holding answer with an owner and a day. Log the question, and never guess.
# - Terms (all in GLOSSARY.md): **status update**, **demo script**, **holding answer**, **kill criterion**, **STAR**.
#
# **Interview:** "Your sponsor asks whether the pilot works. You have one demo and three open questions. What do you say?" Strong answer: "I show the demo and say what it does not prove. I state the open questions, each with an owner and a day. I give no number I have not measured, and I name the next date."

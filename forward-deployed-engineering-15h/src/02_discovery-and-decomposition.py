# %% [markdown]
# # 02 · Finding the real problem: discovery and decomposition
#
# Level L1 · Part 1 · core · ~20 min · builds on lesson 01

# %% [markdown]
# ## Goal
#
# By the end of this lesson you can turn a short customer interview into facts, numbers and guesses, and split one vague request into problems that each have a test, an observable and an owner.

# %% [markdown]
# ## Why it matters
#
# Basket Bazaar's support team reads every delivery message by hand and picks a label for it. The ops lead says, "Our deliveries are bad. Fix it." The code below shows the plan that comes out of that request. Each step is a solution, and none says how anyone would know it worked.
#
# - **Without it:** the team builds a dashboard, demos it, and learns weeks later that it solved another problem.
# - **With it:** each problem has a number you can measure before you build, so a wrong guess shows up in a day.
# - **When you don't need it:** when the customer has already named one measurable problem and a test. Then go to scoping (lesson 03).

# %%
# This is the plan the team would write before any discovery.
request = "Our Basket Bazaar deliveries are bad. Fix it."

# Without decomposition the team starts from a solution it likes.
# All three steps below are fixes the team likes, not findings from discovery.
plan = ["build a triage dashboard", "add a second support queue", "hire two more drivers"]

print(request)
for step in plan:
    # The question the plan skips: how would we know it worked?
    print(f"  {step:<28} measured by: (nothing written down)")

# %% [markdown]
# ## The idea
#
# **Discovery** means asking about the failure before you talk about the fix: what went wrong, how often, for whom, and what people did next. A **discovery interview** is a conversation built for that. **Decomposition** means splitting a vague request into smaller problems. Each problem should name an **observable** (the number or record that would change), a **test** (how you would check it, with data you can get) and an **owner** (the person who would confirm the result). Think of a doctor who takes a history before prescribing: symptoms first, then the diagnosis, then the treatment.

# %% [markdown]
# ## Picture
#
# One vague request becomes problems, and each problem gets a test. Nothing is built yet.

# %% [markdown]
# ```mermaid
# flowchart TD
#     REQ["Vague request: our deliveries are bad"] --> INT["Discovery interview: facts, numbers, who"]
#     INT --> P1["Problem 1: missing and wrong items filed by hand"]
#     INT --> P2["Problem 2: late deliveries not reported for a while"]
#     INT --> P3["Problem 3: damaged items sent to the wrong queue"]
#     P1 --> T1["Test: compare first label with reviewed label"]
#     P2 --> T2["Test: delivery time vs message time"]
#     P3 --> T3["Test: queue log vs message export"]
# ```

# %% [markdown]
# ## Step by step

# %% [markdown]
# ### Step 1: read the interview
#
# The transcript below is **invented for this lesson**: a fictional ops lead at Basket Bazaar, not a real customer. Every number in it is invented too. Read it the way you would read a real interview: who said what, and what they could see for themselves.

# %%
TRANSCRIPT = """\
FDE: Walk me through the last bad delivery you remember.
OPS: Tuesday. A customer ordered 6 eggs and got 4. The message said two eggs were missing, and an agent filed it by hand.
FDE: How often does that happen?
OPS: Maybe 12 times a week? Nobody counts properly.
FDE: What do you do when it happens?
OPS: The agent refunds the missing items and writes it in a spreadsheet.
FDE: Would a new tool fix this?
OPS: Honestly I just want the label before an agent opens the message, so the easy ones go out the same day.
OPS: Some customers write days after the delivery.
OPS: Damaged items sometimes land in the wrong queue.
FDE: Who else would use it?
OPS: The support agents, I think. I would need to ask them.
"""

for number, line in enumerate(TRANSCRIPT.strip().splitlines(), start=1):
    print(f"{number:>2}  {line}")

# %% [markdown]
# ### Step 2: sort facts, numbers and guesses
#
# Not every line is a fact. Some are numbers you must check in data. Some are guesses ("maybe", "I think"). Some are requests or questions from the interviewer. Sort them before you trust any of them. The rule is simple and the code is short.

# %%
import re

HEDGES = ("maybe", "probably", "i think")


def kind_of(text):
    # A rough toy: a keyword rule misfires, for example on a plain fact that
    # happens to contain "maybe". It is not a judge of what is true.
    # A person still reads each line.
    lower = text.lower()
    if any(hedge in lower for hedge in HEDGES):
        return "guess: verify"
    if re.search(r"\d", text):
        return "number: check in data"
    if text.endswith("?"):
        return "question"
    return "statement"


for line in TRANSCRIPT.strip().splitlines():
    speaker, text = line.split(": ", 1)
    # The FDE's own lines are requests or questions, not facts to sort.
    kind = ("question" if text.endswith("?") else "request") if speaker == "FDE" else kind_of(text)
    note = "  <- real need (lesson 03)" if "same day" in text else ""
    print(f"{speaker:<4} {kind:<22} {text[:50]}{note}")

# %% [markdown]
# Each kind goes somewhere else. A number goes to the data (lesson 05). A guess goes on the assumptions list (an **assumption** is something you believe without proof yet; lesson 03 keeps that list). The FDE's own requests and questions are part of the conversation, not open items. A statement about how the work runs is a lead to test in Step 3.
#
# The one open item is **ask the support agents**, because the ops lead does not know who else would use the tool. The real need to carry into scoping (lesson 03) is the ops lead's own: a label before an agent opens the message, so the easy ones go out the same day.

# %% [markdown]
# ### Step 3: decompose the request
#
# Now split "our deliveries are bad" into problems. The owners below are invented roles for the example. Each problem gets an observable and a test. The request itself is kept as the last row, because it is the one you started with.
#
# Where each problem came from: problem 1 from the eggs story and "maybe 12 times a week" (lines 2 and 4); problems 2 and 3 from lines 9 and 10. Those two were volunteered, so they are leads to test, not findings.

# %%
REQUIRED = ("observable", "test", "owner")


def missing_parts(problem):
    return [key for key in REQUIRED if not problem.get(key)]

# %% [markdown]
# A problem is testable only when all three keys are filled in. The check below reads them, and the last row fails it on purpose.

# %%
problems = [
    {"problem": "Missing and wrong items are filed by hand",
     "observable": "messages whose label an agent changes after review, per week",
     "test": "compare the first label with the reviewed label for two weeks of messages",
     "owner": "ops lead"},
    {"problem": "Late deliveries are not reported for a while",
     "observable": "days from delivery to the first support message",
     "test": "compare the delivery time in the order export with received_at in the message export",
     "owner": "store manager"},
    {"problem": "Damaged items go to the wrong queue",
     "observable": "damaged-item messages in the wrong queue, per week",
     "test": "join the queue log to the message export by message id",
     "owner": "support lead"},
    {"problem": "Our deliveries are bad",
     "observable": "", "test": "", "owner": ""},
]

for p in problems:
    gaps = missing_parts(p)
    status = "testable" if not gaps else "not testable yet, missing: " + ", ".join(gaps)
    print(f"{p['problem']:<46} {status}")

# %% [markdown]
# The first three rows are testable. The request in the last row is not, and it does not need to be. Its job is to be split until every piece passes the check.

# %% [markdown]
# ### Step 4: read the customer's data before you write code
#
# Discovery does not stop at the interview. Before you write any code, read what the customer's systems produce. Here is a tiny **invented** delivery-message export, written to `../data/02/`: one row per message that a customer sent about an order, with the label an agent picked by hand. The order-line export arrives in lesson 05: a larger invented file with more rows, copies and messy units and dates. This one has five rows, and one row is a duplicate on purpose.

# %%
import csv
from pathlib import Path

out_dir = Path("../data/02")
out_dir.mkdir(parents=True, exist_ok=True)
sample = out_dir / "delivery_messages_sample.csv"
sample.write_text(
    "message_id,order_id,store,received_at,label,message\n"
    "M-2001,BB-1001,Store 12,2026-10-20 18:40,missing_item,Order BB-1001: 6 eggs ordered and 4 came. Two eggs are missing.\n"
    "M-2002,BB-1002,Store 12,2026-10-20 19:05,late,Order BB-1002: the driver came 50 minutes after the slot.\n"
    "M-2003,BB-1003,Store 07,2026-10-20 19:30,damaged,Order BB-1003: the bread arrived squashed flat.\n"
    "M-2004,BB-1004,Store 07,2026-10-21 09:50,wrong_item,Order BB-1004: I got oat milk and I ordered whole milk.\n"
    "M-2004,BB-1004,Store 07,2026-10-21 09:50,wrong_item,Order BB-1004: I got oat milk and I ordered whole milk.\n"
)

with sample.open(newline="") as f:
    rows = list(csv.DictReader(f))

ids = [r["message_id"] for r in rows]
print("columns:", list(rows[0]))
print("rows:", len(rows))
print("message ids that appear more than once:", sorted({i for i in ids if ids.count(i) > 1}))

# %% [markdown]
# The sample is too small to check the late-delivery problem: every row is same-day or next-day, so it cannot show deliveries reported days later. A larger export can show that.

# Before you trust a column, ask the customer what it means, who writes it and when. Two questions from this sample: where does `received_at` come from, the support tool or the customer's phone? Why does `M-2004` appear twice: a retry in the export, or two real messages? Those questions are the discovery work. Step 5 applies the same habit to code.

# %% [markdown]
# ### Step 5: learn an unfamiliar codebase quickly
#
# Customers sometimes hand you their code. The first hour is for finding your way around, not for changing anything: list the files, find the entry point, then read one file. The tree below is **invented** for this example, a small delivery app that nobody on your team has seen. It lives in memory, so nothing is read from disk.

# %%
TREE = {
    "basket_app/__main__.py": 'from basket_app.app import main\n\nif __name__ == "__main__":\n    main()\n',
    "basket_app/app.py": "def main():\n    print('serving orders')\n",
    "basket_app/triage.py": "def unlabelled(messages):\n    return [m for m in messages if not m['label']]\n",
}

print("basket_app/ (invented):", *TREE, sep="\n  ")
print("entry point:", [p for p, text in TREE.items() if '__name__ == "__main__"' in text])
print("first lines of triage.py:", *TREE["basket_app/triage.py"].splitlines()[:2], sep="\n  ")

# %% [markdown]
# ## At work
#
# - Discovery, scoping or requirements work is named in 76% of the 97 FDE and applied-AI postings sampled in our research, so employers list it as a core duty. Scope what you learned in → lesson 03.
# - A decomposition exercise is a reported interview exercise: one report (techinterview.org and aced.io) gives 45 minutes to structure a vague problem such as "logistics delays" and to question an evasive **stakeholder** (anyone with a stake in the outcome). Practise the same moves in the Try it below.
# - The problems you split out become the tests you run during the proof-of-concept sprint (lesson 03 scopes it, lesson 09 delivers it).

# %% [markdown]
# ## Common mistakes
#
# - **Writing the solution as the problem.** "Build a dashboard" is a fix, not a problem. Write the failure, then the test.
# - **Trusting a guess.** A hedged line ("maybe 12 times a week") is a claim to check, not a fact.
# - **Reading a field that is not there.** A problem written down during a call, before anyone picked a test, has no `test` key. Reading it fails loudly:

# %% tags=["raises-exception"]
# A problem written down during a call, before anyone picked a test.
call_note = {"problem": "Missing and wrong items are filed by hand",
             "observable": "messages whose label an agent changes, per week",
             "owner": "ops lead"}

call_note["test"]

# %% [markdown]
# The fix is to add the key during discovery, or to read it with `call_note.get("test")`, which returns `None` instead of raising.

# %% [markdown]
# ## Try it
#
# The request is: "Support agents say delivery messages take too long to sort." Write two testable problems in the same format (problem, observable, test, owner). Pick each owner as the person who would confirm the result: the one who sees the number every day. For each test, name the log or export you would ask for. Then run the check. If a field is missing, the check says which one.

# %%
# your code here
new_problems = [
    # {"problem": ..., "observable": ..., "test": ..., "owner": ...},
]

for p in new_problems:
    gaps = missing_parts(p)
    print(p["problem"], "->", "testable" if not gaps else "missing: " + ", ".join(gaps))

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
new_problems = [
    {"problem": "Agents take too long to set a label",
     "observable": "minutes from received_at to the label being set, median per agent",
     "test": "compare received_at with the label time in the support tool log for 50 messages",
     "owner": "support lead"},
    {"problem": "Duplicate refunds reach the customer",
     "observable": "orders with two refund lines for the same item, per week",
     "test": "group the refund export by order id and item and count the pairs",
     "owner": "finance lead"},
]

for p in new_problems:
    gaps = missing_parts(p)
    print(p["problem"], "->", "testable" if not gaps else "missing: " + ", ".join(gaps))

# %% [markdown]
# ## Recap
#
# - Discovery asks about the failure first: what, how often, for whom, what people did next.
# - Sort what you heard into facts to check in data, guesses to verify, and requests for the next conversation.
# - Decompose a vague request until each problem has an observable, a test and an owner.
# - Read the customer's data before you write code; it shows the questions to ask.
# - Words to keep: **discovery**, **decomposition**, **assumption**, **observable**, **stakeholder** (all in GLOSSARY.md).
#
# **Interview:** "A customer says, 'Our deliveries are bad.' What do you do first?" Strong answer: "Ask for specific failures with counts and examples, split the request into testable problems with owners, and start with the one the data can test first."

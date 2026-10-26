# %% [markdown]
# # 11 · Build an eval set from real failures
#
# Level L3 · Part 2 · core · ~30 min · builds on lesson 10

# %% [markdown]
# ## Goal
#
# By the end of this lesson you can turn real failure cases from a customer's support queue into a labelled eval set file, score a real model prompt on it, and run a pytest regression check that blocks a new prompt when it breaks a case that passed before.

# %% [markdown]
# ## Why it matters
#
# Basket Bazaar (a fictional grocery delivery app) has a support queue with wrong tags. Lesson 10 showed that two good demo messages prove very little. The team now has twelve messages from the support queue, including ones the keyword rule tagged wrong, typed into a spreadsheet. Without a set, someone pastes each message into a chat window by hand, reads the answer and remembers the ones that look wrong. Each prompt change means twelve manual reads, and the case that broke last week is the one nobody re-reads. With the set in a file, one function scores every case and one pytest run blocks a release that breaks an old case.
#
# **When you don't need one:** a rule with one right answer per input that a plain unit test already covers. Use the tests you know.

# %% [markdown]
# ## The idea
#
# A **real failure** becomes a **case**: the customer's message, the order it names, and the **expected label** that a person writes before the feature runs. Many cases together are an **eval set** (also called a golden set). A **regression test** is a check that fails when a case that passed before now fails. Analogy: a pharmacy keeps a log of every dispensing error that reached a patient, and checks each new label against it before printing. The log grows with each incident and is never trimmed just because an old case is quiet.

# %% [markdown]
# ## Picture
#
# Real failures go into the eval set. Every new prompt is scored on the set, and the gate compares it with the version that shipped.

# %% [markdown]
# ```mermaid
# flowchart LR
#     Q[Support queue: real failures] --> C[Cases: message, order, expected label]
#     C --> K{Order exists in the export?}
#     K -- no --> F[Fix the case before any run]
#     K -- yes --> E[Eval set file]
#     E --> R[Score prompt v1 and candidate v2]
#     R --> G{pytest: no case that passed in v1 fails in v2?}
#     G -- no --> B[Blocked: fix v2]
#     G -- yes --> S[Ship v2, add new failures to the set]
# ```

# %% [markdown]
# ## Step by step

# %% [markdown]
# ### Step 1: the failure cases from the queue
#
# The twelve cases below are **invented** for this lesson. Ten are the messages from lesson 10, where the keyword rule got seven wrong. Two are new messages from the queue. Each names an order, and each expected label is written by hand, before any model runs. The notebook saves them as a CSV file in `data/11/`. The set records what each case must keep doing, not a list of today's failures: both prompts pass all twelve (Steps 3 and 4). The first code cell only sets up the model recording: no model is called yet.

# %%
import sys
sys.path.insert(0, "..")  # lets the notebook import llm_setup.py and llm_replay.py
import llm_replay
# Without a key, the saved recording is replayed, so the outputs below still appear.
llm_replay.start("11_eval-set-from-real-failures")  # records the model calls below once

# %% [markdown]
# The twelve cases are a list here. Each row is one labelled case: the id, the order, the message and the expected label.

# %%
import csv
import json
from pathlib import Path

DATA = Path("../data/11")
DATA.mkdir(parents=True, exist_ok=True)

CASES = [
    ("C01", "BB-1101", "Order BB-1101: the milk is missing from my delivery.", "missing_item"),
    ("C02", "BB-1102", "Order BB-1102: only three of the four eggs made it into the bag.", "missing_item"),
    ("C03", "BB-1103", "Order BB-1103: my bananas arrived bruised and brown.", "damaged"),
    ("C04", "BB-1104", "Order BB-1104: the driver came two hours after the slot.", "late"),
    ("C05", "BB-1105", "Order BB-1105: I was sent oat milk, I ordered almond.", "wrong_item"),
    ("C06", "BB-1106", "Order BB-1106: where is my delivery? The app still says pending.", "late"),
    ("C07", "BB-1107", "Order BB-1107: two bags of rice were not in the box.", "missing_item"),
    ("C08", "BB-1108", "Order BB-1108: the yoghurt came in a crushed pot.", "damaged"),
    ("C09", "BB-1109", "Order BB-1109: no bread at all, and I paid for it.", "missing_item"),
    ("C10", "BB-1110", "Order BB-1110: the courier left my order at the wrong flat.", "other"),
    ("C11", "BB-1112", "Order BB-1112: I got two of the three cartons I paid for.", "missing_item"),
    ("C12", "BB-1111", "Order BB-1111: the box split open and two tins rolled out.", "damaged"),
]

# %% [markdown]
# The list becomes a CSV file, one row per case. The first three lines show it.

# %%
with (DATA / "eval_set.csv").open("w", newline="") as f:
    csv.writer(f).writerows([["case_id", "order_id", "message", "want"], *CASES])

print((DATA / "eval_set.csv").read_text().splitlines()[:3], "...")

# %% [markdown]
# ### Step 2: check each case before it is used
#
# A case that names an order the export does not have cannot be scored fairly, and a bad label is a bad test. The check below loads the cases with a Pydantic model, so a typo in a label fails at once. Then it looks each order up in lesson 05's clean orders file. That file is invented with a fixed random seed, with no real customer data. First, a peek at it.

# %%
from typing import Literal, get_args

from pydantic import BaseModel, Field

with open("../data/05/orders_clean.csv", newline="") as f:
    print(f.readline().strip(), "(header of the orders file)")

Issue = Literal["missing_item", "wrong_item", "late", "damaged", "other"]
VALID = set(get_args(Issue))


class EvalCase(BaseModel):
    case_id: str
    order_id: str = Field(pattern=r"^BB-\d{4}$")
    message: str = Field(min_length=10)
    want: Issue


with (DATA / "eval_set.csv").open(newline="") as f:
    cases = [EvalCase(**row) for row in csv.DictReader(f)]

with open("../data/05/orders_clean.csv", newline="") as f:
    ORDER_IDS = {row["order_id"] for row in csv.DictReader(f)}

unknown = [c.case_id for c in cases if c.order_id not in ORDER_IDS]
print(f"{len(cases)} cases loaded; orders not in the export: {unknown or 'none'}")

# %% [markdown]
# ### Step 3: the feature, and prompt v1 (what shipped)
#
# The feature is the real model with a prompt. All twelve messages go in one request, and the model returns one label per case id. That keeps the set to one model call per prompt, not twelve. The scorer is plain code: it compares each label with the expected one, and a missing answer counts as a fail. The helper cells below only define functions. Nothing calls the model yet.

# %% [markdown]
# The labels come back in one structure, `TriageBatch`, and `PROMPT_V1` is the prompt that shipped. Nothing is called yet.

# %%
class Triage(BaseModel):
    case_id: str = Field(description="the case id exactly as given, such as C01")
    issue: Issue


class TriageBatch(BaseModel):
    labels: list[Triage] = Field(description="one entry for every case id given")


PROMPT_V1 = ("Label each grocery delivery support message with one issue: missing_item, wrong_item, "
             "late, damaged or other. Return one label for every case id.")

# %% [markdown]
# `score` compares each label with the expected one, and a missing answer counts as a fail. `show` prints the score and each failing case. Both are plain code.

# %%
def score(labels: dict) -> dict:
    return {c.case_id: {"want": c.want, "got": labels.get(c.case_id),
                        "passed": labels.get(c.case_id) == c.want} for c in cases}


def show(name: str, rows: dict) -> None:
    print(f"{name}: {sum(r['passed'] for r in rows.values())} of {len(rows)} pass")
    text = {c.case_id: c.message for c in cases}
    for cid, r in rows.items():
        if not r["passed"]:
            print(f"  FAIL {cid}: want={r['want']:<12} got={str(r['got']):<12} {text[cid][:44]}")

# %% [markdown]
# `run_feature` is the real model call: all twelve messages go in one request, and one label per case id comes back. It is only defined here.

# %%
def run_feature(prompt: str) -> dict:
    from llm_setup import get_llm
    numbered = "\n".join(f"{c.case_id}: {c.message}" for c in cases)
    batch = get_llm().with_structured_output(TriageBatch, method="json_schema").invoke(
        [("system", prompt), ("human", numbered)])
    return {t.case_id: t.issue for t in batch.labels}

# %% [markdown]
# Now the first model call: prompt v1, the version that shipped. The result is scored and saved to `data/11/scored_v1.json`. Later cells read that file, so they still run when the model step is skipped. Without a key, the saved recording replays this call, and the later cells use the saved score files.

# %% tags=["needs-llm"]
rows_v1 = score(run_feature(PROMPT_V1))
(DATA / "scored_v1.json").write_text(json.dumps(rows_v1, indent=1))
show("prompt v1", rows_v1)

# %% [markdown]
# ### Step 4: prompt v2, the candidate
#
# The team edits the prompt. Version 2 is a tidier prompt: it writes the five definitions down, and it adds one rule: a count of items (two, three, only, not all) is a missing_item. C11 ("two of the three cartons") already passes under v1, so the new rule is not there to fix it. The team wants to know whether the new rule breaks anything. The candidate has not shipped. This is the second and last model call in the lesson, so the notebook makes two calls in total.

# %%
PROMPT_V2 = PROMPT_V1 + """
Definitions:
- missing_item: the customer did not get all of an item they paid for, even when they say only some of it arrived.
- late: the delivery came after the slot, or still shows as pending.
- damaged: broken, bruised, crushed, split or leaking.
- wrong_item: the customer got a different item from the one ordered.
- other: none of the above, such as a courier problem.
- Rule: if the customer names a count of items (two, three, only, not all), the issue is missing_item."""

# %% [markdown]
# The second model call: the same twelve cases, with prompt v2. The result is saved to `data/11/scored_v2.json`.

# %% tags=["needs-llm"]
rows_v2 = score(run_feature(PROMPT_V2))
(DATA / "scored_v2.json").write_text(json.dumps(rows_v2, indent=1))
show("prompt v2 (candidate)", rows_v2)

# %% [markdown]
# Both prompts score 12 of 12 on these invented cases, so this set cannot tell them apart. Equal scores do not prove nothing changed. Step 5 checks the cases one by one.

# %% [markdown]
# ### Step 5: the regression test in pytest
#
# A pass count can hide a swap: a candidate can fix two cases and break one that passed before. The gate is a pytest file. It reads the two saved score files, and it fails when a case that passed in v1 fails in v2. It also checks the eval set itself: unique ids, valid labels and known orders. No model is called here. The file is written into `data/11/` and run in a subprocess, as lesson 04 does. The cell below is a file write (`%%writefile`): it only saves the test file, and nothing runs yet.

# %%
%%writefile ../data/11/test_eval_regression.py
"""Regression checks for the triage eval (lesson 11). No model is called: they read the saved files."""
import csv
import json
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
VALID = {"missing_item", "wrong_item", "late", "damaged", "other"}


def cases():
    with (HERE / "eval_set.csv").open(newline="") as f:
        return list(csv.DictReader(f))


def scored(name):
    path = HERE / f"scored_{name}.json"
    if not path.exists():
        pytest.skip(f"no scored results for {name}")
    return json.loads(path.read_text())


def test_case_ids_are_unique():
    ids = [c["case_id"] for c in cases()]
    assert len(ids) == len(set(ids))


def test_every_case_has_a_valid_label_and_a_known_order():
    orders = HERE.parent / "05" / "orders_clean.csv"  # lesson 05's clean orders file
    known = {row["order_id"] for row in csv.DictReader(orders.open(newline=""))}
    for c in cases():
        assert c["want"] in VALID, c["case_id"]
        assert c["order_id"] in known, c["case_id"]


def test_candidate_answers_every_case():
    missing = [cid for cid, r in scored("v2").items() if r["got"] is None]
    assert missing == [], f"no label for: {missing}"


def test_no_regression_from_shipped_to_candidate():
    shipped, candidate = scored("v1"), scored("v2")
    broken = [cid for cid, r in shipped.items() if r["passed"] and not candidate[cid]["passed"]]
    assert broken == [], f"regressions, release blocked: {broken}"

# %% [markdown]
# Run the file with pytest, in a subprocess, from the data folder, with `--color=no` so the output is plain text. Exit code 0 means every check passed. A non-zero code means the gate blocked the release, and the last lines name the case.

# %%
import subprocess

result = subprocess.run([sys.executable, "-m", "pytest", "-q", "--color=no", "-p", "no:cacheprovider",
                         "test_eval_regression.py"],
                        cwd=str(DATA.resolve()), capture_output=True, text=True)
print("pytest exit code:", result.returncode, "(0 means all checks passed)")
print("\n".join(result.stdout.strip().splitlines()[-4:]))

# %% [markdown]
# Read the result. Both prompts score 12 of 12 on these invented cases, so this set cannot tell them apart. The gate passes, and v2 could ship. That is a weak answer: a swap can only show on a case that the shipped prompt gets right some of the time, and this set has none of those. Try it below adds three harder cases.

# %% [markdown]
# To see the gate fire, take the candidate's scores, flip one case to failed in a copy, and run the same check. The saved file is not changed. No model call is needed.

# %%
shipped = json.loads((DATA / "scored_v1.json").read_text())
flipped = json.loads((DATA / "scored_v2.json").read_text())  # a copy in memory
flipped["C11"]["passed"] = False  # the copy: one case flipped to failed
broken = [cid for cid, r in shipped.items() if r["passed"] and not flipped[cid]["passed"]]
print(f"regressions, release blocked: [{', '.join(broken)}]" if broken else "pass", "| exit code:", int(bool(broken)))

# %% [markdown]
# ## At work
#
# - Anthropic's guide to agent evals says to start with 20 to 50 tasks drawn from real failures, such as a support queue or a bug tracker. It also says a 0% pass rate usually means a broken task, so read the transcripts first (https://anthropic.com/engineering/demystifying-evals-for-ai-agents). → lesson 12 grades the model's outputs with code, a model and a human, and compares them.
# - The same guide separates capability evals (start low) from regression evals (near 100%). A capability eval the feature now passes moves into the regression set.
# - Tests for the code around the model are ordinary pytest tests, run in CI (for example GitHub Actions) on every change. The set only covers cases someone wrote down, so lesson 16 adds logs, traces and a latency metric to see what live requests actually do.
#
# Go deeper: repeated runs of the same case (pass^k) are not covered here.

# %% [markdown]
# ## Common mistakes
#
# - **A typo in a label.** The label `missing` is not one of the five. Pydantic refuses it at once, so the bad case never reaches the scorer.

# %% tags=["raises-exception"]
EvalCase(case_id="C01", order_id="BB-1101", message="the milk is missing from my delivery", want="missing")

# %% [markdown]
# - **Writing the expected label after seeing the model's answer.** Then the case tests the model's habit, not the customer's need. Write the label first, from the business rule, and only then run the feature.
# - **Trusting a case whose order is not in the export.** Step 2 catches it. A case that names no real order can pass or fail for the wrong reason.

# %% [markdown]
# ## Try it
#
Write `check_new_case(row)`. It takes one new row from the queue, before anyone runs the model, and returns the problems: a label that is not one of the five, an order the export does not have, or a `case_id` already in the set. An empty list means the row can be added. The stub returns `None` until you replace `...`. Then test it on the row below, which has a label typo, an order the export does not have, and a case id already in the set. `VALID`, `ORDER_IDS` and `cases` from Step 2 are already defined; use them.

# %%
# your code here
def check_new_case(row: dict) -> list[str]:
    """Problems with a new case row. An empty list means it can be added."""
    ...  # write the three checks


new_row = {"case_id": "C01", "order_id": "BB-1199", "message": "my melon came in a crushed box", "want": "damged"}
print(check_new_case(new_row))

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
def check_new_case(row: dict) -> list[str]:
    """Problems with a new case row. An empty list means it can be added."""
    problems = []
    if row["want"] not in VALID:
        problems.append(f"label {row['want']!r} is not one of the five")
    if row["order_id"] not in ORDER_IDS:
        problems.append(f"order {row['order_id']} is not in the export")
    if row["case_id"] in {c.case_id for c in cases}:
        problems.append(f"case id {row['case_id']} is already in the set")
    return problems


print(check_new_case(new_row))

# %% [markdown]
# **Harder cases.** The set has no case the shipped prompt gets right only sometimes. Write three new rows before anyone runs the model, in a list called `hard_rows`:
#
# 1. a message that mixes late and damaged. Decide the label first and write the team rule that picks it.
# 2. a count message that is really `wrong_item`, such as "I ordered two limes and got two lemons". The count rule in v2 would say `missing_item`.
# 3. a vague message such as "something is off with my order". Its label is `other`.
#
# Give each a case id from `C13`, an order id from the export and the label you wrote. Check each with `check_new_case`. Running the model on them would be a model call; the budget is two, so stop here.

# %%
# your code here
hard_rows = []  # three dicts: case_id, order_id, message, want

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
hard_rows = [
    {"case_id": "C13", "order_id": "BB-1111", "message": "the yoghurt came two hours late and the lid was cracked", "want": "damaged"},
    {"case_id": "C14", "order_id": "BB-1112", "message": "I ordered two limes and got two lemons.", "want": "wrong_item"},
    {"case_id": "C15", "order_id": "BB-1105", "message": "something is off with my order, I cannot say what.", "want": "other"},
]
for row in hard_rows:
    print(row["case_id"], check_new_case(row) or "can be added")

# %% [markdown]
# ## Recap
#
# - A real failure becomes a case: the message, the order it names, and an expected label written before the run.
# - Score every prompt on the same set, and keep the scorer in code.
# - A **regression** is a case that passed in the shipped version and fails in the candidate. A pytest **gate** blocks the release on it.
# - Check the set itself first: valid labels, known orders, unique ids. A broken case looks like a broken feature.
# - A set that every version passes cannot show a regression. Add harder cases (Try it) that the shipped prompt gets right only some of the time.
#
# **Interview:** "How do you test an LLM feature before you change its prompt?" Strong answer: "I keep a labelled set of real failures with expected answers written first. I score the old and new prompt on it, and a pytest gate fails the change if any case that passed before now fails."

# %%
llm_replay.stop()  # saves the recording of the two model calls

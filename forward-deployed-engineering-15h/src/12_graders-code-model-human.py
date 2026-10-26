# %% [markdown]
# # 12 · Grade outputs with code, a model and a person
#
# Level L3 · Part 2 · professional · ~30 min · builds on lesson 11

# %% [markdown]
# ## Goal
#
# By the end of this lesson you can grade one batch of drafted customer replies three ways (with code rules, with a model grader and with a person's review sample), and measure how often the graders agree, so you know which automatic grader you can trust.

# %% [markdown]
# ## Why it matters
#
# Lesson 11 graded a label, which is easy to check. A customer reply is free text. No `==` tells you whether a reply is polite, answers the problem, or promises a refund the team cannot give. Teams usually fail in one of two ways: they read every reply by hand and tire after a few, or they trust one automatic check that nobody tests.
#
# With three graders, each checks what it does well. An agreement number tells you whether the automatic grader can stand in for the person.
#
# **When you don't need this:** an output with one right answer, such as a label or a number. Exact match from lesson 11 is enough there.

# %% [markdown]
# ## The idea
#
# A **grader** marks an output as pass or fail. Three kinds exist, and each has a blind spot. A **code grader** is fast and cheap but reads only the words, so it misses meaning. A **model grader** reads meaning against a written **rubric**, but it can be lenient and change between runs. A **person** is the gold standard and too slow for every case. The usual setup: code checks rules, a model checks meaning, and a person reviews a sample to measure both.
#
# Analogy: a machine marks multiple-choice questions, a teacher marks essays, and a head teacher re-marks a sample to check the teacher is strict in the same way.

# %% [markdown]
# ## Picture
#
# One batch of replies goes to all three graders. The agreement check decides which grader can run alone.

# %% [markdown]
# ```mermaid
# flowchart LR
#     R[Drafted replies from the feature] --> C[Code grader: rules on words]
#     R --> M[Model grader: rubric on meaning]
#     R --> P[Person: review sample]
#     C --> A{Agreement with the person}
#     M --> A
#     P --> A
#     A -- high --> T[Automatic grader runs on every release]
#     A -- low --> F[Fix the rubric or the rules, then grade again]
# ```

# %% [markdown]
# ## Step by step

# %% [markdown]
# ### Step 1: the cases and the replies to grade
#
# The twelve cases come from lesson 11: the customer's message, the order it names and the issue label written before any run. The notebook reads them from `data/11/eval_set.csv`, which lesson 11 writes. The first model call drafts one reply per case with the feature's prompt. All twelve go in one request, so the lesson makes two model calls in total. Replay means the saved answers are used when there is no key.

# %%
import sys
sys.path.insert(0, "..")  # lets the notebook import llm_setup.py and llm_replay.py
import llm_replay
llm_replay.start("12_graders-code-model-human")  # records the two model calls below once

import csv
import json
from pathlib import Path

DATA = Path("../data/12")
DATA.mkdir(parents=True, exist_ok=True)
SRC = Path("../data/11/eval_set.csv")  # written by lesson 11
if not SRC.exists():
    raise FileNotFoundError("Run lesson 11 first: it writes the twelve cases this lesson grades.")

with SRC.open(newline="") as f:
    cases = list(csv.DictReader(f))
print(len(cases), "cases. Three rows:")
for c in cases[:3]:
    print(c["case_id"], c["order_id"], c["want"], "|", c["message"])

# %% [markdown]
# The feature is the reply writer. Its prompt asks for two or three sentences that name the order and say what happens next. The output is checked, typed data, as in lesson 06: one `Draft` per case id.

# %%
from pydantic import BaseModel, Field

from llm_setup import get_llm


class Draft(BaseModel):
    case_id: str = Field(description="the case id exactly as given, such as C01")
    reply: str = Field(description="the reply to the customer, two or three sentences")


class DraftBatch(BaseModel):
    replies: list[Draft] = Field(description="one reply for every case id given")


PROMPT_REPLY = ("You write the reply a grocery delivery company sends to a customer about a problem with "
                "an order. For each case id, write two or three sentences. Name the order id and say what "
                "the team will do next. Return one reply for every case id.")


def draft_replies() -> dict:
    numbered = "\n".join(f"{c['case_id']} (order {c['order_id']}): {c['message']}" for c in cases)
    batch = get_llm().with_structured_output(DraftBatch, method="json_schema").invoke(
        [("system", PROMPT_REPLY), ("human", numbered)])
    return {d.case_id: d.reply for d in batch.replies}

# %% [markdown]
# The first model call: one reply per case. The replies are saved to `data/12/replies.json`, so the grading cells below read the same text every run.

# %% tags=["needs-llm"]
replies = draft_replies()  # model call 1 of 2
(DATA / "replies.json").write_text(json.dumps(replies, indent=1))
print(len(replies), "replies saved. One of them:", replies["C01"])

# %% [markdown]
# ### Step 2: the code grader
#
# The code grader is a list of yes-or-no rules on the words of the reply. It needs no model, runs in microseconds and gives the same answer every time. Each rule is a separate check, so a failure names the rule that broke. A reply passes only when every rule passes. The rules are a short list in code, so the team can read and change them.

# %%
import re

MONEY = re.compile(r"[$£€]\s?\d|\b\d+\s?(?:pounds|dollars|euros)\b", re.IGNORECASE)
TIME_PROMISE = re.compile(
    r"\b(?:within|in|by|before)\s+(?:\d+|an?|one|two|three|four|five|six)\s+(?:minutes?|hours?|days?)\b"
    r"|\b(?:today|tomorrow|tonight)\b", re.IGNORECASE)


def code_grade(case: dict, reply: str) -> dict:
    """Plain rules on the words. The reply passes when every rule passes."""
    rules = {
        "names_order": case["order_id"] in reply,
        "no_money": not MONEY.search(reply),
        "no_time_promise": not TIME_PROMISE.search(reply),
        "length_ok": 15 <= len(reply.split()) <= 60,
    }
    return {"passed": all(rules.values()), "failed": [name for name, ok in rules.items() if not ok]}


code_results = {c["case_id"]: code_grade(c, replies[c["case_id"]]) for c in cases}
print("code grader passes:", sum(r["passed"] for r in code_results.values()), "of", len(code_results))
for cid, r in code_results.items():
    if not r["passed"]:
        print(f"  {cid} fails {r['failed']}")

# %% [markdown]
# Read the output. In the recorded run only one reply fails, C03, on the word "today". The rule list has no entry for "immediately", so a reply that promises something "immediately" passes. The rules also cannot tell whether a reply answers the problem: a reply that names the order and has the right length passes even when it talks about the wrong issue. The model grader covers that part. Step 5 shows what the rules miss.
#
# The numbers in this lesson come from the recorded run. A live run may draft different replies, so every count below may change, and the gate may fail.

# %% [markdown]
# ### Step 3: the model grader
#
# The model grader reads each reply with the customer's message and the issue label, and applies a written rubric. It returns a pass or fail and a one-line reason, so a person can check the reason as well as the verdict. All twelve replies go in one request, which is the second and last model call. The rubric is short on purpose: a long rubric gives the grader more places to be inconsistent.

# %%
class Verdict(BaseModel):
    case_id: str = Field(description="the case id exactly as given")
    passed: bool = Field(description="true only if the reply meets the rubric")
    reason: str = Field(description="one sentence that quotes the part of the reply that decided it")


class VerdictBatch(BaseModel):
    verdicts: list[Verdict] = Field(description="one verdict for every case id given")


RUBRIC = ("You grade a customer reply. Pass it only if both hold:\n"
          "1. It answers the problem the customer reports, using the issue label given "
          "(missing_item means something the customer paid for did not arrive).\n"
          "2. It makes no promise the company cannot check: no refund amount, no delivery time, no date.\n"
          "Otherwise fail it. Give one verdict for every case id.")


def model_grade() -> dict:
    items = "\n".join(f"{c['case_id']} | label: {c['want']} | customer: {c['message']} | reply: {replies[c['case_id']]}"
                      for c in cases)
    batch = get_llm().with_structured_output(VerdictBatch, method="json_schema").invoke(
        [("system", RUBRIC), ("human", items)])
    return {v.case_id: {"passed": v.passed, "reason": v.reason} for v in batch.verdicts}

# %% [markdown]
# The second model call: the same twelve replies, graded against the rubric. The verdicts are saved to `data/12/model_grades.json`.

# %% tags=["needs-llm"]
model_results = model_grade()  # model call 2 of 2
(DATA / "model_grades.json").write_text(json.dumps(model_results, indent=1))
print("model grader passes:", sum(r["passed"] for r in model_results.values()), "of", len(model_results))

# %% [markdown]
# ### Step 4: a person's review sample
#
# A person reads the twelve replies and writes pass or fail. The grades are a **sample the course team wrote** to show the method. In your team a support lead writes them, and they become the reference the automatic graders are measured against.
#
# The person's rule: fail any promise about time, vague or specific, and any refund amount. The rubric in Step 3 names only amounts, delivery times and dates, so it can miss a vague word such as "shortly". Here the fails are "immediately" (C01, C07, C11), "right away" (C02, C09), "as soon as possible" (C05), "today" (C03) and "shortly" (C06). The passes (C04, C08, C10, C12) name no time and no amount.

# %%
HUMAN = {"C01": False, "C02": False, "C03": False, "C04": True, "C05": False, "C06": False,
         "C07": False, "C08": True, "C09": False, "C10": True, "C11": False, "C12": True}  # True = pass
print(sum(HUMAN.values()), "of", len(HUMAN), "pass")

# %% [markdown]
# ### Step 5: how far the graders agree
#
# **Percent agreement** counts the cases where two graders give the same verdict. **Cohen's kappa** subtracts the agreement two graders would reach by chance. Kappa is 1 for perfect agreement, 0 at chance level, and below 0 when they agree less than chance. Worked example: a grader that passes every reply agrees with a person who passed nine of twelve on 75% of cases, yet its kappa is 0. `cohen_kappa_score` computes it. A kappa under about 0.6 is a common rule of thumb (not a standard) for more work before the grader runs alone.

# %%
from sklearn.metrics import cohen_kappa_score

ids = [c["case_id"] for c in cases]
code_pass = {i: code_results[i]["passed"] for i in ids}
model_pass = {i: model_results[i]["passed"] for i in ids}


def compare(name: str, a: dict, b: dict) -> None:
    same = sum(a[i] == b[i] for i in ids) / len(ids)
    kappa = cohen_kappa_score([a[i] for i in ids], [b[i] for i in ids])
    print(f"{name:<18} agree {same:.0%}   kappa {kappa:.2f}")


compare("code vs person", code_pass, HUMAN)
compare("model vs person", model_pass, HUMAN)
compare("code vs model", code_pass, model_pass)

# %% [markdown]
# Now the cases where the graders disagree with the person. The reasons come from the graders, so a reader can see why each one decided.

# %%
for cid in ids:
    if code_pass[cid] != HUMAN[cid]:
        print(f"{cid}: code says {code_pass[cid]}, person says {HUMAN[cid]}")
    if model_pass[cid] != HUMAN[cid]:
        print(f"{cid}: model says {model_pass[cid]}, person says {HUMAN[cid]}. Reason: {model_results[cid]['reason']}")

# %% [markdown]
# The code grader disagrees most. In the recorded run it passes seven replies the person failed, because its rules have no entry for "immediately", "right away" or "as soon as possible". The model grader misses two. C03 says "today" (a date promise), but the model passed it. C06 says "shortly", a time promise the model did not count. In the recorded run the model agrees on ten of twelve. Neither grader is right everywhere.

# %% [markdown]
# Add the missing phrases to the rule and run the same cases again. `code_grade` looks up `TIME_PROMISE` when it runs, so the new pattern is used. Run the next cell once: running it again stacks the same phrases onto the pattern. Cell 15's results stay the v1 results. This step calls no model.

# %%
TIME_PROMISE = re.compile(TIME_PROMISE.pattern + r"|\b(?:immediately|right away|as soon as possible)\b", re.IGNORECASE)
code_v2_pass = {c["case_id"]: code_grade(c, replies[c["case_id"]])["passed"] for c in cases}
compare("code v2 (tuned on 12)", code_v2_pass, HUMAN)

# %% [markdown]
# Read the last line with care. The phrases were chosen after reading these twelve replies, so the test flatters the rule. In the recorded run the rule agrees on eleven of twelve; its one miss is C06, "shortly", a phrase no rule names yet. The number shows that the rule matches this sample, not that it will match next month's replies. The only honest check is new cases, which the team grades with the person and runs through the same code. Lesson 16 shows how to keep these checks running on live traffic.

# %% [markdown]
# ### Step 6: a gate in pytest
#
# The gate turns the numbers into a rule a release can fail. Every case needs a verdict from each grader, and each automatic grader must reach kappa 0.6 or more against the person. The gate tests the fixed v2 rule, the one with the three extra phrases. The first rule (kappa 0.09 in the recorded run) would be blocked, as the check in the run cell below shows.

# %% [markdown]
# The test reads the saved verdicts from `data/12/`; the run cell further down saves them. Two checks: every case has a verdict from each grader, and each automatic grader reaches kappa 0.6 against the person. The cell below only saves the file; nothing runs yet.

# %%
%%writefile ../data/12/test_grader_gate.py
"""Gate for the graders (lesson 12). No model is called: it reads the saved verdicts."""
import json
from pathlib import Path

import pytest
from sklearn.metrics import cohen_kappa_score

HERE = Path(__file__).resolve().parent
GRADERS = {"code": "code_v2.json", "model": "model.json"}


def load(name):
    return json.loads((HERE / name).read_text())


def test_every_case_has_a_verdict_from_each_grader():
    if not (HERE / "person.json").exists():
        pytest.skip("no saved verdicts yet")
    person = load("person.json")
    for name in GRADERS.values():
        assert set(load(name)) == set(person), name


def test_each_automatic_grader_agrees_with_the_person():
    if not (HERE / "person.json").exists():
        pytest.skip("no saved verdicts yet")
    person = load("person.json")
    for grader, name in GRADERS.items():
        got = load(name)
        kappa = cohen_kappa_score([got[c] for c in person], [person[c] for c in person])
        assert kappa >= 0.6, f"{grader} grader kappa {kappa:.2f} is below 0.6: do not run it alone"

# %% [markdown]
# Run it with pytest from the data folder. This cell first saves the verdicts the gate reads (no model call), then prints the first rule's check. Exit code 0 means both automatic graders passed the gate. Otherwise the last lines name the grader and its kappa.

# %%
import subprocess

# save the verdicts the gate reads (no model call)
for name, verdicts in {"person": HUMAN, "code_v2": code_v2_pass, "model": model_pass}.items():
    (DATA / f"{name}.json").write_text(json.dumps(verdicts, indent=1))
print("first code rule passes the 0.6 bar:", cohen_kappa_score([code_pass[i] for i in ids], [HUMAN[i] for i in ids]) >= 0.6)

result = subprocess.run([sys.executable, "-m", "pytest", "-q", "--color=no", "-p", "no:cacheprovider",
                         "test_grader_gate.py"], cwd=str(DATA.resolve()), capture_output=True, text=True)
print("gate exit code:", result.returncode, "(0 means both automatic graders passed the gate)")
print("\n".join(result.stdout.strip().splitlines()[-3:]))

# %% [markdown]
# ## At work
#
# - Anthropic's eval guide names three grader types: code (fast, brittle), model (flexible, must be calibrated against humans) and human (gold, slow) (https://anthropic.com/engineering/demystifying-evals-for-ai-agents). → lesson 16 keeps these checks running on live traffic.
# - In a customer engagement, domain experts write the review sample in the first two weeks, and the agreed score becomes the acceptance test. → lesson 20 is a checkpoint built this way.
# - A model grader is a paid call on every run. A nightly suite of thousands costs real money, so set a budget per customer. → lesson 18.
#
# Go deeper: repeated runs of the same reply to find flaky grades, and checks that the model grader does not favour the longer reply.

# %% [markdown]
# ## Common mistakes
#
# - **A grader with a missing verdict.** The person's list has eleven grades, but the code list has twelve. `cohen_kappa_score` refuses to compare lists of different lengths, so the mistake shows at once. Compare by case id, and check that every grader covered every case.

# %% tags=["raises-exception"]
cohen_kappa_score([code_pass[i] for i in ids], [HUMAN[i] for i in ids[:11]])  # the last person grade is missing

# %% [markdown]
# The error message lists the lengths it found: 12 against 11, the mismatch.
#
# - **Reading twelve cases as a precise number.** One changed verdict moves percent agreement by about eight points. Use the kappa as a warning sign, and collect more cases before you decide anything about a release.
# - **Writing the rule after seeing the replies, then trusting the score.** That is what Step 5 did on purpose. Keep a second set of replies that nobody read before the rules were written, and measure on it.

# %% [markdown]
# ## Try it
#
# Write `percent_agreement(a, b)`. It returns the share of positions where the two lists give the same verdict, as a number from 0 to 1. Then try it on a lazy grader that passes every reply, against a person who passed nine replies and failed three. The percent looks fine, and kappa shows the problem. Use `cohen_kappa_score` from Step 5 for the comparison. Until you write the function, the stub returns None, so the print shows None: that is expected.

# %%
# your code here
def percent_agreement(a: list, b: list) -> float:
    """Share of positions where the two verdict lists match."""
    ...  # write it: a number from 0 to 1


lazy = [True] * 12                  # a grader that passes every reply
person = [True] * 9 + [False] * 3   # nine good replies, three bad ones
print(percent_agreement(lazy, person), cohen_kappa_score(lazy, person))

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
def percent_agreement(a: list, b: list) -> float:
    """Share of positions where the two verdict lists match."""
    return sum(x == y for x, y in zip(a, b)) / len(a)


lazy = [True] * 12
person = [True] * 9 + [False] * 3
print(percent_agreement(lazy, person), cohen_kappa_score(lazy, person))  # 0.75 and 0.0: the lazy grader is no better than chance

# %% [markdown]
# ## Recap
#
# - A **code grader** checks rules on the words: fast and repeatable, but blind to meaning and to phrases no rule names.
# - A **model grader** applies a short rubric to meaning. Check its verdicts and reasons.
# - A **person's** review sample is the reference. Measure every automatic grader against it.
# - **Percent agreement** is flattered by a grader that always says pass. **Cohen's kappa** corrects for that.
# - Twelve cases give a warning, not a measurement. Grade new cases before you trust a rule.
#
# **Interview:** "How do you know your LLM grader is trustworthy?" Strong answer: "I measure it against a person's sample with kappa, and re-measure on new cases whenever the rubric or model changes."

# %%
llm_replay.stop()  # saves the recording of the two model calls

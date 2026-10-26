# %% [markdown]
# # 10 · Why customer AI needs evals: failures you can't see
#
# Level L3 · Part 2 · core · ~20 min · builds on lesson 06

# %% [markdown]
# ## Goal
#
# By the end of this lesson you can explain why a customer AI feature can pass a demo and still fail quietly. You can say what an eval does that a demo never does: it scores the feature on a labelled set of cases, and it names the old case that a new fix breaks.

# %% [markdown]
# ## Why it matters
#
# Basket Bazaar (a fictional grocery delivery app) wants an AI assistant that tags each customer message: missing item, late, damaged, wrong item or other. The team tries two messages, both tagged right, and says "ready". In the first week the support queue fills with wrong tags. Nothing crashes and no error is logged. The feature returns a wrong label that looks like a normal answer.
#
# Without an eval, the only test is a person reading outputs, and they read the cases they remember. A change that breaks a case from last week goes unseen. With an eval, labelled cases are scored on every change, and each failure has a name.
#
# **When you don't need one:** a feature with one correct answer per input that a plain unit test already covers, such as a price calculation in code. Use the tests you already know.

# %% [markdown]
# ## The idea
#
# An **eval** is a repeatable test for an AI feature. It has four parts: fixed inputs, the answer a person expects for each one, a scorer that marks each answer right or wrong, and a score you can compare from one version to the next. A **regression** is a case that passed before a change and fails after it. A **regression eval** is the set of cases that must keep passing. Analogy: a driving test is not one lucky drive. It is a fixed route with set manoeuvres, each marked, so a learner who passes parking and fails the lane change is told exactly where they failed.

# %% [markdown]
# ## Picture
#
# The feature runs on every case in the eval set. The scorer compares each output with the expected label, and a gate decides whether a change can ship.

# %% [markdown]
# ```mermaid
# flowchart LR
#     C[Customer message] --> F[AI feature]
#     F --> O[Output: a label]
#     O --> S{Scorer: same as expected label?}
#     E[Eval set: real cases + expected labels] --> S
#     S --> R[Score and list of named failures]
#     R --> G{Gate: no case that passed before now fails?}
# ```

# %% [markdown]
# ## Already know this?
#
# Part 2 covers evaluating, securing, deploying and observing a customer AI feature. Five quick questions cover it. If you can answer all of them, skip to lesson 20 (the Part's checkpoint).
#
# 1. Why can a feature pass a demo and still give wrong answers to real customers?
# 2. What does a regression eval catch that a single demo never shows?
# 3. Name the three kinds of grader and the trade-off of each.
# 4. A customer's network blocks the internet. Where does the model call go?
# 5. How do you follow one slow request across the model call and the tool call?

# %% [markdown]
# <details>
# <summary>Answers (click to open)</summary>
#
# 1. The demo used cases the builder picked, and no expected answers were written down first. Two cases show the feature can work, not how often it does.
# 2. A change that fixes one case and breaks an older one. The demo only shows the case being fixed.
# 3. Code (fast and cheap, brittle), model (flexible, not deterministic, check it against people) and human (the gold standard, slow). See lesson 12.
# 4. Through a private route or an egress proxy the customer allows, not the open internet. See lesson 15.
# 5. One trace with a span for each model and tool call, sent to the customer's collector. See lesson 16.
#
# </details>

# %% [markdown]
# ## Explained
#
# ### Why a demo lies, and three failures you cannot see
#
# A demo uses cases its builder chose, with no expected answer written first. Two good outputs show the feature can work, not how often. The failures below all look normal:
#
# | Failure | What you see | Why nothing alarms |
# |---|---|---|
# | Wrong answer, well formed | a valid label, the wrong one | the output passes the shape check from lesson 06 |
# | Quiet miss on wording | "only three of the four milks made it into the bag" is tagged `other` | no error; the words differ from the rule or prompt |
# | Regression | a fix for case A breaks case B | the new version looks good on the case you were fixing |
#
# ### What an eval needs
#
# - **Inputs**: real messages from the support queue.
# - **Expected answers**: written by a person who knows the business, before the run.
# - **A scorer**: code, a model or a person (lesson 12).
# - **A gate**: blocks a release when an old case fails.

# %% [markdown]
# ## Worked example
#
# The feature here is a keyword rule, not a model. It is deterministic, so the numbers below repeat exactly on every run. A model fails the same way, with more varied wording. Lesson 11 runs a real model on this kind of set.

# %% [markdown]
# ### Without an eval: the demo says "ready"
#
# Version 1 of the feature is the keyword rule from lesson 06, extended a little. Two demo messages are tagged, and both look right.

# %%
VALID = {"missing_item", "wrong_item", "late", "damaged", "other"}


def triage_v1(text: str) -> str:
    """Version 1 of the feature under test: a keyword rule standing in for the AI feature."""
    t = text.lower()
    if "missing" in t:
        return "missing_item"
    if "late" in t or "where is" in t:
        return "late"
    return "other"


demo = [
    "Order BB-1101: the milk is missing from my delivery.",
    "Order BB-1106: where is my delivery? The app still says pending.",
]
for text in demo:
    print(triage_v1(text), "<-", text[:45])

# %% [markdown]
# Both demo labels look right, so the team ships. The builder chose these two messages. Now test the same feature on a labelled set. The ten messages below are **invented** for this lesson, and each `want` label was written by hand before the feature ran.

# %%
EVAL_SET = [
    {"text": "Order BB-1101: the milk is missing from my delivery.", "want": "missing_item"},
    {"text": "Order BB-1102: only three of the four eggs made it into the bag.", "want": "missing_item"},
    {"text": "Order BB-1103: my bananas arrived bruised and brown.", "want": "damaged"},
    {"text": "Order BB-1104: the driver came two hours after the slot.", "want": "late"},
    {"text": "Order BB-1105: I was sent oat milk, I ordered almond.", "want": "wrong_item"},
    {"text": "Order BB-1106: where is my delivery? The app still says pending.", "want": "late"},
    {"text": "Order BB-1107: two bags of rice were not in the box.", "want": "missing_item"},
    {"text": "Order BB-1108: the yoghurt came in a crushed pot.", "want": "damaged"},
    {"text": "Order BB-1109: no bread at all, and I paid for it.", "want": "missing_item"},
    {"text": "Order BB-1110: the courier left my order at the wrong flat.", "want": "other"},
]

shape_ok = sum(triage_v1(c["text"]) in VALID for c in EVAL_SET)
print(f"shape check: {shape_ok} of {len(EVAL_SET)} outputs are valid labels")

# %% [markdown]
# The shape check passes every output. That is the failure you cannot see: nothing crashes, every label is valid, and most of them are wrong. Count the right ones against the expected labels.

# %%
correct = 0
for case in EVAL_SET:
    got = triage_v1(case["text"])
    if got == case["want"]:
        correct += 1
    else:
        print(f"WRONG  want={case['want']:<12} got={got:<12} {case['text'][:48]}")
print(f"correct: {correct} of {len(EVAL_SET)}")

# %% [markdown]
# Next, the team fixes the cases they saw. Version 2 adds words for missing, damaged and wrong items. The demo still looks right. Without a record of version 1's results, nobody can tell which cases version 2 broke.

# %%
def triage_v2(text: str) -> str:
    """Version 2: the team adds the wording it saw in the queue."""
    t = text.lower()
    if "missing" in t or "only" in t or "not in" in t or "no bread" in t:
        return "missing_item"
    if "bruised" in t or "crushed" in t:
        return "damaged"
    if "late" in t or "where is" in t or "after the slot" in t:
        return "late"
    if "wrong" in t or "sent" in t:
        return "wrong_item"
    return "other"


print("demo:", [triage_v2(t) for t in demo])

# %% [markdown]
# ### With an eval: the numbers name the regression
#
# The eval keeps each case's result, so two versions can be compared case by case. The same ten cases and the same scorer run on both versions.

# %%
def run_eval(triage, cases):
    """Score a feature on the eval set. One row per case: (passed, want, got, text)."""
    rows = []
    for c in cases:
        got = triage(c["text"])
        rows.append((got == c["want"], c["want"], got, c["text"]))
    return rows


v1_rows = run_eval(triage_v1, EVAL_SET)
v2_rows = run_eval(triage_v2, EVAL_SET)
for name, rows in [("v1", v1_rows), ("v2", v2_rows)]:
    print(f"{name}: {sum(r[0] for r in rows)} of {len(rows)} pass")

fixed = [new[3] for old, new in zip(v1_rows, v2_rows) if not old[0] and new[0]]
regressions = [old[3] for old, new in zip(v1_rows, v2_rows) if old[0] and not new[0]]
print(f"v2 fixed {len(fixed)} cases and broke {len(regressions)}")
for text in regressions:
    print("REGRESSION:", text)
print("gate:", "BLOCK the release until the case passes again" if regressions else "pass")

# %% [markdown]
# Read the numbers. The demo showed two right answers. The eval showed 3 of 10 for version 1 and 9 of 10 for version 2. It also named the one case that version 2 broke, so the release is blocked on a named case, not on a feeling.

# %% [markdown]
# ## How it simplifies the architecture
#
# Without an eval, a change goes out on a person's reading. With one, the same change runs through the same set, and the gate decides.
#
# ```mermaid
# flowchart LR
#     D1[Developer changes prompt or rule] --> M[A person reads two or three outputs]
#     M --> S1[Ships]
#     S1 --> Q1[Support queue finds wrong tags weeks later]
#     Q1 --> H1[Hand fix, no record of what broke]
# ```
#
# ```mermaid
# flowchart LR
#     D2[Developer changes prompt or rule] --> T[One command runs the eval set]
#     T --> S2[Score per case, failures named]
#     S2 --> G{Gate: any old case fail?}
#     G -- yes --> F[Fix the rule, or change the label on purpose and say why]
#     G -- no --> OK[Ship, and add new real failures to the set]
# ```
#
# | | Without evals | With evals |
# |---|---|---|
# | Test cases | in someone's head | a labelled file that grows |
# | Check per change | a person reads outputs | one run, one score |
# | Regression found by | a customer | the gate, before release |
# | Glue added | none, and no record | one scorer (about 10 lines here) and one stored result per case |

# %% [markdown]
# ## What an eval does not solve
#
# - **It only covers the cases in the set.** New wording from customers is not measured until someone adds it. Lesson 11 grows the set from real failures.
# - **A code scorer only checks labels.** Free text needs a model or a human to grade it (lesson 12).
# - **It does not stop a bad action.** A guardrail blocks an action at run time, in code (lesson 19). An eval measures before release.
# - **It does not watch real traffic.** Live customer messages can differ from the set. Watch production after launch (lesson 16).
#
# **Alternatives** (use them with evals, not instead): unit tests for the code around the model, a human review of a random sample, and production metrics.

# %% [markdown]
# ## At work
#
# - Anthropic's guide to agent evals says to start with 20 to 50 tasks taken from real failures, such as the support queue or a bug tracker. It also says a 0% pass rate over many trials usually means a broken task, so read the transcripts first (https://anthropic.com/engineering/demystifying-evals-for-ai-agents). → lesson 11 builds the set this way.
# - The same guide separates capability evals (start low) from regression evals (near 100%), and says a saturated capability eval moves into the regression set. → lesson 12 compares the graders that score them.
# - OWASP lists misinformation (LLM09) as a named risk for LLM apps, so a confident wrong answer is a business and security problem, not only a quality one (https://genai.owasp.org/llm-top-10/). → lesson 19 adds guardrails for actions.
#
# Go deeper: the scoring methods (exact match, code, model and human graders) are compared in lesson 12.

# %% [markdown]
# ## Common misconceptions
#
# - **"If the demo works, the feature works."** The demo used cases the builder chose, and nobody wrote the expected answers first. Two cases show that the feature can work, not how often it does.
# - **"A valid output is a correct output."** A schema check (lesson 06) proves the shape. `other` is a valid label for every message. It is correct only when the expected label says so.
# - **"Evals are a test before launch."** Each prompt, model or tool change can break an old case. The set runs on every change, and it grows with each real failure.
# - **"You need an AI judge to eval an AI feature."** When the answer has one right label, a code check is cheaper and repeatable. A model or a person grades free text (lesson 12).

# %% [markdown]
# ## Check yourself
#
# 1. A support lead says: "The new version got our five test messages right, so ship it." What is missing?
# 2. The new prompt fixes seven cases and breaks one case that passed last month. What should the gate do, and why?
# 3. A customer writes in slang that your set never covered, and the feature misses it. Is that an eval failure or a feature failure? What do you do next?
# 4. Your eval reports 95%, and the customer still complains. Name two things the eval may not measure.

# %% [markdown] tags=["solution"]
# **Answers**
#
# 1. The team chose five cases and wrote no expected answers first, so five cases cannot show how often the feature is right. Build a labelled set of real cases (20 to 50 to start, lesson 11).
# 2. Block the release. A regression is a case the customer already had working. Fix the rule or the prompt so it passes again, or change its label on purpose and record why. Seven fixes do not excuse one broken case.
# 3. Both: the eval did not cover that wording, and the feature failed on it. Add the real messages with their expected labels to the set, rerun the eval, then make the next change.
# 4. The set may not match the customer's real mix of messages, so the 95% describes the old set. The scorer may also mark a wrong answer right, for example a loose text match. Watch live traffic after launch (lesson 16).

# %% [markdown]
# ## Recap
#
# - A demo shows that a feature can work. An eval shows how often it works, on a labelled set written before the run.
# - The dangerous failures are quiet: a valid label that is wrong, and a fix that breaks an old case.
# - A **regression** is a case that passed before and fails now. A **regression eval** is the set that catches it, and a **gate** blocks the release.
# - A **grader** marks answers right or wrong: code, a model or a person (lesson 12). A **guardrail** stops an unsafe action at run time (lesson 19).
# - Words to keep: **eval**, **regression**, **gate**, **grader** (all in GLOSSARY.md).
#
# **Interview:** "How do you know your LLM feature still works after you ship it?" Strong answer: "I keep a labelled set of real cases with expected answers, score every change against it, and treat any old case that now fails as a blocked release."

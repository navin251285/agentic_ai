# %% [markdown]
# # 19 · Why loops run unattended, and what goes wrong
# Level L5 · Part 3 · core · ~20 min · builds on 18
#
# ## Goal
# Name what goes wrong when a loop runs with nobody watching (cost growth, a repeated write, instructions hidden in tool output, code nobody reads, a check the agent can game), and decide which steps a person must still verify.
#
# ## Why it matters
# Lesson 18 ran one loop with a checker and a budget while you watched it. Put the same loop on a schedule, give it a write tool and let it run overnight. Without extra controls:
#
# - **Cost grows faster than the turns.** Each turn re-reads the history, so the bill grows with the square of the turns. The table below shows it.
# - **A retry repeats a write.** A timeout followed by a retry can pay the same refund twice.
# - **Text is an instruction.** A ticket or a web page the loop reads can say "ignore the limit". The model cannot tell it from your prompt.
# - **"Done" is a claim.** Nobody reads the diff, so the code grows faster than the people who understand it.
#
# The code below shows the first two problems with numbers, then a few lines that stop them. You do not need any of this for a loop you start by hand, on a scratch repo, while you watch it.

# %% [markdown]
# ## The idea
# **An unattended loop is a loop nobody watches while it runs. Its risks come from four places: it keeps spending, it repeats its writes, it reads text it should not obey, and it reports work that no person has read. The fix is a few fixed rules outside the model: caps, a gate on every write, a named human for irreversible steps, and a checker the maker cannot edit.**
#
# Analogy: a night-shift contractor with a company card and no manager on call. The card has a spending limit. Any payment over a set amount waits for a signature. Every payment is checked against the list of payments already made. The contractor cannot rewrite those rules, even if a note on the job site asks them to.

# %% [markdown]
# ## Picture
# The same loop, with and without controls. The model's turns are the same in both. Only the boundary between the model and the world changes.
#
# ```mermaid
# flowchart LR
#   subgraph Without["Without controls"]
#     A1["Model proposes a call"] --> B1["Tool runs at once"]
#     B1 --> C1["Result goes back to the model"]
#     C1 --> A1
#   end
# ```
#
# ```mermaid
# flowchart LR
#   subgraph With["With controls"]
#     A2["Model proposes a call"] --> G["Gate: cap, duplicate check, limit"]
#     G -->|"read-only or allowed"| B2["Tool runs"]
#     G -->|"over the limit"| H["Hold for a person"]
#     G -->|"repeat or over the cap"| X["Skip or stop"]
#     B2 --> C2["Result goes back to the model"]
#     C2 --> A2
#   end
# ```

# %% [markdown]
# ## Already know this?
# This is the first lesson of Part 3 (production: triggers, approvals and safety for unattended loops), which runs to lesson 24. Answer each question in one line. Where you can answer it, skip to the lesson named.
#
# 1. Why does a loop that re-reads its whole history cost more each turn? Skip to lesson 15.
# 2. What must a retried write carry so that it cannot run twice? Skip to lesson 13.
# 3. Why must a checker be a file or a process the maker cannot edit? Skip to lesson 14.
# 4. What should a scheduled run do when its worker dies halfway through? Skip to lesson 20.
# 5. Why should two loop runs not edit the same working copy? Skip to lesson 21.

# %% [markdown]
# ## Explained
# ### Five things that go wrong without a person
# **1. Spending without an end.** Spend grows with turns times the size of the context. A loop with no cap on turns or money has no natural stop. The cap is checked before a call, so the last response can still overshoot it.
#
# **2. Repeated writes.** A timeout does not tell you whether the write happened. A retry of a refund or an email can run the write twice. Only an idempotency key, or a check that the write is already done, makes a retry safe.

# %% [markdown]
# ### Untrusted text, unread code and gamed checks
# **3. Untrusted text.** Each turn re-reads tool results: tickets, web pages, repo files. Any of them can carry instructions. Simon Willison's "lethal trifecta" (2025-06-16) names the danger: private data, untrusted text and a way to act outside (send, pay, publish). Meta's Rule of Two (2025-10-31) is the matching rule: an agent should have at most two of these (untrusted input, sensitive data, outside action) in one session without a person supervising.

# %% [markdown]
# **4. Code nobody understands.** The agent can ship changes faster than people read them. Three named risks follow. *Comprehension debt*: the team cannot explain or change the code later. *Intent debt*: the code does what the prompt said, not what the team meant, and the meaning is written nowhere a later run can read. *Cognitive surrender*: the reviewer stops checking and accepts the output. The bottleneck is review bandwidth, not generation. Osmani (2026-06-07) names comprehension debt and cognitive surrender; IBM's loop-engineering article (2026-07-17) adds intent debt. These are widely stated, qualitative findings, not measured figures.

# %% [markdown]
# **5. Checks the agent can game.** A *reward hack* satisfies the check instead of the goal, for example by deleting a failing assertion. Lesson 14 showed a separate checker. A checker is only useful if the maker cannot edit it.
#
# The Claude Agent SDK has permission modes (`default`, `acceptEdits`, `plan`, `dontAsk`, `auto`, `bypassPermissions`). Lesson 23 teaches them. One rule is enough for now: an unattended run never uses `bypassPermissions` on a laptop.

# %% [markdown]
# ## Worked example
# The example is the Brightside Outfitters support desk, the loop of lesson 18 with two more tools: `issue_refund` and `send_email`. The proposals below are written by hand for this demo. They stand for what a model might propose on one night. No model is called, so this notebook needs no key.

# %% [markdown]
# ### Step 1: what cost looks like with no cap (no model call)
# Assume a turn sends the system prompt and the ticket (3,000 tokens) plus everything from earlier turns, and each turn adds 1,200 tokens of model reply and tool result. The numbers are assumptions you can change.

# %%
START_TOKENS = 3_000    # system prompt and ticket
TOKENS_PER_TURN = 1_200 # the model's reply and one tool result

def input_tokens(turns):
    """Input tokens sent over all turns. Each turn re-sends the history."""
    return sum(START_TOKENS + TOKENS_PER_TURN * t for t in range(turns))

for turns in (5, 50, 500):
    print(f"{turns:>4} turns: {input_tokens(turns):>12,} input tokens")

# %% [markdown]
# Going from 50 turns to 500 is ten times the turns and about 93 times the input tokens. That is why a cap on turns is a cost control, not only a safety one.

# %% [markdown]
# ### Step 2: a retry with no gate (no model call)
# The proposals of one night. The third call is a retry of the second: the first try timed out, so the loop sent it again. Nothing checks it.

# %%
proposals = [
    {"tool": "read_order", "args": {"order_id": "BO-1042"}},
    {"tool": "issue_refund", "args": {"order_id": "BO-1042", "amount": 500}},
    {"tool": "issue_refund", "args": {"order_id": "BO-1042", "amount": 40}},
    {"tool": "issue_refund", "args": {"order_id": "BO-1042", "amount": 40}},  # retry of the line above
    {"tool": "send_email", "args": {"to": "name@example.com", "body": "Your refund is on its way."}},
]
paid = 0
for turn, call in enumerate(proposals, start=1):
    print(f"{turn}. runs  {call['tool']:<13} {call['args']}")
    if call["tool"] == "issue_refund":
        paid += call["args"]["amount"]
print(f"refunds paid: {paid} units (the 40 was paid twice, and 500 needed a person)")

# %% [markdown]
# Without a gate, the loop pays what it proposes: 580 units, with the 40 paid twice. The 500 refund never reached a person.

# %% [markdown]
# ### Step 3: the same proposals through a gate (no model call)
# The gate is plain Python at the boundary between the model and the tools. It is about 15 lines. The model never sees its code and cannot change it.

# %%
TURN_CAP = 30            # hard cap, checked before every call
REFUND_LIMIT = 100       # units. Above this a person must approve
WRITE_TOOLS = {"issue_refund", "send_email"}
done_writes = set()      # keys of writes already made

def gate(turn, call):
    """Return (decision, reason). Runs before every tool call."""
    if turn > TURN_CAP:
        return "stop", "turn cap reached"
    if call["tool"] not in WRITE_TOOLS:
        return "run", "read-only"
    if call["tool"] == "issue_refund" and call["args"]["amount"] > REFUND_LIMIT:
        return "hold", "over the limit: a person approves"
    key = (call["tool"], tuple(sorted(call["args"].items())))  # a simple idempotency key
    if key in done_writes:
        return "skip", "same write already made"
    done_writes.add(key)
    return "run", "write allowed"

paid = 0
for turn, call in enumerate(proposals, start=1):
    decision, reason = gate(turn, call)
    print(f"{turn}. {decision:<5} {call['tool']:<13} {reason}")
    if decision == "run" and call["tool"] == "issue_refund":
        paid += call["args"]["amount"]
print(f"refunds paid: {paid} units; the 500 waits for a person")

# %% [markdown]
# Each proposal gets one decision. The duplicate is skipped, the large refund is held, and the paid total is 40. A real system would use the payment provider's own idempotency key, and the hold would go to a review queue.

# %% [markdown]
# ## How it simplifies the architecture
# The gate does not make the model smarter. It moves the trust from the model's judgement to a few rules the team can read and test.
#
# | | Without controls | With controls |
# |---|---|---|
# | Moving parts | model, tools, and the hope that the prompt is followed | model, tools, one gate, one cap, one hold queue |
# | Places a rule lives | every tool, or nowhere | one function at the tool boundary |
# | Duplicate write | paid twice | skipped and logged |
# | Large write | runs at once | held for a person |
# | Runaway loop | stops when the model says so | stops at the cap |
#

# %% [markdown]
# ## What this does not solve
# - **Intent.** The gate sees arguments, not the meaning of the ticket. Intent debt needs a written spec and a reviewer.
# - **Unlisted tools.** A new write tool that is not in `WRITE_TOOLS` passes the gate. Default-deny is safer: allow only the tools on a list.
# - **Real systems.** The duplicate check works only if the payment system honours the key.
# - **Approval fatigue.** A person who approves 200 holds a day stops reading them. Fewer, clearer holds work better.
# - **Injection.** A gate on arguments does not stop a prompt that asks for an allowed action. Lesson 23 covers that.
#
# You do not need the gate for one loop you start and watch. Alternatives: a fixed workflow with no model in the loop, a sandbox with no network, or a human who approves each batch.

# %% [markdown]
# ## At work
# - **Review bandwidth decides how far you can let loops run.** Human review bandwidth, not generation, is the ceiling: Stripe's agents make 1,000+ merged PRs a week, each human-reviewed. Comprehension debt and cognitive surrender are the named risks (qualitative, not measured). → lesson 21 (isolated runs and review load).
# - **Approvals are a loop exit, not a checkbox.** Good products show the real arguments of a write before a person says yes, and pause the run until they answer. → lesson 22.
# - **Permission mode is a deployment decision.** Unattended runs use a non-interactive mode with an allowlist inside a sandbox. Bypass modes belong in isolated containers only. → lesson 23.
# - **Scheduled runs die halfway.** A worker that crashes mid-run needs a lease and a restart rule, or the same refund runs twice. → lesson 20.

# %% [markdown]
# ## Common misconceptions
# - **"A budget cap stops the cost."** It stops the next call. The last response can still overshoot, and running subagents keep spending.
# - **"A passing test means the loop is safe."** It means the check passed. A check the agent can edit proves nothing.
# - **"The model will ignore instructions in the ticket."** Usually it does. Under the lethal trifecta, "usually" is not a control.
# - **"A person reviews every change, so the loop is safe."** Reviewers under load stop reading. Count the review load before you rely on it.

# %% [markdown]
# ## Production checklist
# Before a loop runs unattended, check each line. A "no" means the run needs a person.
#
# - [ ] A cap on turns and on money, checked before every call.
# - [ ] Every write has an idempotency key, and the gate checks it.
# - [ ] Writes above a limit, and every irreversible action, wait for a person.
# - [ ] The run's tools have no more than two of: untrusted input, private data, an outside action.
# - [ ] The checker is outside the maker's reach (files and processes the agent cannot edit).
# - [ ] A stop, a hold and a skip each leave a record a person can read.

# %% [markdown]
# ## Check yourself
# 1. A loop has no cap and each turn adds 1,200 tokens. Why does the input cost grow faster than the turns?
# 2. A refund times out. What should the retry carry, and what must the gate check?
# 3. A loop can read a web page and send email. Which two of the three lethal-trifecta parts are present, and what does the Rule of Two ask you to do?
# 4. Why should the checker live where the maker cannot edit it?

# %% [markdown] tags=["solution"]
# **Answers.**
# 1. Each turn re-sends the whole history, so the input for turn `t` is 3,000 + 1,200·t tokens. Adding these up over all turns grows with the square of the turns (Step 1: 50 turns = 1.62M, 500 turns = 151.2M).
# 2. An idempotency key for the write. The gate checks whether that key was already done and skips it (Step 3).
# 3. Untrusted text (the web page) and an outside action (email) are present. That is two, the most the Rule of Two allows without a person. Do not add the third (private data) to this run. If the run also needs private data, remove one capability or put a person in the loop.
# 4. A maker that can edit the check can make the check pass. This is reward hacking; lesson 14 shows the separation.

# %% [markdown]
# ## Recap
# - An unattended loop has four risks: spend without an end, repeated writes, instructions hidden in text, and work nobody read.
# - The lethal trifecta is private data, untrusted text and an outside action. Keep at most two in an unattended run (Rule of Two).
# - Controls live outside the model: a turn cap, a gate on each write with a duplicate check and a limit, and a checker the maker cannot edit.
# - Comprehension debt, intent debt and cognitive surrender are the human limits. Name who verifies each step.
#
# **Interview:** How do you run an agent loop unattended safely? *A turn and money cap; a deterministic gate on every write (duplicate key, limit, hold for approval); no untrusted text plus write tools in one run without a person; and a checker the agent cannot edit.*


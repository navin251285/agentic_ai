# %% [markdown]
# # 01 · Why loop engineering, and what a loop is (and is not)
# Level L1 · Part 1 · core · ~25 min · builds on none
#
# ## Goal
# Draw the inner and outer loop of the desk agent and say which part is a workflow, an agent and a loop.
#
# ## Why it matters
# Without loop engineering, **a person is the loop**. Take the Brightside Outfitters support desk (the fictional shop used in every lesson of this course). A customer wants a refund for a damaged jacket. Someone prompts the model to read the order, check the policy, issue the refund, check the payment and write the reply. Each step is a turn typed by hand. If the model stops early, the person types again. If it goes wrong, nothing stops it except the person.
#
# Without loop engineering: the person is the loop.
#
# ```mermaid
# flowchart LR
#   P[Person] -->|types a prompt| M[Model]
#   M -->|one answer| P
#   P -->|reads it, types the next prompt| M
# ```
#
# The cost is the person's time. Example assumption, not measured: a person types about 6 prompts per ticket, so 200 tickets a week is about 1,200 typed prompts.

# %% [markdown]
# ### What a loop changes
# With a loop, the system picks the next step, checks the result against a rule you wrote, and stops when the rule says so. You still design and review the work, but you stop typing every turn.
#
# Two words you will see often. A **turn cap** limits how many model calls one run may make; a **dollar cap** limits what one run may spend. A **handoff** means the loop stops and gives the case to a person.
#
# You do not need a loop for a one-off question or for a fixed sequence of steps you already know. That fixed sequence is a workflow (see below).

# %% [markdown]
# ## The idea
# **Loop engineering is designing the system that prompts, checks, remembers and re-runs an agent, so a person does not drive it turn by turn.** The basic cycle is act, observe, decide, repeat, until a check you can run says stop. The desk agent reads the order, sees the refund is not issued yet, issues it, reads the payment status, and stops when the check passes.
#
# Analogy: a thermostat. You do not switch the heater on every hour. You set a target, a sensor checks it, and the system decides when to switch on and off. Loop engineering sets the target, the checks and the stop rules. The model does the work inside them.

# %% [markdown]
# ## Picture
# The inner loop is the agent loop: model, tool, result, model. The result of a tool comes back as an **observation**, which the model reads next. The outer loop wraps it with a trigger, a goal the machine can check, **state kept outside the model** (a file or database the model cannot forget), and stop rules.
#
# ```mermaid
# flowchart TB
#   T["Trigger: schedule, event or person"] --> G["Goal: a check the machine can run"]
#   G --> A["Inner loop: model call"]
#   A -->|asks for a tool| X["Run the tool"]
#   X -->|result comes back as an observation| A
#   A -->|no more tool calls| V["Verifier: test or order check"]
#   V -->|not done, under the caps| G
#   V -->|done| D["Stop: done, stuck, over budget or hand off"]
# ```

# %% [markdown]
# ## Already know this?
# This is the first lesson of Part 1 (lessons 01–08), so these questions cover the whole Part:
# 1. Can you call a chat model with an API key and read the reply text? (skip to lesson 02)
# 2. Can you write a loop that sends a tool result back to the model until the model stops asking for tools? (skip to lesson 03)
# 3. Can you check a function's arguments with pydantic before you run it? (skip to lesson 04)
# 4. Can you say why a loop needs a turn cap and a dollar cap? (skip to lesson 05)
# 5. Can you write a pytest test that a loop can use as its stop check? (skip to lesson 07)
#
# Yes to all five: skip to lesson 08 and try the checkpoint first.

# %% [markdown]
# ## Explained
#
# ### Four layers, one stack
# Each layer is a bigger thing you design. Each one answers a bigger question.
#
# | Layer | What you design | The question it answers | Lessons |
# |---|---|---|---|
# | Prompt engineering | the words of one request | what do I ask? | 02 (the model call) |
# | Context engineering | what the model can see in its window | what is in view right now? | 15 (context growth) |
# | Harness engineering | the environment one run executes in: tools, permissions, sandbox | what can one run do? | 16 (tools, MCP, skills, hooks), 23 (injection and permissions) |
# | Loop engineering | the system that triggers, checks, retries, stops and resumes many runs | what runs next, and when does it stop? | 09–30 |
#
# The labels are not standard yet. Sources draw the boundaries differently. This course teaches the mechanisms (caps, verifier, state, trigger, traces) and uses "loop engineering" for the outer layer.
#
# %% [markdown]
# ### Workflow, agent or loop?
# - **Workflow:** your code decides the steps. The model fills in one of them, for example it classifies a ticket and your code sends a template. Fixed, cheap, easy to test.
# - **Agent:** the model decides which tool to call next, inside one run, until it stops. This is the inner loop.
# - **Loop:** the system runs agents again and again over time, with a trigger, a goal a machine can check, state outside the model, and stop rules.
#
# Start with the simplest thing that works. Use an agent when the next step depends on what the model finds. Use a loop when the work spans many runs or must run without a person watching.
#
# %% [markdown]
# ### What the evidence says (as of October 2026)
# The term is under five months old (first essay 2026-06-07). Practitioners coined it. Anthropic's guide "Loop engineering: getting started with loops" (2026-06-30) names four loop types: turn-based, goal-based, time-based and proactive. One workshop paper (arXiv 2608.21884) looked at 36,710 public GitHub repositories and found 217 autonomous agent loops, which is 0.59 percent. It found no measured benefit yet. No job posting we checked uses the title "loop engineer", while several use "harness engineer". Loops are rare and unproven, so measure the benefit in your own team.
#
# %% [markdown]
# ### What a loop is not
# - It is not a `while True`. A loop with no cap and no checkable stop keeps calling the model and keeps billing.
# - It is not "the model said it is done". "Done" is a claim. A check you can run decides it.
#
# %% [markdown]
# ## Worked example: three ways to do one refund
# Task: a customer gets a refund for a damaged jacket, and the desk must also send a reply.
#
# 1. **Person-driven.** Assume about 6 typed prompts per ticket. The person's time is the bottleneck.
# 2. **Workflow.** Your code runs `get_order`, the policy check and `issue_refund`, then the model writes the reply. It is fast and testable, but it breaks on the first case nobody wrote a step for, such as two orders on one account.

# %% [markdown]
# 3. **Loop.** An agent with the same tools chooses the order of the steps. The goal is "refund issued and reply sent". The verifier reads the order record. The stop rules are done, a turn cap of 8, a budget cap, or a handoff to a person above a set refund amount.
#
# The loop does not remove review. It moves the person from typing steps to reading handoffs.

# %%
# The evidence ratio from the paper: 217 loops in 36,710 repositories.
loops_found, repos_checked = 217, 36710
print(f"Share of repositories with an autonomous agent loop: {loops_found / repos_checked:.2%}")

# %% [markdown]
# ## How it simplifies the architecture
# Loop engineering does not add a new model. It moves the decisions out of a person's head and into the system.
#
# With loop engineering: the person only gets the handoff.
#
# ```mermaid
# flowchart LR
#   T["Trigger: schedule or event"] --> G["Goal: a check the machine can run"]
#   G --> A["Agent: model and tools"]
#   A --> V["Verifier: order or test check"]
#   V -->|not done, under the caps| A
#   V -->|done| E1["Exit: done"]
#   V -->|stuck or over budget| E2["Exit: stop"]
#   V -->|needs a decision| H["Handoff to a person"]
# ```

# %% [markdown]
# Count the moving parts before and after.
#
# | Part | Without loop engineering | With loop engineering |
# |---|---|---|
# | Next step | a person decides every turn | the goal and the agent decide, by rule |
# | "Done" | the person reads the reply and judges it | a verifier runs a check; a person sees only handoffs |
# | Retries | the person types again | a retry policy inside the loop (lesson 13) |
# | Stop | the person stops it, or nothing does | caps and four exits (lessons 05–06) |
# | Memory between runs | chat history in someone's head | a state file or database (lesson 12) |
# | Glue | copy and paste between chat windows | one loop function with named exits |
#
# %% [markdown]
# **What it does not solve:** a weak verifier passes bad work; a loop can still spend money; a person still has to review; the benefit is not measured yet.
#
# **When you do not need it:** a single question, a fixed pipeline you already run, or a task you do once by hand.
#
# **Alternatives:** one model call (lesson 02), a workflow with fixed code steps, or an agent loop with no outer loop (lessons 03–08).
#
# %% [markdown]
# ### Where the course goes
# Two terms used below: a **Ralph loop** (lesson 11) runs one item per iteration, in a fresh context each time, and commits only when the check is green. A **stuck detector** stops a run that repeats the same failure.
#
# | Part | Level | What you build | Checkpoint |
# |---|---|---|---|
# | 1 Foundations: the model call and the loop by hand | L1 | the desk loop with caps, a verifier and a stuck detector | 08 |
# | 2 Control: outer loops, state, retries and review | L3 | a Ralph loop with a separate checker and a CI eval gate | 18 |
# | 3 Production: triggers, approvals and safety | L5 | a triggered loop with approvals and isolated runs | 24 |
# | 4 Enterprise: durable runs, cost, operation, governance | L6 | the enterprise loop, end to end | 30 |

# %% [markdown]
# ## At work
# - Anthropic's guide (2026-06-30) splits loops into turn-based, goal-based (`/goal`), time-based (`/loop`, `/schedule`) and proactive. Teams use this split to decide which loop may run unattended. → lessons 10, 20
# - Practitioner stop rules are a short list: a mechanical success check, an iteration cap, a dollar cap, a detector for the same failure twice, and a **dual exit** (the loop stops only when a machine check passes, never on the model's own word alone). → lessons 05, 06, 07
# - The known failure modes are an unverified "done", **reward hacking** (the agent games the check, for example by deleting a failing test), and cost growth from sub-agents. → lessons 07, 14
# - Go deeper: the "Where next" module of this course maps the job titles that use these ideas.

# %% [markdown]
# ## Common misconceptions
# 1. **"Loop engineering is a new kind of model."** It is system design around a model. The same model can run as a workflow, an agent or a loop.
# 2. **"A loop is a `while` statement."** A `while` with no cap and no checkable stop bills forever. The stop rule is the design.
# 3. **"If the model says it is done, it is done."** A model's "done" is a claim. A deterministic check, such as a test or an order lookup, decides it.

# %% [markdown]
# ## Check yourself
# 1. A teammate says their agent is "loop engineering" because it calls the model ten times in one run. What is missing?
# 2. The desk must check each refund against the order database, and the steps never change. Workflow, agent or loop?
# 3. An agent is told to make the tests pass, and it deletes a failing test. Which part of the loop failed, and what would you add?
# 4. A nightly job must triage tickets while nobody is online. Name the three outer-loop parts you need on top of the agent loop.
# 5. The paper found no measured benefit. What should your team measure before it rolls out a loop?
# 6. On paper, draw the inner and outer loop for the desk refund agent and label the trigger, goal, verifier, state and stop rules.

# %% [markdown] tags=["solution"]
# **Answers**
# 1. Ten calls in one run is an agent loop (the inner loop). Loop engineering also needs a trigger for the runs, a goal a machine can check, a verifier, state outside the model, and stop rules.
# 2. A workflow. The steps are fixed, so code should decide them. Use an agent only when the next step depends on what the model finds.
# 3. The verifier and the goal were weak: the check did not protect the tests. Add a fixed set of tests the agent cannot edit, and run the check in a fresh copy of the repo (lessons 07 and 14).
# 4. A trigger (schedule), stop rules (caps and a handoff to a person), and state that survives between runs.
# 5. Your own numbers against a baseline with no loop: task success rate, cost per finished task, handoff rate, and how many handoffs a person had to fix.
# 6. Same as the Picture in cell 3.

# %% [markdown]
# ## Recap
# - Loop engineering designs the system around the agent: trigger, goal, verifier, state and stop rules.
# - A workflow has fixed code steps. An agent chooses its next tool inside one run. A loop repeats agents over time with a stop rule.
# - Prompt, context, harness and loop engineering are nested layers. The labels are not standard; the mechanisms are.
# - The evidence is early: 217 loops in 36,710 repositories, and no measured benefit yet.
# - Words to keep: **inner loop** (the agent loop), **outer loop** (the system around it), **verifier** (the check that decides "done").
#
# **Interview:** "How is an agent loop different from loop engineering?" A strong answer: the agent loop is the model, tool and observation cycle inside one run. Loop engineering is the outer system that decides what runs, checks the result, retries, stops and resumes many runs, with caps and a verifier.

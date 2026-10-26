# %% [markdown]
# # 30 · Ambiguity and the business case: saying no and saying what it is worth
#
# Level L5 · Part 3 · professional · ~25 min · builds on lesson 08

# %% [markdown]
# ## Goal
#
# By the end of this lesson you can turn a vague customer request into one question with a test, write a short business case that shows cost against value over a stated period, say no to an out-of-scope request in writing with an alternative, and reset a customer's expectations after a missed date.

# %% [markdown]
# ## Why it matters
#
# Basket Bazaar's ops lead says: "Make the delivery-issue triage smarter." Two weeks later a store manager asks for a shopper app, and the delivery-message export is three days late. Each of these can end the engagement, or quietly cost you weeks of unpaid work.
#
# - **Without it:** you say yes to everything. The scope grows, the date slips with no warning, and nobody can tell whether the work was worth it.
# - **With it:** one question to build and measure, a business case with a payback date, a no with a reason and an option, and a missed date with a new date you can keep.
# - **When you don't need it:** a small fixed-price change the customer has already costed and signed.
#
# The numbers in this lesson are **invented** for teaching. Replace each one with a measured or agreed value before you show a customer.

# %% [markdown]
# ## The idea
#
# **Ambiguity** is a request with no test of success yet. Your first job is to turn it into one question that can be answered with data, such as "Can the triage label the day's delivery issues correctly at least 90% of the time, so agents can skip the hand read for routine ones?" **Presales** is the work before a contract: discovery, a demo and a small proof of concept (POC). Its goal is a **technical win**, when the customer's technical people agree the approach works. **Value-based selling** means you justify the work by the outcome the customer gets, not by the hours or features you build. A **business case** is a short written comparison of cost and value over a stated period, with every number labelled as measured, agreed or a guess. An **expectation reset** is a written update that moves a date or scope, with the reason and a new date you can meet.

# %% [markdown]
# ## Picture

# %% [markdown]
# ```mermaid
# flowchart LR
#     A["Vague ask: make the triage smarter"] --> B["One question with a test"]
#     B --> C["Business case: cost vs value over a stated period"]
#     C --> D{"Pays back inside the period?"}
#     D -->|yes| E["Agree the next step in writing"]
#     D -->|not yet| F["Small pilot that measures the missing number"]
#     D -->|no| G["Say no in writing, with an option"]
# ```

# %% [markdown]
# ## Explained
#
# **1. Turn the ask into a question.** "Smarter" is not testable. Ask what the store would do differently and how you would know. For Basket Bazaar, the answer is criterion C1 from lesson 03: the share of labelled delivery issues (the lesson 11 cases) that the triage labels correctly. Its target is 90% (invented, to agree), the same gate lesson 31 uses. Now there is something to build and something to measure.
#
# %% [markdown]
# **2. Write the business case.** Four inputs cover most cases: how often the problem happens, what it costs each time, the share your work can remove, and what the work and running cost. Add a period (one year, three years) and show the result for it. A case with one number and no period hides the answer.

# %% [markdown]
# **3. Say no in writing.** An out-of-scope request is not a refusal of the customer. It is a statement of the current scope, the effect of the change and the choices. Name the non-goal from lesson 03 (what the pilot will not do), give the effect in days and money, and offer the options: backlog, a signed change request, or leave it out. Nothing starts until someone with authority signs.
#
# **4. Reset expectations early.** A date at risk is news the customer needs now, not on the due date. Say what happened, what it changes, the new date you can meet and what you need from the customer. Do not change the success targets to hide the slip.

# %% [markdown]
# ## Worked example: the one-store pilot or the six-store rollout
#
# This is **presales** work: the pilot comes before any rollout contract, and its result is the technical win. Basket Bazaar's ops lead wants the triage in six of its 12 stores. The current pilot is one store. The ops lead's guess is about 12 delivery issues a week in that store (a guess, not measured). Here is the business case for the two scopes, over one and three years. Money is in dollars and every input is invented for teaching.

# %%
# Invented teaching numbers. Replace each with a measured or agreed value.
COST_PER_ISSUE = 9.00           # $ per delivery issue read by hand: agent time to read, classify and route (invented)
SHARE_AUTOMATED = 0.50          # share of hand-read issues the triage clears without a manual read (a target to test in the pilot)
WEEKS_PER_YEAR = 50
PILOT_BUILD_COST = 8_000        # $ one-off for the one-store pilot: about two weeks of one FDE (invented; a week is about $4,000)
ROLLOUT_BUILD_COST = 16_000     # $ one-off for six stores: about four weeks of one FDE, pilot included (invented)
RUN_COST_PER_YEAR = 3_600       # $ per year: this workflow's hosting and support time only (invented, same for both scopes).
                                # The platform fixed cost of lesson 29 is shared by every workflow, so it is excluded here.
SCOPES = [                      # (label, delivery issues per week, one-off build cost)
    ("one store", 12, PILOT_BUILD_COST),
    ("six stores", 72, ROLLOUT_BUILD_COST),  # 72 assumes each of the six stores has the pilot store's 12 a week (6 x 12)
]

def business_case(issues_per_week, build_cost, years):
    benefit = issues_per_week * WEEKS_PER_YEAR * COST_PER_ISSUE * SHARE_AUTOMATED * years
    cost = build_cost + RUN_COST_PER_YEAR * years
    return benefit, cost, benefit - cost

print(f"{'scope':<12}{'years':>6}{'benefit':>10}{'cost':>10}{'net':>10}")
for label, issues, build in SCOPES:
    for years in (1, 3):
        benefit, cost, net = business_case(issues, build, years)
        print(f"{label:<12}{years:>6}{benefit:>10,.0f}{cost:>10,.0f}{net:>+10,.0f}")

# %% [markdown]
# A negative net means the case has not paid back yet. Read the table by horizon, not by the one number you like. One store is negative at one and at three years. Its yearly benefit (2,700) is below its running cost (3,600), so it never pays back on its own, and that is fine: the pilot buys the measurement. Six stores is negative after one year and positive after three. The next cell finds the **payback period**: the months until the yearly gain covers the build cost.

# %%
def payback_months(issues_per_week, build_cost):
    benefit_per_year = issues_per_week * WEEKS_PER_YEAR * COST_PER_ISSUE * SHARE_AUTOMATED
    yearly_gain = benefit_per_year - RUN_COST_PER_YEAR  # what is left each year after running costs
    if yearly_gain <= 0:
        return None  # the benefit never covers the running cost
    return build_cost / (yearly_gain / 12)

for label, issues, build in SCOPES:
    months = payback_months(issues, build)
    result = "never: the benefit does not cover running costs" if months is None else f"{months:.1f} months"
    print(f"{label:<12} payback: {result}")

# %% [markdown]
# So the honest answer for Basket Bazaar is: **not yet**. The six-store payback of 15.2 months is the $16,000 build divided by the yearly gain after running costs ($16,200 − $3,600 = $12,600 a year). The three-year net agrees: 3 × $12,600 − $16,000 = +$21,800. But the 12-issues-a-week input is a guess and the 50% share is a target, so the case cannot yet support a rollout price.

# %% [markdown]
# The one-store case is cheaper because it builds only the pilot, $8,000. The six-store case builds the full $16,000, pilot included.

# %% [markdown]
# The offer to the customer is a two-week pilot (10 working days) in one store. It costs about two weeks of FDE time, $8,000. The check: $8,000 is about a sixth of the $48,600 three-year benefit the rollout depends on, so the pilot is small against the decision it informs. If the measured share supports it, the rollout adds the other $8,000 of the $16,000 build, priced on that measured share, with a go/no-go on a set date.

# %% [markdown]
# ## Try it
#
# Change one input and rerun. Use `SHARE_AUTOMATED` = 0.30 (the pilot finds a weaker share) and check the six-store payback and three-year net. Does the rollout still pay back within three years? Put `SHARE_AUTOMATED` back to 0.50 when you finish.

# %%
# your code here
# Set SHARE_AUTOMATED to 0.30, then print payback_months(72, ROLLOUT_BUILD_COST)
# and the three-year net from business_case(72, ROLLOUT_BUILD_COST, 3).

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
SHARE_AUTOMATED = 0.30
print(f"six stores payback: {payback_months(72, ROLLOUT_BUILD_COST):.1f} months")
_, _, net3 = business_case(72, ROLLOUT_BUILD_COST, 3)
print(f"six stores three-year net: {net3:+,.0f}")
SHARE_AUTOMATED = 0.50  # put the lesson's value back

# %% [markdown]
# **Why this change matters.** At 30% the payback moves from 15.2 to about 31 months, and the three-year net is still positive but much smaller. A measured share changes the answer, so measure it before you quote a price.

# %% [markdown]
# **Terms from lesson 03, used in the replies below.** A **non-goal** is something the pilot will not do, written down with a reason and a place the work goes. A **kill rule** (kill criterion) is a rule agreed before the work starts that stops the pilot early. Here it is: the store's delivery-message export is not sent by day 3. A **time box** is a fixed end date: the date stays and the scope is cut to fit. The pilot is a 10-working-day sprint, so **day 10** is its decision day. In this lesson every day count is a working day.

# %% [markdown]
# **Saying no to the shopper app.** The store manager asks for a shopper app that shows each customer the triage status of their own delivery issue. It is a non-goal of the pilot, so the reply names it as one and offers options. Here is a written reply you can adapt:
#
# > "Thanks for the shopper app idea. It is not in the pilot, so it is a non-goal for now. The pilot answers one question: can the triage label the day's delivery issues correctly at least 90% of the time, so agents can skip the hand read for routine ones? The shopper app would add a second review of customer data access and, by our estimate, about three weeks of work. That is 15 working days, so the decision date would move from day 10 to day 25. Options: (a) log it in the backlog for the next phase, (b) a change request with its cost and date, signed by the ops lead, or (c) leave it out. Which do you choose by Friday?"

# %% [markdown]
# **Why this wording.** It names the current scope first, so the no is about the plan, not the person. It gives the effect in days, which the customer can check. It ends with three options and a date for the answer.

# %% [markdown]
# **Resetting after a missed date.** The kill rule stops the pilot on day 3 if the delivery-message export is missing. On day 3 the store says the export is three days late and will arrive on day 6. The kill rule is triggered that day, so the reset asks for a signed exception to carry on:

# %% [markdown]
# > "The delivery-message export was due on day 3 and has not arrived. The agreed kill rule says to stop and rescope when a file is missing, so the rule has been triggered today. The store says the file will be here on day 6. To carry on we need a signed exception: the file on day 6, the labelling run on days 6 and 7, and the decision on day 12 instead of day 10. We will cut the demo to half a day. The targets do not change. Day 12 is outside the 10-day time box, so this is a change request. Please sign by end of day 4. If it is not signed by then, or the file is not here on day 6, we stop and rescope, as agreed."

# %% [markdown]
# **Why this wording.** It states the rule that was triggered first, so the customer sees that the default is the agreed stop and the choice to continue is theirs. It gives a new date and a smaller demo, and it says what happens if either condition fails.

# %% [markdown]
# ## At work
#
# - Solutions and applied AI architect postings name value-based selling, the technical win, the POC and RFP questionnaires as core work (RESEARCH.md, section 5g). → lesson 31 delivers one scoped deployment end to end.
# - Field teams judge success by the customer outcome, such as the go-live date and the delivery-issue rate, not by feature count (RESEARCH.md, section 3). A business case must use that same outcome as its value. → lesson 21 looks at what changes between a POC and production.
# - The customer's **golden set** (the labelled test cases with expected answers, written before the feature runs; lesson 10) becomes the acceptance criterion in the contract (RESEARCH.md, section 7.1). That is the test that turns a vague "it works" into something you can sign. → lesson 11 builds the eval set from real failures.
# - Interview loops include "estimate value or build the business case for an AI pilot" (RESEARCH.md, section 10, question 15).

# %% [markdown]
# ## Common misconceptions
#
# - **"Saying no makes you the blocker."** A no with a reason, a cost and an option keeps the customer in control of the choice. A silent yes that slips the date is the real blocker.
# - **"The business case needs a big number."** A small, honest number with its inputs labelled is more credible than a large one with hidden guesses. Customers check the inputs.
# - **"Wait until the due date to tell the customer."** The kill rule means you act on day 3, the day the export was due, not on day 10 when the sprint ends. A risk you hold back for a week becomes a surprise the customer remembers.
# - **"Value means features shipped."** Value is the customer outcome: fewer hand-read issues, faster answers to customers, a go-live date kept. Features are only the means.

# %% [markdown]
# ## Production checklist
#
# - Every business-case input has a source: measured, agreed, or labelled as a guess with the week it will be measured.
# - The case states its period (one year, three years) and shows the result for it.
# - The non-goals are written down and signed, so the out-of-scope list can be quoted.
# - Every change request has its effect on days, cost and the decision date.
# - Every date reset names the new date, the reason and what the customer must confirm, in writing, the same working day.

# %% [markdown]
# ## Check yourself
#
# 1. A store manager wants a feature by next week that is not in the plan. What do you write first?
# 2. The six-store case is negative after one year and positive after three. What do you tell the customer?
# 3. The delivery-message export is three days late, and you learn on day 3 that it will arrive on day 6. When do you send the reset, and what does it ask for?
# 4. Your business case uses "about 12 delivery issues a week, the ops lead's guess". Can you show it to the customer as the basis for the rollout price?

# %% [markdown] tags=["solution"]
# **Answers** (hidden until you expand this cell):
#
# 1. A written reply that names the current scope and the non-goal, gives the effect on days and cost, and offers the backlog or a change request. Commit to nothing until the ops lead signs.
# 2. Show both horizons. Say the one-store pilot is the cheap way to measure the share the triage clears, and that the rollout price waits for the measured number.
# 3. The same working day, day 3. The kill rule was triggered that day, so the reset asks for a signed exception to carry on, and says the pilot stops if the exception is not signed by day 4 or the file is not here on day 6. Waiting for day 6 would leave the customer no time to choose.
# 4. Not as the basis for the price. Label it as a guess, and measure it in week 1 of the pilot before the rollout decision uses it.

# %% [markdown]
# ## Recap
#
# - Turn a vague ask into one question with a test, such as the labelling criterion C1 from lesson 03.
# - A business case compares cost and value over a stated period, with every input labelled.
# - Say no in writing: the current scope, the effect in days and money, and the options.
# - Reset a missed date the same working day: what happened, the new date, the change request, what you need.
# - Terms: **ambiguity**, **presales**, **technical win**, **value-based selling**, **business case**, **payback period**, **expectation reset** (in GLOSSARY.md).
#
# **Interview:** "The customer wants a feature that will take three weeks, and the sprint is full. What do you do?" Strong answer: "I restate the current scope and its non-goals, show the effect on the date and the cost, and offer three options in writing: backlog, a signed change request, or leave it out. I do not start the work until the customer signs."

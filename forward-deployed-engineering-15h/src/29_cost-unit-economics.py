# %% [markdown]
# # 29 · Cost engineering: unit economics for a customer deployment
#
# Level L5 · Part 3 · professional · ~25 min · builds on lessons 18, 28

# %% [markdown]
# ## Goal
#
# By the end you can work out the monthly cost of one customer, the cost per query and per resolved case, and the margin on the contract. You can also rank the levers by how many dollars each one moves, and say which two matter most.

# %% [markdown]
# ## Why it matters
#
# Lesson 18 projected the model bill from measured token counts. It is small: about $47 a month for Basket Bazaar's 600,000 messages (with an assumed 30% cache hit rate). A team that looks only at that bill concludes the feature is nearly free. It is not. Every answer a person has to check costs staff time, and that is the larger cost.
#
# | | Token bill only | Whole bill (this lesson) |
# |---|---|---|
# | What the team sees | about $47 a month for the model | the model, the people checking answers and the platform |
# | Biggest cost | none visible | the people checking answers |
# | Decision | "cut the model price" | "reduce the share of answers that need a person" |
#
# - **When you don't need it:** a free internal pilot with no contract. Count the model calls and nothing else until someone pays for the feature.

# %% [markdown]
# ## The idea
#
# **Unit economics** means the cost and the revenue of one unit of work: one query, one resolved case, one customer for one month. Each monthly cost is either **variable** (it grows with queries: model tokens, staff time for checks) or **fixed** (it does not: hosting, monitoring, eval runs). Add the blocks, divide by the units, and you have the number to quote.

# %% [markdown]
# The **margin** is what is left of the contract price after the whole bill: model tokens, the people who check answers, and fixed platform costs (hosting, on-call share, eval runs, review staff). The **gross margin** is that amount as a share of the price. The code calls it *margin* for short.
#
# Analogy: a bakery does not stop at the price of flour. It counts the cost of one loaf, including the baker's time to pack and check it. The biggest cost is often the one nobody writes on the flour invoice.
#
# Every input carries a label: **measured** (from lesson 18 or 28), **agreed** (in the contract) or **a guess** (to be replaced by a measured number). A business case with unlabelled numbers is not one.

# %% [markdown]
# ## Picture
#
# Three blocks make the bill. Units are divided into it to give the numbers a customer asks for.

# %% [markdown]
# ```mermaid
# flowchart LR
#     Q[Queries a month] --> M[Cache misses call the model]
#     Q --> F[Flagged answers go to a person]
#     M --> T[Token bill]
#     F --> H[Hours of checking x staff rate]
#     T --> B[Monthly bill for one customer]
#     H --> B
#     X[Fixed platform cost] --> B
#     B --> U[Cost per query, per resolved case, margin]
# ```

# %% [markdown]
# ## Step by step

# %% [markdown]
# ### Step 1: the inputs, each labelled
#
# The model price is the table from lesson 18, dated the same way. It comes from the Gemini API pricing page (standard paid tier, text), last checked 2026-10-22; lesson 18 has the same table and its source note. The per-call tokens are measured counts: 389 input tokens and 10 output tokens in lesson 18's first recorded call (lesson 18's average over its calls is 386). The volumes and shares are guesses for Basket Bazaar. Each guess has a hint on where to get the real number. Replace each guess as soon as you have one.
#
# From this step on, the helpers below read `IN_TOKENS`, `OUT_TOKENS` and `INPUTS` as globals on purpose, so every lever starts from the same base case.

# %%
PRICE = {"input": 0.25, "output": 1.50, "cache_read": 0.025}  # USD per million tokens (Gemini 3.1 Flash-Lite, as in lesson 18)
PRICE_DATE = "2026-10-22"
IN_TOKENS, OUT_TOKENS = 389, 10          # measured: 389 input tokens and 10 output tokens in lesson 18's first recorded call (its average over calls is 386)

INPUTS = {
    "queries_per_month": 600_000,    # guess: 20,000 messages a day (lesson 18's volume); take it from the pilot's logs
    "cache_hit_rate": 0.30,          # guess: share of messages answered from our answer cache; measure it on the eval set
    "flagged_share": 0.02,           # guess: share of answers a person must check; in the pilot, count the fallback answers (lesson 28) plus the answers you sample for review
    "minutes_per_check": 2.0,        # guess: minutes for one person to check one flagged answer; time five checks in the pilot
    "staff_rate_per_hour": 30.0,     # guess: loaded cost of one support person (salary plus overheads), USD; ask finance
    "fixed_per_month": 3_000.0,      # guess: hosting, monitoring, eval runs, on-call share, USD; take it from the cloud bill
    "prefix_cache_share": 0.0,       # guess: share of input tokens in a repeated prefix that is billed as a cache read (0 = off today)
    "price_per_month": 20_000.0,     # agreed in the contract (invented for this lesson), USD
}
print(f"prices (USD per 1M tokens, {PRICE_DATE}):", PRICE)
print("tokens per miss: input", IN_TOKENS, "| output", OUT_TOKENS)
print("queries a month:", f"{INPUTS['queries_per_month']:,}", "| contract price:", f"${INPUTS['price_per_month']:,.0f}")

# %% [markdown]
# ### Step 2: the model bill per query
#
# Only a cache miss calls the model, so the token cost of one query is the cost of one miss times the share of misses. The answer cache costs nothing per hit in this simple model.
#
# The provider's prompt-prefix cache is a different layer. It makes a repeated prefix of the prompt (system prompt, policy text) cheaper to read on each miss. It is off today (`prefix_cache_share` is 0), and Step 5 turns it on as a lever. The simple model leaves out cache storage fees, and providers set a minimum prefix length before caching applies, so check that your prefix clears it.

# %%
def model_cost_per_query(inp: dict, price: dict) -> float:
    """Token cost of one query, in USD. Only cache misses call the model."""
    s = inp.get("prefix_cache_share", 0.0)  # share of input tokens billed at the cache-read price
    in_price = s * price["cache_read"] + (1 - s) * price["input"]
    per_miss = IN_TOKENS / 1e6 * in_price + OUT_TOKENS / 1e6 * price["output"]
    return (1 - inp["cache_hit_rate"]) * per_miss


per_query = model_cost_per_query(INPUTS, PRICE)
print(f"model cost per query: ${per_query:.8f}")
print(f"model bill a month: ${per_query * INPUTS['queries_per_month']:,.2f}")

# %% [markdown]
# ### Step 3: the monthly bill, in three blocks
#
# People are a block of their own. The number of answers a person checks is the queries times the flagged share. Hours are those checks times the minutes each takes. The platform block is fixed.

# %%
def monthly_bill(inp: dict, price: dict) -> dict:
    """The monthly cost of one customer, in USD, in three blocks."""
    q = inp["queries_per_month"]
    checks = q * inp["flagged_share"]
    return {
        "model tokens": q * model_cost_per_query(inp, price),
        "people checking answers": checks * inp["minutes_per_check"] / 60 * inp["staff_rate_per_hour"],
        "fixed platform": inp["fixed_per_month"],
    }


bill = monthly_bill(INPUTS, PRICE)
total = sum(bill.values())
for name, usd in sorted(bill.items(), key=lambda kv: -kv[1]):
    print(f"{name:<26} ${usd:>10,.2f}  {usd / total:6.1%}")
print(f"{'total a month':<26} ${total:>10,.2f}")

# %% [markdown]
# ### Step 4: the unit numbers a customer asks for
#
# Cost per query divides the bill by all queries. Cost per resolved case divides it by the queries answered with no person involved. A flagged answer that a person checks and sends is also resolved, but this simple count leaves it out, so this figure is a little high. The margin is the contract price minus the bill, as a share of the price.

# %%
q = INPUTS["queries_per_month"]
resolved = q * (1 - INPUTS["flagged_share"])
margin = (INPUTS["price_per_month"] - total) / INPUTS["price_per_month"]
print(f"cost per query:          ${total / q:.4f}")
print(f"cost per resolved case:  ${total / resolved:.4f}")
print(f"cost per customer-month: ${total:,.2f} against a price of ${INPUTS['price_per_month']:,.0f}")
print(f"gross margin: {margin:.1%}")

# %% [markdown]
# ### Step 5: which lever moves the bill most
#
# A lever is one input changed by a stated amount. Each row changes one input and keeps the rest. The saving is the old bill minus the new one. The list is sorted by saving, so the top two rows are the two levers to work on first.
#
# The sizes are illustrative guesses. Size each lever to what is realistic for this customer, not to a round number, and replace them with your measured numbers before you quote a saving.

# %%
def bill_with(change: dict) -> float:
    """Total monthly bill after one change. 'price_factor' scales the model price table."""
    inp = {**INPUTS, **{k: v for k, v in change.items() if k != "price_factor"}}
    price = {k: v * change.get("price_factor", 1) for k, v in PRICE.items()}
    return sum(monthly_bill(inp, price).values())


LEVERS = {
    "flagged share 2% -> 1% (better rules, fewer checks)": {"flagged_share": 0.01},
    "minutes per check 2 -> 1.5 (a faster review screen)": {"minutes_per_check": 1.5},
    "cache hits 30% -> 50%": {"cache_hit_rate": 0.50},
    "model price halved (a smaller model)": {"price_factor": 0.5},
    "prompt-prefix cache on 60% of input tokens (guess)": {"prefix_cache_share": 0.6},
    "fixed platform 3,000 -> 2,000 (guess)": {"fixed_per_month": 2_000.0},
}
saving = {name: total - bill_with(change) for name, change in LEVERS.items()}
for rank, (name, usd) in enumerate(sorted(saving.items(), key=lambda kv: -kv[1]), start=1):
    print(f"{rank}. ${usd:>9,.2f} a month  {name}")

# %% [markdown]
# Reading the list: the token levers are small. Halving the model price saves $24 a month, the prompt-prefix cache $22 and a higher answer-cache hit rate $13, against about $47 of model bill today. Cutting the fixed platform cost by $1,000 is worth more than any of them. The two biggest levers are the share of answers a person checks ($6,000 a month) and the minutes per check ($3,000 a month). Work on those first. Check the numbers with your own measured shares before you quote them.

# %% [markdown]
# ## At work
#
# - Customers ask for cost per resolved case and cost per tenant per month, not cost per token. Teams that quote tokens lose the margin on the people who check answers. → lesson 30 turns these numbers into a go or no-go.
# - The cheapest saving is usually fewer answers that need a person, not a cheaper model. Measure the flagged share in the first pilot week, then set the target. → lesson 28 defines the fallback count.
# - Model routing (a small model answers first, a larger one only the hard cases) is a lever you can price with this table. Measure both models on the same eval set before you move traffic. → lesson 11 builds that eval set.
#
# Go deeper: contract terms for price changes when the model price moves are a commercial topic and are not taught here.

# %% [markdown]
# ## Common mistakes
#
# - **A new customer with no resolved cases yet.** Dividing by zero stops the report. Guard the division, and show "no data yet" instead of a number. The bill is not zero even with no traffic: fixed costs start before the first query.

# %% tags=["raises-exception"]
new_customer_resolved = 0
print(total / new_customer_resolved)

# %% [markdown]
# The fix is a guard before the division, as in the Try-it below. A missing number is better than a crash in a customer report.
#
# - **Using the per-million price on a single token.** The table is in dollars per million tokens. Multiply by `tokens / 1e6`, not by `tokens`, or the bill is a million times too big. The wrong line and the right line, for one call:

# %%
print(f"wrong: ${IN_TOKENS * PRICE['input']:,.2f} for one call")
print(f"right: ${IN_TOKENS / 1e6 * PRICE['input']:.8f} for one call")

# %% [markdown]
# ## Production checklist
#
# - [ ] Every number in the bill is labelled measured, agreed or a guess, with its date.
# - [ ] The people who check answers are in the bill, not only the model. Measure the flagged share in the pilot, counting the fallback answers from lesson 28 and your review sampling.
# - [ ] Cost per query, per resolved case and per customer-month are reported, not only the token count.
# - [ ] Prices come from one dated table; a model change reruns this calculation before it ships.
# - [ ] A per-tenant budget with an alert sits on top of the bill (lesson 18).

# %% [markdown]
# ## Try it
#
# Write `cost_per_resolved_case(total_cost, resolved)`. It returns the cost of one resolved case in USD, rounded to 4 places, or `None` when no case is resolved yet. The first call uses the bill from Step 3 and the resolved count from Step 4; the second call is the new customer.
#
# Expected output once it works: `0.0256 None`. Until you replace the `...`, the stub returns None, so the cell prints `None None`.

# %%
# your code here
def cost_per_resolved_case(total_cost: float, resolved: float) -> float | None:
    """Cost of one resolved case in USD, or None when there are no resolved cases yet."""
    ...  # write the guard and the division


print(cost_per_resolved_case(total, resolved), cost_per_resolved_case(total, 0))

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
def cost_per_resolved_case(total_cost: float, resolved: float) -> float | None:
    """Cost of one resolved case in USD, or None when there are no resolved cases yet."""
    if resolved <= 0:
        return None
    return round(total_cost / resolved, 4)


print(cost_per_resolved_case(total, resolved), cost_per_resolved_case(total, 0))

# %% [markdown]
# ## Recap
#
# - Unit economics divides the monthly bill by the units a customer buys: queries, resolved cases, customer-months.
# - Label every number as measured, agreed or a guess, with its date.
# - People who check answers are often the biggest cost. The model bill can be small.
# - Rank the levers by dollars saved, and work on the top two.
# - Words to keep: **unit economics**, **cost per resolved case**, **gross margin**, **variable cost**, **fixed cost** (all in GLOSSARY.md).
#
# **Interview:** "A customer's AI feature costs more than the contract pays. Where do you look first?" Strong answer: "I split the bill into the model tokens, the people who check answers and the fixed platform cost, and I divide each by queries and resolved cases. Usually the human checks dominate, so I cut the flagged share and the minutes per check before I touch the model price."

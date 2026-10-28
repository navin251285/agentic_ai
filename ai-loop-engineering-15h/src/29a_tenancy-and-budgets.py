# %% [markdown]
# # 29a · Tenancy and budgets: per-tenant limits, per-run traps and gateway keys
# Level L6 · Part 4 · core · ~20 min · builds on 28b
#
# ## Goal
# Give each tenant a daily and a monthly ceiling at the gateway, give each run a cap that fits inside that ceiling, and show why a per-run cap is not a monthly limit: an hourly schedule with a $20 run cap can spend $14,400 in a month.
#
# ## Before you start
# No key, no Docker and no network. This is a walkthrough: you read a request, check the arithmetic in the cells, and compare the numbers. Nothing is sent to a model or to a service. The request shapes are the ones the Claude and LiteLLM docs specify.

# %% [markdown]
# ## Why it matters
# Lesson 28b runs many workers for one shop. A second shop makes the problem sharper. Without tenant limits:
#
# | Without this | What goes wrong |
# |---|---|
# | One budget for the whole platform | One tenant's loop spends the month for everyone |
# | A cap on each run only | Runs can repeat all month. Each one stays under its cap, and the total does not |
# | One shared key for every tenant | You cannot say which tenant spent what, or cut one tenant off alone |
# | No tenant id on the traces | A noisy tenant hides inside the platform's total |
#
# With a gateway key per tenant, every call carries the tenant's key, and the gateway refuses the call once that tenant's window is spent. You do not need this for one team on one laptop.
#
# Terms used in this lesson:
# - A **gateway** is a proxy every model call passes through, so it can count spend and refuse calls.
# - A **session** is one agent run. A **deployment** starts sessions on a schedule.
# - **Managed Agents** is the hosted platform that runs them (lesson 28a).
# - **budget_reached** is the state a session enters at its cap. The platform pauses it there.

# %% [markdown]
# ## The idea
# **Three limits work together. A run cap stops one run. A tenant ceiling, set on a gateway key with a day window and a month window, stops one tenant. A provider limit is shared by everyone and is the last one to hit. A per-run cap alone never limits a tenant, because the number of runs is not capped.**
#
# Analogy: a hotel gives each guest a room budget for one night (the run cap), and each company a monthly card limit (the tenant ceiling). A nightly limit per guest does not stop a company that books a new guest every night.

# %% [markdown]
# ## Picture
# Each tenant has its own key and ceiling. The run cap sits inside the key, and every tenant shares the provider's project limit.
#
# ```mermaid
# flowchart LR
#   T1["tenant brightside<br/>key: $300 a day, $3,000 a month"] --> G["gateway<br/>checks the key before each reply"]
#   T2["tenant northwind<br/>key: $100 a day, $1,000 a month"] --> G
#   G --> R["one run<br/>cap per run, pauses with budget_reached"]
#   R --> P["provider project limit<br/>shared by all tenants"]
# ```

# %% [markdown]
# ## Step by step
# ### Step 1: read the per-run cap in the deployment
# A scheduled deployment starts one session per tick. Its `budget` is copied onto each session, so the cap bounds every run. The amount is a string of whole US cents: `"2000"` means 2000 cents, which is $20 USD.
#
# The payload below shows the shape of the deployment's schedule and budget fields. Creating a deployment also needs `agent`, `environment_id` and `initial_events`. To change the budget on an existing deployment, POST only the budget object to `/v1/deployments/$DEPLOYMENT_ID?beta=true`, with the `x-api-key`, `anthropic-version` and `anthropic-beta` headers, or use `ant apply`. The key is read from your environment, never written in the file. The docs page is [Scheduled deployments](https://platform.claude.com/docs/en/managed-agents/scheduled-deployments).

# %%
import json

DEPLOYMENT = {
    "name": "Hourly refund check (Brightside)",
    "schedule": {"type": "cron", "expression": "0 * * * *", "timezone": "UTC"},
    "budget": {"type": "limit", "max_list_cost": {"amount": "2000", "currency": "USD"}},
}
print(json.dumps(DEPLOYMENT, indent=2))

# %% [markdown]
# **What you should see:** the schedule runs every hour, and the cap is `"2000"` in USD cents, which is $20. The next cell reads that cap as money.

# %% [markdown]
# ### Step 2: multiply the cap by the schedule
# The docs say the cap applies to each run, not to the deployment as a whole. So the number that matters is runs per month times cap. This is arithmetic only; no run is made.

# %%
PER_RUN_USD = 20      # "2000" cents = $20 USD per run
RUNS_PER_DAY = 24     # the hourly cron above
RUNS_PER_MONTH = RUNS_PER_DAY * 30

print(f"runs per month: {RUNS_PER_MONTH}")
print(f"cap per run: ${PER_RUN_USD}")
print(f"worst case if every run spends its cap: ${PER_RUN_USD * RUNS_PER_MONTH:,}")

# %% [markdown]
# **What you should see:** 720 runs and a worst case of $14,400 a month. The cap of $20 looked safe, and it is 4.8 times the tenant's whole monthly ceiling of $3,000. The fix is a tenant ceiling at the gateway, sized to the runs.

# %% [markdown]
# ### Step 3: set the tenant ceiling on a gateway key
# A gateway (LiteLLM is the one the docs describe) puts every model call behind a key. Before that key works:
# - **The team must exist first.** `POST /team/new` creates it and returns a `team_id`. The key below names that team; `brightside` stands for it.
# - **Budgets need a database.** The LiteLLM docs say budgets require Postgres, which stores every spend count.
#
# The request creates a key for `brightside`: $300 a day and $3,000 a month, plus a rate limit. It is printed, not sent; sending it needs a running proxy with that database.
#
# CLI or API equivalent: `POST /key/generate` on the proxy, with the master key in the `Authorization: Bearer` header. The master key comes from your environment.

# %%
KEY_REQUEST = {
    "team_id": "brightside",
    "budget_limits": [
        {"budget_duration": "1d", "max_budget": 300},
        {"budget_duration": "30d", "max_budget": 3000},
    ],
    "rpm_limit": 60,
    "max_parallel_requests": 4,
}
print(json.dumps(KEY_REQUEST, indent=2))

# %% [markdown]
# **What you should see:** two windows, one per day and one per 30 days. A call is refused as soon as either window is spent, so the monthly window is the ceiling and the daily one stops a burst early. `rpm_limit` and `max_parallel_requests` are rate limits, not spend limits: they cap how fast the tenant sends requests.

# %% [markdown]
# ### Step 4: check that the run cap fits the ceiling
# Before you schedule a tenant, divide its monthly ceiling by the runs it will make, and cap each run at that size or less. Here the ceiling for `brightside` is $3,000 and the schedule makes 720 runs.

# %%
TENANT_MONTH_USD = 3000
cap_that_fits = TENANT_MONTH_USD / RUNS_PER_MONTH
print(f"largest cap that fits the month: ${cap_that_fits:.2f} per run")
print(f"at $4.00 a run: ${4.00 * RUNS_PER_MONTH:,.0f} a month, under the ${TENANT_MONTH_USD:,} ceiling")

# %% [markdown]
# **What you should see:** about $4.17 is the most each run can spend. A cap of $4.00 leaves room for the overshoot in the next step.

# %% [markdown]
# ### Step 5: see the overshoot inside one run
# A cap is tested before each reply. A reply that starts under the cap is paid for in full, even if it takes the run past the cap. The loop below is arithmetic with example costs, not a model run.
#
# Illustrative model: the cap is tested before each reply, so the reply that crosses it is still paid for. Costs are example numbers, not a measured run. The rule matches the [session budgets page](https://platform.claude.com/docs/en/managed-agents/budgets#when-a-session-reaches-its-budget).

# %%
CAP = 4.00
reply_costs = [1.10, 1.25, 0.90, 0.80, 0.70]  # example USD cost of each model reply in one run
spent = 0.0
for i, cost in enumerate(reply_costs, start=1):
    if spent >= CAP:  # refused before the reply is paid for
        print(f"reply {i}: refused, spent {spent:.2f} has reached the cap {CAP:.2f}")
        break
    spent += cost
    print(f"reply {i}: cost {cost:.2f}, spent {spent:.2f}")
print(f"overshoot: {max(0.0, spent - CAP):.2f} USD past the cap")

# %% [markdown]
# **What you should see:** reply 4 starts at $3.25, which is under the $4.00 cap. It costs $0.80 and ends at $4.05, which is $0.05 past the cap. Reply 5 is refused, and the run stops with `budget_reached`. The worst case with that overshoot is $4.05 × 720 = $2,916 a month, still under $3,000. That headroom is why the Try-it floor is $4, not $4.17.

# %% [markdown]
# ### Step 6: isolate the tenants in the run itself
# A budget stops spending, not leaking. Each tenant's runs also need their own files, settings and network rules. This is the Agent SDK recipe for a shared container (hosting docs). Read only: nothing runs here.
#
# - `query()` is the Agent SDK call that starts one agent run. Its `cwd` is the folder that run may read and write.
# - `setting_sources` chooses which settings files load into a run (memory, CLAUDE.md, project settings). `[]` loads none.
# - `CLAUDE_CONFIG_DIR` is the folder where the SDK keeps its per-user config and transcripts. One folder per tenant keeps them apart.
#
# | Layer | What to set | What it stops |
# |---|---|---|
# | Working folder | a `cwd` per tenant on every `query()` | one tenant's runs reading another's files |
# | Settings | a `CLAUDE_CONFIG_DIR` per tenant, `setting_sources=[]` | memory and settings from another tenant |
# | Network | per-tenant egress rules at the proxy | one tenant calling another's systems |

# %% [markdown]
# ## At real scale
# - **Per-run caps are not a ceiling.** The Managed Agents docs say the cap is per run, not cumulative. Set the tenant ceiling at the gateway, sized to runs per month. → lesson 29b shows who spent what.
# - **A key per tenant.** A shared key cannot be cut off for one tenant. Give each tenant a team and a key. Budgets reset on `budget_duration` and need Postgres ([LiteLLM users](https://docs.litellm.ai/docs/proxy/users)).
# - **Budgets stop spending, rate limits stop bursts.** Once a tenant's window is spent, its requests fail until the window resets or the key changes. Before that point, `rpm_limit` and `max_parallel_requests` cap the burst, so one tenant cannot use the provider's shared limit (lesson 28b).
# - **Isolation is a recipe, not a switch.** The Agent SDK hosting docs list the per-tenant settings ([code.claude.com/docs/en/agent-sdk/hosting](https://code.claude.com/docs/en/agent-sdk/hosting)).
#
# %% [markdown]
# Sources: [Scheduled deployments, budget per run](https://platform.claude.com/docs/en/managed-agents/scheduled-deployments), [Session budgets, when a session reaches its budget](https://platform.claude.com/docs/en/managed-agents/budgets#when-a-session-reaches-its-budget), [LiteLLM budgets and keys](https://docs.litellm.ai/docs/proxy/users), [LiteLLM team budgets](https://docs.litellm.ai/docs/proxy/team_budgets).

# %% [markdown]
# ## Decision guide
# | Situation | Approach | Why |
# |---|---|---|
# | One run should never cost more than X | Run cap per run (`budget`, or your own counter) | Stops one run; does not stop many runs |
# | A tenant must not exceed a monthly amount | Gateway key with a month window | Counts every run and call of that tenant |
# | A burst from one tenant slows others | `rpm_limit` and parallel-run caps per tenant | Shares the provider limit fairly |
# | A tenant leaves or is paused | Disable its key | One switch, no code change to the loop |
# | Reports per tenant | `tenant.id` on spans and in the key's metadata | Totals by tenant come from the traces |

# %% [markdown]
# ## What just happened
# You printed one deployment payload, one gateway key request, and then did the arithmetic that joins them. The cap of $20 looked safe for one run and was a $14,400 month for one tenant. The fix was not a smaller run cap alone. It was a monthly window at the gateway, sized to the number of runs. The overshoot cell showed that a cap is tested before each reply, so the reply that starts under the cap can finish past it: $4.05 against a $4.00 cap.

# %% [markdown]
# ## Common mistakes
# The common mistake is to read a per-run cap as a monthly ceiling. This cell does the multiplication the mistake skips: the assert fails, which is the expected result.

# %% tags=["raises-exception"]
per_run_cap_usd = 20
monthly_ceiling_usd = 3000
runs = 720  # hourly, for a month
assert per_run_cap_usd * runs <= monthly_ceiling_usd, (
    f"a ${per_run_cap_usd} cap over {runs} runs is ${per_run_cap_usd * runs:,}, "
    f"above the ${monthly_ceiling_usd:,} ceiling"
)

# %% [markdown]
# The assert uses the same numbers as Step 2 ($20 cap, 720 runs). It fails because $14,400 is above the $3,000 ceiling. The fix is in Step 4: set the cap from the ceiling and the runs, and keep the gateway's monthly window as the hard limit.

# %% [markdown]
# ## Try it
# Write `per_run_cap_for(monthly_ceiling_usd, runs_per_month)` that returns the largest whole-dollar cap that keeps the month under the ceiling. Then print it for `brightside` (3000 a month, 720 runs). Predict the answer first.

# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
import math

def per_run_cap_for(monthly_ceiling_usd, runs_per_month):
    return math.floor(monthly_ceiling_usd / runs_per_month)

# $4 is the floor of 3000 / 720 = 4.17. It leaves headroom: $4.05 x 720 = $2,916 with the Step 5 overshoot, still under $3,000.
print(f"largest whole-dollar cap: ${per_run_cap_for(3000, 720)} per run")  # $4 per run

# %% [markdown]
# ## Key terms
# - **per-run cap** — a limit on one session's list cost (`budget` on a deployment); it does not limit the number of runs.
# - **tenant ceiling** — the most one tenant can spend in a window, set on its gateway key.
# - **budget window** — the period a budget counts over (`budget_duration`, for example `1d` or `30d`); each window is checked on its own.
# - **gateway key** — the credential every call of one tenant carries; the gateway counts spend and rate against it.
# - **budget_reached** — the state a managed session enters when its list cost reaches its cap; it pauses there.
# - **noisy neighbour** — one tenant's burst that uses up a shared limit and slows the others.
# - **tenant id** — the label on every span, cache key and key record that says which tenant a call belongs to.
#
# %% [markdown]
# **Interview:** How do you stop one customer from spending the whole month's budget on your agent platform? Strong answer: a per-run cap stops one run but not many, so put a monthly window on the tenant's gateway key, size each run cap to the ceiling divided by the runs, rate-limit each tenant, and tag every span and cache key with the tenant id.

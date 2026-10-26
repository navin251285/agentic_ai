# %% [markdown]
# # 26 · Feedback loops to product: writing a field report
#
# Level L5 · Part 3 · professional · ~20 min · builds on 25
#
# Walkthrough with code. No keys, no Docker, no model calls. Standard library only (`csv`, `io`, `collections`, `datetime`). The request log is invented for the fictional customers Basket Bazaar and Corner Shop Co.

# %% [markdown]
# ## Goal
#
# By the end you can turn a customer's repeated request into a field report: how often it came back, what it cost, the evidence, a core or custom proposal and one decision for product. A check flags any claim that has no source.

# %% [markdown]
# ## Why it matters
#
# Field requests arrive as emails, chats and calls. Each one gets a quick fix and is closed. Product hears "Basket Bazaar says the eggs are wrong" once, from one person, with no number. Nobody sees that the same problem came back four times from two customers in two weeks.
#
# - **Without this lesson:** the request reaches product as a vague complaint. It is ranked by whoever shouts loudest, and the hand fixes hide the cost.
# - **With it:** the requests are counted across customers, the cost is in hours, every number names its source, and product gets one decision to make.
# - **When you don't need it:** a one-off wish from one customer that will never come back. Note it in the customer's file and move on.

# %% [markdown]
# ## The idea
#
# A **field report** is a short, evidence-backed note from the field to the product team. It says what customers asked, how often, what it costs, what proves it, whether the fix is **core** or **custom** (lesson 25), and which decision you need. The rule: every number is copied from a run or a log that someone can repeat. It is never remembered.
#
# Analogy: a referral letter from a GP to a specialist. It gives the symptom, the tests, the results and one question. A letter that says "patient seems unwell" gets no appointment.

# %% [markdown]
# ## Picture
#
# The lesson 25 field note is the short version. This lesson writes the full report from a repeated request.

# %% [markdown]
# ```mermaid
# flowchart LR
#     R[Repeated requests from customers] --> C[Count them by theme and customer]
#     C --> E[Attach evidence: order ids, numbers from the run]
#     E --> K{Core or custom?}
#     K -->|core| P[Product: one shared fix]
#     K -->|custom| F[Stays in the customer's config]
#     P --> D[One decision, an owner and a date]
# ```

# %% [markdown]
# ## Step by step

# %% [markdown]
# ### Step 1: the request log
#
# Every request goes in one log, with the date, the customer, the role, the words used, a theme and the minutes it took to fix by hand. The log is invented. Read it first.

# %%
import csv
import io
from collections import defaultdict
from datetime import date

REQUESTS = """date,customer,role,what they asked,theme,fix_minutes
2026-10-06,Basket Bazaar,store manager Store 01,eggs look short on the nightly sheet,units,40
2026-10-08,Basket Bazaar,store manager Store 02,a dozen is counted as one egg,units,25
2026-10-09,Corner Shop Co,owner,the same order line is counted twice,copies,15
2026-10-13,Basket Bazaar,ops lead,an order from the 2026/10/20 file is missing from the sheet,dates,30
2026-10-15,Basket Bazaar,store manager Store 03,rice totals in grams are wrong on the sheet,units,35
2026-10-20,Corner Shop Co,owner,water sold by the case is not counted,units,20
"""


def load_requests(text):
    """Read the request log. csv gives text, so the minutes become numbers here, once."""
    rows = list(csv.DictReader(io.StringIO(text)))
    for row in rows:
        row["fix_minutes"] = int(row["fix_minutes"])
    return rows


requests = load_requests(REQUESTS)
print(len(requests), "requests logged")
print(requests[0])

# %% [markdown]
# **You should see:** `6 requests logged`, then the first row as a dict with `fix_minutes` as an integer (40), not text.

# %% [markdown]
# ### Step 2: count by theme and customer
#
# A repeated request shows up as one theme with many rows. Count the rows and the distinct customers for each theme. Sort the biggest first.
#
# The copies and dates rows are single requests. Each one stays in the customer file, because one request each is not "repeated". They are not part of the four unit requests that the report counts.

# %%
def by_theme(rows):
    """Group the requests by theme."""
    groups = defaultdict(list)
    for row in rows:
        groups[row["theme"]].append(row)
    return groups


for theme, rows in sorted(by_theme(requests).items(), key=lambda kv: -len(kv[1])):
    customers = {row["customer"] for row in rows}
    print(f"{theme:<8} {len(rows)} request(s) from {len(customers)} customer(s)")

# %% [markdown]
# **You should see:** `units` first, with 4 requests from 2 customers. Copies and dates come next with one request each. The count says where the repeated problem is, before anyone argues about it.

# %% [markdown]
# ### Step 3: count the cost and the span
#
# A repeated request costs time every time it comes back. Add the minutes of the `units` rows, the first and last date, and the customers who asked.

# %%
units = by_theme(requests)["units"]
customers_units = {row["customer"] for row in units}
hours = sum(row["fix_minutes"] for row in units) / 60
first = min(row["date"] for row in units)
last = max(row["date"] for row in units)
print(f"units: {len(units)} requests from {len(customers_units)} customers, {first} to {last}")
print(f"hours of manual fixing: {hours:.1f}")

# %% [markdown]
# **You should see:** 4 requests from 2 customers between 2026-10-06 and 2026-10-20, and 2.0 hours of manual fixing. ISO dates sort as text, so `min` and `max` work here.

# %% [markdown]
# ### Step 4: the evidence from lesson 25
#
# The numbers about eggs come from the lesson 25 run, not from this log. Setup from lesson 25 (its output, copied; the export is invented): the shipped script said 14 eggs, the cleaned count is 45, two copies were dropped and one row was refused.

# %%
# Setup from lesson 25 (its output, copied). Each value names the run that produced it.
L25 = {
    "eggs_shipped_script": 14,
    "eggs_clean": 45,
    "copies_dropped": ["BB-1000", "BB-1003"],
    "rejected_rows": ["BB-1006: date 2026/10/20 11:00 is in no agreed format"],
}

LOG, RUN25 = "requests log", "lesson 25 run"
numbers = [
    {"what": "requests about units", "value": len(units), "source": LOG},
    {"what": "customers who asked about units", "value": len(customers_units), "source": LOG},
    {"what": "hours of manual unit fixes", "value": f"{hours:.1f}", "source": LOG},
    {"what": "eggs: shipped script vs clean count", "value": f"{L25['eggs_shipped_script']} vs {L25['eggs_clean']}",
     "source": RUN25},
    {"what": "copies dropped", "value": len(L25["copies_dropped"]), "source": RUN25},
]
print(len(numbers), "numbers, each with a source")

# %% [markdown]
# **You should see:** `5 numbers, each with a source`. Every row of `numbers` says where it came from. A number with no source is a guess, and the check in the next step refuses it.

# %% [markdown]
# ### Step 5: write the report and check it
#
# The report is data: one dict with a fixed set of sections. `check_report` lists what is missing. An empty list means the report is ready to send.

# %%
REQUIRED = ("title", "problem", "numbers", "evidence", "core_or_custom", "ask", "owner", "by_date")


def check_report(report):
    """Return the problems. An empty list means every section is there and every number has a source."""
    problems = [f"missing: {key}" for key in REQUIRED if not report.get(key)]
    for claim in report.get("numbers", []):
        if not claim.get("source"):
            problems.append(f"no source for: {claim.get('what', '?')}")
    return problems

# %% [markdown]
# Now the report itself. Its numbers are the ones from Step 4, and its core and custom split comes from lesson 25.

# %%
span_days = (date.fromisoformat(last) - date.fromisoformat(first)).days
report = {
    "title": "Units on the nightly sheet (Basket Bazaar, Corner Shop Co)",
    "problem": f"The same unit problem came back {len(units)} times from {len(customers_units)} customers, "
               f"between {first} and {last} ({span_days} days). Each time it was fixed by hand.",
    "numbers": numbers,
    "evidence": [
        "dozens counted as single eggs (BB-1000 and BB-1002 lines, lesson 25 export)",
        "copies counted twice: BB-1000 and BB-1003 (other theme, same export)",
        "BB-1006 refused: date in no agreed format (other theme, same export)",
    ],
    "core_or_custom": {
        "core": "unit table and conversion to a base unit, as one shared mechanism",
        "custom": "Basket Bazaar's store-closing rules stay in its own config",
    },
    "ask": "Decide whether the unit conversion moves into the shared core, with its own tests.",
    "owner": "product owner, cleaning module",
    "by_date": "2026-11-06",
}
print(check_report(report) or "ready to send")

# %% [markdown]
# **You should see:** `ready to send`. The same check is what refuses a number with no source, so keep it next to the report.

# %% [markdown]
# ### Step 6: render the text product reads

# %%
def render(report):
    """Turn a checked report into the text the product team reads."""
    lines = [f"## {report['title']}", report["problem"], "", "**Numbers**"]
    lines += [f"- {c['what']}: {c['value']} (source: {c['source']})" for c in report["numbers"]]
    lines += ["", "**Evidence**"] + [f"- {e}" for e in report["evidence"]]
    lines += ["", f"**Core:** {report['core_or_custom']['core']}",
              f"**Custom, not moved:** {report['core_or_custom']['custom']}"]
    lines += ["", f"**Decision asked:** {report['ask']} Owner: {report['owner']}. By {report['by_date']}."]
    return "\n".join(lines)


print(render(report))

# %% [markdown]
# **You should see:** short markdown with the numbers and their sources, the evidence, then the `**Core:**` and `**Custom, not moved:**` lines, and last one decision line with an owner and a date. The printout is the whole report, about 19 lines.
#
# No tracker is named here. In a team's ticket tool the same fields are the form. If the tool has an API, the `report` dict is the request body.

# %% [markdown]
# ## At work
#
# - **Product feedback is part of the job.** (see lesson 25) → lesson 30 for the business case behind each request.
# - **Bespoke work can fork the product.** Without a product organisation that generalises what field teams learn, the bespoke work multiplies (see lesson 25). → lesson 30.
# - **Codify the repeat, don't just close the ticket.** Field engineers exist partly to "identify and codify repeatable deployment patterns" for the product (Anthropic job posting: https://job-boards.greenhouse.io/anthropic/jobs/5390795008). → lesson 30.

# %% [markdown]
# ## Common mistakes
#
# - **Adding up the csv text.** `csv` returns every value as text, so the minutes cannot be added. Here is the failure:

# %% tags=["raises-exception"]
# Wrong: the minutes are still text, so the sum fails.
raw = list(csv.DictReader(io.StringIO(REQUESTS)))
sum(row["fix_minutes"] for row in raw)

# %% [markdown]
# The fix is in Step 1: `load_requests` converts the minutes once, when the log is read.
#
# - **Sending the complaint instead of the report.** A draft with only a complaint fails the check. Here is what the check says about it:

# %%
draft = {"title": "Eggs are wrong", "problem": "Customer is angry. Please fix.", "ask": "fix it"}
print(check_report(draft))

# %% [markdown]
# The fix is the full report: the numbers with sources, the evidence, the core or custom split, one decision, an owner and a date.

# %% [markdown]
# ## Production checklist
#
# Before the report goes to product, every line should be true:
#
# - [ ] Every number names its source: the request log or a run you can repeat (this lesson).
# - [ ] Every request is in the log, not only in someone's memory.
# - [ ] Each piece is marked core or custom, and custom rules stay in the customer's config (lesson 25).
# - [ ] The report asks for one decision, with an owner and a date.
# - [ ] The business case for that decision goes with the report (lesson 30).

# %% [markdown]
# ## Try it
#
# A seventh request arrives: on 2026-10-27 Corner Shop Co's owner says the water case still counts as one bottle, and the fix took 20 minutes. Add the row to the log, then print how many requests and customers the `units` theme now has, and the hours of fixes.

# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
MORE = REQUESTS + "2026-10-27,Corner Shop Co,owner,the water case still counts as 1 bottle,units,20\n"
rows_2 = by_theme(load_requests(MORE))["units"]
print(len(rows_2), "requests,", len({row["customer"] for row in rows_2}), "customers,",
      f"{sum(row['fix_minutes'] for row in rows_2) / 60:.1f} hours")  # expect 5 requests, 2 customers, 2.3 hours

# %% [markdown]
# ## Recap
#
# - A **field report** turns a repeated request into one decision for product.
# - Count by theme and distinct customer. Every number names its source; a check refuses the rest.
# - Keep custom rules in the customer's config. Send the core proposal with its evidence.
# - Words to keep: **field report**, plus **core** and **custom** from lesson 25.
#
# **Go deeper:** the business case that makes product act is in lesson 30.
#
# **Interview:** "A customer asks for the same change for the third time. What do you send to product?" Strong answer: "A short field report. It counts how many customers asked and what the manual fixes cost in hours. It names the rows that prove the problem and marks the fix as core or custom. It asks for one decision, with an owner and a date."


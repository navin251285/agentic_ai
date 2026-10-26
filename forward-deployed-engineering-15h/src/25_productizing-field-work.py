# %% [markdown]
# # 25 · Productizing field work: reusable components, custom vs core
#
# Level L5 · Part 3 · core · ~25 min · builds on 21
#
# Hands-on. No keys, no Docker, no model calls. Standard library only (`csv`, `collections`, `datetime`). The export in this lesson is invented and small enough to check by hand.

# %% [markdown]
# ## Goal
#
# By the end you can split one customer's cleaning script into a shared core and that customer's config, prove that the refactor did not change the answers where the old code was right, and reuse the same core for a second customer without copying it.

# %% [markdown]
# ## Why it matters
#
# Basket Bazaar's export cleaning is working. The next customer, Corner Shop Co (fictional), asks for the same thing. The quick route is to copy the script and change it. Then two copies exist, and every bug has to be found and fixed in both. With three customers the copies drift apart, and nobody knows which one is right.
#
# - **Without this lesson:** each customer gets its own copy of the script. A bug found at one customer is still in the others. Each copy gets its own quiet fixes and its own wrong totals.
# - **With it:** the shared mechanism is one component. Each customer's rules sit in a small config. A fix ships once, and one check runs it on every customer's sample.
# - **When you don't need it:** a one-off script for one customer that will never be run again. Keep it custom and delete it when the job is done.

# %% [markdown]
# ## The idea
#
# A piece of field code is **custom** when it encodes one customer's decision, such as their stable key or a store's closing time. It is **core** when the same mechanism serves many customers, such as parsing dates, converting units or removing copies. The FDE's job is to split the two. Core code takes the customer's rules as **config**. Custom rules stay in the customer's own folder.
#
# A **refactor** changes the structure of a program without changing what it does on purpose. You prove it with a **characterisation check**: run the old and the new code on the same input and compare them where the old code was right.
#
# Analogy: the wall socket is core, and the plug adapter for one country is custom. Nobody rewires the wall for one traveller.

# %% [markdown]
# ## Picture
#
# One core serves every customer. Only the config differs, and field notes go back to the product team.

# %% [markdown]
# ```mermaid
# flowchart LR
#     A[Basket Bazaar export] --> CA[Config A: key, dates, units]
#     B[Corner Shop export] --> CB[Config B: key, dates, units]
#     CA --> CORE[Core: clean_rows and totals]
#     CB --> CORE
#     CORE --> OUT[Clean rows and a log of every decision]
#     CORE -->|field note| PROD[Product team: one shared fix]
# ```

# %% [markdown]
# ## Step by step

# %% [markdown]
# ### Step 1: the script as it was shipped
#
# Here is a 10-line sample of Basket Bazaar's export (invented; the full file is lesson 05's) with copies, messy spelling, two date formats and units that need converting. The shipped script adds the quantities per item name. Read the export first, then trust no total until you have checked it.

# %%
import csv
import io
from collections import Counter
from datetime import datetime

EXPORT = """order_id,store,item,qty,unit,ordered_at
BB-1000,Store 01,eggs,2,dozen,2026-10-20 08:00
BB-1000,Store 01,eggs,2,dozen,2026-10-20 08:00
BB-1001,Store 02,eggs,6,each,20/10/2026 09:15
BB-1001,Store 02,milk,1,each,20/10/2026 09:15
 bb-1002 ,Store 02,Eggs ,1,dozen,2026-10-20 09:40
BB-1003,Store 03,rice,500,g,2026-10-20 10:05
BB-1003,Store 03,rice,500,g,2026-10-20 10:05
BB-1004,Store 03,eggs,3,each,2026-10-20 10:30
BB-1005,Store 01,bread,1,each,31/10/2026 08:00
BB-1006,Store 01,eggs,1,dozen,2026/10/20 11:00
"""
print(EXPORT)

# %% [markdown]
# The shipped function, as the team wrote it. It reads the export and adds up the quantities.

# %%
def old_totals(text):
    """The script as shipped: add qty per item name, nothing else."""
    totals = Counter()
    for row in csv.DictReader(io.StringIO(text)):
        totals[row["item"]] += int(row["qty"])  # raw spelling, raw units, copies counted twice
    return totals


old = old_totals(EXPORT)
print(dict(sorted(old.items())))
print("eggs the customer sees:", old["eggs"])

# %% [markdown]
# The script runs without an error and prints 14 eggs. The true count is 45:
#
# - two copies of the first order are counted twice (2 + 2 eggs),
# - a dozen is counted as one egg,
# - `Eggs ` with a capital and a trailing space is a second item,
# - the last line has a date in a format nobody agreed to. It must be refused and reported, not guessed.
#
# 45 = 24 + 6 + 12 + 3 eggs (the first order's dozens, the 6 eggs, the `Eggs ` dozen and the 3 eggs). The rejected last line (12 more eggs) is not counted until the customer confirms its date.
#
# Nothing in the old script warns you. That is the danger of field code.

# %% [markdown]
# ### Step 2: decide what is custom and what is core
#
# Before you change the code, sort each piece. The table is the decision. Write it down, because product will review it later.
#
# | Piece of code | Custom or core | Why |
# | --- | --- | --- |
# | Trim spaces, fix case | core | every export has messy text |
# | Parse a date from a list of formats | core | the formats are config |
# | Convert units to a base unit | core mechanism, custom table | each customer's units differ |
# | Remove copies by stable key | core | the key is config |
# | "Store 03 closes at 18:00" | custom | one store's business rule |
#
# Rule of thumb: when two customers need the same mechanism, move it to core. When one customer needs a decision, keep it custom behind one function, so it can move later.

# %%
# Custom: Store 03 closes at 18:00. One function outside clean_rows; the core never calls it.
def store_03_closed(when):
    return when.hour >= 18


print("Store 03 closed at 18:30?", store_03_closed(datetime(2026, 10, 20, 18, 30)))

# %% [markdown]
# ### Step 3: move the customer's rules into one config
#
# `CUSTOMER` holds everything that is specific to Basket Bazaar. The two core functions below read the config. They know nothing about Basket Bazaar.

# %%
CUSTOMER = {  # custom: this customer's rules. The next customer gets a new dict, not new code.
    "stable_key": ("order_id", "item"),  # one row per order and item
    "date_formats": ("%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M"),  # the two formats this export uses
    "to_base": {"each": ("each", 1), "dozen": ("each", 12), "g": ("g", 1)},  # unit: (base unit, factor)
}


def normalise(row):
    """Core: trim spaces and fix case, so ' bb-1002 ' and 'BB-1002' are one order."""
    return {**row, "order_id": row["order_id"].strip().upper(), "item": row["item"].strip().lower()}


def parse_when(text, formats):
    """Core: try each format in turn. Return None when none matches. Never guess."""
    for fmt in formats:
        try:
            return datetime.strptime(text.strip(), fmt)
        except ValueError:
            pass  # not this format: try the next one
    return None

# %% [markdown]
# ### Step 4: the core cleaning function
#
# `clean_rows` does the work for any customer. Every decision goes into a log: kept, copy dropped, or rejected with a reason. A rejected row is counted and reported. It is never dropped without a trace.

# %%
def read_row(raw, config):
    """Core: normalise one row and check it. Return (reason or None, values)."""
    row = normalise(raw)
    if row["unit"] not in config["to_base"]:
        return "rejected: unknown unit", None
    when = parse_when(row["ordered_at"], config["date_formats"])
    if when is None:
        return "rejected: unreadable date", None
    base_unit, factor = config["to_base"][row["unit"]]
    key = tuple(row[col] for col in config["stable_key"])
    return None, {"key": key, "order_id": row["order_id"], "item": row["item"], "base_unit": base_unit,
                  "qty": int(row["qty"]) * factor, "ordered_at": when}

# %% [markdown]
# `clean_rows` runs `read_row` on every line and keeps a log of each decision. A copy is dropped once. A row with the same key but different values is reported, not chosen.

# %%
def clean_rows(text, config):
    """Core: clean one export with one customer's config. Return the kept rows and a log of decisions."""
    kept, log, seen = [], Counter(), {}
    for raw in csv.DictReader(io.StringIO(text)):
        problem, row = read_row(raw, config)
        if problem:
            log[problem] += 1
            continue
        value = (row["item"], row["base_unit"], row["qty"])
        if row["key"] in seen:  # the same key again: an exact copy is counted once, a conflict is reported
            log["copy dropped" if seen[row["key"]] == value else "rejected: conflicting copy"] += 1
            continue
        seen[row["key"]] = value
        kept.append({k: v for k, v in row.items() if k != "key"})
        log["kept"] += 1
    return kept, log


# %% [markdown]
# Totals are core too: they add the base quantities per item and unit.

# %%
def totals_by_item(kept):
    """Core: add the base quantities per (item, base unit)."""
    totals = Counter()
    for row in kept:
        totals[(row["item"], row["base_unit"])] += row["qty"]
    return totals


kept, log = clean_rows(EXPORT, CUSTOMER)
print("log:", dict(log))
for (item, unit), qty in sorted(totals_by_item(kept).items()):
    print(item, qty, unit)

# %% [markdown]
# The log says 7 rows kept, 2 copies dropped and 1 row rejected for its date. The totals now use base units: 45 eggs, and the milk and bread lines are unchanged. The refused row is in the log, so the team can ask the customer about it.

# %% [markdown]
# The export above has no conflicting copy, so the third branch in `clean_rows` did not run. Here is a two-row export that triggers it: the same key with two different quantities.

# %%
CONFLICT = """order_id,store,item,qty,unit,ordered_at
BB-1000,Store 01,eggs,3,each,2026-10-20 08:00
BB-1000,Store 01,eggs,2,dozen,2026-10-20 08:00
"""
print("conflict log:", dict(clean_rows(CONFLICT, CUSTOMER)[1]))  # kept 1; the second row is reported, not chosen

# %% [markdown]
# ### Step 5: the characterisation check
#
# Did the refactor change anything it should not have? Compare old and new where the old code was right. Where it was wrong, the difference must have a reason in the log.

# %%
new = totals_by_item(kept)
for item, unit in [("eggs", "each"), ("milk", "each"), ("rice", "g"), ("bread", "each")]:
    print(f"{item:<6} old {old[item]:>5}   new {new[(item, unit)]:>5} {unit}")

assert new[("eggs", "each")] == 45  # the hand count from the export
assert log["copy dropped"] == 2
assert old["milk"] == new[("milk", "each")] and old["bread"] == new[("bread", "each")]  # where the old code was right, the new agrees

# %% [markdown]
# Milk and bread agree, so the old code was right for them. Eggs and rice differ. The log explains the copies and the date: the copy of the first order and the copy of the rice line are dropped, and the unreadable date is rejected. The dozens and the spelling of `Eggs ` are explained by the config and `normalise`. The check passed, so the refactor changed only what it was meant to change.

# %% [markdown]
# ### Step 6: a second customer, the same core
#
# Corner Shop Co has a different key (`line_no`), one date format and units in kilograms. Write a new config. Do not touch `clean_rows`, `normalise` or `parse_when`. If you have to change the core for the second customer, stop and ask whether the change belongs in the config.

# %%
SHOP = """order_id,line_no,item,qty,unit,ordered_at
CS-7,1,bread,2,each,03/11/2026 07:30
CS-7,2,rice,1,kg,03/11/2026 07:30
CS-7,2,rice,1,kg,03/11/2026 07:30
"""
CORNER_SHOP = {  # the second customer: other key, other date format, other units
    "stable_key": ("order_id", "line_no"),
    "date_formats": ("%d/%m/%Y %H:%M",),
    "to_base": {"each": ("each", 1), "kg": ("g", 1000)},
}
shop_kept, shop_log = clean_rows(SHOP, CORNER_SHOP)
print("log:", dict(shop_log))
for (item, unit), qty in sorted(totals_by_item(shop_kept).items()):
    print(item, qty, unit)

# %% [markdown]
# The same functions gave the right answer with a new config. A copy-and-edit fork would have needed the copy-and-edit fixes all over again.

# %% [markdown]
# ### Step 7: send the pattern back to product
#
# The field note is the output of this lesson. It names the core piece, the customers who use it, and the custom rules that stayed out. For this lesson it reads: **core**: `clean_rows`, `normalise`, `parse_when`, `totals_by_item`; **customers**: Basket Bazaar and Corner Shop Co, config only; **custom, not moved**: the store-closing rules. The product team decides whether the core becomes a shared component with its own tests. The full format of the field note is lesson 26.

# %%
assert "store_03_closed" not in clean_rows.__code__.co_names  # the core never calls the custom rule

# %% [markdown]
# ## At work
#
# - **Platforms come from field work.** Palantir's forward deployed engineers build prototypes on a platform, and a product organisation turns what they learn into shared parts. Without that, you end up with "thousands of large, bespoke solutions" to maintain (Cagan, SVPG). → lesson 23, lesson 26.
# - **Product feedback is part of the job.** → lesson 26.
# - **Shared parts change for every customer at once.** A connector or eval harness upgrade reaches all tenants, so it needs a zero-downtime plan and regression checks. → lesson 24 (zero-downtime changes).
# - **Go deeper:** the business case for building a shared component is in lesson 30.

# %% [markdown]
# ## Common mistakes
#
# - **One date format for every customer.** Customer B's export then stops the run. Here is the failure:

# %% tags=["raises-exception"]
# Wrong: a date parser for one format only. The second customer's day-first dates would crash the run.
datetime.strptime("20/10/2026 09:15", "%Y-%m-%d %H:%M")

# %% [markdown]
# The fix is in Step 3: the formats are part of the config, and `parse_when` tries each of them.
#
# - **Forking the core for one customer.** Two copies drift apart within a month. Put the difference in the config, or keep it custom behind one function.
# - **Refactoring without the check.** If you do not record the old answers, you cannot prove the new code is right. Step 5 is that proof.

# %% [markdown]
# ## Production checklist
#
# Before you call a shared component "ready" for a second customer, every line should be true:
#
# - [ ] Each customer-specific rule sits in a config, not in core code (this lesson).
# - [ ] Every unreadable row is counted and reported, never dropped silently (lesson 05).
# - [ ] The characterisation check passes on every customer's sample (lessons 11, 20).
# - [ ] A change to shared code goes out with a zero-downtime plan (lesson 24).
# - [ ] The field note has reached the product owner (lesson 26).

# %% [markdown]
# ## Try it
#
# Corner Shop Co also sells water by the case, and one case is 24 bottles. Add the unit to their config without changing any function, then clean this one-line export and print the water total in bottles.

# %%
# your code here
SHOP_2 = """order_id,line_no,item,qty,unit,ordered_at
CS-8,1,water,2,case,03/11/2026 08:00
"""

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
CORNER_SHOP["to_base"]["case"] = ("each", 24)  # config only: no function changed
rows_2, log_2 = clean_rows(SHOP_2, CORNER_SHOP)
print(dict(log_2), dict(totals_by_item(rows_2)))  # expect 2 cases x 24 = 48 each

# %% [markdown]
# ## Recap
#
# - **Custom** code encodes one customer's decision. **Core** code serves many customers and takes their rules as config.
# - A **refactor** keeps behaviour: check old against new on the same input, and explain every difference.
# - Refuse and count the rows you cannot read. Never guess a format or a unit.
# - The second customer should cost a config, not a copy. Send the pattern back as a field note.
# - Words to keep: **custom**, **core**, **config**, **refactor**, **characterisation check** (all in the glossary).
#
# **Interview:** "A second customer wants a feature only they need. Custom or core?" Strong answer: "I ask whether another customer needs the same mechanism. If so it goes in core, and their rules go in config. If it is only their decision, it stays custom behind one function, and I do not fork the core for them. I write the decision down so product can review it."

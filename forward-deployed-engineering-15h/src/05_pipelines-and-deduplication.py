# %% [markdown]
# # 05 · Ingesting customer data: files, pipelines and deduplication
#
# Level L1 · Part 1 · core · ~25 min · builds on lesson 04

# %% [markdown]
# ## Goal
#
# By the end of this lesson you can load a messy customer export, clean it in named steps (text, units, dates, duplicates), refuse to guess when a row is unclear, and write a file in one format that the customer's system can read.

# %% [markdown]
# ## Why it matters
#
# Basket Bazaar's ops team sends one export of **order lines** every night: one row per item in an order, with the order id, store, item, quantity, unit and time. The export is **invented**: Basket Bazaar is a fictional grocery delivery app, and the file was generated with a fixed seed, so it holds no real customer data. It has the faults a real export has: exact copies, copies with extra spaces and capitals, quantities in `dozen` and `kg`, and two date formats. Every later lesson reads the cleaned file this lesson writes.
#
# Without a pipeline, the first script prints a clean-looking answer that is wrong. Run it:

# %%
import csv
import logging
from collections import Counter  # counts per value: a value not seen yet starts at 0
from datetime import datetime
from pathlib import Path

DATA = Path("../data/05")  # this lesson's folder
RAW = DATA / "orders.csv"  # the export as the ops team sends it
with RAW.open(newline="") as f:
    rows = list(csv.DictReader(f))  # every value stays text: nothing is converted yet
eggs = sum(int(r["qty"]) for r in rows if r["item"] == "eggs")  # 2 dozen counts as 2 eggs here
print("order lines:", len(rows), "| eggs, naive sum of qty:", eggs)
print("orders, naive count of order_id:", len({r["order_id"] for r in rows}))

# %% [markdown]
# The script raises no error. Both numbers are wrong. A `qty` of 2 in `dozen` means 24 eggs, not 2. The copies are counted twice. The order id ` bb-1002 ` (lowercase, with spaces) is a different text from `BB-1002`, so one order counts as two. The pipeline below gives the real numbers: 864 eggs (in each) and 120 orders.

# %% [markdown]
# ## The idea
#
# **Ingestion** is getting a customer's data into your system. A **pipeline** does it in fixed steps. The shape is **ETL**: **extract** (read the file), **transform** (fix text, units and dates, drop duplicates) and **load** (write a clean file). Each step is small, so a failure points at one step.
#
# A **stable key** names one real thing the same way in every export. This export has no line id, so the key is the whole cleaned line: order, store, item, quantity, unit and time. Two lines that match on every column are one line. **Deduplication** keeps one row per key. Analogy: a receiving desk checks each delivery, converts it to one standard unit and logs it. A line listed twice on the delivery note is counted once.

# %% [markdown]
# ## Picture
#
# Each box is one step. The raw file goes in one end and one clean file comes out.

# %% [markdown]
# ```mermaid
# flowchart LR
#     A[Raw CSV<br/>copies, spaces, dozen and kg, two date formats] --> B[Normalise text<br/>trim spaces, fix case]
#     B --> C[Convert units<br/>to each and g]
#     C --> D[Parse dates<br/>two explicit formats]
#     D --> E[Dedupe by key<br/>the whole cleaned line]
#     E --> F[Clean CSV<br/>base units, ISO dates]
# ```

# %% [markdown]
# ## Step by step

# %% [markdown]
# ### Step 1: read the file as text and peek at it
#
# Read every value as text first. Then look at the first lines and count the units and date formats before you trust any count.

# %%
for line in RAW.read_text().splitlines()[:5]:  # the header and four lines, exactly as they are in the file
    print(line)
print("units:", dict(Counter(r["unit"] for r in rows)))
print("day-first dates:", sum("/" in r["ordered_at"] for r in rows), "| ISO dates:", sum("-" in r["ordered_at"] for r in rows))

# %% [markdown]
# ### Step 2: normalise the text and convert the units
#
# Trim the spaces and fix the case of the key and the item. Then convert each quantity to the base unit: `each` for counts, `g` for weight. `dozen` is 12 each and `kg` is 1000 g. A unit the table does not know raises a `KeyError`. It is never guessed.

# %%
BASE = {"each": ("each", 1), "dozen": ("each", 12), "g": ("g", 1), "kg": ("g", 1000)}  # unit: (base unit, factor)
COLUMNS = ["order_id", "store", "item", "qty_base", "unit_base", "ordered_at"]


def normalise(rows):
    """Trim spaces, fix case and convert each quantity to its base unit."""
    out = []
    for r in rows:
        unit, factor = BASE[r["unit"].strip().lower()]  # an unknown unit raises KeyError
        out.append({"order_id": r["order_id"].strip().upper(), "store": r["store"].strip(),
                    "item": r["item"].strip().lower(), "qty_base": int(r["qty"]) * factor,
                    "unit_base": unit, "ordered_at": r["ordered_at"].strip()})
    return out


print("rows converted to a base unit:", sum(BASE[r["unit"]][1] != 1 for r in rows))
print(normalise(rows[:1]))

# %% [markdown]
# ### Step 3: parse the two date formats
#
# The export uses `2026-10-22 01:24` and `22/10/2026 01:24`. Try each format on its own. A date that matches neither becomes `None`. Never let a tool guess: `10/11/2026` could be October or November. Here the day-first format is the one the customer's tool writes.

# %%
DATE_FORMATS = ("%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M")  # the two formats this export uses


def parse_when(text):
    """Return the ISO time for a date in either known format, or None when neither matches."""
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%dT%H:%M")
        except ValueError:
            pass  # not this format: try the next one
    return None


print(parse_when("22/10/2026 01:24"), parse_when("2026-10-22 01:24"), parse_when("31-02-2026 01:24"))


def parse_dates(rows):
    """Replace each date with its ISO time. A date that matches neither format becomes '' (unplaceable)."""
    return [{**r, "ordered_at": parse_when(r["ordered_at"]) or ""} for r in rows]

# %% [markdown]
# ### Step 4: deduplicate by the key
#
# Keep the first line for each key. Only exact matches on the cleaned columns are copies, so two lines that share an order but differ in quantity are both kept.

# %%
def dedupe(rows):
    """Keep the first row for each key: the whole cleaned line."""
    seen, kept = set(), []
    for r in rows:
        key = tuple(r.values())
        if key not in seen:
            seen.add(key)
            kept.append(r)
    return kept

# %% [markdown]
# ### Step 5: run the pipeline, count what was removed, and apply the unplaceable rule
#
# A date that matches neither format is **unplaceable**. It is never guessed. It is kept with an empty date, so it still shows in the counts. The run stops only when the count is over `MAX_UNPLACEABLE` (2, agreed with the customer). The function logs the rows in and out of each step, and it counts the removed copies in two groups: lines identical in the raw file, and lines that are copies only after the trimming and case fix.

# %%
MAX_UNPLACEABLE = 2  # more unplaceable dates than this stops the run
logging.basicConfig(level=logging.INFO, format="%(message)s", force=True)
log = logging.getLogger("pipeline")


def run_step(name, step, rows):
    log.info("%-11s %4d rows in", name, len(rows))
    out = step(rows)
    log.info("%-11s %4d rows out", name, len(out))
    return out


def run_pipeline(raw):
    rows = run_step("normalise", normalise, raw)
    rows = run_step("parse dates", parse_dates, rows)
    unplaceable = sum(r["ordered_at"] == "" for r in rows)
    print(f"unplaceable dates: {unplaceable} (limit {MAX_UNPLACEABLE})")
    if unplaceable > MAX_UNPLACEABLE:
        raise ValueError(f"{unplaceable} dates matched neither format: over the limit of {MAX_UNPLACEABLE}")
    clean = run_step("dedupe", dedupe, rows)
    identical = len(raw) - len({tuple(r.values()) for r in raw})  # copies identical in the raw file
    print(f"rows in: {len(raw)} | rows out: {len(clean)} | removed: {len(raw) - len(clean)} "
          f"({identical} identical lines, {len(raw) - len(clean) - identical} copies after trimming and case)")
    return clean


# The limit in action: two unplaceable dates are kept with an empty date ...
two_bad = [dict(r) for r in rows[:3]]
two_bad[0]["ordered_at"] = two_bad[1]["ordered_at"] = "31-02-2026 10:00"  # matches neither format
print([r["ordered_at"] for r in run_pipeline(two_bad)])

# %% [markdown]
# Three unplaceable dates are over the limit, so the run stops and names the count:

# %% tags=["raises-exception"]
# Three bad dates: over the limit of 2, so the run stops.
three_bad = [dict(r) for r in rows[:4]]
for r in three_bad[:3]:
    r["ordered_at"] = "31-02-2026 10:00"  # matches neither format
run_pipeline(three_bad)

# %% [markdown]
# ### Step 6: run on the real export, check, and write the file for the next lessons
#
# The checks come first: no line appears twice and every quantity has a base unit. A failed check stops the notebook here. The file keeps the same six columns, with ISO dates, and lessons 06, 09, 11, 19, 23, 24 and 24a read it.

# %%
clean = run_pipeline(rows)
assert len({tuple(r.values()) for r in clean}) == len(clean), "a duplicate survived"
assert all(r["unit_base"] in {"each", "g"} for r in clean), "a unit was not converted"
with (DATA / "orders_clean.csv").open("w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=COLUMNS)
    writer.writeheader()
    writer.writerows(clean)
print("clean lines:", len(clean), "| distinct orders:", len({r["order_id"] for r in clean}))
print("eggs, clean total in each:", sum(int(r["qty_base"]) for r in clean if r["item"] == "eggs"))
for line in (DATA / "orders_clean.csv").read_text().splitlines()[:4]:
    print(line)

# %% [markdown]
# ## Under the hood
#
# Deduplication is a loop with a set. The set remembers the keys already kept. Write it once by hand to see what a library's drop-duplicates does. Hand-written because interviewers ask you to write dedupe (about 12 lines); in real work use a library's drop-duplicates. Check that both give the same count.

# %%
def dedupe_by_hand(rows, key):
    """Keep the first row seen for each key. A set remembers the keys kept so far."""
    seen, kept = set(), []
    for row in rows:
        k = key(row)
        if k not in seen:
            seen.add(k)
            kept.append(row)
    return kept


by_hand = dedupe_by_hand(normalise(rows), key=lambda r: tuple(r.values()))
print("by hand:", len(by_hand), "| pipeline:", len(clean))
assert len(by_hand) == len(clean)

# %% [markdown]
# The set holds one key per kept row, so memory grows with the file. For a few thousand rows that is nothing. For a file too big for memory, sort it by key and keep one row per run, or let the customer's warehouse do the merge.

# %% [markdown]
# ## At work
#
# - Event senders such as Stripe can deliver the same event twice. The receiver keeps one copy per event ID (Stripe webhook docs: https://docs.stripe.com/webhooks). This lesson applies the same rule, a stable key, to a file. → lesson 04 covers the write-side version, the idempotency key.
# - Exports drift: a new column, a new date format or a new unit after a tool upgrade. A pipeline that stops on an unknown value is safer than one that guesses. The stops in Step 5 and Common mistakes show two such stops. → lesson 11 turns checks like these into an eval set.
# - Customers often send Excel as well as CSV. Excel needs a reader library such as openpyxl (in this course's requirements), and the same rules apply. → lesson 14 packages a job like this for the customer's environment.

# %% [markdown]
# ## Common mistakes
#
# - **One date format for every row.** The first day-first row stops the run. Here the format is ISO only, and the error prints:

# %% tags=["raises-exception"]
# Wrong: one format for every row. The first day-first row does not match and the run stops.
for row in rows:
    datetime.strptime(row["ordered_at"], "%Y-%m-%d %H:%M")

# %% [markdown]
# The fix is Step 3: try each known format on its own, and count what matches neither.
#
# - **Deduplicating before normalising.** `BB-1002` and ` bb-1002 ` look different to a raw comparison, so the copy survives. The removed count below is 8 too small. Normalise first (Step 2), then deduplicate.

# %%
# Wrong: deduplicate the raw lines. Only the 15 identical lines go; the 8 copies with spaces and case stay.
print("removed by raw dedupe:", len(rows) - len(dedupe(rows)), "| right answer:", len(rows) - len(clean))

# %% [markdown]
# ## Try it
#
# The function below should count the distinct orders in the raw export. It skips the cleaning step, so it counts order ids that differ only in spaces or case. Fix it so the number matches the clean file.

# %%
# your code here
def count_orders(rows):
    """Count the distinct orders in the raw export. It must match the clean file."""
    return len({r["order_id"] for r in rows})


print("distinct orders:", count_orders(rows), "| clean file:", len({r["order_id"] for r in clean}))

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
# The bug: 128 spellings of the order id, but 120 orders. Trim and fix the case first, as Step 2 does.
def count_orders(rows):
    """Count the distinct orders in the raw export. It must match the clean file."""
    return len({r["order_id"].strip().upper() for r in rows})


print("distinct orders:", count_orders(rows), "| clean file:", len({r["order_id"] for r in clean}))

# %% [markdown]
# ## Recap
#
# - Read everything as text, then convert each column on purpose. Never let a tool guess.
# - A pipeline is small named steps. Log the rows in and out of each one.
# - A stable key names one real thing the same way in every export. Normalise it before you compare.
# - An unplaceable date is counted and kept empty. The run stops only over the agreed limit.
# - Words to keep: **ingestion**, **pipeline**, **ETL**, **stable key**, **deduplication**, **unplaceable**.
#
# **Interview:** "A customer sends a nightly CSV with duplicate rows, two date formats and units that differ by row. How do you turn it into reliable data?" Strong answer: "I load everything as text, normalise the key columns and convert each quantity to one base unit, parse each date format explicitly and count what fails, and deduplicate by a stable key. I stop when the failures pass the agreed limit, and I count rows in and out."

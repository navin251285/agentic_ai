# %% [markdown]
# # 06 · A customer workflow with structured output and tool calling
#
# Level L1 · Part 1 · core · ~30 min · builds on lesson 04

# %% [markdown]
# ## Goal
#
# By the end of this lesson you can turn a customer's free-text message into a checked record. A model fills a Pydantic form, a tool looks up the order, and a check rejects a record that names an order that does not exist. You can also say, in one sentence, when a model is the wrong tool.

# %% [markdown]
# ## Why it matters
#
# Customers write messages like "only three of my four milks came". The support team needs the same facts from every message: which order, what went wrong, which item and how many. Without a model you write keyword rules, and the rules miss real wording. The cell below runs one rule on two messages. Both messages are **invented** for Basket Bazaar, a fictional grocery delivery app.

# %% [markdown]
# The first code cell sets up the recording for the model calls later in this lesson. It is plain setup: no model is called here.

# %%
import sys
sys.path.insert(0, "..")  # lets the notebook import llm_setup.py and llm_replay.py
import llm_replay
# Without a key, the saved recording is replayed, so the outputs below still appear.
llm_replay.start("06_structured-output-and-tool-calling")  # records the model calls below once

# %% [markdown]
# The rule finds the issue word and the order number. Run it on both messages.

# %%
import re

messages = [
    "Order BB-1108: the milk is missing from my delivery. Can I get a credit?",
    "Order BB-1108: only three of the four milks made it into the bag.",
]
for text in messages:
    issue = "missing_item" if "missing" in text.lower() else "other"
    order = re.search(r"BB-\d+", text)
    print(f"keyword rule -> issue={issue!r}, order={order.group() if order else None}")

# %% [markdown]
# The second message is the same problem, but it has no word 'missing', so the rule files it as 'other'.
#
# - **Without it:** keyword rules, a pattern per issue type, and a person retyping the rest. Each new wording is a new bug, and nobody sees it fail.
# - **With it:** a model reads the message and fills one fixed form (**structured output**). It asks a **tool** for the order's facts instead of recalling them. Plain code checks the form before a case is opened.
# - **When you don't need it:** when the customer picks an issue from a dropdown and types the order number into a box, the data is already structured. Use code for that.

# %% [markdown]
# ## The idea
#
# **Structured output** means the model answers in a shape you define, here a Pydantic class, not free text. **Tool calling** lets the model ask your code to run a function (here `lookup_order`) with arguments the model picks. Your code runs it and sends back the result. The model never touches the order system itself. A **check** is plain code that runs after the model and does not trust the form. Analogy: a call-centre agent fills in a claim form and asks the warehouse desk for the order. A supervisor compares the form with the order before any money moves.
#
# **When a model is the wrong tool:** when the answer is one correct value you can compute or look up by its key (an order's line count, store or total), use code, and keep the model only for reading messy wording into a form that code then checks.

# %% [markdown]
# ## Picture
#
# The model reads the message and asks for the order. The check decides whether the case opens.

# %% [markdown]
# ```mermaid
# flowchart LR
#     M[Customer message] --> L[Model reads it]
#     L -- tool call: lookup_order --> T[Our code reads the orders file]
#     T -- order lines --> L
#     L -- structured output --> R[CaseRecord]
#     R --> C{Check: order exists, item and qty fit?}
#     C -- yes --> OK[Case opens for the agent]
#     C -- no --> NO[Rejected: a person reviews]
# ```

# %% [markdown]
# ## Step by step

# %% [markdown]
# ### Step 1: the message and the orders file
#
# The message is invented. The orders file is the one lesson 05 cleaned: one row per order and item, with a single unit per row. It is invented too, with no real customer data. Read it into a dictionary keyed by order number.

# %%
import csv
from pathlib import Path

ORDERS_FILE = Path("../data/05/orders_clean.csv")  # written by lesson 05 (invented data)
CUSTOMER_MESSAGE = ("Hi, I'm writing about order BB-1108. The delivery came today "
                    "but the milk is missing. I paid for four. Can I get a credit?")

ORDERS: dict[str, list[dict]] = {}
with ORDERS_FILE.open(newline="") as f:
    for row in csv.DictReader(f):
        ORDERS.setdefault(row["order_id"], []).append(row)

print("customer message (invented):", CUSTOMER_MESSAGE)
print("orders loaded:", len(ORDERS), "| lines for BB-1108:", ORDERS["BB-1108"])

# %% [markdown]
# ### Step 2: the form the model must fill
#
# A Pydantic class is the schema. The `Field` descriptions are sent to the model, so they are part of the instructions. `Literal` limits `issue` to five values. The triage labels come from the delivery-message triage (scoped in lesson 03, built in lesson 20): four issues (`missing_item`, `late`, `damaged`, `wrong_item`), plus `other` for a message that fits none of them. The order export has no labels, so the lesson 05 file is not the source here.

# %%
from typing import Literal

from pydantic import BaseModel, Field


class CaseRecord(BaseModel):
    """One support case, filled from a customer message. The fields are for this lab only."""
    order_id: str = Field(description="the order number as written, such as BB-1108")
    issue: Literal["missing_item", "wrong_item", "late", "damaged", "other"]
    item: str | None = Field(default=None, description="the item the customer names, in lower case, or null")
    qty_claimed: int | None = Field(default=None, description="how many of that item the customer says they paid for, or null")
    summary: str = Field(description="one short sentence for the support agent")


print("fields the model must fill:", list(CaseRecord.model_fields))

# %% [markdown]
# ### Step 3: the tool
#
# A tool is a Python function with a docstring. LangChain sends the name, the arguments and the docstring to the model. The model reads the docstring to decide when to call it. The function reads the orders file, so the model never has to remember an order.

# %%
import json

from langchain_core.tools import tool


@tool
def lookup_order(order_id: str) -> str:
    """Look up one Basket Bazaar order by its order number, such as BB-1108. Returns its lines as JSON, or says it is not found."""
    lines = ORDERS.get(order_id)
    return json.dumps(lines) if lines else f"order {order_id} not found"


print(lookup_order.invoke({"order_id": "BB-1108"}))
print(lookup_order.invoke({"order_id": "BB-9999"}))

# %% [markdown]
# ### Step 4: model call 1 of 2, the model asks for the order
#
# The model gets the message and the tool. It does not fill the form yet. It returns a tool call: a name and arguments, which our code will run.

# %% tags=["needs-llm"]
# langchain-google-genai 4.4.2: bind_tools, with_structured_output(method='json_schema'), ToolMessage verified against this version
from llm_setup import get_llm

SYSTEM = "You help Basket Bazaar's support team. Look up the order when the message gives an order number."
llm = get_llm()
asked = [("system", SYSTEM), ("human", CUSTOMER_MESSAGE)]
first = llm.bind_tools([lookup_order]).invoke(asked)
print("model asked for:", [(c["name"], c["args"]) for c in first.tool_calls])

# %% [markdown]
# ### Step 5: model call 2 of 2, the model fills the form
#
# Our code runs the tool and sends the result back as a `ToolMessage`. Then the model fills the `CaseRecord` form. `method="json_schema"` asks for JSON that matches the class. Pydantic checks the reply before it reaches us. Call 1 can only ask for a tool. Call 2 sees the tool's answer and writes the form. The two jobs are kept separate.

# %% tags=["needs-llm"]
from langchain_core.messages import ToolMessage

call = first.tool_calls[0]
result = lookup_order.invoke(call["args"])
print("tool result:", result)

history = asked + [first, ToolMessage(content=result, tool_call_id=call["id"])]
form = llm.with_structured_output(CaseRecord, method="json_schema")
record = form.invoke(history + [("human", "Fill the case record from the message and the lookup result.")])
print(record.model_dump_json(indent=2))

# %% [markdown]
# ### Step 6: the check, in plain code
#
# The check does not ask the model anything. It compares the record with the orders file: the order must exist, the item must be on it, and the claimed quantity cannot be more than the order holds. Quantities are compared only for `each` lines, so the units match.

# %%
def check_record(rec: CaseRecord) -> list[str]:
    """Rules a model's form must pass before a case opens. Returns the problems (empty list = passed)."""
    lines = ORDERS.get(rec.order_id)
    if not lines:
        return [f"order {rec.order_id} is not in the orders export"]
    problems = []
    # Item matching is exact, so it depends on the model writing the item in lower case, as the Field description asks.
    if rec.item and rec.item not in {line["item"] for line in lines}:
        problems.append(f"{rec.item} is not on order {rec.order_id}")
    if rec.issue == "missing_item" and not rec.item:
        problems.append("a missing-item case must name the item")
    for line in lines:
        # qty_claimed is checked only for 'each' lines. Grams and similar lines are skipped on purpose: their units differ.
        if rec.item == line["item"] and rec.qty_claimed is not None and line["unit_base"] == "each":
            if rec.qty_claimed > int(line["qty_base"]):
                problems.append(f"claims {rec.qty_claimed} {rec.item}, the order has {line['qty_base']}")
    return problems


if "record" in globals():
    print("check on the model's record:", check_record(record) or "passed: the case can open")
else:
    print("model step skipped (no recording and no key), so the check runs on the test cases below")

# %% [markdown]
# ### Step 7: test the check on bad records
#
# These three records are written by hand, on purpose, to test the check. They are **not** model output. A real model can make the same mistakes: an order number it invented, a missing-item case with no item, or a quantity above the order.

# %%
bad_cases = [
    CaseRecord(order_id="BB-9999", issue="late", summary="test: an order number that does not exist"),
    CaseRecord(order_id="BB-1108", issue="missing_item", summary="test: no item named"),
    CaseRecord(order_id="BB-1108", issue="missing_item", item="milk", qty_claimed=9, summary="test: too many"),
]
for case in bad_cases:
    print(case.order_id, "->", check_record(case) or "passed")

# %% [markdown]
# ## At work
#
# - Teams that connect a model to order or ticket systems keep the model's answer in a typed schema and validate it before any action. Pydantic is the validation layer most current LLM SDKs and FastAPI use (https://pypi.org/project/pydantic/). The OWASP LLM Top 10 (2025) lists improper output handling as a risk: model output used without checks (https://genai.owasp.org). → lesson 19 adds tools that take actions, and the guardrails around them.
# - A check like Step 6 is the first test you write. Lesson 11 builds an eval set from real failures, so you can see how often records fail and why, not just that one example failed.
# - Each model call costs money and time. Teams code the lookup and keep the model for reading wording. → lesson 18 measures the cost and latency of these calls.
#
# Go deeper: how an agent repeats tool calls in a loop is lesson 19.

# %% [markdown]
# ## Common mistakes
#
# - **Trusting a form because it has the right shape.** Pydantic checks types, not facts. A wrong type is refused at once, as this cell shows. The `issue` value `lost` is not in the list, and `qty_claimed` is text, not a number.

# %% tags=["raises-exception"]
CaseRecord(order_id="BB-1108", issue="lost", qty_claimed="four", summary="test")

# %% [markdown]
# The fix is the type and the list in Step 2. Types catch the first kind of error. The check in Step 6 catches the second kind: a well-formed record about an order that does not exist.
#
# - **Letting the model recall the order.** It may say the order has four milks when the file says otherwise. Look the order up with the tool, and check the answer against the file. The check in Step 6 then rejects a quantity above the order, as this cell shows.

# %%
print(check_record(CaseRecord(order_id="BB-1108", issue="missing_item", item="milk", qty_claimed=9, summary="test")))

# %% [markdown]
# ## Try it
#
# Write a new function `check_quantity`. It stands alone, so you do not need to change `check_record`. Its rule: a missing-item claim cannot say the customer paid for zero of the item. Return a list of problems, as `check_record` does. The stub prints None until you replace `...`. Then test it on the record below.

# %%
# your code here
def check_quantity(rec: CaseRecord) -> list[str]:
    """Reject a missing-item claim that says zero of the item was paid for."""
    ...  # write the rule


test = CaseRecord(order_id="BB-1108", issue="missing_item", item="milk", qty_claimed=0, summary="test")
print(check_quantity(test))

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
def check_quantity(rec: CaseRecord) -> list[str]:
    """Reject a missing-item claim that says zero of the item was paid for."""
    if rec.issue == "missing_item" and rec.qty_claimed == 0:
        return [f"a missing-item case cannot claim zero {rec.item}"]
    return []


test = CaseRecord(order_id="BB-1108", issue="missing_item", item="milk", qty_claimed=0, summary="test")
print(check_quantity(test))

# %% [markdown]
# ## Recap
#
# - A model can fill a fixed form (structured output). Pydantic defines the form and refuses a wrong type.
# - Tool calling lets the model ask our code for facts, such as an order's lines. The model does not query the system itself.
# - Plain code checks every record against the source before any action. A well-formed record can still be wrong.
# - Use code for any answer you can look up or compute. Use the model only to read messy wording.
# - Words to keep: **structured output**, **tool calling**, **schema**, **check** (all in GLOSSARY.md).
#
# **Interview:** "A model turns customer messages into refund cases. How do you stop an order number it made up from reaching the refund system?" Strong answer: "A typed schema, a tool that looks the order up, and a code check that rejects unknown orders before any action. Then I measure the reject rate on an eval set."

# %%
llm_replay.stop()  # saves the recording of the two model calls

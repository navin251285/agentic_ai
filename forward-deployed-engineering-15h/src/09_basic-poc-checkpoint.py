# %% [markdown]
# # 09 · Checkpoint: a working proof of concept for one customer workflow
#
# Level L1 · Part 1 · core · ~30 min · builds on lessons 04, 05, 06, 07

# %% [markdown]
# ## Goal
#
# By the end of this checkpoint you have run one Basket Bazaar workflow from end to end against the mock customer API. A customer message becomes a checked case. The case writes one credit, once, even when the reply is lost. A one-page status update shows the result to a non-engineer, with every number labelled.

# %% [markdown]
# ## Why it matters
#
# Lessons 04 to 07 each work alone. The API client reads pages, the pipeline cleans a file, the model fills a form and the status page explains progress. A proof of concept is only useful when the four pieces run together on one case.
#
# - **Without this checkpoint:** the four scripts never meet. The first live run finds the gaps: one page read as the whole list, a made-up order number, a credit written twice after a dropped reply, and a demo that shows one lucky record.
# - **With it:** one run, five checks (the requirements below, each with the cell that checks it), and one page for the ops lead that says what was measured and what was not.
# - **When you don't need it:** never skip it before a customer sees the work. Only a throwaway test skips the end-to-end run.

# %% [markdown]
# ## The idea
#
# A **proof of concept** is a thin slice of the real job: one workflow, real inputs, every step checked. Think of a test flight on one route with one passenger, before the airline sells seats on every route. The slice is thin on purpose. It proves the path works. It does not prove the rate, and the status page says so.
#
# Here is the path. The mock customer API and the cleaned orders file are the only sources. The model reads the message, the code checks it, and only then is a credit written.

# %% [markdown]
# ```mermaid
# flowchart LR
#     F[Cleaned orders file, lesson 05] --> A[Customer API: read every line, lesson 04]
#     M[Customer message] --> L[Model fills CaseRecord, lesson 06, requirement 2]
#     L --> C{Check against the API lines}
#     A --> C
#     C -- passes --> K[Credit written once, with an idempotency key, lesson 04]
#     C -- fails --> H[Held for a person]
#     K --> S[Status update for the ops lead, lesson 07]
#     H --> S
# ```

# %% [markdown]
# ## Requirements
#
# Your checkpoint is done when all five hold:
#
# 1. Every order line the customer's API holds is read, and the count matches the API's `total` and the file (lesson 04).
# 2. The model turns the customer's message into a `CaseRecord` form, with a tool call and structured output (lesson 06).
# 3. Plain code checks the record against the API's lines before any action. A case that fails the check is held, not credited (lesson 06).
# 4. A passing case writes one credit with an idempotency key. A lost reply does not write it twice (lesson 04).
# 5. A one-page status update names the decision, its owner and its day, and labels every number as measured, guess or invented (lesson 07).
#
# Checked in: 1 hidden cell 22, 2 Step 3, 3 Step 4, 4 Build it 2, 5 Build it 3.
#
# Only the model cannot be checked by counting. Use code for the rest.

# %% [markdown]
# ## Build it

# %%
import sys
sys.path.insert(0, "..")  # lets the notebook import llm_setup.py and llm_replay.py
import llm_replay
llm_replay.start("09_basic-poc-checkpoint")  # records the model calls below once; replays them without a key

# %% [markdown]
# ### Setup: the invented orders file
#
# The data is the cleaned orders file from lesson 05: 120 invented orders in 224 lines, one row per order and item. It was made by lesson 05's code with a fixed random seed, so it holds no real customer data. The mock customer API serves these lines. Peek at the first rows before you use them.

# %%
from pathlib import Path
import csv

ORDERS_CSV = Path("../data/05/orders_clean.csv").resolve()
if not ORDERS_CSV.exists():
    raise FileNotFoundError("run lesson 05 first: it writes the cleaned orders file")
with ORDERS_CSV.open(newline="") as f:
    FILE_ROWS = list(csv.DictReader(f))
print("file lines:", len(FILE_ROWS), "| orders:", len({r["order_id"] for r in FILE_ROWS}), "(invented)")
for line in ORDERS_CSV.read_text().splitlines()[:3]:
    print(line)

# %% [markdown]
# ### Setup: write the mock customer API
#
# The mock is a real HTTP server. The next cell writes its code to `../apps/09/mock_erp.py`. It serves the invented lines from the file above and stands in for a customer's order system. The `/lab/` paths are lab controls only.

# %%
%%writefile ../apps/09/mock_erp.py
"""Basket Bazaar mock customer API for the checkpoint (lesson 09). INVENTED data, lab only.

It serves the cleaned order lines from lesson 05 and keeps the credits it receives.
The /lab/ endpoints exist only for this course: a real customer API has none of them.
"""
import csv
import os
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

TOKEN = os.environ.get("MOCK_ERP_TOKEN", "")
ORDERS = Path(__file__).resolve().parents[2] / "data" / "05" / "orders_clean.csv"  # lesson 05's file
with ORDERS.open(newline="") as f:
    LINES = list(csv.DictReader(f))  # one row per order line, as lesson 05 wrote it
CREDITS: list[dict] = []
SAVED: dict[str, dict] = {}   # Idempotency-Key -> the body first returned for it
FAULTS: list[str] = []        # next calls: "429", "503", or "lost" (written, reply lost)

app = FastAPI(title="Basket Bazaar mock customer API (invented, lesson 09)")


class Credit(BaseModel):
    order_id: str
    item: str
    qty: int = Field(ge=1)


class Plan(BaseModel):
    faults: list[str]


def require_token(authorization: str | None = Header(default=None)):
    if authorization != f"Bearer {TOKEN}":
        raise HTTPException(401, "missing or wrong bearer token")


def error(code: int) -> JSONResponse:
    headers = {"Retry-After": "1"} if code == 429 else {}
    return JSONResponse({"detail": f"injected {code}"}, status_code=code, headers=headers)


def next_fault() -> str | None:
    return FAULTS.pop(0) if FAULTS else None


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/orders", dependencies=[Depends(require_token)])
def list_lines(limit: int = Query(20, ge=1, le=50), cursor: str = "0"):
    fault = next_fault()
    if fault in ("429", "503"):
        return error(int(fault))
    start, end = int(cursor), int(cursor) + limit
    more = end < len(LINES)
    return {"data": LINES[start:end], "has_more": more,
            "next_cursor": str(end) if more else None, "total": len(LINES)}


@app.post("/credits", dependencies=[Depends(require_token)])
def create_credit(credit: Credit, response: Response, idempotency_key: str | None = Header(default=None)):
    if idempotency_key and idempotency_key in SAVED:  # a repeat: return the first answer, write nothing
        response.headers["Idempotent-Replayed"] = "true"
        return SAVED[idempotency_key]
    fault = next_fault()
    if fault in ("429", "503"):  # rejected before any write
        return error(int(fault))
    CREDITS.append(credit.model_dump())
    body = {"credit_id": f"CR-{len(CREDITS)}", **credit.model_dump()}
    if idempotency_key:
        SAVED[idempotency_key] = body
    if fault == "lost":  # written, but the reply is lost on the way back
        return error(503)
    return body


@app.post("/lab/faults")
def set_faults(plan: Plan):  # lab only
    FAULTS[:] = plan.faults
    return {"queued": len(FAULTS)}


@app.post("/lab/reset")
def reset():  # lab only: empty the credits and the saved answers
    CREDITS.clear()
    SAVED.clear()
    FAULTS.clear()
    return {"ok": True}


@app.get("/lab/state")
def state():  # lab only: what the customer's system holds right now
    return {"credits": CREDITS}

# %% [markdown]
# ### Setup: start the mock and wait until it answers
#
# The mock runs in its own process on this checkpoint's port (8090). The token comes from `.env`; the default is a lab value. The server is stopped at the end.

# %%
import atexit, os, socket, subprocess, sys, time

import httpx

from tut_env import env

PORT = 8090  # this checkpoint's port (progress.py --ports 09)
BASE = f"http://127.0.0.1:{PORT}"
os.environ["MOCK_ERP_TOKEN"] = env("MOCK_ERP_TOKEN", "lab-token-not-a-secret")  # exported, never printed

with socket.socket() as probe:
    if probe.connect_ex(("127.0.0.1", PORT)) == 0:
        raise RuntimeError(f"port {PORT} is already in use: stop the other process first")

server = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "mock_erp:app", "--app-dir", os.path.abspath("../apps/09"),
     "--port", str(PORT), "--log-level", "warning"])
_ = atexit.register(server.terminate)  # also stops the server if the kernel exits early
print("mock customer API started on port", PORT, "| token set from .env (not printed)")

# %% [markdown]
# Wait until the server answers `/health`, then open a client that sends the token on every call. The token is never printed.

# %%
def wait_healthy(timeout=15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(f"{BASE}/health", timeout=0.5).status_code == 200:
                return True
        except httpx.TransportError:
            pass  # not listening yet
        time.sleep(0.2)
    return False


if not wait_healthy():
    raise RuntimeError("the mock customer API did not start")
client = httpx.Client(base_url=BASE, timeout=5.0,
                      headers={"Authorization": f"Bearer {os.environ['MOCK_ERP_TOKEN']}"})
print("mock customer API is up | token sent on every call (not printed)")

# %% [markdown]
# ### Build it 1: read every line from the customer's API
#
# Write `read_all_lines(client)`. It follows `next_cursor` until it is `None`, and it returns every line. The count must match the API's `total` and the file's row count. Use lesson 04's pagination. Retry only the failures that can succeed later. The answer below shows one way, with a retry helper called `send`.

# %%
# your code here
def read_all_lines(client):
    """Return every order line the customer's API holds."""
    return []  # stub: replace this body


lines = read_all_lines(client)
print("lines read:", len(lines), "| file has:", len(FILE_ROWS))

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential_jitter

RETRYABLE = {429, 502, 503, 504}  # a later try may succeed; a 400, 401 or 422 never will


def should_try_again(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRYABLE
    return isinstance(exc, httpx.TransportError)


def wait_policy(retry_state) -> float:
    exc = retry_state.outcome.exception()
    if isinstance(exc, httpx.HTTPStatusError) and "Retry-After" in exc.response.headers:
        return float(exc.response.headers["Retry-After"])  # obey the server when it says how long
    return wait_exponential_jitter(initial=0.2, max=5)(retry_state)


# %% [markdown]
# The reader below calls `send`, which tries again only for the codes above and waits as the server asks. The lab's fault queue (`/lab/faults`) is used in order: each request takes the next queued fault, and a request with nothing queued succeeds.

# %% tags=["solution"]
@retry(retry=retry_if_exception(should_try_again), wait=wait_policy,
       stop=stop_after_attempt(4), reraise=True)
def send(client, method, path, **kwargs):
    response = client.request(method, path, **kwargs)
    response.raise_for_status()
    return response


def read_all_lines(client):
    lines, cursor = [], "0"
    while cursor is not None:  # None means: that was the last page
        body = send(client, "GET", "/orders", params={"limit": 50, "cursor": cursor}).json()
        lines.extend(body["data"])
        cursor = body["next_cursor"]
    return lines


client.post("/lab/faults", json={"faults": ["429"]})  # the first page fails once; the retry recovers
lines = read_all_lines(client)
total = client.get("/orders", params={"limit": 1}).json()["total"]
assert len(lines) == len(FILE_ROWS) == total, "the API and the file disagree on the line count"
print("lines read:", len(lines), "| file:", len(FILE_ROWS), "| API total:", total, "(counts match)")

# %% [markdown]
# ### Step 2: the form the model fills
#
# The form and the lookup tool come from lesson 06. The tool reads the lines from step 1, so the model never has to remember an order.
# This step needs the lines from Build it 1. If your `read_all_lines` is not done, run its hidden answer cell first.

# %%
import json
from typing import Literal

from langchain_core.tools import tool
from pydantic import BaseModel, Field


class CaseRecord(BaseModel):
    """One support case, filled from a customer message (invented data, lab only)."""
    order_id: str = Field(description="the order number as written, such as BB-1108")
    issue: Literal["missing_item", "wrong_item", "late", "damaged", "other"]
    item: str | None = Field(default=None, description="the item the customer names, in lower case, or null")
    qty_claimed: int | None = Field(default=None, description="how many of that item the customer says they paid for, or null")
    summary: str = Field(description="one short sentence for the support agent")


LINES_BY_ORDER: dict[str, list[dict]] = {}
for line in lines:
    LINES_BY_ORDER.setdefault(line["order_id"], []).append(line)


@tool
def lookup_order(order_id: str) -> str:
    """Look up one Basket Bazaar order by its order number, such as BB-1108. Returns its lines as JSON, or says it is not found."""
    found = LINES_BY_ORDER.get(order_id)
    return json.dumps(found) if found else f"order {order_id} not found"


print(lookup_order.invoke({"order_id": "BB-1108"})[:120], "...")

# %% [markdown]
# ### Step 3: the model reads the message (2 model calls)
#
# This cell makes the only two model calls in the checkpoint. Call 1 asks for the order lookup. Call 2 fills the form, with the lookup's answer. The customer message is invented. It is the same message lesson 06 used. If the model cannot run here, the next cell uses a hand-written test case instead, and says so.
#
# The printed line `API key loaded: True` only says that a key is set in `.env`. In replay mode the two calls are answered from the saved recording, so this cell runs with no key.

# %% tags=["needs-llm"]
from llm_setup import get_llm

SYSTEM = "You help Basket Bazaar's support team. Look up the order when the message gives an order number."
MESSAGE = ("Hi, I'm writing about order BB-1108. The delivery came today "
           "but the milk is missing. I paid for four. Can I get a credit?")
llm = get_llm()
asked = [("system", SYSTEM), ("human", MESSAGE)]
first = llm.bind_tools([lookup_order]).invoke(asked)
print("model asked for:", [(c["name"], c["args"]) for c in first.tool_calls])

from langchain_core.messages import ToolMessage

call = first.tool_calls[0]
result = lookup_order.invoke(call["args"])
history = asked + [first, ToolMessage(content=result, tool_call_id=call["id"])]
form = llm.with_structured_output(CaseRecord, method="json_schema")
record = form.invoke(history + [("human", "Fill the case record from the message and the lookup result.")])
print(record.model_dump_json(indent=2))

# %% [markdown]
# ### If the model step was skipped
#
# No key and no recording means the model cell did not run. This cell then uses a hand-written test case, and says so on screen. It is not model output.

# %%
if "record" not in globals():  # the model cell was skipped: no recording and no key
    record = CaseRecord(order_id="BB-1108", issue="missing_item", item="milk", qty_claimed=4,
                        summary="hand-written test case, not model output")
    print("model step skipped: the checkpoint uses a hand-written test case (not model output)")
print("case record:", record.order_id, record.issue, record.item, record.qty_claimed)

# %% [markdown]
# ### Step 4: the check, in plain code
#
# The check does not ask the model anything. It compares the record with the customer's own lines. The order must exist, the item must be on it, and the claim cannot be more than the order holds. Quantities are compared only for `each` lines, so the units match.
#
# If your `read_all_lines` returned fewer than 224 lines, fix Build it 1 before going on: the check in this step needs all of them.
# Known gap of this proof of concept: a line in another unit is not compared, so a quantity claim on it passes silently. The answer cell below passes the global `lines` from Build it 1 into the check.

# %%
def check_record(rec: CaseRecord, lines: list[dict]) -> list[str]:
    """Plain code a model's form must pass before any credit. Returns the problems (empty list = passed)."""
    # known gap: quantities are compared only for 'each' lines; other units pass silently
    mine = [line for line in lines if line["order_id"] == rec.order_id]
    if not mine:
        return [f"order {rec.order_id} is not in the customer's API"]
    problems = []
    if rec.item and rec.item not in {line["item"] for line in mine}:
        problems.append(f"{rec.item} is not on order {rec.order_id}")
    if rec.issue == "missing_item" and not rec.item:
        problems.append("a missing-item case must name the item")
    if rec.issue == "missing_item" and not rec.qty_claimed:
        problems.append("a missing-item case must say how many were paid for")
    for line in mine:
        if rec.item == line["item"] and rec.qty_claimed and line["unit_base"] == "each":
            if rec.qty_claimed > int(line["qty_base"]):
                problems.append(f"claims {rec.qty_claimed} {rec.item}, the order has {line['qty_base']}")
    return problems


print("check on the case record:", check_record(record, lines) or "passed: the case can go on")

# %% [markdown]
# ### Build it 2: open the case and write one credit
#
# Write `open_case_and_credit(record, client)`. If the check fails, return `"held for a person"` with the problems and write nothing. If it passes, POST one credit with an **idempotency key** built from the order, the item and the order date. The key must stay the same on every retry of this one operation.
#
# This needs `send`, the retry helper in the Build it 1 answer. If you wrote your own retry, you can use it; otherwise run that hidden answer cell first.

# %%
# your code here
def open_case_and_credit(record, client):
    """Check the case; if it passes, write one credit with an idempotency key. Return what happened."""
    return {"decision": None}  # stub: replace this body


decision = open_case_and_credit(record, client)
print("decision:", decision)

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
def open_case_and_credit(record, client):
    """Check the case; if it passes, write one credit with an idempotency key. Return what happened."""
    problems = check_record(record, lines)
    if problems:
        return {"decision": "held for a person", "problems": problems}
    order_date = LINES_BY_ORDER[record.order_id][0]["ordered_at"][:10]
    key = f"credit-{record.order_id}-{record.item}-{order_date}"  # same operation, same key, every retry
    body = {"order_id": record.order_id, "item": record.item, "qty": record.qty_claimed}
    resp = send(client, "POST", "/credits", json=body, headers={"Idempotency-Key": key})
    return {"decision": "credit written", "credit_id": resp.json()["credit_id"],
            "replayed": resp.headers.get("Idempotent-Replayed")}

# %% [markdown]
# Now run the answer. The lab injects a lost reply **before** the call: the mock will write the credit and then return 503. `/lab/faults` is a lab control for this course. A real customer API has no such endpoint.

# %%
client.post("/lab/faults", json={"faults": ["lost"]})  # lab control: the write happens, then the reply is lost
decision = open_case_and_credit(record, client)
print("decision:", decision)
print("credits held by the customer:", len(client.get("/lab/state").json()["credits"]), "(one, even after the lost reply)")

# %% [markdown]
# What happened: the first POST wrote the credit and returned 503. The retry sent the same `Idempotency-Key`, so the server replayed the saved answer instead of writing again. That is why the output shows `replayed: 'true'`, and why the customer holds one credit.

# %% [markdown]
# ### Build it 3: the one-page status update
#
# Write `status_page(decision, n_api, n_file)`. It returns a dictionary with these keys, which the `render` helper below reads:
# `headline` (text), `where_we_are` (list of text), `what_we_know` (list of text), `decision` (`ask`, `owner`, `due`),
# `risks` (list of text), `open_question` (`question`, `owner`, `due`). Fill the numbers and labels from the arguments.
# Label every number as measured, guess or invented.

# %%
# your code here
def status_page(decision, n_api, n_file):
    """Return the one-page status update as a dictionary. Label every number."""
    return {"headline": "", "where_we_are": [], "what_we_know": [],
            "decision": {"ask": "", "owner": "", "due": ""}, "risks": [],
            "open_question": {"question": "", "owner": "", "due": ""}}  # stub: fill each key


page = status_page(decision, len(lines), len(FILE_ROWS))
print("page keys:", list(page))

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
def status_page(decision, n_api, n_file):
    """Return the one-page status update as a dictionary. Label every number."""
    credited = decision.get("decision") == "credit written"
    outcome = "one credit written (measured in the mock)" if credited else "held for a person (measured)"
    checked = "passed" if credited else "held"
    return {
        "headline": "Checkpoint, invented data: one missing-item message became a checked, keyed credit.",
        "where_we_are": [f"Read {n_api} order lines from the customer API (measured); the file has {n_file}, so the counts match",
                         f"One case ran end to end: model form, code check, {outcome}"],
        "what_we_know": [f"One case was checked and {checked} (measured on invented data); one case is not a rate",
                         "A lost reply did not write the credit twice (measured in the mock, not a real customer)"],
        "decision": {"ask": "Approve a pilot on one store's missing-item cases, using its real export", "owner": "ops lead", "due": "day 10"},
        "risks": ["The customer API here is a mock: real auth, rate limits and field names may differ"],
        "open_question": {"question": "Which store team sends the first real export?", "owner": "FDE", "due": "day 5"},
    }


# %% [markdown]
# ### Render the page as plain text
#
# A helper for the status page. It turns the dictionary into the text a non-engineer reads.

# %%
def render(s):
    lines_out = [s["headline"], "", "Where we are:"]
    lines_out += ["  - " + item for item in s["where_we_are"]]
    lines_out += ["", "What we know:"]
    lines_out += ["  - " + item for item in s["what_we_know"]]
    d = s["decision"]
    lines_out += ["", f"Decision needed: {d['ask']}. Owner: {d['owner']}. By: {d['due']}.", "Risks:"]
    lines_out += ["  - " + risk for risk in s["risks"]]
    q = s["open_question"]
    lines_out.append(f"Open question: {q['question']} Owner: {q['owner']}. By: {q['due']}.")
    return "\n".join(lines_out)


page = status_page(decision, len(lines), len(FILE_ROWS))
text = render(page)
print(text)
print("words:", len(text.split()), "| under 200:", len(text.split()) < 200,
      "| decision has owner and day:", bool(page["decision"]["owner"] and page["decision"]["due"]))

# %% [markdown]
# ## Reference solution
#
# One run from a clean mock, in order: read the lines, open the case, write the status page. The mock queues a 429 on the first read. Build it 2 queues its own lost reply on the credit. The checks at the end must still hold. Compare it with your three steps.

# %% tags=["solution"]
client.post("/lab/reset")  # the customer's system starts empty again
client.post("/lab/faults", json={"faults": ["429"]})  # the first read fails once; the retry recovers
lines = read_all_lines(client)  # build it 1
client.post("/lab/faults", json={"faults": ["lost"]})  # build it 2: the lab's lost reply, injected before the call
decision = open_case_and_credit(record, client)  # build it 2: one credit, despite the lost reply
page = status_page(decision, len(lines), len(FILE_ROWS))  # build it 3
print(render(page))
credits = client.get("/lab/state").json()["credits"]
assert len(lines) == len(FILE_ROWS), "a line went missing"
assert len(credits) == 1, "a retried credit was written twice"
print("checkpoint passed: lines match, one credit held, status page written")

# %% [markdown]
# The lab is finished. Stop the mock customer API and save the recording of the two model calls.

# %%
# Stop the mock customer API now that the checkpoint is done.
server.terminate(); server.wait(timeout=10)
print("mock customer API stopped")
llm_replay.stop()  # saves the recording of the two model calls

# %% [markdown]
# **Interview:** "Show me a proof of concept you built against a customer system that fails at random. What did you check before you showed it?" Strong answer: "The count of lines matched the API's total and the file. Every model output passed a code check against the customer's data before any action. Each write carried an idempotency key, so a lost reply did not write twice. The demo said what it did not prove."

# %% [markdown]
# ## Key terms
#
# - **proof of concept** — a small, working test on real data that answers one question before a full build (lesson 01)
# - **thin slice** — one workflow carried all the way through, end to end, so every step is tested together (lesson 09)
# - **idempotency key** — a unique string a client sends with a write; the server returns the first answer for any repeat (lesson 04)
# - **cursor pagination** — reading a long list in pages with a `next_cursor` until it is null (lesson 04)
# - **structured output** — a model's answer in a fixed shape, checked when it arrives (lesson 06)
# - **tool calling** — the model asks the program to run a named function; the model never touches the system itself (lesson 06)
# - **status update** — a one-page note for a non-engineer: where we are, what we know, the decision with an owner and a day, and the risks (lesson 07)

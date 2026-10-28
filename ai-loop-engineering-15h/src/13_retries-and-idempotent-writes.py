# %% [markdown]
# # 13 · Retries, backoff and idempotent writes
# Level L3 · Part 2 · core · ~25 min · builds on 12
#
# ## Goal
# Retry a transient refund error with exponential backoff and jitter, and make the refund write safe to repeat: a retry or a restart must never refund the same jacket twice.
#
# ## Why it matters
# Lesson 12 keeps the loop's state. This lesson is about the write the loop makes. A refund call can fail in three ways, and a naive loop gets each one wrong:
#
# | What happens | Naive loop | What it costs |
# |---|---|---|
# | 503, nothing written | Stops at once, or retries in a tight loop | The customer waits for a person; a retry storm hits a service that is already struggling |
# | Written, but the reply times out | Retries the write | The jacket is refunded twice: 240 USD paid out for a 120 USD order |
# | Process killed between the write and the reply | Starts again from the top | The same double refund, and no error anywhere |
#
# With a retry policy and one idempotency key per case, a transient error waits and tries again, and a repeat of the same refund returns the first result. You do not need this for a read-only tool: a repeated read is harmless. Use it for every write.

# %% [markdown]
# ## The idea
# **A write is safe to retry when the provider can tell a repeat from a new request. Retry only transient errors (a 503, a timeout), wait longer after each failure with random jitter, and send the same idempotency key on every try and after every restart. The key comes from the case, not from a random number per try, so the provider returns the first result instead of paying out again.**
#
# Analogy: a cheque with a number. If you present cheque 1042 twice, the bank pays it once, because it recognises the number. A new cheque number each time would pay twice.

# %% [markdown]
# ## Picture
# The key is saved with the decision before the first try. Every retry, and every restart, reuses it.
#
# ```mermaid
# flowchart TD
#   A["Decision saved, with its key"] --> B["Try the write with the key"]
#   B -->|"ok"| D["Done: result stored"]
#   B -->|"503: nothing written"| W["Wait: backoff plus jitter"]
#   B -->|"timeout: may be written"| W
#   W --> C{"tries left?"}
#   C -->|"yes"| B
#   C -->|"no"| H["Hand the case to a person"]
#   R["Restart"] --> A
# ```

# %% [markdown]
# ## Step by step
# ### Step 1: a stand-in refund service, and the naive retry (no model call)
# The refund API is a local stand-in, so the failures are scripted and the run is repeatable. Its ledger has a unique `key` column, as payment providers do when they honour an `Idempotency-Key` header. The script says what each call does, in order: `"503"` fails and writes nothing, `"lost_reply"` writes and then times out, and anything else writes and replies.

# %%
import json, random, shutil, sqlite3, sys
from pathlib import Path

sys.path.insert(0, "..")
import llm_replay
llm_replay.start("13_retries-and-idempotent-writes")  # records the model call once, replays it later

ROOT = Path("../data/13")  # run-time files: the ledger and the saved decision
shutil.rmtree(ROOT, ignore_errors=True)
ROOT.mkdir(parents=True)
random.seed(13)  # jitter is random; the seed makes every run print the same waits
ORDER, PAID = "BS-1042", 120.0  # the order and what was paid, from the order record

class TransientError(Exception):
    """A 503 or a timeout: the same call may work if it is tried again later."""

# %% [markdown]
# **The stand-in service.** The idempotency key is a string the caller picks; here it is built from the case. The provider stores each key with its result, and a second call with the same key returns the stored result instead of writing again. Real providers (Stripe-style) send the key as an `Idempotency-Key` header; this stand-in takes it as a parameter, which plays the same role. `reset=True` is a demo-only reset that empties the ledger, so every run starts the same way.
#
# The ledger has a unique `key` column. `script` gives the behaviour of each call, in order: `"503"`, `"lost_reply"`, or anything else for a normal refund.

# %%
class PaymentService:
    def __init__(self, script=(), reset=False):
        self.script, self.calls = list(script), 0
        if reset: (ROOT / "ledger.db").unlink(missing_ok=True)
        self.db = sqlite3.connect(ROOT / "ledger.db")
        with self.db:
            self.db.execute("create table if not exists refunds (id integer primary key, key text unique, order_id text, amount_usd real)")

    def refund(self, order_id, amount_usd, key=None):
        self.calls += 1
        step = self.script.pop(0) if self.script else "ok"
        if step == "503":
            raise TransientError("503 unavailable: nothing was written")
        row = self.db.execute("select amount_usd from refunds where key = ?", (key,)).fetchone() if key else None
        if row:  # the same key: return the first result, write nothing
            return f"already refunded {row[0]} on {order_id}"
        with self.db:  # committed before the reply can be lost
            self.db.execute("insert into refunds (key, order_id, amount_usd) values (?, ?, ?)", (key, order_id, amount_usd))
        if step == "lost_reply":
            raise TransientError("read timeout: the write happened, the reply did not arrive")
        return f"refunded {amount_usd} on {order_id}"

    def paid_out(self, order_id):  # (refunds written, total paid out)
        return self.db.execute("select count(*), coalesce(sum(amount_usd), 0) from refunds "
                               "where order_id = ?", (order_id,)).fetchone()

print("stand-in service ready, ledger starts empty:", PaymentService(reset=True).paid_out(ORDER))

# %% [markdown]
# **The naive loop.** The first version most people write: retry at once, on any error, with no key. The service writes the refund, the reply is lost, and the retry writes it again.

# %%
def naive_refund(svc, order_id, amount, tries=3):
    for n in range(1, tries + 1):
        try:
            return svc.refund(order_id, amount)  # no key
        except TransientError as err:
            print(f"try {n}: {err}")
    return "gave up"

svc = PaymentService(["lost_reply"], reset=True)
print("result:", naive_refund(svc, ORDER, PAID))
print("refunds written, total paid out:", svc.paid_out(ORDER), "| the order paid", PAID)

# %% [markdown]
# ### Step 2: retry only transient errors, with one key (no model call)
# `tenacity` does the waiting. It retries only `TransientError`, waits longer after each try (exponential, with jitter), and gives up after four tries. The key is built from the case, so it is the same on every try and on every restart. The script gives two 503s, then a write whose reply is lost.
#
# - Tries 1–2: 503, nothing written.
# - Try 3: written, reply lost. tenacity counts a lost reply as retryable, because the caller cannot tell a lost reply from a failed write.
# - Try 4: same key found in the ledger, nothing written.
#
# A timeout may or may not have written, which is why the key must go with it. The waits are roughly 0.2 s, 0.4 s and 0.8 s, plus up to 0.2 s of random jitter.

# %%
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

def announce(state):  # tenacity calls this before each sleep
    print(f"  try {state.attempt_number} failed ({state.outcome.exception()}); wait {state.next_action.sleep:.2f} s")

@retry(retry=retry_if_exception_type(TransientError), stop=stop_after_attempt(4),
       wait=wait_exponential_jitter(initial=0.2, max=2, jitter=0.2), before_sleep=announce, reraise=True)
def safe_refund(svc, order_id, amount, key):
    """Retry transient errors only, with the same key on every try."""
    return svc.refund(order_id, amount, key=key)

def case_key(order_id):  # from the case, never random: a restart builds the same key
    return f"case-C-17:refund:{order_id}"

svc = PaymentService(["503", "503", "lost_reply"], reset=True)
print("result:", safe_refund(svc, ORDER, PAID, case_key(ORDER)))
print("refunds written, total paid out:", svc.paid_out(ORDER), "| calls to the service:", svc.calls)

# %% [markdown]
# ### Step 3: the model decides the refund (needs a model, one call)
# The desk model reads the request and calls `issue_refund`. How `bind_tools` and `tool_calls` work is in lesson 04. Here the function is only a schema: its body raises `NotImplementedError` on purpose, and the loop does the write itself, in `safe_refund`. The loop checks the amount against what was paid before it saves the decision. The decision is saved to disk before any write, so a restart never has to ask the model again.

# %% tags=["needs-llm"]
from langchain_core.messages import HumanMessage, SystemMessage
from llm_setup import get_llm

def issue_refund(order_id: str, amount_usd: float) -> str:
    """Refund an amount on one order. The amount may not be more than the amount paid."""
    raise NotImplementedError("the loop runs the write itself, in safe_refund")

SYSTEM = ("You are the support desk for Brightside Outfitters. Refund what was paid for a damaged item, "
          "by calling issue_refund once. Never refund more than was paid.")
REQUEST = "Customer C-17 says the trail jacket from order BS-1042 arrived torn after one wash. Order BS-1042 paid 120 USD."

llm = get_llm()  # Gemini by default; the key comes from .env
reply = llm.bind_tools([issue_refund]).invoke([SystemMessage(content=SYSTEM), HumanMessage(content=REQUEST)])
call = reply.tool_calls[0]
decision = {"order_id": call["args"]["order_id"], "amount_usd": float(call["args"]["amount_usd"])}
assert decision["order_id"] == ORDER and decision["amount_usd"] <= PAID, "plain-Python policy check failed"
(ROOT / "decision.json").write_text(json.dumps(decision))  # saved before the first write
print("model asked for:", call["name"], decision, "| model calls: 1")

# %% [markdown]
# ### Step 4: the process dies after the write (no model call)
# This cell needs the decision that step 3 saved (run it, or replay it). Without a key, step 3 is skipped; the fallback in the code then uses the order record and says so.
#
# Process 1 makes one try with the saved decision. The write lands, the reply is lost, and we simulate a crash by dropping the connection and not retrying. Process 2 starts from the saved decision file and the ledger. It reads the decision from disk, not from the model, and it uses the same key. The ledger returns the first result, and no second refund is written.

# %%
if not (ROOT / "decision.json").exists():  # no-key run: step 3 was skipped, so use the order record
    (ROOT / "decision.json").write_text(json.dumps({"order_id": ORDER, "amount_usd": PAID})); print("fallback: the order record, not a model decision")
saved = json.loads((ROOT / "decision.json").read_text())   # the decision, saved in step 3
svc = PaymentService(["lost_reply"], reset=True)           # process 1: the ledger is the file on disk
try:
    svc.refund(saved["order_id"], saved["amount_usd"], key=case_key(saved["order_id"]))
except TransientError as err:
    print("process 1 ended after:", err)
svc.db.close()

svc2 = PaymentService()                                    # process 2: a new connection, no model call
print("process 2:", safe_refund(svc2, saved["order_id"], saved["amount_usd"], case_key(saved["order_id"])))
print("refunds written, total paid out:", svc2.paid_out(ORDER), "| model calls in this notebook: 1")

# %% [markdown]
# **What the recorded run showed** (one sample, the course's default Gemini model, recorded 2026-10-27). The model asked for one `issue_refund` call with the order BS-1042 and 120 USD. The write was made once. Process 2 found the key in the ledger and wrote nothing. The count above is the evidence: one refund, 120 USD paid out.

# %% [markdown]
# ### Step 5: a hung provider, and a fallback (no model call)
# Two more guards sit around a model call. A **per-hop timeout** stops one hung request from holding the loop: the client takes a `timeout` in seconds. A **model fallback** moves to a second model when the first raises an error. This step sets the timeout and prints it. The first cell needs no key. The second builds the client, so it is tagged `needs-llm` and is skipped without a key. The fallback is shown in the text only, because it needs a second provider's key.

# %%
TIMEOUT_S = 20  # the client gives up on one hung request after this many seconds
print("per-hop timeout we set (s):", TIMEOUT_S)

# %% [markdown]
# The next cell builds the real client with that timeout. It makes no model call, so it needs a key only to build the client.

# %% tags=["needs-llm"]
primary = get_llm(timeout=TIMEOUT_S)  # builds the client only: no model call
print("client timeout (s):", primary.timeout, "| client max_retries:", primary.max_retries)

# %% [markdown]
# The fallback chain is one line on the model object: `primary.with_fallbacks([backup])`, where `backup` is a model from another provider. It runs `backup` only when `primary` raises. A circuit breaker stops calling a service after a few failures in a row and fails fast until a cool-down ends. Gateways and service meshes usually provide it; tenacity does not.
#
# Keep the retries in one place. The Gemini client already retries transient errors itself: `max_retries` (printed above) is passed on as the SDK's attempt count, and the pinned `langchain-google-genai` sets it to 6 by default. Put a tenacity retry around the same call as well, and the attempts multiply: 4 tenacity tries × 6 client attempts can send up to 24 requests for one failed step. To keep one retry layer, set the client's `max_retries=1` and let tenacity do the retrying.

# %% [markdown]
# ## Under the hood
# Tenacity hides its jitter rule, so here is the AWS rule written by hand. It is not used above. The AWS architecture post on backoff calls this rule "Full Jitter": wait a random time between 0 and the capped exponential step (https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/). The post reports that jitter cut the call count by more than half with 100 contending clients. Tenacity's `wait_exponential_jitter` is a different rule: the exponential step plus a small random extra of up to `jitter` seconds, which is what the waits in step 2 used.
#
# The idempotent write itself is the unique `key` column and the lookup in `refund` above (about 8 lines). This is the part interviews ask you to write.

# %%
def full_jitter(attempt, base=0.2, cap=2.0):
    return random.uniform(0, min(cap, base * 2 ** attempt))
print('full jitter waits (s), attempts 0-3:', [round(full_jitter(n), 2) for n in range(4)])

# %% [markdown]
# ## At work
# - Stripe's idempotency rule is the production form of this lesson. A retry with the same key returns the saved response, and the key must be unique per request. Stripe may delete a key once it is at least 24 hours old, and it returns an error when a reused key comes with different parameters. → lesson 26a builds the durable version of the saved decision.
# - Google's Gemini API docs say to retry only transient errors (such as 429 and 5xx), wait about one second before the first retry, and add jitter. The official SDKs retry transient errors automatically; check the client's `max_retries` (step 5). → lesson 27 counts retries and cost per run, so a retry storm shows up in the numbers.
# - A refund or a send is the write that needs an approval step before it runs, not a silent retry. → lesson 22 pauses the loop for a person when a write is risky.

# %% [markdown]
# ## Common mistakes
# Wrong: a new random key on every try. Each try looks like a new request to the provider, so nothing is recognised. The cell below makes that mistake. The error it raises is expected: the assert is the check that catches the second refund. The cell calls `svc.refund` directly, not through tenacity, so there is no retry in it at all.

# %% tags=["raises-exception"]
import uuid
svc = PaymentService(["lost_reply"], reset=True)
try:
    svc.refund(ORDER, PAID, key=str(uuid.uuid4()))   # try 1: written, reply lost
except TransientError:
    pass
svc.refund(ORDER, PAID, key=str(uuid.uuid4()))       # try 2: a new key, so a new refund
assert svc.paid_out(ORDER)[0] == 1, f"this error is expected: {svc.paid_out(ORDER)[0]} refunds written for one order"  # AssertionError

# %% [markdown]
# Right: build the key once, from the case (`case_key`), and send it on every try and after every restart.
#
# Wrong: retrying every error. A refund refused for more than was paid will be refused again, so a retry only wastes time. Retry the transient errors you name, and let everything else stop the loop.

# %% [markdown]
# ## Try it
# A refund for more than was paid raises a `ValueError` in the service. How many tries does `safe_refund` make? Predict first, then run the cell.

# %%
# your code here

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
class OverPaid(ValueError):
    pass

class OverPaidService:
    tries = 0
    def refund(self, order_id, amount_usd, key=None):
        self.tries += 1
        raise OverPaid(f"{amount_usd} is more than the {PAID} paid")

over = OverPaidService()
try:
    safe_refund(over, ORDER, 500, case_key(ORDER))
except OverPaid as err:
    print("stopped at once:", err, "| tries:", over.tries)
# One try. The retry names TransientError only, so a ValueError is not retried.

# %% [markdown]
# Save the recording. This is the last cell that touches the model layer.

# %%
llm_replay.stop()  # saves the recording (record mode) and closes the replay

# %% [markdown]
# ## Recap
# - A transient error (503, timeout) is retried with exponential backoff and jitter. Any other error stops the loop at once.
# - A repeated write is safe only when every try sends the same idempotency key. Build the key from the case, and save it with the decision.
# - A restart reads the saved decision and the ledger, not the model. The provider returns the first result, so the refund is written once.
# - Timeouts and fallbacks guard each model hop. A circuit breaker is text only here: gateways usually supply it.
#
# **Interview:** How do you make a retried refund safe? Strong answer: retry only transient errors with exponential backoff and jitter, cap the tries, and send one idempotency key built from the case on every try and after a restart. The provider then returns the first result for a repeat instead of writing again.

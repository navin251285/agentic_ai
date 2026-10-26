# %% [markdown]
# # 18 · Cost, latency and caching: budgets for a customer's AI features
#
# Level L3 · Part 2 · core · ~25 min · builds on lesson 06

# %% [markdown]
# ## Goal
#
# By the end of this lesson you can set a token and a latency budget for one AI feature, measure both on a real model call, trim the context so it fits the budget, and cache repeated answers in an LRU cache with limits. You can also say what a cache must never share between two customers.

# %% [markdown]
# ## Why it matters
#
# Every support message that reaches the model is a bill and a wait for the customer. Nobody sees the cost when the feature is a prototype with ten test messages. It shows up when real traffic arrives. The volumes below are **invented** for Basket Bazaar, a fictional grocery delivery app. Only the price comes from outside: it is the list price of the model, checked on 2026-10-22.
#
# The cell below is the arithmetic a team does before launch. It assumes the simplest design: every message carries the whole case history, and nothing is saved.

# %%
MESSAGES_PER_DAY = 20_000       # invented volume for one customer
TOKENS_PER_CALL = 1_300         # invented: the whole case history pasted into every prompt (a rounded guess; Step 2 counts 1,279)
PRICE_IN_PER_MTOK = 0.25        # USD per million input tokens (Gemini 3.1 Flash-Lite, standard, text)

daily_tokens = MESSAGES_PER_DAY * TOKENS_PER_CALL
daily_cost = daily_tokens / 1_000_000 * PRICE_IN_PER_MTOK
print(f"{daily_tokens:,} input tokens a day, about ${daily_cost:,.2f} a day, ${daily_cost * 30:,.0f} a month")

# %% [markdown]
# - **Without budgets:** the bill grows with every message, and nobody decides how much a case may cost. A slow model answer keeps the customer waiting, and a repeat question is paid for again.
# - **With budgets:** each case has a token limit and a latency limit that you measure. The context is trimmed to fit. Repeated questions are answered from a cache, and each store has its own budget.
# - **When you don't need it:** a prototype with a few dozen calls a day. Measure once, and add budgets when the volume is real.

# %% [markdown]
# ## The idea
#
# A **token** is the unit a model reads and bills: roughly three-quarters of a word in English. A **token budget** is the most input tokens you allow for one call (output is kept small with `max_output_tokens`). A **latency budget** is the longest wait you allow. A **cache** keeps an answer you already paid for. An **LRU cache** (least recently used) throws out the entry nobody asked for longest when it is full.
#
# Analogy: a corner shop's small fridge. It has room for a few products. The shop keeps what sells and throws out what sits longest on the shelf. A shop that never measures what it sells will run out of room, and will throw away the wrong things.
#
# A cached answer belongs to one store (the tenant, lesson 23) and one version of the prompt. Put the tenant and the prompt version in the cache key, so one store never gets another store's answer.

# %% [markdown]
# ## Picture
#
# A message is answered from the cache when possible. Otherwise the context is trimmed, the model is called, and the call is checked against the budgets.

# %% [markdown]
# ```mermaid
# flowchart LR
#     Q[Customer message] --> N[Normalise the text]
#     N --> C{Cache hit for this tenant and prompt version?}
#     C -- yes --> A[Saved answer: no model call]
#     C -- no --> T[Trim the context to the token budget]
#     T --> M[Model call]
#     M --> B{Within token and latency budget?}
#     B -- yes --> S[Store in cache and answer]
#     B -- no --> F[Log it and send the case to a person]
# ```

# %% [markdown]
# ## Step by step

# %% [markdown]
# The first code cell sets up the recording for the model calls in this lesson. The recording replays without a key, so the outputs below appear on any laptop.

# %%
import sys
sys.path.insert(0, "..")  # lets the notebook import llm_setup.py and llm_replay.py
import llm_replay
llm_replay.start("18_cost-and-latency-budgets")  # records the model calls below once

# %% [markdown]
# ### Step 1: the price table and the budgets
#
# The price table comes from the Gemini API pricing page (standard paid tier, text), last updated 2026-10-22 UTC. The course's model is set in `.env`. The prices here are for Gemini 3.1 Flash-Lite, the model this lesson was recorded with. If you change the model, change this table too. Prices move often, so print the date with every cost you show.

# %%
PRICE = {"input": 0.25, "output": 1.50, "cache_read": 0.025}  # USD per million tokens
PRICE_DATE = "2026-10-22"
TOKEN_BUDGET = 1_500          # input tokens allowed for one model call
LATENCY_BUDGET_MS = 5_000     # longest wait allowed for one model call
CONTEXT_BUDGET = 400          # tokens of case history kept in a prompt
TENANT = "store-07"           # one store (the tenant, lesson 23); part of every cache key
PROMPT_VERSION = "triage-v1"  # change it when the prompt changes, so old answers are not reused

print(f"prices (USD per 1M tokens, {PRICE_DATE}):", PRICE)
print("budgets: tokens per call", TOKEN_BUDGET, "| latency ms", LATENCY_BUDGET_MS, "| context tokens", CONTEXT_BUDGET)


def norm(text: str) -> str:
    """Lower case and single spaces, so small differences in typing hit the same cache entry."""
    return " ".join(text.lower().split())


def check_budget(call: dict) -> list[str]:
    """Return the budget problems of one call. An empty list means the call is within budget."""
    problems = []
    if call["input_tokens"] > TOKEN_BUDGET:
        problems.append(f"{call['input_tokens']} input tokens is over the {TOKEN_BUDGET} budget")
    if call["latency_ms"] > LATENCY_BUDGET_MS:
        problems.append(f"{call['latency_ms']} ms is over the {LATENCY_BUDGET_MS} ms budget")
    return problems

# %% [markdown]
# ### Step 2: the case history
#
# The thread below is invented: 30 earlier notes about one customer's orders. In a real system it would come from the ticket tool. The system message sets the job for the model.

# %%
SYSTEM = "You help Basket Bazaar's support team. Reply in one line: the issue type and the order number."
THREAD = [("system", SYSTEM)]
for day in range(1, 31):  # invented notes, deterministic
    THREAD.append(("human", f"Day {day}: I checked order BB-{1100 + day} and the delivery was {day * 3} minutes late."))
    THREAD.append(("ai", f"Noted. Support has logged the late delivery for BB-{1100 + day}."))

from langchain_core.messages.utils import count_tokens_approximately

print("messages in the thread:", len(THREAD))
print("approximate tokens for the full thread:", count_tokens_approximately(THREAD))

# %% [markdown]
# ### Step 3: trim the context to the budget
#
# `trim_messages` keeps the newest messages that fit in `max_tokens` and always keeps the system message. The count is an **approximation** (about four characters per token), so it is cheap and needs no model call. The model's own count, from its answer, is the one to trust, and Step 4 reads it.

# %%
from langchain_core.messages import trim_messages

trimmed = trim_messages(
    THREAD,
    max_tokens=CONTEXT_BUDGET,
    token_counter="approximate",
    strategy="last",
    include_system=True,
)
print("kept", len(trimmed), "of", len(THREAD), "messages")
print("approximate tokens after trimming:", count_tokens_approximately(trimmed))
print("newest kept note:", trimmed[-2].content)

# %% [markdown]
# Reading the output: the thread has 61 messages, the system message plus 60 notes and replies. The trim keeps 18: the system message and the 17 newest messages (notes and the replies to them). `trimmed[-2]` is the newest customer note, because the last item in the list is the model's reply to it.

# %% [markdown]
# ### Step 4: a real model call, measured and checked
#
# The function `triage` calls the model with the trimmed history and the new message. It records the input tokens, output tokens and the time of the call. The cache comes in Step 5. The first call is for one message about a missing milk. Its tokens and latency are checked against the budgets. The latency is the real wait when you record with a key. When you replay, it is the time of the replay, so it is much smaller than a real call.

# %% tags=["needs-llm"]
import time
from functools import lru_cache

from llm_setup import get_llm

llm = get_llm(max_output_tokens=80)  # answers are short, so output cost stays small
CALLS: list[dict] = []               # one entry per real model call


@lru_cache(maxsize=128)
def triage(tenant: str, prompt_version: str, message: str) -> str:
    """Answer one support message. tenant and prompt_version are only part of the cache key."""
    history = trim_messages(THREAD, max_tokens=CONTEXT_BUDGET, token_counter="approximate",
                            strategy="last", include_system=True)
    started = time.perf_counter()
    reply = llm.invoke(history + [("human", message)])
    CALLS.append({"tenant": tenant, "input_tokens": reply.usage_metadata["input_tokens"],
                  "output_tokens": reply.usage_metadata["output_tokens"],
                  "latency_ms": round((time.perf_counter() - started) * 1000)})
    return reply.text  # plain text of the reply, not the provider's content blocks


MSG_A = "Order BB-1108: the milk is missing from my delivery. Can I get a credit?"
answer = triage(TENANT, PROMPT_VERSION, norm(MSG_A))
print("answer:", answer)
print("measured call:", CALLS[-1])

print("budget check:", check_budget(CALLS[-1]) or "within budget")

# %% [markdown]
# Reading the result: the model counted 389 input tokens for this call, against the approximate 384 after trimming, so the approximate count is close. The latency printed here is replay time, not a real wait. The within-budget check for latency is only meaningful when the call is recorded live with a key.

# %% [markdown]
# ### Step 5: the LRU cache saves a second call
#
# `functools.lru_cache` is the standard-library cache. It keeps 128 answers and drops the least recently used one when it is full. The cache key is the three arguments, so the tenant and the prompt version are part of it. The second message is new, so it calls the model. The third message is the first one again with different capitals and spaces. After `norm`, it is the same text, so the cache answers and no model call is made.

# %% tags=["needs-llm"]
MSG_B = "Order BB-1118: two loaves of bread arrived squashed."
triage(TENANT, PROMPT_VERSION, norm(MSG_B))
repeat = "order BB-1108:   the MILK is missing from my delivery. Can I get a credit?"
repeat_answer = triage(TENANT, PROMPT_VERSION, norm(repeat))

print("model calls made:", len(CALLS))
print("cache:", triage.cache_info())
print("repeat answered from cache:", repeat_answer == answer)

# %% [markdown]
# Reading `CacheInfo(hits=1, misses=2)`: A missed (Step 4), B missed (this step), and the repeat of A was a hit. Two model calls, one saved.

# %% [markdown]
# ### Step 6: cost per case and the monthly bill
#
# The numbers now come from the calls, not from a guess. `CALLS` holds the real token counts. The projection uses the invented volume from the start of the lesson, and a cache hit rate that you should replace with a measured one from your own traffic. The naive line uses the counted 1,279 tokens; the 1,300 in the first cell was a rounded guess. The 30% hit rate is an assumption, so the budgeted monthly figure is illustrative.

# %%
if CALLS:
    avg_in = sum(c["input_tokens"] for c in CALLS) / len(CALLS)
    avg_out = sum(c["output_tokens"] for c in CALLS) / len(CALLS)
    cost_per_call = avg_in / 1e6 * PRICE["input"] + avg_out / 1e6 * PRICE["output"]
    naive_in = count_tokens_approximately(THREAD)
    naive_cost = naive_in / 1e6 * PRICE["input"]
    hit_rate = 0.30  # assumption (invented): 30% of messages repeat an earlier question
    budgeted_day = MESSAGES_PER_DAY * (1 - hit_rate) * cost_per_call
    print(f"measured: {avg_in:.0f} input and {avg_out:.0f} output tokens per call, ${cost_per_call:.6f} per call")
    print(f"no budget, no cache (input only): about ${naive_cost * MESSAGES_PER_DAY * 30:,.0f} a month (full thread, estimate)")
    print(f"budget and cache ({hit_rate:.0%} hits, assumed, illustrative): about ${budgeted_day * 30:,.0f} a month (prices {PRICE_DATE})")
else:
    print("no measured calls (no recording and no key), so the projection is skipped.")

# %% [markdown]
# ## Under the hood
#
# `lru_cache` has no limit on the size of an answer and no expiry. A support answer can go stale when a policy changes. Here is a small cache with three limits: a maximum number of entries, a maximum total size, and a time to live. Its `OrderedDict` keeps the least recently used entry first. The clock is passed in, so the test below needs no waiting. This class is about 30 lines, the interview-mechanism exception (`hand_code: interview` allows up to 40 lines).

# %%
from collections import OrderedDict


class BudgetedLRU:
    """LRU cache with limits on entries, total size and time to live (seconds)."""

    def __init__(self, max_entries: int, max_size: int, ttl_s: float):
        self.max_entries, self.max_size, self.ttl_s = max_entries, max_size, ttl_s
        self.data = OrderedDict()  # key -> (value, size, stored_at), least recently used first
        self.size = 0

    def get(self, key, now: float):
        if key not in self.data:
            return None
        value, size, stored_at = self.data[key]
        if now - stored_at > self.ttl_s:  # expired: a miss
            self._drop(key)
            return None
        self.data.move_to_end(key)  # now the most recently used
        return value

    def put(self, key, value, size: int, now: float) -> bool:
        if key in self.data:
            self._drop(key)
        if size > self.max_size:  # too big to keep at all
            return False
        self.data[key] = (value, size, now)
        self.size += size
        while len(self.data) > self.max_entries or self.size > self.max_size:
            self._drop(next(iter(self.data)))  # evict the least recently used
        return True

    def _drop(self, key):
        _, size, _ = self.data.pop(key)
        self.size -= size

# %% [markdown]
# A small test of the three limits. Entries "a" and "b" fill the cache. "c" pushes out the least recently used one, "b", because the cache holds at most 2 entries. A value bigger than the whole size limit is refused.

# %%
cache = BudgetedLRU(max_entries=2, max_size=100, ttl_s=60)
cache.put("a", "answer A", size=40, now=0)
cache.put("b", "answer B", size=40, now=0)
cache.get("a", now=1)                          # "a" is now the most recently used
cache.put("c", "answer C", size=40, now=2)     # 3 entries > max_entries=2: "b", the least recently used, is evicted
print("b after eviction:", cache.get("b", now=3))
print("a still there:", cache.get("a", now=3))
print("'big' (500 characters) stored:", cache.put("big", "x", size=500, now=4))  # over max_size=100: refused
print("a after 100 s (ttl 60):", cache.get("a", now=100))

# %% [markdown]
# Use this cache in production when answers can go stale. Wiring it in is short: the answer function checks the cache first, and calls the model only on a miss. The next cell does that for the message from Step 4. The answer is already in `triage`'s cache, so no second model call is made. Then it shows that the same text for another tenant is a miss. The key is what separates the two tenants. The history the model reads must also be per tenant, because the key only stops a stored answer being reused.

# %% tags=["needs-llm"]
answer_cache = BudgetedLRU(max_entries=50, max_size=10_000, ttl_s=3600)  # size counted in characters


def triage_with_budgets(tenant: str, prompt_version: str, text: str, now: float) -> str:
    """Check the BudgetedLRU first; call triage (and store its answer) only on a miss."""
    key = (tenant, prompt_version, norm(text))
    hit = answer_cache.get(key, now)
    if hit is not None:
        return hit
    reply = triage(tenant, prompt_version, norm(text))
    answer_cache.put(key, reply, size=len(reply), now=now)
    return reply


print("first ask, same answer:", triage_with_budgets(TENANT, PROMPT_VERSION, MSG_A, now=0) == answer)
print("same text, other tenant, cache key:", answer_cache.get(("store-03", PROMPT_VERSION, norm(MSG_A)), now=10))

# %% [markdown]
# ## At work
#
# - Set a budget per store and alert before it is spent (OWASP LLM10, Unbounded Consumption, lists unlimited model use as a risk). How cost is quoted to customers: → lesson 29.
# - Providers offer a cheaper price for a repeated prompt prefix. On Gemini, the cache read costs $0.025 per million tokens against $0.25 for normal input (Flash-Lite, 2026-10-22). That is a different layer from the answer cache here. → lesson 29 compares the layers.
# - The answer cache must be keyed by tenant and prompt version, and it needs a time to live. Teams that skip this serve one store's answer to another store, or an old policy after a change. → lesson 23 covers tenant isolation.
#
# Go deeper: how the trace of one call shows its tokens and latency is lesson 16.

# %% [markdown]
# ## Common mistakes
#
# - **Passing a list as a cache key.** `lru_cache` needs hashable arguments. A list of messages cannot be a key, so the cell below fails before any model call. Pass the text, not the list.

# %% tags=["raises-exception"]
triage(TENANT, PROMPT_VERSION, [norm(MSG_A)])

# %% [markdown]
# The fix is to pass a string, as in Step 5. Keep the messages inside the function, where they are built from the text.
#
# - **Setting a budget without measuring.** A budget of 1,500 tokens means nothing until you know what a typical call uses. Measure first, then set the limit with some room, as the `CALLS` list does. The 1,500 budget is a ceiling per call. Trimming is what keeps cost down: 386 tokens against 1,279.

# %% [markdown]
# ## Try it
#
# Write `case_cost(call)`. It takes one entry of `CALLS` (a dictionary with `input_tokens` and `output_tokens`) and returns its cost in US dollars, using the `PRICE` table. The test uses a made-up call record of one million input tokens and no output, so the answer should be the input price, 0.25. The stub returns None until you replace `...`.

# %%
# your code here
def case_cost(call: dict) -> float:
    """Dollar cost of one model call, from the PRICE table (USD per million tokens)."""
    ...  # write the formula


print(case_cost({"input_tokens": 1_000_000, "output_tokens": 0}))

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
def case_cost(call: dict) -> float:
    """Dollar cost of one model call, from the PRICE table (USD per million tokens)."""
    return call["input_tokens"] / 1e6 * PRICE["input"] + call["output_tokens"] / 1e6 * PRICE["output"]


print(case_cost({"input_tokens": 1_000_000, "output_tokens": 0}))

# %% [markdown]
# ## Recap
#
# - A budget is a number you measure on real calls: input tokens and latency per call, cost per resolved case.
# - Trim the context to a fixed budget. Keep the system message and the newest notes.
# - An LRU cache saves model calls for repeated questions. Key it by tenant and prompt version, and give it a size limit and a time to live.
# - Prices change. Print the date with every cost.
# - Words to keep: **token budget**, **latency budget**, **cache hit**, **LRU cache**, **time to live** (all in GLOSSARY.md).
#
# **Interview:** "A support feature's bill doubled in a month. What do you measure, and what do you change first?" Strong answer: "Tokens and latency per call and per resolved case, on real traffic. Then trim the context to a budget and add an answer cache keyed by tenant and prompt version, with a size limit and an expiry. Set a per-store budget with an alert."

# %%
llm_replay.stop()  # saves the recording of the model calls

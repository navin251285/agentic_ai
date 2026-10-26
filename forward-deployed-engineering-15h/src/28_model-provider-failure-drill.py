# %% [markdown]
# # 28 · Failure drill: a model provider goes down
#
# Level L5 · Part 3 · professional · ~25 min · builds on lessons 18, 20
#
# This lesson starts one Compose service, the lab route to the model, on port 8280, and makes **4 model calls** in total (the budget is 5). The calls are recorded once and replay on any laptop with no key. Two cells tagged `needs-docker` start and stop the route (Step 2 and Step 9). Without Docker, those two cells are skipped, and the model calls and the drill switches replay from the recording of the last real run, so the answers and counts below come out the same.

# %% [markdown]
# ## Goal
#
# By the end you can break the path to a model on purpose, under a burst of load, and watch what a customer would see: errors, answer time, and how many answers came from the fallback. You can then recover the feature with a circuit breaker, a capped retry and a labelled fallback, and show the numbers that prove it.

# %% [markdown]
# ## Why it matters
#
# A model provider has outages and rate limits, and the customer sees an error page either way. Take the Basket Bazaar volume from lesson 18 (an invented 20,000 messages a day). A 10-minute outage is about 139 messages.
#
# | | Without a fallback, breaker or retry rules | With them |
# |---|---|---|
# | Each of the 139 messages | an error page, and the customer repeats the message | a labelled answer from the rules, flagged for a person |
# | Retries | every message retries as fast as it can, so the outage gets louder | each call retries once, after a jittered wait; the breaker stops the calls once the route is down |
#
# - **When you don't need it:** a nightly batch that can wait, or a prototype with ten messages a day.

# %% [markdown]
# ## The idea
#
# Three small mechanisms work together. A **retry** tries again after a short wait, but only for errors a later try can fix: rate limits and server errors, not a wrong key. A **circuit breaker** counts failures. After too many, it stops calling the provider, answers at once, and lets one **test call** through after a cooldown. Here each call gets at most one retry, so a retry cannot multiply an outage.

# %% [markdown]
# A **fallback** is a simpler answer, here keyword rules, that is labelled and sent to a person. Analogy: a shop's card machine goes down. The clerk tries the card twice, then stops trying the machine for a few minutes, writes the orders on a pad and enters them later. The shop still trades, and everyone knows which sales still need checking.
#
# The drill breaks the path the customer controls. You cannot switch off the provider from a notebook, so the lab route passes calls on to the real provider while it is up, and answers 503 when the drill says so. A customer's code sees the same 503.

# %% [markdown]
# ## Picture
#
# Every message follows the same path. Only the arrows out of "model call" change during an outage.

# %% [markdown]
# ```mermaid
# flowchart LR
#     M[Support message] --> B{Breaker closed?}
#     B -- yes --> C[Model call through the route]
#     C -- answer --> A[Model label]
#     C -- 429 or 5xx --> R{Retry left for this call?}
#     R -- yes, after a wait --> C
#     R -- no --> F[Rules fallback, flagged for a person]
#     B -- no, open --> F
# ```

# %% [markdown]
# ## Step by step
#
# ### Step 1: the recording and the settings
#
# The first code cell starts the recording of the model calls, so every call after it is saved once and replayed later. It also reads the settings from `.env`. The route address is the only one this lesson needs (`PROVIDER_ROUTE_URL`). The model id is the one `llm_setup` reads (`TUT_LLM_MODEL`).

# %%
import sys
sys.path.insert(0, "..")  # lets the notebook import llm_setup.py and tut_env.py
import time

import httpx
import llm_replay
from llm_setup import get_llm
from tut_env import env

llm_replay.start("28_model-provider-failure-drill")  # records the model calls below once
ROUTE_URL = env("PROVIDER_ROUTE_URL", "http://localhost:8280")  # the customer's route to the model (Compose below)

# %% [markdown]
# ### Step 2: start the customer route in Docker
#
# One Compose service on port 8280. Docker starts it and waits for its health check. This cell needs Docker; without it, the cell is skipped and the recorded model calls and drill switches still replay.

# %% tags=["needs-docker"]
import subprocess

COMPOSE = ["docker", "compose", "-p", "tut-forward-deployed-engineering-15h-28",  # one Compose project per lesson
           "-f", "../infra/compose/provider-drill-28.yml", "--env-file", "../.env"]
up = subprocess.run([*COMPOSE, "up", "-d", "--build", "--wait"], capture_output=True, text=True, timeout=900)
up.check_returncode()  # stop here if the route did not start

# %% [markdown]
# ### Step 3: the model, the rules and the retry rules
#
# The model is the real Gemini model from `llm_setup`, called through the route. The route is a small proxy: `base_url` sends the client's calls to it, and the route forwards them to the provider. `max_retries=0` turns off the client's own hidden retries, so they do not stack on the retry rules below. Those rules are the only retry layer. `timeout=10` gives each call 10 seconds; a call that runs longer raises an error, and the breaker counts it as a failure.

# %% tags=["needs-llm"]
LABELS = ["missing item", "wrong item", "late delivery", "other"]
SYSTEM = ("You triage grocery delivery issues for Basket Bazaar. Reply with one label only: "
          "missing item, wrong item, late delivery or other.")
llm = get_llm(base_url=ROUTE_URL, max_retries=0, max_output_tokens=64, timeout=10)  # 10 s per call

# %% [markdown]
# The fallback is a few keyword rules: no model, no cost, and always a person to check the answer.

# %%
def rules_triage(text: str) -> str:
    """The fallback: keyword rules, no model. Its answers always go to a person."""
    text = (text or "").lower()
    return next((label for word, label in [("missing", "missing item"), ("wrong", "wrong item"),
                                           ("late", "late delivery")] if word in text), "other")


print(rules_triage("I got the wrong bread"), "|", rules_triage(None))

# %% [markdown]
# The retry rules come from `tenacity`, and nothing is written by hand. `stop_after_attempt(2)` allows one try and one retry for each call. `wait_exponential_jitter` waits about half a second before the retry, plus a random 0 to 0.25 s, so failing calls do not all retry together. `retry_if_exception` retries only the errors a later try can fix: rate limits and server errors, not a wrong key. The Google client puts the HTTP status in `exc.code`, and Step 5 prints that code to check it on your SDK version.

# %% [markdown]
# Now the model call with those rules. `tenacity` runs the attempts and the waits. A bad answer (not one of the labels) is raised as a `ValueError`: the retry rule does not retry it, and the breaker does not count it as an outage. `llm.invoke(...)` returns a message object, and `.text` is its answer as a string.

# %%
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential_jitter

TRANSIENT_CODES = {429, 500, 502, 503, 504}  # a later try can fix these; a 400 or 401 cannot
LAST_ERROR, ATTEMPTS = {}, {"model": 0}  # ATTEMPTS counts every call that reached the route


def is_transient(exc: BaseException) -> bool:
    return getattr(exc, "code", None) in TRANSIENT_CODES


@retry(stop=stop_after_attempt(2),  # one try and at most one retry, for each call
       wait=wait_exponential_jitter(initial=0.5, max=4, jitter=0.25),  # 0.5 s to 0.75 s before the retry
       retry=retry_if_exception(is_transient), reraise=True)
def ask_model(text: str) -> str:
    ATTEMPTS["model"] += 1
    try:
        reply = llm.invoke([("system", SYSTEM), ("human", text)]).text.strip().strip(".").lower()
    except Exception as exc:
        LAST_ERROR["what"] = f"{type(exc).__name__} code={getattr(exc, 'code', None)}: {str(exc)[:60]}"
        raise
    if reply not in LABELS:  # checked output: anything else is not an answer
        raise ValueError(f"not a label: {reply!r}")
    return reply

# %% [markdown]
# The breaker comes from the `pybreaker` library. This drill trips it on one failed request so the drill is short. Production waits for several failures in a short window. A bad answer is excluded: it is not an outage. A request that exhausts its retry counts as one failure.

# %%
import pybreaker

BREAKER = pybreaker.CircuitBreaker(fail_max=1, reset_timeout=5, name="model-route")
BREAKER.add_excluded_exception(ValueError)


def triage(text: str) -> dict:
    """One issue: the model if the breaker and the route allow it, else the rules. It never raises."""
    started, attempts_before = time.perf_counter(), ATTEMPTS["model"]
    try:
        label, source, reason = BREAKER.call(ask_model, text), "model", ""
    except Exception:  # breaker open, retry used up, or a bad answer
        reason = "provider attempt failed" if ATTEMPTS["model"] > attempts_before else "breaker open: no call made"
        label, source = rules_triage(text), "rules"
    return {"label": label, "source": source, "reason": reason, "needs_person": source == "rules",
            "ms": round((time.perf_counter() - started) * 1000, 1)}

# %% [markdown]
# ### Step 4: the healthy route
#
# One message with the route up. The answer comes from the model, the route forwards the call, and the breaker stays closed. Times vary per run and replay is not a latency measurement; read the pattern: an open breaker answers in well under 50 ms, and a retried request takes at least 500 ms.

# %% tags=["needs-llm"]
first = triage("Order BB-1108: the milk is missing from my delivery. Can I get a credit?")
print({k: v for k, v in first.items() if k != "ms"}, "| model calls:", ATTEMPTS["model"], "| breaker:", BREAKER.current_state)


# %% [markdown]
# ### Step 5: the drill starts, and one message trips the breaker
#
# The drill makes the route answer 503 to every call. Watch one message. The model is tried, fails with 503, and is retried once after a wait of 0.5 to 0.75 s. Then the fallback answers. Those two failed calls are model calls 2 and 3 in the recording: the first try and the one retry. The wait is why this message is slower than the healthy one (at least 500 ms). The breaker counts the whole request as one failure, so `fail_max=1` opens it now.

# %% tags=["needs-llm"]
print("route, drill on:", httpx.post(f"{ROUTE_URL}/_drill/down").json())
tripped = triage("Order BB-1119: I got the wrong bread, and two loaves were squashed.")
print({k: v for k, v in tripped.items() if k != "ms"}, "| waited for the retry:", tripped["ms"] >= 500)
print("last error:", LAST_ERROR["what"], "| breaker:", BREAKER.current_state, "| model calls:", ATTEMPTS["model"])

# %% [markdown]
# ### Step 6: thirty messages at once, during the outage
#
# Six workers send 30 messages at the same time. The messages come from a fixed seed, so every run sends the same ones. The breaker is open, so no message reaches the route: each one gets the fallback at once.

# %%
import math, random
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

rng = random.Random(28)  # seeded: the same 30 messages every run
KINDS = ["the milk is missing from my delivery", "I got the wrong bread", "my delivery was 40 minutes late"]
LOAD = [f"Order BB-{1200 + i}: " + rng.choice(KINDS) for i in range(30)]

before = ATTEMPTS["model"]
with ThreadPoolExecutor(max_workers=6) as pool:
    answers = list(pool.map(triage, LOAD))
print("messages:", len(answers), "| answered:", sum(bool(a["label"]) for a in answers),
      "| source:", dict(Counter(a["source"] for a in answers)), "| reason:", dict(Counter(a["reason"] for a in answers)))
p95 = sorted(a["ms"] for a in answers)[math.ceil(0.95 * len(answers)) - 1]  # nearest rank: 95 of every 100 messages took this long or less
print("provider attempts during the load:", ATTEMPTS["model"] - before, "| p95 under 50 ms:", p95 < 50)

# %% [markdown]
# The p95 is small because an open breaker makes no network call. Times vary per run and replay is not a latency measurement; read the pattern: an open breaker answers in well under 50 ms, and a retried request takes at least 500 ms.

# %% [markdown]
# ### Step 7: the drill ends, and the breaker recovers
#
# The route answers again. After the cooldown, the next message is the test call. It succeeds, the breaker closes, and the answer comes from the model again. This is model call 4, the last one in the recording.

# %% tags=["needs-llm"]
print("route, drill off:", httpx.post(f"{ROUTE_URL}/_drill/up").json())
time.sleep(5.5)  # wait out the 5-second cooldown: pybreaker lets one test call through only after it
recovered = triage("Order BB-1140: I got the wrong bread again, and two loaves were squashed.")
print({k: v for k, v in recovered.items() if k != "ms"}, "| breaker:", BREAKER.current_state, "| model calls:", ATTEMPTS["model"])

# %% [markdown]
# ### Step 8: the scorecard
#
# The recording holds exactly 4 model calls: the healthy one, two refused with 503 by the drill (the first try and the retry), and the test call. That is why the route shows forwarded 2 and refused 2. The budget is 5, so one call is spare.

# %% tags=["needs-llm"]
route = httpx.get(f"{ROUTE_URL}/_drill/state").json()
served = [first, tripped, *answers, recovered]
fallbacks = sum(a["source"] == "rules" for a in served)
print("messages:", len(served), "| answered:", sum(bool(a["label"]) for a in served),
      "| by the model:", sum(a["source"] == "model" for a in served), "| by the rules, to a person:", fallbacks)
print("model calls by the feature:", ATTEMPTS["model"], "| calls in the recording:", llm_replay.calls(), "| budget 5")
print("route counters: forwarded", route["forwarded"], "| refused", route["refused"])

# %% [markdown]
# ### Step 9: stop the route
#
# The drill is over. Docker removes the route. The recording is kept. This cell needs Docker, like Step 2.

# %% tags=["needs-docker"]
down = subprocess.run([*COMPOSE, "down", "--remove-orphans"], capture_output=True, text=True, timeout=300)
print("compose down, exit code:", down.returncode)

# %% [markdown]
# ## At work
#
# - Common practice: a timeout on every call, retries only for 429 and 5xx with backoff, and a human queue for what the model cannot answer. → lesson 17 covers who gets paged and the runbook's switch.
# - In an outage, customer teams watch the fallback rate and the p95 answer time first, not the provider's status page. → lesson 16 builds those panels.
# - A second model provider is a new vendor for the customer's security review: data flows, subprocessors, retention. → lesson 27.
# - OWASP LLM10 (Unbounded Consumption): per-tenant limits and spend caps are the controls. → lesson 18 sets the budgets.
#
# %% [markdown]
# Go deeper: workflows that resume a half-finished case after a crash need durable execution, which this course does not teach.
#
# Go deeper: a **retry cap shared by all requests** (say, 10 retries a minute for the whole feature). Here the count is per call, and no library gives you the shared count out of the box: tenacity's rules see one call, and pybreaker counts failures, not retries. It needs a counter that every worker reads and writes, such as a gateway rate limit. That is a platform decision, so this lesson does not build it.

# %% [markdown]
# ## Common mistakes
#
# - **A fallback that breaks on the input.** The fallback runs when things go wrong, so it must not fail on odd input. The first draft of `rules_triage` called `text.lower()` straight away, and an empty message (`None`) crashed it. The version above checks the input with `(text or "")`, so the same empty message gets the label `other`, which a person checks.

# %% tags=["raises-exception"]
first_draft = lambda text: text.lower()  # the first draft, without the check
first_draft(None)  # AttributeError: an empty message breaks a fallback that does not check its input

# %% [markdown]
# - **Retrying every error.** A 401 (a wrong key) retried five times is still a 401. A retry policy that hides it behind the fallback turns a configuration error into a silent slow answer. Only 429 and 5xx are retried here, and the fallback rate is what tells you.
# - **Thinking the retry count is shared.** `stop_after_attempt(2)` counts the tries of one call. Ten workers that each fail once make ten retries, not one. A shared cap is the Go deeper note in At work.
# - **A breaker that trips on one blip, or never closes.** `fail_max=1` is for the drill. A cooldown shorter than the provider's recovery makes the breaker open and close all day.

# %% [markdown]
# ## Production checklist
#
# - [ ] Every model call has a timeout and a capped retry count.
# - [ ] Only transient errors (429, 5xx) are retried; 400 and 401 page a person.
# - [ ] One breaker per provider route, with an alert when it opens.
# - [ ] Every fallback answer is labelled and goes to a person; the fallback rate is on the dashboard.
# - [ ] A cap on retries across all requests is in place (a gateway limit or shared counter), or the team has accepted per-call caps on purpose.
# - [ ] The runbook names the route switch and its owner, and the drill runs before go-live and after each change.

# %% [markdown]
# ## Try it
#
# Write `fallback_share(answers)`. It takes a list of answers (the dictionaries `triage` returns) and returns the share that came from the rules, as a number between 0 and 1. The 30 load answers are all fallbacks, so the share is 1.0. The first and the recovered answers came from the model, so their share is 0.0. Over the whole scorecard (33 messages, 31 from the rules), the share is 31 / 33, about 0.939.

# %%
def fallback_share(answers: list[dict]) -> float:
    """Share of answers whose source is 'rules'."""
    # your code here
    return 0.0


print(fallback_share(answers), fallback_share([first, recovered]), round(fallback_share(served), 3))

# %% [markdown]
# **Answer** — try it first, then expand the hidden cell below.

# %% tags=["solution"]
def fallback_share(answers: list[dict]) -> float:
    """Share of answers whose source is 'rules'."""
    return sum(a["source"] == "rules" for a in answers) / len(answers)


print(fallback_share(answers), fallback_share([first, recovered]), round(fallback_share(served), 3))

# %% [markdown]
# ## Recap
#
# - A drill breaks the path the customer controls and shows what users get: errors, answer time, fallback share.
# - Retry only transient errors, once per call here, with a jittered wait.
# - A breaker stops calls to a failing route and tests it after a cooldown.
# - A fallback is labelled and goes to a person. Test it with odd input too.
# - **Graceful degradation**: keep serving a reduced answer when a dependency fails.
# - **Half-open**: the breaker's test state after a cool-down, where one request goes through.
# - Only per-call caps are built here. A **retry budget** shared by all requests is not built in this lab (see Go deeper in At work).
# - Words to keep: **circuit breaker**, **half-open**, **retry**, **fallback**, **graceful degradation**, **failure drill** (GLOSSARY.md).

# %% [markdown]
# **Interview:** "A model provider returns 503 for twenty minutes. What does the customer see, and what does your code do?" Strong answer: "Every call has a timeout and one jittered retry for 429 and 5xx only, and a breaker stops the calls and tests the route after a cooldown. Each fallback answer is labelled and goes to a person, and we alert on the fallback rate."

# %% [markdown]
# The last cell stops the recording. Nothing after it calls the model.

# %%
llm_replay.stop()  # saves the recording of the model calls

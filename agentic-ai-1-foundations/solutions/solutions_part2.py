# %% [markdown]
# # Solutions · Part 2: Calling a real model
# Answers to the "Try it" exercises. Try each one yourself first.
#
# Model calls here are recorded once with `llm_replay` (`../data/llm_cassettes/solutions_part2.yaml`)
# and replayed with no key.

# %%
import sys; sys.path.insert(0, "..")
import os
import llm_replay
from dotenv import load_dotenv
from google import genai
from google.genai import types

llm_replay.start("solutions_part2")
load_dotenv("../.env")
MODEL = os.environ.get("TUT_LLM_MODEL", "gemini-3.5-flash-lite")
client = genai.Client(vertexai=True, api_key=os.environ.get("GOOGLE_CLOUD_API_KEY") or "replay-no-key-needed")

def config(max_output_tokens: int) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        max_output_tokens=max_output_tokens,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))

# %% [markdown]
# ## Lesson 07
# Setup from lesson 07: the same three calls as the lesson (`hello`, `response` about note 5, and
# `cut`, the same prompt with only 10 output tokens). They are recorded in this notebook's own cassette.
# This is a separate recording, so the wording and token counts can differ by a token or two from the lesson's.

# %% tags=["needs-llm"]
hello = client.models.generate_content(model=MODEL, contents="Say hello in five words.", config=config(60))
prompt = "Summarise this note in one short sentence.\nNote 5: The rover Perseverance landed on Mars in February 2021."
response = client.models.generate_content(model=MODEL, contents=prompt, config=config(60))
cut = client.models.generate_content(model=MODEL, contents=prompt, config=config(10))
print(hello.text.strip(), "|", response.text.strip(), "|", cut.text.strip())

# %% [markdown]
# `describe` reads the model version, the finish reason and the usage fields. Thinking tokens are
# `None` when the model did not think, so `or 0` turns that into a number.

# %%
def describe(resp) -> str:
    u = resp.usage_metadata
    reason = resp.candidates[0].finish_reason.value
    status = "ok" if reason == "STOP" else "CUT"
    return (f"{resp.model_version} | {reason} | {u.prompt_token_count} in, "
            f"{u.candidates_token_count} out, {u.thoughts_token_count or 0} thinking | {status}")

for r in (hello, response, cut):
    print(describe(r))

# %% [markdown]
# ## Lesson 08
# Setup from lesson 08: Scout's system text, the `{"role", "text"}` → Gemini converter, the validity
# checker and the `ask` chat step, unchanged.

# %%
NOTES = [
    {"id": 1, "text": "Mars has two small moons, Phobos and Deimos."},
    {"id": 2, "text": "Venus spins backwards compared with most planets."},
    {"id": 3, "text": "A day on Mars lasts about 24 hours and 39 minutes."},
    {"id": 4, "text": "Jupiter is the largest planet in the solar system."},
    {"id": 5, "text": "The rover Perseverance landed on Mars in February 2021."},
    {"id": 6, "text": "Saturn's rings are mostly made of ice."},
]
SYSTEM_TEXT = ("You are Scout, a research assistant. Answer only from the user's notes below and this chat. "
               "If the notes do not cover it, say so in one sentence. Keep answers to one sentence.\n\n"
               + "\n".join(f"Note {n['id']}: {n['text']}" for n in NOTES))
GEMINI_ROLES = {"user": "user", "assistant": "model"}

def to_gemini(messages):
    system = messages[0]["text"] if messages and messages[0]["role"] == "system" else None
    rest = messages[1:] if system is not None else messages
    return system, [types.Content(role=GEMINI_ROLES[m["role"]], parts=[types.Part(text=m["text"])]) for m in rest]

def check_messages(messages):
    if not messages:
        raise ValueError("message list is empty")
    for i, m in enumerate(messages):
        if m["role"] not in ("system", "user", "assistant"):
            raise ValueError(f"message {i}: unknown role {m['role']!r}")
        if m["role"] == "system" and i != 0:
            raise ValueError(f"message {i}: system message must come first")
        if not m["text"].strip():
            raise ValueError(f"message {i}: empty text")
    if messages[-1]["role"] != "user":
        raise ValueError(f"last message must be from the user, not {messages[-1]['role']!r}")

def ask(messages, user_text):
    messages.append({"role": "user", "text": user_text})
    check_messages(messages)
    system, contents = to_gemini(messages)
    cfg = config(60)
    cfg.system_instruction = system
    resp = client.models.generate_content(model=MODEL, contents=contents, config=cfg)
    messages.append({"role": "assistant", "text": resp.text.strip()})
    print(f"[{resp.usage_metadata.prompt_token_count:>3} in] {user_text} -> {resp.text.strip()}")

# %% [markdown]
# The correction only works because turn 2 is resent with turn 1: the model reads both and the later one wins.
# Note 4 (Jupiter) should come back, not note 6 (Saturn).

# %% tags=["needs-llm"]
ben = [{"role": "system", "text": SYSTEM_TEXT}]
ask(ben, "I'm Ben and I study Saturn.")
ask(ben, "Sorry, I meant Jupiter, not Saturn.")
ask(ben, "Which note is about the planet I study?")
print("mentions note 4:", "4" in ben[-1]["text"] or "Jupiter" in ben[-1]["text"])

# %% [markdown]
# A system message in second place is rejected by the checker, before any request is sent.

# %%
bad = [{"role": "user", "text": "Hi"}, {"role": "system", "text": "New rules!"}, {"role": "user", "text": "Go"}]
try:
    check_messages(bad)
except ValueError as err:
    print("rejected:", err)

# %% [markdown]
# ## Lesson 09
# Setup from the lesson: the toy provider store and its `create` (our own stand-in, not a vendor API).

# %%
from datetime import datetime, timedelta

def turn(role, text):
    return types.Content(role=role, parts=[types.Part(text=text)])

class ToyInteractionStore:
    def __init__(self, retention_days):
        self.retention = timedelta(days=retention_days)
        self.records, self.now, self.count = {}, datetime(2026, 10, 6, 9, 0), 0

    def history(self, interaction_id):
        turns = []
        while interaction_id:
            rec = self.records.get(interaction_id)
            if rec is None or self.now > rec["expires"]:
                raise LookupError(f"interaction {interaction_id!r} not found (never stored, deleted or expired)")
            turns = [turn("user", rec["input"]), turn("model", rec["output"])] + turns
            interaction_id = rec["previous_id"]
        return turns

def create(provider, input, previous_interaction_id=None, store=True):
    contents = provider.history(previous_interaction_id) + [turn("user", input)]
    resp = client.models.generate_content(model=MODEL, contents=contents, config=config(60))
    provider.count += 1
    new_id = f"int_{provider.count:03d}"
    if store:
        provider.records[new_id] = {"previous_id": previous_interaction_id, "input": input,
                                    "output": resp.text.strip(), "expires": provider.now + provider.retention}
    print(new_id, "->", resp.text.strip())
    return new_id

# %% [markdown]
# `delete` removes one record, like `client.interactions.delete(id)`.

# %%
def delete(provider, interaction_id):
    provider.records.pop(interaction_id, None)

# %% [markdown]
# Two turns, then delete the first and continue from the second.

# %% tags=["needs-llm"]
store = ToyInteractionStore(retention_days=55)
first = create(store, "Hi, I'm Asha.")
second = create(store, "I study Mars rovers.", first)
delete(store, first)
try:
    create(store, "What is my name?", second)
except LookupError as err:
    print("cannot continue:", err)

# %% [markdown]
# It fails even though `int_002` still exists. `history` walks the chain backwards: `int_002` points to
# `int_001`, which is gone, so the history cannot be rebuilt. Deleting any turn breaks every later turn
# that chains through it. (How a real provider handles this is not stated in the docs we checked; test it
# before relying on it.)

# %% [markdown]
# ## Lesson 11
# Setup from lesson 11: the recorded timings of the streamed Mars answer (`../data/recorded/11.json`,
# recorded output from a live run). The answer finds the first chunk after which the joined text holds
# a sentence end.

# %%
import json
from pathlib import Path

timing = json.loads(Path("../data/recorded/11.json").read_text())

def first_sentence_at(texts, stream_times):
    so_far = ""
    for text, at in zip(texts, stream_times):
        so_far += text
        if any(mark in so_far for mark in ".!?"):
            return at
    return None

print("TTFT              :", timing["stream_times"][0], "s")
print("first sentence at :", first_sentence_at(timing["chunk_texts"], timing["stream_times"]), "s")
print("blocking total    :", timing["blocking_total"], "s")

# %% [markdown]
# The first full sentence arrives a little after the first token but well before the blocking call
# returns, so a voice assistant can start speaking early.

# %% [markdown]
# ## Lesson 12
# Setup from lesson 12: the price table, `cost_usd`, and the per-turn `(input, output, cost)` tuples of the
# lesson's 10-turn chat, which the lesson saved to `../data/recorded/12.json` (recorded output, no new calls).

# %%
PRICES_PER_MTOK = {"gemini-3.5-flash-lite": {"input": 0.30, "output": 2.50},
                   "gemini-3.8-flash": {"input": 0.75, "output": 3.75}}   # promo until 2026-12-31, then 1.50 / 7.50

def cost_usd(model, input_tokens, output_tokens):
    p = PRICES_PER_MTOK[model]
    return (input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000

turns = json.loads(Path("../data/recorded/12.json").read_text())
lite = sum(cost_usd("gemini-3.5-flash-lite", i, o) for i, o, _ in turns)
flash = sum(cost_usd("gemini-3.8-flash", i, o) for i, o, _ in turns)
print(f"flash-lite ${lite:.4f} | 3.8-flash ${flash:.4f} | x{flash / lite:.1f} dearer")
after = sum((i * 1.50 + o * 7.50) / 1_000_000 for i, o, _ in turns)    # 3.8-flash list price from 2027-01-01
print(f"after 2026-12-31: 3.8-flash ${after:.4f} | x{after / lite:.1f} dearer")

# %% [markdown]
# 2. Rebuild `chat_cost` from S, k and the average output, then step up one turn at a time.

# %%
inputs = [t[0] for t in turns]
S, k = inputs[0], (inputs[-1] - inputs[0]) / (len(inputs) - 1)
avg_out = sum(t[1] for t in turns) / len(turns)

def chat_cost(n):
    return cost_usd("gemini-3.5-flash-lite", round(n * S + k * n * (n - 1) / 2), round(n * avg_out))

n = 1
while chat_cost(n) <= 0.05:
    n += 1
print(f"first chat length over $0.05: {n} turns (${chat_cost(n):.4f})")

# %% [markdown]
# ## Lesson 13
# Setup from lesson 13: `classify` and `safe_call` (unchanged), then `summarise` retries once when cut.
# Test with the no-key stub `fake_call` first, then with the real `safe_call` (recorded here).

# %%
import uuid
from google.genai import errors

def classify(resp) -> str:
    if resp.prompt_feedback and resp.prompt_feedback.block_reason:
        return "blocked"
    if not resp.candidates:
        return "empty"
    reason = resp.candidates[0].finish_reason.value
    if reason == "MAX_TOKENS":
        return "cut"
    if reason in {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION"}:
        return "blocked"
    if reason == "MALFORMED_FUNCTION_CALL":
        return "bad_tool_call"
    return "ok" if reason == "STOP" and (resp.text or resp.function_calls) else "empty"

def safe_call(contents, max_output_tokens):
    call_id = uuid.uuid4().hex[:12]
    try:
        resp = client.models.generate_content(model=MODEL, contents=contents, config=config(max_output_tokens))
    except errors.APIError as e:
        kind = "retryable" if e.code == 429 or e.code >= 500 else "client_error"
        print(f"[{call_id}] {kind} {e.code} {e.status}")
        return kind, None
    status = classify(resp)
    print(f"[{call_id}] {status} response_id={resp.response_id}")
    return status, resp

# %%
def summarise(note_text, budget, call=safe_call):
    prompt = f"Summarise this note in one short sentence.\nNote: {note_text}"
    status, resp = call(prompt, budget)
    if status == "cut":
        status, resp = call(prompt, budget * 4)
    return resp.text if status == "ok" else None

class _Reply:            # stands in for the lesson's `ok` reply from step 2
    text = "Perseverance landed on Mars in February 2021."

def fake_call(prompt, budget):
    return ("cut", None) if budget < 20 else ("ok", _Reply())

print("stub, budget 8:", summarise("The rover Perseverance landed on Mars in February 2021.", 8, call=fake_call))
print("stub, budget 2:", summarise("The rover Perseverance landed on Mars in February 2021.", 2, call=fake_call))

print(summarise("The rover Perseverance landed on Mars in February 2021.", 8))

# %%
llm_replay.stop()

# %% [markdown]
# ## Lesson 14
# No model calls and no server: the fake `send` from the lesson stands in for the provider. The recorder
# is stopped above, so nothing here touches the cassette. Setup from lesson 14: `retry_decision`,
# `backoff_delay` and `GiveUp`.

# %%
import random, time

class GiveUp(Exception):
    pass

def retry_decision(status, body):
    if status == 200:
        return False, "ok"
    if status is None:
        return True, "timeout or network error"
    details = (body.get("error") or {}).get("details") or {}
    if isinstance(details, dict) and details.get("error_code") == "enforced_spend_limit_reached":
        return False, "spend cap reached: wait for next month"
    if status in (408, 429) or status >= 500:
        return True, f"{status}: temporary"
    return False, f"{status}: fix the request"

def backoff_delay(attempt, base=0.5, cap=8.0, rng=random):
    return rng.uniform(0, min(cap, base * 2 ** attempt))

# %% [markdown]
# The answer: add up the waits, and check the budget **before** sleeping.

# %%
def call_with_budget(send, max_wait_s, max_attempts=4, rng=random.Random(14)):
    waited = 0.0
    for attempt in range(max_attempts):
        status, headers, body = send()
        retry, why = retry_decision(status, body)
        if status == 200:
            return body
        if not retry or attempt == max_attempts - 1:
            raise GiveUp(why)
        ra = headers.get("retry-after")
        wait = float(ra) if ra else backoff_delay(attempt, rng=rng)
        if waited + wait > max_wait_s:
            raise GiveUp("wait budget exhausted")
        time.sleep(wait)
        waited += wait
        print(f"  waited {wait:.1f}s (total {waited:.1f}s)")

# %% [markdown]
# Test it with the lesson's fake `send`.

# %%
def make_flaky():
    n = [0]
    def send():
        n[0] += 1
        if n[0] <= 2:
            return 429, {"retry-after": "1"}, {"error": {"type": "rate_limit_error"}}
        return 200, {}, {"text": "Perseverance landed on Mars in February 2021."}
    return send

print("budget 3.0:", call_with_budget(make_flaky(), 3.0))
try:
    call_with_budget(make_flaky(), 1.5)
except GiveUp as e:
    print("budget 1.5: gave up:", e)

# %% [markdown]
# ## Lesson 17
# No model calls: the recorded results from the lesson (`../data/recorded/17.json`) stand in for `results`.
# Setup from lesson 17: the dated price table, `cost_usd`, `summarise` and `choose`.

# %%
import json, pathlib
from datetime import date
from statistics import mean

FAMILY_17 = [("small", "gemini-3.5-flash-lite"), ("medium", "gemini-3.8-flash"), ("large", "gemini-3.1-pro-preview")]
PRICES_17 = {"gemini-3.5-flash-lite": [(date(2026, 1, 1), 0.30, 2.50)],
             "gemini-3.8-flash": [(date(2026, 1, 1), 0.75, 3.75), (date(2027, 1, 1), 1.50, 7.50)],
             "gemini-3.1-pro-preview": [(date(2026, 1, 1), 2.00, 12.00)]}

def cost_17(model, tokens_in, tokens_out, day):
    _, p_in, p_out = [r for r in PRICES_17[model] if r[0] <= day][-1]
    return (tokens_in * p_in + tokens_out * p_out) / 1_000_000

results_17 = json.loads(pathlib.Path("../data/recorded/17.json").read_text())

def summarise_17(results, day):
    rows = []
    for task in ("lookup", "math"):
        for size, model in FAMILY_17:
            rs = [r for r in results if r["task"] == task and r["model"] == model]
            rows.append({"task": task, "size": size, "model": model, "passed": sum(r["ok"] for r in rs),
                         "runs": len(rs), "seconds": mean(r["seconds"] for r in rs),
                         "cost": mean(cost_17(model, r["in"], r["out"], day) for r in rs)})
    return rows

def choose_17(table, task, max_seconds=30.0):
    ok = [t for t in table if t["task"] == task and t["passed"] == t["runs"] and t["seconds"] <= max_seconds]
    return min(ok, key=lambda t: t["cost"]) if ok else None

# %% [markdown]
# **1.** Re-price every run at January 2027 prices. Medium doubles, but it still costs far less than large,
# and small still fails, so the choice for "math" does not change.

# %%
jan = summarise_17(results_17, date(2027, 1, 15))
for t in (t for t in jan if t["task"] == "math"):
    print(f"{t['size']:<7}${t['cost'] * 300_000:>9,.2f} a month   passed {t['passed']}/{t['runs']}")
print("math ->", choose_17(jan, "math")["model"])

# %% [markdown]
# **2.** With a 2-second budget, only the small model is fast enough. It passed the look-up, so "lookup"
# still gets flash-lite, but it fails math, so no model qualifies for "math". Options: improve the prompt
# until the small model passes, stream the answer so the user sees text sooner (lesson 11), or renegotiate
# the budget. Never quietly ship the failing model.

# %%
oct_table = summarise_17(results_17, date(2026, 10, 8))
for task in ("lookup", "math"):
    best = choose_17(oct_table, task, max_seconds=2.0)
    print(f"{task:<7}-> {best['model'] if best else 'no model qualifies'}")

# %% [markdown]
# ## Lesson 18
# No model calls: the scripted `FakeBackend` stands in for Gemini, and the recorder is stopped above.
# Setup from lesson 18 (condensed): Scout's system message, cost and `Ledger`, the fake backend, and the
# reference `fit_to_window`, `open_stream` and `chat_turn`.

# %%
import random, re, time
from google.genai import errors

NOTES_18 = ["Mars has two small moons, Phobos and Deimos.", "Venus spins backwards compared with most planets.",
            "A day on Mars lasts about 24 hours and 39 minutes.", "Jupiter is the largest planet in the solar system.",
            "The rover Perseverance landed on Mars in February 2021.", "Saturn's rings are mostly made of ice."]
SYSTEM_18 = {"role": "system", "text": "You are Scout, a research assistant. Answer only from the user's notes "
             "below and this chat. If the notes do not cover it, say so in one sentence. Keep answers to one "
             "sentence.\n\n" + "\n".join(f"Note {i}: {t}" for i, t in enumerate(NOTES_18, 1))}
WINDOW_18, MAX_OUTPUT_18, MODEL_18 = 2_000, 120, "gemini-3.5-flash-lite"

def to_gemini_18(messages):
    roles = {"user": "user", "assistant": "model"}
    return messages[0]["text"], [types.Content(role=roles[m["role"]], parts=[types.Part(text=m["text"])])
                                 for m in messages[1:]]

def cost_18(tokens_in, tokens_out):
    return (tokens_in * 0.30 + tokens_out * 2.50) / 1_000_000

class Ledger18:
    def __init__(self):
        self.turns = []
    def add(self, tokens_in, tokens_out):
        self.turns.append((tokens_in, tokens_out, cost_18(tokens_in, tokens_out)))
        return self.turns[-1][2]
    @property
    def total(self):
        return sum(t[2] for t in self.turns)

# %% [markdown]
# The fake backend from lesson 18 (well-behaved version only: no forced failures).

# %%
def word_tokens_18(text):
    return len(re.findall(r"[\w']+|[.,!?]", text))

def chunk_18(text=None, finish=None, tokens_in=0, tokens_out=0):
    parts = [types.Part(text=text)] if text else []
    usage = types.GenerateContentResponseUsageMetadata(
        prompt_token_count=tokens_in, candidates_token_count=tokens_out) if finish else None
    cand = types.Candidate(content=types.Content(role="model", parts=parts), finish_reason=finish)
    return types.GenerateContentResponse(candidates=[cand], usage_metadata=usage)

class FakeBackend18:
    def count(self, system, contents):
        return word_tokens_18(system) + sum(1 + word_tokens_18(c.parts[0].text) for c in contents)
    def stream(self, system, contents, max_output):
        user = [c.parts[0].text for c in contents if c.role == "user"][-1]
        words = {w.lower() for w in re.findall(r"[\w']+", user)}
        best = max(NOTES_18, key=lambda n: len(words & {w.lower() for w in re.findall(r"[\w']+", n)}))
        reply = ("From the notes: " + best).split(" ")[:max_output]
        for i in range(0, len(reply), 3):
            yield chunk_18(" ".join(reply[i:i + 3]) + " ")
        yield chunk_18(finish="STOP", tokens_in=self.count(system, contents), tokens_out=len(reply))

# %% [markdown]
# Lesson 18's reference `fit_to_window`, `open_stream` and `chat_turn`, condensed.

# %%
def fit_to_window_18(backend, messages, window, max_output):
    system, rest = messages[0], messages[1:]
    while True:
        n_in = backend.count(*to_gemini_18([system] + rest))
        if n_in <= window - max_output or len(rest) <= 1:
            return [system] + rest
        rest = rest[2:]

def open_stream_18(backend, system, contents, max_output, max_attempts=4, rng=random.Random(18)):
    for attempt in range(max_attempts):
        try:
            stream = backend.stream(system, contents, max_output)
            return next(stream), stream
        except errors.APIError as e:
            if e.code not in {408, 429, 500, 502, 503, 504} or attempt == max_attempts - 1:
                raise
            time.sleep(rng.uniform(0, min(8.0, 0.5 * 2 ** attempt)))

def chat_turn_18(backend, history, user_text, ledger, window=WINDOW_18, max_output=MAX_OUTPUT_18):
    history.append({"role": "user", "text": user_text})
    first, stream = open_stream_18(backend, *to_gemini_18(fit_to_window_18(backend, history, window, max_output)), max_output)
    chunks = [first] + list(stream)
    text = "".join(ch.text or "" for ch in chunks).strip()
    u = chunks[-1].usage_metadata
    cost = ledger.add(u.prompt_token_count or 0, u.candidates_token_count or 0)
    print(f"scout> {text}\n       ${cost:.5f} this turn, ${ledger.total:.5f} so far")
    history.append({"role": "assistant", "text": text})

# %% [markdown]
# **Answer.** Before each turn, count the request as it would be sent (history plus the new line) and price
# it with `MAX_OUTPUT` output tokens: that is the most the turn can cost (lesson 12). If the total so far
# plus that worst case would pass the budget, refuse and stop. The untrimmed count is used, which can only
# over-estimate, so the cap is never broken.

# %%
def chat_loop_capped(backend, inputs, budget_usd, max_output=MAX_OUTPUT_18):
    history, ledger = [SYSTEM_18], Ledger18()
    for line in inputs:
        if line.strip() == "/quit":
            break
        worst = cost_18(backend.count(*to_gemini_18(history + [{"role": "user", "text": line}])), max_output)
        if ledger.total + worst > budget_usd:
            print(f"  ! budget reached: ${ledger.total:.5f} spent, the next turn could cost up to ${worst:.5f}")
            break
        print(f"you>   {line}")
        chat_turn_18(backend, history, line, ledger, max_output=max_output)
    return history, ledger

# %% [markdown]
# To pick a budget that allows exactly two turns, first look at the worst cases. Then run with a budget
# between "two turns" and "three turns".

# %%
LINES_18 = ["How long is a day on Mars?", "Which rover landed on Mars in 2021?", "What are Saturn's rings made of?"]
_, ledger_all = chat_loop_capped(FakeBackend18(), LINES_18, budget_usd=1.0)
print("actual costs:", [round(t[2], 6) for t in ledger_all.turns])

# %% [markdown]
# Each turn really costs well under $0.0001, but the worst case is about $0.00035, because 120 output
# tokens are reserved at the output price. Two turns spent plus a third worst case is about $0.00049,
# so a budget of $0.00045 allows exactly two turns.

# %%
history_capped, ledger_capped = chat_loop_capped(FakeBackend18(), LINES_18, budget_usd=0.00045)
print(len(ledger_capped.turns), "turns run, total", f"${ledger_capped.total:.5f}")

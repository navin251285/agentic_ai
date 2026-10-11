# %% [markdown]
# # Solutions · Part 5: Inside the loop: measuring and tuning
# Answers to the "Try it" exercises. Try each one yourself first.

# %%
import json
import jiter

# %% [markdown]
# ## Lesson 36
# Setup from lesson 36: the fake Anthropic-style event stream and the `SAVE` reply, unchanged.

# %%
def end(reason: str, used: int):
    yield {"type": "message_delta", "delta": {"stop_reason": reason}, "usage": {"output_tokens": used}}
    yield {"type": "message_stop"}

def fake_events(reply: dict, piece: int = 12, max_tokens: int = 10_000, turn: int = 1):
    blocks = ([("text", reply["text"])] if reply.get("text") else []) + [
        (c, json.dumps(c["args"])) for c in reply.get("tool_calls", [])]
    used = 0
    yield {"type": "message_start", "message": {"role": "assistant", "content": []}}
    for index, (kind, body) in enumerate(blocks):
        start = ({"type": "text", "text": ""} if kind == "text" else
                 {"type": "tool_use", "id": f"toolu_{turn}{index}", "name": kind["name"], "input": {}})
        yield {"type": "content_block_start", "index": index, "content_block": start}
        for i in range(0, len(body), piece):
            if used == max_tokens:  # cut stream: the docs do not say whether a stop event arrives
                yield from end("max_tokens", used); return
            used += 1
            delta = ({"type": "text_delta", "text": body[i:i + piece]} if kind == "text" else
                     {"type": "input_json_delta", "partial_json": body[i:i + piece]})
            yield {"type": "content_block_delta", "index": index, "delta": delta}
        yield {"type": "content_block_stop", "index": index}
    yield from end("tool_use" if reply.get("tool_calls") else "end_turn", used)

SAVE = {"text": "Saving it now.", "tool_calls": [{"name": "write_file", "args": {
    "filename": "mars_day.txt", "text": "A day on Mars lasts about 1479 minutes."}}]}

# %% [markdown]
# `partial_mode=True` drops an unfinished trailing string, so every string it returns is complete.
# (A trailing number could still grow, e.g. `12` becoming `120`; Scout's file arguments are strings.)

# %%
def final_fields(buffer: str) -> dict:
    return jiter.from_json(buffer.encode(), partial_mode=True) if buffer.strip() else {}

buffer, k = "", 0  # k counts only the argument deltas (input_json_delta), starting at 1
for ev in fake_events(SAVE, piece=4):
    if ev["type"] == "content_block_delta" and ev["delta"]["type"] == "input_json_delta":
        k += 1
        buffer += ev["delta"]["partial_json"]
        ready = final_fields(buffer)
        print(f"delta {k:2}: {buffer[-20:]!r:24} final: {ready}")
        if "filename" in ready:
            print(f"Saving to {ready['filename']}...  (file name final at delta {k})")
            break

# %% [markdown]
# ## Lesson 37
# Setup from lesson 37: `check_reply` and the neutral messages of the fake run (`RESULTS["fake"]["messages"]`).

# %%
def check_reply(reply: dict) -> dict:
    assert reply.get("role") == "assistant", f"role must be 'assistant', got {reply.get('role')!r}"
    calls = reply.get("tool_calls", [])
    assert calls or isinstance(reply.get("text"), str), "a reply needs text or tool_calls"
    for c in calls:
        assert isinstance(c.get("id"), str) and c["id"], f"tool call without an id: {c}"
        assert isinstance(c.get("args"), dict), f"args must be a dict, got {type(c.get('args')).__name__}"
    return reply

def call(i, name, args): return {"role": "assistant", "tool_calls": [{"id": f"call_{i}", "name": name, "args": args}]}
def result(i, name, content): return {"role": "tool", "call_id": f"call_{i}", "name": name, "content": content, "is_error": False}
FAKE_MESSAGES = [
    {"role": "user", "text": "How many minutes long is a day on Mars? Save the answer to mars_day.txt."},
    call(1, "search_notes", {"query": "day on Mars"}),
    result(1, "search_notes", '[{"id": 3, "text": "A day on Mars lasts about 24 hours and 39 minutes."}]'),
    call(2, "calculator", {"expression": "24*60+39"}), result(2, "calculator", "1479"),
    call(3, "write_file", {"filename": "mars_day.txt", "text": "A day on Mars lasts about 1479 minutes."}),
    result(3, "write_file", '"saved 39 characters to mars_day.txt"'),
    {"role": "assistant", "text": "A day on Mars lasts about 1479 minutes. Saved to mars_day.txt."},
]

# %% [markdown]
# The request half: `arguments` becomes a JSON string, and a tool result is a `tool` message linked by
# `tool_call_id`.

# %%
def to_chat(messages: list[dict], system: str) -> list[dict]:
    out = [{"role": "system", "content": system}]
    for m in messages:
        if m["role"] == "user":
            out.append({"role": "user", "content": m["text"]})
        elif m["role"] == "assistant" and m.get("tool_calls"):
            out.append({"role": "assistant", "content": None, "tool_calls": [
                {"id": c["id"], "type": "function",
                 "function": {"name": c["name"], "arguments": json.dumps(c["args"])}} for c in m["tool_calls"]]})
        elif m["role"] == "assistant":
            out.append({"role": "assistant", "content": m["text"]})
        else:
            out.append({"role": "tool", "tool_call_id": m["call_id"], "content": m["content"]})
    return out

def from_chat(message: dict) -> dict:
    calls = [{"id": tc["id"], "name": tc["function"]["name"], "args": json.loads(tc["function"]["arguments"])}
             for tc in message.get("tool_calls") or []]
    reply = {"tool_calls": calls} if calls else {"text": message.get("content") or ""}
    return check_reply({"role": "assistant", **reply})

# %% [markdown]
# The round trip: every assistant turn converted to chat format and back must equal the original.

# %%
chat = to_chat(FAKE_MESSAGES, "You are Scout.")
print([m["role"] for m in chat])
print(chat[2]["tool_calls"][0])
originals = [m for m in FAKE_MESSAGES if m["role"] == "assistant"]
back = [from_chat(m) for m in chat if m["role"] == "assistant"]
print("round trip equal:", back == originals)
print("tool_call_ids:", [m["tool_call_id"] for m in chat if m["role"] == "tool"])

# %% [markdown]
# ## Lesson 38
# Setup from lesson 38, compact: notes, tools, the 50 questions, the scripted replies, the token bucket,
# the stub provider, the async loop and `run_batch` (semaphore + shared limiter).

# %%
import ast, asyncio, math, operator, random, time

NOTES_38 = ["Mars has two small moons, Phobos and Deimos.", "Venus spins backwards compared with most planets.",
            "A day on Mars lasts about 24 hours and 39 minutes.", "Jupiter is the largest planet in the solar system.",
            "The rover Perseverance landed on Mars in February 2021.", "Saturn's rings are mostly made of ice."]
NOTES_38 = [{"id": i, "text": t} for i, t in enumerate(NOTES_38, 1)]
OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
def evaluate(n):
    if isinstance(n, ast.Constant) and type(n.value) in (int, float):
        return n.value
    return OPS[type(n.op)](evaluate(n.left), evaluate(n.right))
TOOLS_38 = {"search_notes": lambda query: [n for n in NOTES_38 if all(w in n["text"].lower() for w in query.lower().split())],
            "calculator": lambda expression: evaluate(ast.parse(expression, mode="eval").body)}
def run_tool(call, tools):
    try:
        return {"content": json.dumps(tools[call["name"]](**call["args"])), "is_error": False}
    except Exception as e:
        return {"content": f"{type(e).__name__}: {e}", "is_error": True}

TOPICS = [("Mars's moons", "moons"), ("Venus", "backwards"), ("Jupiter", "largest"),
          ("Perseverance", "Perseverance"), ("Saturn's rings", "rings")]
QUESTIONS = [{"id": i, "text": f"Q{i:02d}: How many minutes long is a day on Mars?", "query": "day on Mars", "math": True}
             if i % 3 == 0 else {"id": i, "text": f"Q{i:02d}: What do my notes say about {TOPICS[i % 5][0]}?",
                                 "query": TOPICS[i % 5][1], "math": False} for i in range(50)]
BY_TEXT = {q["text"]: q for q in QUESTIONS}

def scripted_reply(q, messages):
    results = [json.loads(m["content"]) for m in messages if m["role"] == "tool"]
    cid = f"q{q['id']}_call{len(results) + 1}"
    if not results:
        return {"role": "assistant", "tool_calls": [{"id": cid, "name": "search_notes", "args": {"query": q["query"]}}]}
    if q["math"] and len(results) == 1:
        return {"role": "assistant", "tool_calls": [{"id": cid, "name": "calculator", "args": {"expression": "24*60+39"}}]}
    return {"role": "assistant", "text": str(results[-1])}

# %%
class TokenBucket:
    def __init__(self, rate, capacity):
        self.rate, self.capacity, self.tokens, self.last = rate, capacity, float(capacity), time.monotonic()
    def try_take(self):
        now = time.monotonic()
        self.tokens, self.last = min(self.capacity, self.tokens + (now - self.last) * self.rate), now
        if self.tokens >= 1:
            self.tokens -= 1
            return 0.0
        return (1 - self.tokens) / self.rate

class RateLimited(Exception):
    def __init__(self, retry_after):
        super().__init__("429"); self.retry_after = retry_after

def stub_latency(qid, step):
    rng = random.Random(qid * 10 + step)
    return 0.04 + rng.expovariate(1 / 0.02) + (0.4 if rng.random() < 0.05 else 0.0)

class StubProvider:
    def __init__(self, rate=50, burst=10):
        self.bucket, self.calls, self.rejected = TokenBucket(rate, burst), 0, 0
    async def __call__(self, messages):
        if (wait := self.bucket.try_take()) > 0:
            self.rejected += 1
            raise RateLimited(wait)
        self.calls += 1
        q = BY_TEXT[messages[0]["text"]]
        await asyncio.sleep(stub_latency(q["id"], sum(m["role"] == "assistant" for m in messages) + 1))
        return scripted_reply(q, messages)

class AsyncRateLimiter:
    def __init__(self, rate, capacity):
        self.bucket, self.lock = TokenBucket(rate, capacity), asyncio.Lock()
    async def acquire(self):
        async with self.lock:
            while (wait := self.bucket.try_take()) > 0:
                await asyncio.sleep(wait)

# %%
async def run_agent_async(question, provider, limiter):
    messages = [{"role": "user", "text": question}]
    for _ in range(8):
        while True:
            await limiter.acquire()
            try:
                reply = await provider(messages); break
            except RateLimited as e:
                await asyncio.sleep(e.retry_after)
        messages.append(reply)
        if not reply.get("tool_calls"):
            return reply["text"]
        for call in reply["tool_calls"]:
            res = await asyncio.to_thread(run_tool, call, TOOLS_38)
            messages.append({"role": "tool", "call_id": call["id"], **res})

async def run_batch(questions, concurrency, limiter):
    provider, sem, latencies = StubProvider(), asyncio.Semaphore(concurrency), []
    async def one(q):
        async with sem:
            t0 = time.perf_counter()
            await run_agent_async(q["text"], provider, limiter)
            latencies.append(time.perf_counter() - t0)
    start = time.perf_counter()
    await asyncio.gather(*(one(q) for q in questions))
    return time.perf_counter() - start, latencies, provider.rejected

def percentile(values, p):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(p / 100 * len(ordered)) - 1)]

# %% [markdown]
# The answer: sweep the concurrency with a fresh shared limiter each time, then pick the knee.

# %%
sweep = []
for n in (1, 2, 5, 10, 20, 40):
    wall, lat, rejected = await run_batch(QUESTIONS, n, AsyncRateLimiter(45, 5))
    sweep.append((n, 50 / wall, percentile(lat, 95)))
    print(f"conc {n:>2}: {50 / wall:5.1f} conv/s | p95 {percentile(lat, 95):.3f} s | 429s {rejected}")
best = max(t for _, t, _ in sweep)
knee = min(n for n, t, _ in sweep if t >= 0.9 * best)
print(f"best {best:.1f} conv/s; smallest concurrency within 10 %: {knee}")

# %% [markdown]
# Past the knee the rate limit is the bottleneck: throughput stays flat, but conversations wait in the
# limiter's queue, so p95 grows. The knee gives (almost) the same throughput with lower latency and
# fewer open connections, and leaves headroom for retries and other traffic.

# %% [markdown]
# ## Lesson 39
# Setup from lesson 39, compact: two tools with side effects, the key ledger, checkpoints, the resumable
# loop and Scout's history-driven fake. Own folders, so the lesson's files are not touched.

# %%
import os, shutil
from collections import Counter
from pathlib import Path

SCOUT_DIR, RUNS_DIR = Path("../data/scout_files_39s"), Path("../data/runs_39s")
LEDGER, EFFECTS = SCOUT_DIR / ".keys.json", Counter()
def reset():
    for d in (SCOUT_DIR, RUNS_DIR):
        shutil.rmtree(d, ignore_errors=True); d.mkdir(parents=True)
    EFFECTS.clear()
def write_file(filename, text):
    (SCOUT_DIR / filename).write_text(text); EFFECTS["write_file"] += 1
    return f"saved {len(text)} characters to {filename}"
def append_file(filename, text):
    with (SCOUT_DIR / filename).open("a") as f: f.write(text + "\n")
    EFFECTS["append_file"] += 1
    return f"added 1 line to {filename}"
def lines(name):
    p = SCOUT_DIR / name
    return p.read_text().splitlines() if p.exists() else []

# %%
def idempotent(fn):
    def wrapper(idempotency_key=None, **args):
        seen = json.loads(LEDGER.read_text()) if LEDGER.exists() else {}
        if idempotency_key in seen:
            print(f"  {fn.__name__}: key {idempotency_key!r} seen before -> saved result")
            return seen[idempotency_key]["result"]
        result = fn(**args)
        seen[idempotency_key] = {"args": args, "result": result}
        LEDGER.write_text(json.dumps(seen))
        return result
    wrapper.__name__ = fn.__name__
    return wrapper

TOOLS_ONCE = {"search_notes": lambda query: [{"id": 3, "text": "A day on Mars lasts about 24 hours and 39 minutes."}],
              "calculator": lambda expression: 24 * 60 + 39,
              "write_file": idempotent(write_file), "append_file": idempotent(append_file)}
SIDE_EFFECTS = {"write_file", "append_file"}

# %%
def run_tool_keyed(call, tools, key):
    args = {**call["args"], "idempotency_key": key} if call["name"] in SIDE_EFFECTS else call["args"]
    try:
        return {"content": json.dumps(tools[call["name"]](**args)), "is_error": False}
    except Exception as e:
        return {"content": f"{type(e).__name__}: {e}", "is_error": True}

def save_checkpoint(run_id, state):
    path = RUNS_DIR / f"{run_id}.json"; tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state)); os.replace(tmp, path)
def load_checkpoint(run_id):
    path = RUNS_DIR / f"{run_id}.json"
    return json.loads(path.read_text()) if path.exists() else None
def pending_calls(messages):
    turns = [i for i, m in enumerate(messages) if m["role"] == "assistant"]
    if not turns: return []
    answered = {m["call_id"] for m in messages[turns[-1] + 1:] if m["role"] == "tool"}
    return [(i, c) for i, c in enumerate(messages[turns[-1]].get("tool_calls", [])) if c["id"] not in answered]

# %%
def run_agent_resumable(run_id, question, model, tools, max_steps=8):
    state = load_checkpoint(run_id) or {"run_id": run_id, "messages": [{"role": "user", "text": question}]}
    messages = state["messages"]
    while True:
        step = sum(m["role"] == "assistant" for m in messages)
        for i, call in pending_calls(messages):
            key = f"{run_id}:step{step}:call{i}"
            result = run_tool_keyed(call, tools, key)
            print(f"step {step}: {call['name']} key={key} -> {result['content'][:40]}")
            messages.append({"role": "tool", "call_id": call["id"], "name": call["name"], **result})
            save_checkpoint(run_id, state)
        if messages[-1]["role"] == "assistant":
            return {"answer": messages[-1]["text"], "stop": "end_of_turn", "steps": step}
        if step == max_steps:
            return {"answer": None, "stop": "step_limit", "steps": step}
        messages.append(model(messages)); save_checkpoint(run_id, state)

def tool(name, **args): return [{"name": name, "args": args}]
def scout_model(messages):
    """Stateless fake: decides from the history; call ids continue after those already issued."""
    results = [json.loads(m["content"]) for m in messages if m["role"] == "tool"]
    n_ids = sum(len(m.get("tool_calls", [])) for m in messages)
    plan = [tool("search_notes", query="day on Mars"), tool("calculator", expression="24*60+39"),
            tool("write_file", filename="mars_day.txt", text="A day on Mars lasts about 1479 minutes."),
            tool("append_file", filename="journal.txt", text="saved mars_day.txt")]
    if len(results) < len(plan):
        return {"role": "assistant", "tool_calls": [{**c, "id": f"call_{n_ids + 1}"} for c in plan[len(results)]]}
    return {"role": "assistant", "text": f"A day on Mars lasts about {results[1]} minutes."}

# %% [markdown]
# The answer: wrap `append_file` so the process dies right after it, run, then resume with the normal
# tools.

# %%
class Killed(BaseException):
    pass
def die_after(fn):
    def wrapper(**args):
        fn(**args)
        raise Killed(f"killed right after {fn.__name__}")
    return wrapper

reset()
doomed = {**TOOLS_ONCE, "append_file": die_after(TOOLS_ONCE["append_file"])}
try:
    run_agent_resumable("run-99", "Mars day?", scout_model, doomed)
except Killed as e:
    print("KILLED:", e)
run = run_agent_resumable("run-99", "Mars day?", scout_model, TOOLS_ONCE)
print(run["stop"], "|", run["answer"], "| effects:", dict(EFFECTS), "| journal:", lines("journal.txt"))
assert run["stop"] == "end_of_turn" and lines("journal.txt") == ["saved mars_day.txt"]
assert EFFECTS == Counter({"write_file": 1, "append_file": 1})

# %% [markdown]
# The resumed `append_file` call used key `run-99:step4:call0`, the same one the killed run saved in the
# ledger, so the journal line was not written again.

# %% [markdown]
# ## Lesson 40
# Setup from lesson 40: the price table, `cost_usd`, the benchmark results saved by the recording run
# (`../data/recorded/40.json`, recorded output) and the Anthropic request from step 9.

# %%
import copy, pathlib
PRICES_PER_MTOK_40 = {"gemini-3.5-flash-lite": {"input": 0.30, "output": 2.50}}   # USD, 2026-10-06
def cost_usd_40(model: str, input_tokens: int, output_tokens: int) -> float:
    price = PRICES_PER_MTOK_40[model]
    return (input_tokens * price["input"] + output_tokens * price["output"]) / 1_000_000

results_40 = json.loads(pathlib.Path("../data/recorded/40.json").read_text())["bench"]
claude_reply = [{"type": "thinking", "thinking": "", "signature": "EosnCkYICxIMMb3LzNrMu..."},
                {"type": "tool_use", "id": "toolu_01", "name": "search_notes", "input": {"query": "day on Mars"}}]
next_request = {"messages": [
    {"role": "user", "content": "How many minutes long is a day on Mars?"},
    {"role": "assistant", "content": claude_reply},
    {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_01", "content": "{}"}]}]}
print({level: len(rows) for level, rows in results_40.items()})

# %% [markdown]
# **1.** Cost per correct answer, and the thinking share of the bill.

# %%
def level_cost(rows: list[dict]) -> tuple[float, float]:
    calls = [c for r in rows for c in r["calls"]]
    tin, tout, tthink = (sum(c[k] for c in calls) for k in ("in", "out", "thoughts"))
    return cost_usd_40("gemini-3.5-flash-lite", tin, tout + tthink), cost_usd_40("gemini-3.5-flash-lite", 0, tthink)

for level, rows in results_40.items():
    total, think = level_cost(rows)
    correct = sum(r["correct"] for r in rows)
    print(f"{level:4}: ${total / max(correct, 1):.6f} per correct answer ({correct}/10) | thinking {think / total:.0%}")

# %% [markdown]
# **2.** 5,000 questions a day for 30 days: cost per question times 150,000.

# %%
for level, rows in results_40.items():
    per_question = level_cost(rows)[0] / len(rows)
    print(f"{level:4}: ${per_question * 5_000 * 30:,.2f} per month")

# %% [markdown]
# **3.** `check_resent`: the last assistant message must repeat the previous reply exactly.

# %%
def check_resent(previous_reply: list[dict], next_messages: list[dict]) -> None:
    last = [m for m in next_messages if m["role"] == "assistant"][-1]
    if last["content"] != previous_reply:
        raise ValueError("the assistant turn was changed: thinking blocks must be sent back unchanged")

check_resent(claude_reply, next_request["messages"])
print("unchanged history: ok")
broken = copy.deepcopy(next_request["messages"])
broken[1]["content"] = [b for b in broken[1]["content"] if b["type"] != "thinking"]
try:
    check_resent(claude_reply, broken)
except ValueError as e:
    print("dropped thinking block:", e)

# %% [markdown]
# ## Lesson 41
# Setup from lesson 41, unchanged: token counter, Scout's long prompt, the `PrefixCache` simulator,
# `sim_chat`, `hit_rate`, the Gemini price table and the recorded real usage.

# %%
import hashlib, os, random
os.environ["TIKTOKEN_CACHE_DIR"] = "../data/tiktoken_cache"
import tiktoken
ENC = tiktoken.get_encoding("o200k_base")
def tokens(text): return len(ENC.encode(text))
rng = random.Random(31)
def rover_log(first_sol, n):
    return "\n".join(f"Sol {s}: drove {rng.randint(0, 120)} m, wind {rng.randint(1, 15)} m/s, dust opacity "
                     f"{rng.uniform(0.2, 1.5):.2f}, battery {rng.randint(40, 100)}%, photos {rng.randint(0, 60)}."
                     for s in range(first_sol, first_sol + n))
NOTEBOOKS = {1: rover_log(1, 100), 2: rover_log(101, 100),
             3: rover_log(201, 55) + "\nReminder for the talk: a day on Mars (a sol) lasts 24 hours and 39 minutes."}
def schema(name, description, prop, kind):
    return {"name": name, "description": description,
            "parameters": {"type": "object", "required": [prop], "properties": {prop: {"type": kind}}}}
SCHEMAS = [schema("search_notes", "Search the notebooks; returns id, title and size.", "query", "string"),
           schema("read_note", "Return the full text of one notebook by id.", "note_id", "integer"),
           schema("calculator", "Evaluate arithmetic with + - * / and brackets.", "expression", "string")]
RULES = ("You are Scout, a research assistant. Answer only from the field notebooks below. "
         "Answer in one short sentence and quote the sol number.")
SYSTEM_LONG = RULES + "\n\n" + "\n\n".join(f"# Notebook {i}\n{t}" for i, t in NOTEBOOKS.items())

# %%
CACHE_RULES = {"model": "claude-sonnet-5-5", "input": 2.00, "output": 10.00, "write": {"5m": 1.25, "1h": 2.0},
               "read": 0.05, "min_tokens": 512, "max_breakpoints": 4, "lookback": 20}
TTL_SECONDS = {"5m": 300, "1h": 3600}
def prefix_key(blocks): return hashlib.sha256(json.dumps([b["text"] for b in blocks]).encode()).hexdigest()

class PrefixCache:
    def __init__(self, rules=CACHE_RULES):
        self.rules, self.store = rules, {}
    def call(self, blocks, now):
        bps = [i for i, b in enumerate(blocks) if b.get("cache")]
        if len(bps) > self.rules["max_breakpoints"]:
            raise ValueError(f"{len(bps)} cache breakpoints; the API allows {self.rules['max_breakpoints']}")
        sizes = [tokens(b["text"]) for b in blocks]
        read, last = 0, (bps[-1] if bps else -1)
        for i in range(last, max(last - self.rules["lookback"], -1), -1):
            if self.store.get(prefix_key(blocks[:i + 1]), -1) >= now:
                read = sum(sizes[:i + 1])
                break
        written = 0
        for i in bps:
            n, ttl = sum(sizes[:i + 1]), blocks[i]["cache"]
            if n >= self.rules["min_tokens"]:
                self.store[prefix_key(blocks[:i + 1])] = now + TTL_SECONDS[ttl]
                written = max(written, n - read)
        return {"input": sum(sizes) - read - written, "cache_write": written, "cache_read": read}

# %%
def build_request(messages, system=SYSTEM_LONG, ttl="5m"):
    blocks = [{"text": json.dumps(SCHEMAS)}, {"text": system, "cache": ttl}]
    blocks += [{"text": f"{m['role']}: {m['text']}"} for m in messages]
    blocks[-1] = {**blocks[-1], "cache": ttl}
    return blocks
QUESTIONS = ["How far did the rover drive on sol 12?", "What was the battery level on sol 150?",
             "Which sol had the most photos in notebook 3?", "How long is a day on Mars?",
             "What was the dust opacity on sol 77?"]
def cost_cached(u, out_tokens, rules=CACHE_RULES, ttl="5m"):
    return (u["input"] * rules["input"] + u["cache_write"] * rules["input"] * rules["write"][ttl]
            + u["cache_read"] * rules["input"] * rules["read"] + out_tokens * rules["output"]) / 1_000_000
def sim_chat(cache, make_user_text=lambda q, t: q, system_at=lambda t: SYSTEM_LONG, gap_s=30, ttl="5m"):
    messages, rows = [], []
    for turn, q in enumerate(QUESTIONS):
        now = turn * gap_s
        messages.append({"role": "user", "text": make_user_text(q, now)})
        u = cache.call(build_request(messages, system_at(now), ttl), now)
        rows.append({**u, "cost": cost_cached(u, 20, ttl=ttl)})
        messages.append({"role": "assistant", "text": f"(answer {turn + 1}, about twenty tokens long)"})
    return rows
def hit_rate(rows):
    return sum(r["cache_read"] for r in rows) / sum(r["input"] + r["cache_write"] + r["cache_read"] for r in rows)
PRICES_PER_MTOK = {"gemini-3.5-flash-lite": {"input": 0.30, "cached": 0.03, "output": 2.50}}
def gemini_cost(prompt, cached, out, model="gemini-3.5-flash-lite"):
    p = PRICES_PER_MTOK[model]
    return ((prompt - cached) * p["input"] + cached * p["cached"] + out * p["output"]) / 1_000_000

# %% [markdown]
# **1.** A constant name at the top does not hurt: the cache needs the prefix to be identical between
# calls, not free of user data. It is the same on every turn, so the hit rate stays at 80%.

# %%
named = sim_chat(PrefixCache(), system_at=lambda t: "User: Asha.\n" + SYSTEM_LONG)
print(f"constant name at the top: hit rate {hit_rate(named):.0%}")

# %% [markdown]
# **2.** A name that changes every turn breaks the prefix like the timestamp did. Fix: move it into the
# newest user message.

# %%
NAMES = ["Asha", "Ben", "Chen", "Dara", "Eli"]
kiosk = sim_chat(PrefixCache(), system_at=lambda t: f"User: {NAMES[int(t // 30)]}.\n" + SYSTEM_LONG)
kiosk_fixed = sim_chat(PrefixCache(), make_user_text=lambda q, t: f"[user: {NAMES[int(t // 30)]}] {q}")
print(f"name at the top : hit rate {hit_rate(kiosk):.0%}, ${sum(r['cost'] for r in kiosk):.4f}")
print(f"name in the turn: hit rate {hit_rate(kiosk_fixed):.0%}, ${sum(r['cost'] for r in kiosk_fixed):.4f}")

# %% [markdown]
# **3.** Price the buggy run's tokens with the fixed run's cached counts, then scale the difference.

# %%
saved = json.load(open("../data/recorded/41.json"))
buggy_bill = sum(gemini_cost(**r) for r in saved["buggy"])
as_if_cached = sum(gemini_cost(b["prompt"], f["cached"], b["out"]) for b, f in zip(saved["buggy"], saved["fixed"]))
print(f"buggy ${buggy_bill:.4f} vs ${as_if_cached:.4f} with caching per 5-turn chat")
print(f"the bug costs ${(buggy_bill - as_if_cached) * 5_000 * 30:,.2f} per month at 5,000 chats a day")

# %% [markdown]
# ## Lesson 42
# Setup from lesson 42, unchanged: the notes, `batch_line`, `LocalBatchService`, `first_words`,
# `choose_mode` and the recorded token counts of the 50 live calls (no model calls here).

# %%
import json, pathlib, random
NOTES_50 = json.loads(pathlib.Path("../data/notes_50.json").read_text())
SUMMARY_RULES = "Summarise the research note in one line of at most 12 words. Reply with the line only."
PRICES_PER_MTOK = {"gemini-3.5-flash-lite": {"input": 0.30, "output": 2.50}}
MODEL = "gemini-3.5-flash-lite"
def cost_usd(model, i, o): return (i * PRICES_PER_MTOK[model]["input"] + o * PRICES_PER_MTOK[model]["output"]) / 1e6

def batch_line(note):
    return {"key": f"note-{note['id']}",
            "request": {"contents": [{"role": "user", "parts": [{"text": note["text"]}]}],
                        "systemInstruction": {"parts": [{"text": SUMMARY_RULES}]},
                        "generationConfig": {"maxOutputTokens": 40, "temperature": 0}}}

def first_words(request):
    text = request["contents"][0]["parts"][0]["text"].strip()
    if not text:
        raise ValueError("400 INVALID_ARGUMENT: model input cannot be empty")
    return " ".join(text.split()[:12])

# %%
class LocalBatchService:
    QUEUE_MIN, RUN_MIN = 20, 40
    def __init__(self, runner, seed=42):
        self.runner, self.rng, self.jobs = runner, random.Random(seed), {}
    def create(self, lines):
        name = f"batches/local-{len(self.jobs) + 1}"
        self.jobs[name] = {"lines": lines, "clock": 0, "results": None}
        return name
    def get(self, name, minutes_waited):
        job = self.jobs[name]; job["clock"] += minutes_waited
        if job["clock"] < self.QUEUE_MIN: return "JOB_STATE_PENDING"
        if job["clock"] < self.QUEUE_MIN + self.RUN_MIN: return "JOB_STATE_RUNNING"
        if job["results"] is None:
            job["results"] = [self._run(l) for l in job["lines"]]; self.rng.shuffle(job["results"])
        return "JOB_STATE_SUCCEEDED"
    def _run(self, line):
        try: return {"key": line["key"], "response": self.runner(line["request"])}
        except ValueError as e: return {"key": line["key"], "error": str(e)}

def run_to_end(service, name):
    delay, state = 5, "JOB_STATE_PENDING"
    while state not in ("JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_EXPIRED", "JOB_STATE_CANCELLED"):
        state = service.get(name, delay); delay = min(delay * 2, 60)
    return state

# %%
DOCUMENTED_MAX_H = {"anthropic": 24, "gemini-api": 48, "vertex": 72}
def choose_mode(someone_waiting, deadline_hours, provider, monthly_saving_usd):
    if someone_waiting: return "live: a person is waiting for the answer"
    if deadline_hours < DOCUMENTED_MAX_H[provider]:
        return "live (or batch + live fallback): batch may not finish before the deadline"
    if monthly_saving_usd < 10: return "live: saving too small to justify a second code path"
    return "batch"

live = {int(k): v for k, v in json.loads(pathlib.Path("../data/recorded/42.json").read_text()).items()}
live_cost = cost_usd(MODEL, sum(r["in"] for r in live.values()), sum(r["out"] for r in live.values()))
batch_cost = live_cost * 0.5

service = LocalBatchService(first_words)
first = service.create([batch_line(n) for n in NOTES_50] + [batch_line({"id": 51, "text": "   "})])
run_to_end(service, first)
ok = {r["key"]: r["response"] for r in service.jobs[first]["results"] if "response" in r}
print(len(ok), "summaries after the first batch")

# %% [markdown]
# **1.** Resubmit only the failed key, as its own small batch, then merge by key.

# %%
fixed_note = {"id": 51, "text": "Saturn's rings are mostly water ice and are thinner than a few hundred metres."}
retry = service.create([batch_line(fixed_note)])
print("retry job:", retry, run_to_end(service, retry))
for r in service.jobs[retry]["results"]:
    if "response" in r:
        ok[r["key"]] = r["response"]
print(len(ok), "summaries; note-51:", ok["note-51"])

# %% [markdown]
# **2.** Vertex may queue a job up to 72 h, and 30 h is less than that, so `choose_mode` says live (or
# batch with a live fallback), whatever the saving. The saving is small anyway.

# %%
saving = (live_cost - batch_cost) * 2_000 / 50 * 30
print(f"monthly saving at 2,000/day: ${saving:.2f}")
print(choose_mode(False, 30, "vertex", saving))

# %% [markdown]
# ## Lesson 43
# Setup from lesson 43: the price table, `cost_usd` and the Gemini 3 media-token table, unchanged.

# %%
MODEL_43 = "gemini-3.5-flash-lite"
PRICES_43 = {"gemini-3.5-flash-lite": {"input": 0.30, "output": 2.50}}
GEMINI3_MEDIA_TOKENS = {
    "image": {"unspecified": 1120, "low": 280, "medium": 560, "high": 1120, "ultra_high": 2240},
    "pdf_page": {"unspecified": 560, "low": 280, "medium": 560, "high": 1120},
}

def cost_43(input_tokens: int, output_tokens: int = 0) -> float:
    p = PRICES_43[MODEL_43]
    return (input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000

def estimate_media_tokens(kind: str, count: int = 1, resolution: str = "unspecified") -> int:
    return GEMINI3_MEDIA_TOKENS[kind][resolution] * count

# %% [markdown]
# **1.** 5,000 screenshots a day, image tokens only. Default resolution is 4x the tokens of low.

# %%
for res in ["unspecified", "low"]:
    tokens = estimate_media_tokens("image", 5_000, res)
    print(f"{res:>11}: {tokens:,} tokens/day -> ${cost_43(tokens):.2f}/day, ${cost_43(tokens) * 30:.2f}/month")

# %% [markdown]
# **2.** A PDF estimate. A 300-page report at medium is 168,000 tokens, about five cents. Lesson 43 saw the
# real bill come in slightly under the count, so this is an upper bound.

# %%
def pdf_estimate(pages: int, resolution: str = "unspecified") -> tuple[int, float]:
    tokens = estimate_media_tokens("pdf_page", pages, resolution)
    return tokens, cost_43(tokens)

tokens, usd = pdf_estimate(300, "medium")
print(f"300 pages at medium: {tokens:,} tokens, ${usd:.4f}")
print("2 pages, default:", pdf_estimate(2), "(lesson 43 counted 1,120)")

# %% [markdown]
# ## Lesson 44
# Setup from lesson 44: the notes, the two tools, the fake `auto_run` helper and the scripted model.

# %%
import ast, functools, inspect, operator

NOTES_44 = [{"id": 3, "text": "A day on Mars lasts about 24 hours and 39 minutes."},
            {"id": 4, "text": "Jupiter is the largest planet in the solar system."}]

def search_notes(query: str) -> list[dict]:
    """Search the user's notes for a word or phrase (case-insensitive)."""
    return [n for n in NOTES_44 if query.strip().lower() in n["text"].lower()]

OPS_44 = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
def evaluate(node):
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in OPS_44:
        return OPS_44[type(node.op)](evaluate(node.left), evaluate(node.right))
    raise ValueError("not plain arithmetic")

def calculator(expression: str) -> float:
    """Evaluate an arithmetic expression."""
    try:
        return evaluate(ast.parse(expression, mode="eval").body)
    except SyntaxError:
        raise ValueError(f"'{expression}' is not valid arithmetic") from None

# %% [markdown]
# `auto_run` and the script, unchanged from the lesson.

# %%
def auto_run(question, model, tools, max_calls=10):
    messages = [{"role": "user", "text": question}]
    for _ in range(max_calls):
        reply = model(messages)
        messages.append(reply)
        if not reply.get("tool_calls"):
            return reply["text"]
        for call in reply["tool_calls"]:
            try:
                out = {"result": tools[call["name"]](**call["args"])}
            except Exception as e:
                out = {"error": str(e)}
            messages.append({"role": "tool", "name": call["name"], "content": out})
    return None

def scripted(replies):
    state = {"n": 0}
    def model(messages):
        state["n"] += 1
        reply = replies[state["n"] - 1]
        return reply(messages) if callable(reply) else reply
    return model

def calc(expr): return {"tool_calls": [{"name": "calculator", "args": {"expression": expr}}]}
SCRIPT = [{"tool_calls": [{"name": "search_notes", "args": {"query": "day on Mars"}}]},
          calc("24*60+39 minutes"), calc("24*60+39"),
          lambda m: {"text": f"A day on Mars lasts about {m[-1]['content']['result']} minutes."}]

# %% [markdown]
# The answer: `functools.wraps` keeps the name, docstring and (through `__wrapped__`) the signature, so a
# real SDK helper would still build the same schema. The wrapper logs, then re-raises, so the helper's own
# error handling still runs.

# %%
def traced(fn, log: list):
    @functools.wraps(fn)
    def wrapper(**args):
        try:
            result = fn(**args)
        except Exception:
            log.append({"tool": fn.__name__, "args": args, "ok": False})
            raise
        log.append({"tool": fn.__name__, "args": args, "ok": True})
        return result
    return wrapper

log = []
tools = {f.__name__: traced(f, log) for f in (search_notes, calculator)}
print(auto_run("How many minutes long is a day on Mars?", scripted(SCRIPT), tools))
for entry in log:
    print(entry)
assert len(log) == 3 and sum(not e["ok"] for e in log) == 1
print("signature kept:", inspect.signature(tools["calculator"]), "| name:", tools["calculator"].__name__)

# %% [markdown]
# ## Lesson 45
# Setup from lesson 45: the benchmark results saved by the recording run (`../data/recorded/45.json`,
# recorded output), the prices, and condensed copies of `summarise` and `recommend`.

# %%
PRICES_45 = {"gemini-3.5-flash-lite": {"input": 0.30, "output": 2.50},
             "gemini-3.8-flash":      {"input": 0.75, "output": 3.75}}      # USD, 2026-10-06
def cost_45(prices: dict, model: str, tin: int, tout: int) -> float:
    return (tin * prices[model]["input"] + tout * prices[model]["output"]) / 1_000_000

def q_cost_45(prices: dict, model: str, row: dict) -> float:                   # one question's cost
    c = row["calls"]
    return cost_45(prices, model, sum(x["in"] for x in c), sum(x["out"] + x["thoughts"] for x in c))

def table_45(results: dict, prices: dict) -> dict:
    out = {}
    for name, rows in results.items():
        model, per_q = name.split("/")[0], sorted(sum(c["seconds"] for c in r["calls"]) for r in rows)
        out[name] = {"success": sum(r["correct"] for r in rows) / len(rows),
                     "cost": sum(q_cost_45(prices, model, r) for r in rows) / len(rows),
                     "p50_s": per_q[len(per_q) // 2 - 1], "p95_s": per_q[-1]}   # nearest rank, n = 10
    return out

def pick_45(table: dict, floor: float = 0.9, budget_s: float = 10.0):
    ok = [n for n, s in table.items() if s["success"] >= floor and s["p95_s"] <= budget_s]
    return min(ok, key=lambda n: (table[n]["cost"], table[n]["p50_s"])) if ok else None

results_45 = json.loads(pathlib.Path("../data/recorded/45.json").read_text())
now = table_45(results_45, PRICES_45)
print("pick today:", pick_45(now))

# %% [markdown]
# **1.** The January 2027 price for `gemini-3.8-flash`. Only its rows change; flash-lite's do not.

# %%
JAN_2027 = {**PRICES_45, "gemini-3.8-flash": {"input": 1.50, "output": 7.50}}
jan = table_45(results_45, JAN_2027)
for name in jan:
    print(f"{name:28} today ${now[name]['cost'] * 150_000:8,.2f}/month | Jan 2027 ${jan[name]['cost'] * 150_000:8,.2f}/month")
print("pick in Jan 2027:", pick_45(jan))

# %% [markdown]
# Monthly = cost per question × 5,000 a day × 30 days. Doubling the price doubles each
# `gemini-3.8-flash` row, so it can only make the flash-lite configurations look better: if today's pick
# is flash-lite, the pick stays the same.
#
# **2.** Oracle routing: for each question, the cheapest configuration that got it right.

# %%
routed_cost, routed_right = 0.0, 0
for qi in range(len(next(iter(results_45.values())))):
    right = [(q_cost_45(PRICES_45, n.split("/")[0], rows[qi]), n) for n, rows in results_45.items()
             if rows[qi]["correct"]]
    if right:
        routed_cost, routed_right = routed_cost + min(right)[0], routed_right + 1
    else:                                       # nobody got it right: count the cheapest attempt
        routed_cost += min(q_cost_45(PRICES_45, n.split("/")[0], rows[qi]) for n, rows in results_45.items())
best = pick_45(now) or max(now, key=lambda n: now[n]["success"])
n_q = len(next(iter(results_45.values())))
print(f"oracle routing: {routed_right}/{n_q} right, ${routed_cost / n_q:.6f} per question")
print(f"single pick {best}: {now[best]['success']:.0%} right, ${now[best]['cost']:.6f} per question")
print(f"most routing could save: {1 - (routed_cost / n_q) / now[best]['cost']:.0%}")

# %% [markdown]
# In the recorded run the oracle costs about 2% *more* than the pick ("-2%") but gets 10/10 instead of
# 9/10: the only extra spend is sending question 4 to a configuration that does it right. So here routing
# buys quality, not savings. A real router does not know in advance which configuration will be right,
# so it does worse than the oracle. When the cheap configuration already answers almost everything, the oracle's saving is small:
# routing earns its complexity only when the hard questions are a distinct, recognisable group (lesson 54).

# %% [markdown]
# # Solutions · Part 4: The agent loop from scratch
# Answers to the "Try it" exercises. Try each one yourself first.

# %%
import ast
import json
import operator

# %% [markdown]
# ## Lesson 26
# Setup from lesson 26: the notes, `search_notes`, `calculator`, the schemas, `ScriptedModel` and
# `run_agent`, unchanged (the Gemini parts are not needed here).

# %%
NOTES = [
    {"id": 1, "text": "Mars has two small moons, Phobos and Deimos."},
    {"id": 2, "text": "Venus spins backwards compared with most planets."},
    {"id": 3, "text": "A day on Mars lasts about 24 hours and 39 minutes."},
    {"id": 4, "text": "Jupiter is the largest planet in the solar system."},
    {"id": 5, "text": "The rover Perseverance landed on Mars in February 2021."},
    {"id": 6, "text": "Saturn's rings are mostly made of ice."},
]

def search_notes(query: str) -> list[dict]:
    q = query.lower()
    return [note for note in NOTES if q in note["text"].lower()]

OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}

def calculator(expression: str) -> float:
    def ev(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in OPS:
            return OPS[type(node.op)](ev(node.left), ev(node.right))
        raise ValueError(f"not allowed in a calculation: {ast.dump(node)[:40]}")
    return ev(ast.parse(expression, mode="eval").body)

TOOLS = {"search_notes": search_notes, "calculator": calculator}
SCHEMAS = [{"name": "search_notes"}, {"name": "calculator"}]   # the fake never reads them

# %%
def check_history(messages: list[dict]) -> None:
    issued = set()
    for m in messages:
        issued |= {c["id"] for c in m.get("tool_calls", [])}
        if m["role"] == "tool" and m["call_id"] not in issued:
            raise ValueError(f"tool result for unknown call id {m['call_id']!r}")

class ScriptedModel:
    def __init__(self, script: list):
        self.script, self.calls, self.next_id = script, 0, 1

    def __call__(self, messages: list[dict], tools: list[dict]) -> dict:
        check_history(messages)
        self.calls += 1
        if self.calls > 50:
            raise RuntimeError("model called 50 times: the loop never stopped")
        reply = self.script[min(self.calls, len(self.script)) - 1]
        reply = reply(messages) if callable(reply) else json.loads(json.dumps(reply))
        for call in reply.get("tool_calls", []):
            call["id"], self.next_id = f"call_{self.next_id}", self.next_id + 1
        return {"role": "assistant", **reply}

# %%
def run_agent(question: str, model, tools: dict, schemas: list[dict], max_steps: int = 6) -> dict:
    messages = [{"role": "user", "text": question}]
    for step in range(1, max_steps + 1):
        reply = model(messages, schemas)
        messages.append(reply)
        calls = reply.get("tool_calls", [])
        if not calls:
            print(f"step {step}: answer")
            return {"answer": reply["text"], "stop": "end_of_turn", "steps": step, "messages": messages}
        for call in calls:
            result = tools[call["name"]](**call["args"])
            print(f"step {step}: {call['name']}({call['args']}) -> {json.dumps(result)[:60]}")
            messages.append({"role": "tool", "call_id": call["id"], "name": call["name"],
                             "content": json.dumps(result)})
    return {"answer": None, "stop": "step_limit", "steps": max_steps, "messages": messages}

# %% [markdown]
# **Answer.** Three script entries: search, calculate, then an answer built from the last tool result.

# %%
MOONS_SCRIPT = [
    {"tool_calls": [{"name": "search_notes", "args": {"query": "moons"}}]},
    {"tool_calls": [{"name": "calculator", "args": {"expression": "2*3"}}]},
    lambda messages: {"text": f"Mars has 2 moons; times 3 is {json.loads(messages[-1]['content'])}."},
]
run = run_agent("How many moons does Mars have, times 3?", ScriptedModel(MOONS_SCRIPT), TOOLS, SCHEMAS)
assert "6" in run["answer"]
print(run["stop"], "after", run["steps"], "steps:", run["answer"])

# %% [markdown]
# With `max_steps=2` the loop runs both tools but never makes the third call, so there is no answer:

# %%
run = run_agent("How many moons does Mars have, times 3?", ScriptedModel(MOONS_SCRIPT), TOOLS, SCHEMAS,
                max_steps=2)
print(run["stop"], "| answer:", run["answer"])

# %% [markdown]
# ## Lesson 27
# Setup from lesson 27: `json_type`, `schema_from_function` and `ToolRegistry`, unchanged
# (`NOTES`, `ScriptedModel` and `run_agent` come from the Lesson 26 section above).

# %%
import inspect
from typing import Annotated, get_args, get_origin, get_type_hints

JSON_TYPES = {str: "string", int: "integer", float: "number", bool: "boolean"}

def json_type(hint) -> dict:
    if hint in JSON_TYPES:
        return {"type": JSON_TYPES[hint]}
    if get_origin(hint) is list:
        (item,) = get_args(hint)
        return {"type": "array", "items": json_type(item)}
    raise TypeError(f"no JSON Schema type for {hint!r}")

def schema_from_function(fn) -> dict:
    hints = get_type_hints(fn, include_extras=True)
    properties, required = {}, []
    for name, param in inspect.signature(fn).parameters.items():
        if name not in hints:
            raise TypeError(f"{fn.__name__}: parameter {name!r} has no type hint")
        hint, note = hints[name], None
        if get_origin(hint) is Annotated:
            hint, note = get_args(hint)[0], get_args(hint)[1]
        properties[name] = json_type(hint) | ({"description": note} if note else {})
        if param.default is inspect.Parameter.empty:
            required.append(name)
    if not inspect.getdoc(fn):
        raise TypeError(f"{fn.__name__}: needs a docstring; it becomes the tool description")
    return {"name": fn.__name__, "description": inspect.getdoc(fn),
            "parameters": {"type": "object", "properties": properties, "required": required}}

# %%
class ToolRegistry:
    def __init__(self):
        self.functions, self.schemas = {}, []

    def tool(self, fn):
        schema = schema_from_function(fn)
        if schema["name"] in self.functions:
            raise ValueError(f"tool {schema['name']!r} is already registered")
        self.functions[schema["name"]] = fn
        self.schemas.append(schema)
        return fn

# %% [markdown]
# **Answer.** `max_results` has a default, so it appears in `properties` but not in `required`.

# %%
my_tools = ToolRegistry()

@my_tools.tool
def search_notes(query: Annotated[str, "one word to look for, e.g. 'Mars'"],
                 max_results: int = 2) -> list[dict]:
    """Search the user's notes. Returns at most `max_results` notes containing the query word."""
    q = query.lower()
    return [note for note in NOTES if q in note["text"].lower()][:max_results]

params = my_tools.schemas[0]["parameters"]
assert "max_results" in params["properties"] and params["required"] == ["query"]
print(params)

# %% [markdown]
# The model leaves out `max_results`, so the default (2) applies: three notes mention Mars, two come back.

# %%
SCRIPT = [
    {"tool_calls": [{"name": "search_notes", "args": {"query": "Mars"}}]},
    lambda m: {"text": f"I got {len(json.loads(m[-1]['content']))} notes back."},
]
run = run_agent("Which notes mention Mars?", ScriptedModel(SCRIPT), my_tools.functions, my_tools.schemas)
print(run["answer"])

# %% [markdown]
# ## Lesson 28
# Setup from lesson 28: `run_tool` and the `run_agent` that sends error results back
# (`NOTES`, `calculator`, `TOOLS` and `ScriptedModel` come from the Lesson 26 section above).

# %%
def run_tool(call: dict, tools: dict) -> dict:
    fn = tools.get(call["name"])
    if fn is None:
        return {"content": f"unknown tool '{call['name']}'. Available tools: {', '.join(tools)}.",
                "is_error": True}
    try:
        return {"content": json.dumps(fn(**call["args"])), "is_error": False}
    except Exception as e:
        return {"content": f"{type(e).__name__}: {e}", "is_error": True}

def run_agent(question, model, tools, schemas, max_steps=6):
    messages, errors = [{"role": "user", "text": question}], 0
    for step in range(1, max_steps + 1):
        reply = model(messages, schemas)
        messages.append(reply)
        if not reply.get("tool_calls"):
            return {"answer": reply["text"], "stop": "end_of_turn", "steps": step, "errors": errors}
        for call in reply["tool_calls"]:
            result = run_tool(call, tools)
            errors += result["is_error"]
            print(f"step {step}: {call['name']}({call['args']}) -> {result['content'][:80]}")
            messages.append({"role": "tool", "call_id": call["id"], "name": call["name"], **result})
    return {"answer": None, "stop": "step_limit", "steps": max_steps, "errors": errors}

# %% [markdown]
# **Answer.** `calculator_v2` keeps the original as the worker and replaces its unhelpful message with
# one that names the allowed operators and shows how to write a power.

# %%
def calculator_v2(expression: str) -> float:
    try:
        return calculator(expression)
    except (ValueError, SyntaxError) as e:
        raise ValueError(f"cannot calculate '{expression}': only numbers, + - * / and brackets are "
                         f"allowed. For a power, multiply it out, e.g. '2*2*2' for 2 to the 3rd.") from e

print(run_tool({"name": "calculator", "args": {"expression": "2^3"}}, {"calculator": calculator_v2}))

# %% [markdown]
# The fake tries `2^3`, gets the error result, retries with `2*2*2`, and answers from the result.

# %%
POWER_SCRIPT = [
    {"tool_calls": [{"name": "calculator", "args": {"expression": "2^3"}}]},
    {"tool_calls": [{"name": "calculator", "args": {"expression": "2*2*2"}}]},
    lambda m: {"text": f"2 to the power 3 is {json.loads(m[-1]['content'])}."},
]
run = run_agent("What is 2 to the power 3?", ScriptedModel(POWER_SCRIPT),
                {**TOOLS, "calculator": calculator_v2}, SCHEMAS)
assert run["errors"] == 1 and "8" in run["answer"]
print(run["stop"], "| errors:", run["errors"], "|", run["answer"])

# %% [markdown]
# ## Lesson 29
# Setup from lesson 29: Scout's grown notes and `shorten` (`json_type` and `schema_from_function`
# come from the Lesson 27 section above).

# %%
BRIEFING = {"id": 7, "text": "Mars mission briefing: " + "check suits, check air, check water. " * 40}
LOG = [{"id": 100 + d, "text": f"Mars habitat log, day {d}: routine checks, all systems normal."}
       for d in range(1, 31)]
ALL_NOTES = NOTES + [BRIEFING] + LOG

# %% [markdown]
# **Answer.** `detail` defaults to `"short"`, so it is optional in the schema; any other value is an
# actionable error that lists the allowed values.

# %%
def search_notes_v2(query: Annotated[str, "a word or short phrase, e.g. 'Mars'"],
                    detail: Annotated[str, "'short' (id + first 40 characters) or 'full'"] = "short") -> list[dict]:
    """Search the user's notes (case-insensitive). Returns matching notes as {id, text};
    detail='short' cuts each text to 40 characters, detail='full' returns it whole."""
    if detail not in ("short", "full"):
        raise ValueError(f"detail must be 'short' or 'full', not {detail!r}, e.g. detail='short'")
    hits = [n for n in ALL_NOTES if query.lower() in n["text"].lower()]
    return [{"id": n["id"], "text": n["text"] if detail == "full" else n["text"][:40]} for n in hits]

for mode in ["short", "full"]:
    print(mode, len(json.dumps(search_notes_v2("Mars", detail=mode))), "characters")
params = schema_from_function(search_notes_v2)["parameters"]
assert "detail" in params["properties"] and "detail" not in params["required"]
print("required:", params["required"])

# %% [markdown]
# ## Lesson 30
# Setup from lesson 30: `Deadline`, `call_key` and `RepeatWatch` (`ScriptedModel`, `TOOLS` and
# `run_tool` are defined in earlier sections of this file; `run_tool` is the same one lesson 30 uses).

# %%
import time
from collections import Counter

class Deadline:
    def __init__(self, seconds: float, clock=time.monotonic):
        self.seconds, self.clock, self.start = seconds, clock, clock()
    def elapsed(self) -> float:
        return round(self.clock() - self.start, 2)
    def expired(self) -> bool:
        return self.elapsed() >= self.seconds

def call_key(call: dict) -> str:
    return call["name"] + json.dumps(call["args"], sort_keys=True)

class RepeatWatch:
    def __init__(self, max_repeats: int):
        self.max_repeats, self.counts = max_repeats, Counter()
    def seen(self, calls: list[dict]) -> bool:
        self.counts.update(call_key(c) for c in calls)
        return any(self.counts[call_key(c)] > self.max_repeats for c in calls)

# %% [markdown]
# **Answer.** The error check sits after the tools run, next to the repeat check. With `max_repeats=None`
# meaning "off", the error guard fires at step 4 (4 errors > 3).

# %%
def run_agent(question, model, tools, schemas, max_steps=6, timeout_s=60, max_repeats=2,
              max_errors=3, cancel=None, clock=time.monotonic):
    messages, errors = [{"role": "user", "text": question}], 0
    deadline = Deadline(timeout_s, clock)
    repeats = RepeatWatch(max_repeats) if max_repeats is not None else None
    def finish(stop, steps, answer=None):
        return {"answer": answer, "stop": stop, "steps": steps, "errors": errors, "messages": messages}
    for step in range(1, max_steps + 1):
        if cancel is not None and cancel.is_set():
            return finish("cancelled", step - 1)
        if deadline.expired():
            return finish("timeout", step - 1)
        reply = model(messages, schemas)
        messages.append(reply)
        if not reply.get("tool_calls"):
            return finish("end_of_turn", step, reply["text"])
        for call in reply["tool_calls"]:
            result = run_tool(call, tools)
            errors += result["is_error"]
            messages.append({"role": "tool", "call_id": call["id"], "name": call["name"], **result})
        if repeats is not None and repeats.seen(reply["tool_calls"]):
            return finish("repeated_call", step)
        if errors > max_errors:
            return finish("too_many_errors", step)
    return finish("step_limit", max_steps)

# %%
BAD_MATH = [{"tool_calls": [{"name": "calculator", "args": {"expression": "2^3"}}]}]
run = run_agent("What is 2 to the power 3?", ScriptedModel(BAD_MATH), TOOLS, SCHEMAS,
                max_steps=10, max_repeats=None)
print(run["stop"], "after", run["steps"], "steps,", run["errors"], "errors")
assert run["stop"] == "too_many_errors"

# %% [markdown]
# With `max_repeats=2` left on, `repeated_call` fires first, at step 3: `max_repeats=2` trips on the
# third identical call, before `max_errors=3` is exceeded on the fourth (after step 3 there are only
# 3 errors, not more than 3). Repeated failing calls are both a loop and an error streak; whichever
# limit is tighter wins.

# %%
run = run_agent("What is 2 to the power 3?", ScriptedModel(BAD_MATH), TOOLS, SCHEMAS, max_steps=10)
print(run["stop"], "after", run["steps"], "steps,", run["errors"], "errors")
assert (run["stop"], run["steps"]) == ("repeated_call", 3)

# %% [markdown]
# ## Lesson 31
# Setup from lesson 31: the token counter, the three rover notebooks, `search_notes`, `read_note`, the
# schemas, the `run_agent` with a `view`, `trim_old_results` and the research script (`calculator` and
# `ScriptedModel` come from the Lesson 26 section above).

# %%
import os, random
os.environ["TIKTOKEN_CACHE_DIR"] = "../data/tiktoken_cache"
import tiktoken
ENC = tiktoken.get_encoding("o200k_base")
def tokens(text: str) -> int: return len(ENC.encode(text))
def message_tokens(m: dict) -> int:
    return 4 + tokens(m.get("text") or m.get("content") or json.dumps(m.get("tool_calls", [])))

rng = random.Random(31)
def rover_log(first_sol: int, n: int) -> str:
    return "\n".join(f"Sol {s}: drove {rng.randint(0, 120)} m, wind {rng.randint(1, 15)} m/s, dust opacity "
                     f"{rng.uniform(0.2, 1.5):.2f}, battery {rng.randint(40, 100)}%, photos {rng.randint(0, 60)}."
                     for s in range(first_sol, first_sol + n))
NOTEBOOKS = {1: {"title": "Mars field notebook 1", "text": rover_log(1, 100)},
             2: {"title": "Mars field notebook 2", "text": rover_log(101, 100)},
             3: {"title": "Mars field notebook 3", "text": rover_log(201, 55) +
                 "\nReminder for the talk: a day on Mars (a sol) lasts 24 hours and 39 minutes."}}

# %%
SYSTEM31 = "You are Scout."          # the exact text only changes the fixed token count
def search_notes31(query: str) -> list[dict]:
    q = query.lower()
    return [{"id": i, "title": nb["title"], "tokens": tokens(nb["text"])}
            for i, nb in NOTEBOOKS.items() if q in (nb["title"] + nb["text"]).lower()]
def read_note(note_id: int) -> str: return NOTEBOOKS[note_id]["text"]
TOOLS31 = {"search_notes": search_notes31, "read_note": read_note, "calculator": calculator}
SCHEMAS31 = [{"name": n} for n in TOOLS31]
def context_tokens(messages): return tokens(SYSTEM31) + tokens(json.dumps(SCHEMAS31)) + sum(map(message_tokens, messages))

def run_agent31(question, model, tools, schemas, max_steps=8, view=lambda messages: messages):
    messages, sizes = [{"role": "user", "text": question}], []
    for step in range(1, max_steps + 1):
        request = view(messages)
        sizes.append(context_tokens(request))
        reply = model(request, schemas)
        messages.append(reply)
        if not reply.get("tool_calls"):
            return {"answer": reply["text"], "steps": step, "messages": messages, "sizes": sizes}
        for call in reply["tool_calls"]:
            messages.append({"role": "tool", "call_id": call["id"], "name": call["name"], "args": call["args"],
                             "step": step, "content": json.dumps(tools[call["name"]](**call["args"]))})
    return {"answer": None, "steps": max_steps, "messages": messages, "sizes": sizes}

# %%
QUESTION = "How many minutes long is a day on Mars?"
def last_result(messages): return json.loads(messages[-1]["content"])
RESEARCH_SCRIPT = [
    {"tool_calls": [{"name": "search_notes", "args": {"query": "Mars"}}]},
    {"tool_calls": [{"name": "read_note", "args": {"note_id": 1}}]},
    {"tool_calls": [{"name": "read_note", "args": {"note_id": 2}}]},
    {"tool_calls": [{"name": "read_note", "args": {"note_id": 3}}]},
    {"tool_calls": [{"name": "calculator", "args": {"expression": "24*60+39"}}]},
    lambda messages: {"text": f"A day on Mars lasts {last_result(messages):,.0f} minutes."},
]
full = run_agent31(QUESTION, ScriptedModel(RESEARCH_SCRIPT), TOOLS31, SCHEMAS31)

# %% [markdown]
# The answer: the same as `trim_old_results`, with one more condition. A result is kept if its step is
# recent **or** its tool is in `keep_tools`.

# %%
def trim_except(messages: list[dict], keep_steps: int = 2, keep_tools=frozenset({"search_notes"})) -> list[dict]:
    steps = sorted({m["step"] for m in messages if m["role"] == "tool"})
    recent = set(steps[len(steps) - keep_steps:])
    view = []
    for m in messages:
        if m["role"] == "tool" and m["step"] not in recent and m["name"] not in keep_tools:
            note = (f"{m['name']}({json.dumps(m['args'])}) returned {tokens(m['content'])} tokens, "
                    "cleared to save space. Call it again if you need them.")
            m = {**m, "content": json.dumps({"cleared": note})}
        view.append(m)
    return view

run = run_agent31(QUESTION, ScriptedModel(RESEARCH_SCRIPT), TOOLS31, SCHEMAS31, view=trim_except)
print("tokens per call:", run["sizes"])
print("same answer:", run["answer"] == full["answer"], "|", run["answer"])
assert run["answer"] == full["answer"]
kept = [m for m in trim_except(run["messages"][:-1]) if m.get("name") == "search_notes"]
assert "cleared" not in kept[0]["content"]          # the search result survived

# %% [markdown]
# ## Lesson 32
# Setup from lesson 32, unchanged except for names ending in 32 (so the Lesson 31 section above keeps
# its own `context_tokens`): the rover log, the 60 scripted turns, `compact`, `extract_summary`,
# `chat_with_compaction` and `PROBES`. No model calls are needed.

# %%
rng32 = random.Random(32)
SOLS = [{"sol": s, "drove": rng32.randint(0, 120), "wind": rng32.randint(1, 15),
         "opacity": round(rng32.uniform(0.2, 1.5), 2), "battery": rng32.randint(40, 100)} for s in range(1, 301)]
LOG = [f"Sol {d['sol']}: drove {d['drove']} m, wind {d['wind']} m/s, dust opacity {d['opacity']:.2f}, "
       f"battery {d['battery']}%." for d in SOLS]
SYSTEM32 = ("You are Scout, a research assistant over the user's rover log. "
            "Answer only from this chat and the tool results in it.")
WINDOW32, TRIGGER32 = 8_000, 6_000

def context_tokens32(messages):
    body = lambda m: m.get("text") or m.get("content") or json.dumps(m.get("tool_calls", []))
    return tokens(SYSTEM32) + sum(4 + tokens(body(m)) for m in messages)

FACT_TURNS = [
    ("Hi Scout. My project is a 10-minute talk on dust storms on Mars, for my astronomy club.",
     "Great topic. I'll help you dig through the rover log."),
    ("The talk is on 14 November, so we have five weeks.", "Noted: the talk is on 14 November."),
    ("Please use metric units only. My club voted against miles.", "Understood: metric units only."),
    ("A sol is 24 hours and 39 minutes. How many minutes is that?", "A sol is 1,479 minutes (24 x 60 + 39)."),
]

# %%
def block_answer(a, b):
    block = SOLS[a - 1:b]
    dusty = max(block, key=lambda d: d["opacity"])
    return (f"Sols {a}-{b}: the rover drove {sum(d['drove'] for d in block)} m in total; "
            f"the dustiest was sol {dusty['sol']} (opacity {dusty['opacity']:.2f}).")

def turn_messages(t):
    if t <= len(FACT_TURNS):
        q, a = FACT_TURNS[t - 1]
        return [{"role": "user", "text": q, "turn": t}, {"role": "assistant", "text": a, "turn": t}]
    a = (t - 5) * 5 + 1
    call = {"id": f"call_{t}", "name": "read_log", "args": {"first_sol": a, "last_sol": a + 4}}
    return [{"role": "user", "text": f"What happened on sols {a} to {a + 4}?", "turn": t},
            {"role": "assistant", "tool_calls": [call], "turn": t},
            {"role": "tool", "call_id": call["id"], "name": "read_log", "args": call["args"],
             "content": "\n".join(LOG[a - 1:a + 4]), "turn": t},
            {"role": "assistant", "text": block_answer(a, a + 4), "turn": t}]

# %%
def compact(messages, summarise, keep_turns=6):
    turns = sorted({m["turn"] for m in messages if m["role"] != "summary"})
    keep_from = turns[-keep_turns]
    old = [m for m in messages if m["role"] == "summary" or m["turn"] < keep_from]
    recent = [m for m in messages if m["role"] != "summary" and m["turn"] >= keep_from]
    return [{"role": "summary", "text": summarise(old), "turn": keep_from - 1}] + recent

def extract_summary(messages):
    lines = []
    for m in messages:
        if m["role"] == "summary":
            lines.append(m["text"])
        elif m["role"] == "user" and not m["text"].endswith("?"):
            lines.append("User said: " + m["text"])
        elif m["role"] == "assistant" and "text" in m:
            lines.append("Scout said: " + m["text"])
    return "\n".join(lines)

# %%
def chat_with_compaction(n_turns, summarise, keep_turns=6):
    live, sizes, compactions = [], [], 0
    for t in range(1, n_turns + 1):
        live += turn_messages(t)
        if context_tokens32(live) > TRIGGER32:
            live = compact(live, summarise, keep_turns)
            compactions += 1
        assert context_tokens32(live) <= WINDOW32, "over the 8,000-token budget"
        sizes.append(context_tokens32(live))
    return {"live": live, "sizes": sizes, "compactions": compactions}

dusty_31 = max(SOLS[30:35], key=lambda d: d["opacity"])["sol"]
PROBES = [("What is my project about?", ["dust storm"]), ("When is my talk?", ["14 november"]),
          ("Which units must the talk use?", ["metric"]), ("How many minutes is a sol?", ["1479", "1,479"]),
          ("Which sol was the dustiest from sol 31 to sol 35?", [f"sol {dusty_31}"])]

# %% [markdown]
# **1.** Compactions and largest request for `keep_turns` 2, 6 and 12.

# %%
runs32 = {}
for k in (2, 6, 12):
    runs32[k] = chat_with_compaction(60, extract_summary, keep_turns=k)
    print(f"keep_turns={k:2}: {runs32[k]['compactions']} compactions, largest request {max(runs32[k]['sizes']):,} tokens")

# %% [markdown]
# All three stay under 8,000 tokens. 2 and 6 compact twice, 12 three times: keeping more turns frees less
# room per compaction, and each compaction is a model call and a cache break. Keeping fewer turns loses the
# exact recent tool results sooner. 6 is a reasonable middle: as few compactions as 2, with the last six
# turns still word for word.
#
# **2.** `rot_check` on each run's final summary.

# %%
def rot_check(summary_text: str) -> float:
    text = summary_text.lower()
    return sum(any(k in text for k in keys) for _, keys in PROBES) / len(PROBES)

for k, run32 in runs32.items():
    print(f"keep_turns={k:2}: rot_check = {rot_check(run32['live'][0]['text']):.0%}")

# %% [markdown]
# ## Lesson 33
# Setup from lesson 33: the three Mars notes, the `gate` and the hand-written drafts, unchanged.
# `mars_draft` is the draft printed by step 5 of the lesson.

# %%
import re

def gate(draft: str, notes: list[dict]) -> list[str]:
    problems = []
    words = len(draft.split())
    if words > 40:
        problems.append(f"{words} words (max 40)")
    cited = {int(i) for i in re.findall(r"\[(\d+)\]", draft)}
    if not cited:
        problems.append("no [id] citations")
    if cited - {n["id"] for n in notes}:
        problems.append(f"cites unknown notes {sorted(cited - {n['id'] for n in notes})}")
    return problems

mars_notes = [
    {"id": 1, "text": "Mars has two small moons, Phobos and Deimos."},
    {"id": 3, "text": "A day on Mars lasts about 24 hours and 39 minutes."},
    {"id": 5, "text": "The rover Perseverance landed on Mars in February 2021."},
]
bad_drafts = ["Mars has two moons [1] and is the largest planet [4].",
              "Mars has two moons and a day of about 24 hours and 39 minutes."]
mars_draft = ("Mars features two small moons, Phobos and Deimos [1]. A Martian day lasts approximately 24 hours "
              "and 39 minutes [3]. Additionally, the Perseverance rover successfully landed on the planet in "
              "February 2021 [5].")

# %% [markdown]
# The answer: split the draft into sentences after `.`, `!` or `?`, and flag each one with no `[id]`.

# %%
def gate_strict(draft: str, notes: list[dict]) -> list[str]:
    problems = gate(draft, notes)
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", draft.strip()) if s]
    uncited = [s for s in sentences if not re.search(r"\[\d+\]", s)]
    if uncited:
        problems.append(f"{len(uncited)} sentence(s) without a citation: {uncited}")
    return problems

for d in bad_drafts + ["Mars has two moons [1]. It is red.", mars_draft]:
    print(gate_strict(d, mars_notes) or "pass")

# %% [markdown]
# ## Lesson 34
# Setup from lesson 34: `fake_check`, unchanged.

# %%
import asyncio, time

async def fake_check(name: str, delay: float = 0.5, vote: bool = True) -> bool:
    await asyncio.sleep(delay)
    return vote

# %% [markdown]
# The answer: wrap each check in `wait_for`, gather with `return_exceptions=True`, and count anything
# that is not a bool (a `TimeoutError` or another error) as an abstention.

# %%
async def vote_with_timeout(checks: list, timeout: float, need: int = 2) -> dict:
    results = await asyncio.gather(*(asyncio.wait_for(c, timeout) for c in checks), return_exceptions=True)
    votes = [r for r in results if isinstance(r, bool)]
    yes = sum(votes)
    return {"accurate": yes >= need, "yes": yes, "abstained": len(results) - len(votes)}

start = time.perf_counter()
out = await vote_with_timeout([fake_check("numbers"), fake_check("names", delay=2.0), fake_check("claims")],
                              timeout=1.0)
elapsed = time.perf_counter() - start
print(out, f"{elapsed:.1f} s")
assert out == {"accurate": True, "yes": 2, "abstained": 1} and elapsed < 1.5

# %% [markdown]
# ## Lesson 35
# Setup from lesson 35, unchanged: the schema builder, `ToolRegistry`, `run_tool`, `run_agent`,
# `ScriptedModel` and `fingerprint` (the Gemini parts and the other tools are not needed here).

# %%
import hashlib, inspect, json
from collections.abc import Callable
from typing import Annotated, get_args, get_origin, get_type_hints

JSON_TYPES = {str: "string", int: "integer", float: "number", bool: "boolean"}

def json_type(hint) -> dict:
    if hint in JSON_TYPES:
        return {"type": JSON_TYPES[hint]}
    if get_origin(hint) is list:
        return {"type": "array", "items": json_type(get_args(hint)[0])}
    raise TypeError(f"no JSON Schema type for {hint!r}")

def schema_from_function(fn) -> dict:
    hints = get_type_hints(fn, include_extras=True)
    properties, required = {}, []
    for name, param in inspect.signature(fn).parameters.items():
        hint, note = hints[name], None
        if get_origin(hint) is Annotated:
            hint, note = get_args(hint)[0], get_args(hint)[1]
        properties[name] = json_type(hint) | ({"description": note} if note else {})
        if param.default is inspect.Parameter.empty:
            required.append(name)
    return {"name": fn.__name__, "description": inspect.getdoc(fn),
            "parameters": {"type": "object", "properties": properties, "required": required}}

# %% [markdown]
# The registry, `run_tool` and the loop from lesson 35.

# %%
class ToolRegistry:
    def __init__(self):
        self.functions: dict[str, Callable] = {}
        self.schemas: list[dict] = []

    def tool(self, fn):
        schema = schema_from_function(fn)
        if schema["name"] in self.functions:
            raise ValueError(f"tool {schema['name']!r} is already registered")
        self.functions[schema["name"]] = fn
        self.schemas.append(schema)
        return fn

MAX_RESULT_CHARS = 1500

def run_tool(call: dict, tools: dict) -> dict:
    """Run one tool call. Returns {"content": str, "is_error": bool}; never raises."""
    fn = tools.get(call["name"])
    if fn is None:
        return {"content": f"unknown tool '{call['name']}'. Available tools: {', '.join(tools)}.",
                "is_error": True}
    try:
        result = {"content": json.dumps(fn(**call["args"])), "is_error": False}
    except Exception as e:                                    # any failure becomes an observation
        result = {"content": f"{type(e).__name__}: {e}", "is_error": True}
    extra = len(result["content"]) - MAX_RESULT_CHARS
    if extra > 0:
        result["content"] = (result["content"][:MAX_RESULT_CHARS] + f"... [truncated {extra} "
                             "characters: ask for a smaller page or a narrower query]")
    return result

# %% [markdown]
# The loop.

# %%
def run_agent(question: str, model, tools: dict, schemas: list[dict], max_steps: int = 8) -> dict:
    messages, errors = [{"role": "user", "text": question}], 0
    for step in range(1, max_steps + 1):
        reply = model(messages, schemas)
        messages.append(reply)
        calls = reply.get("tool_calls", [])
        if not calls:
            print(f"step {step}: answer")
            return {"answer": reply["text"], "stop": "end_of_turn", "steps": step,
                    "errors": errors, "messages": messages}
        for call in calls:
            result = run_tool(call, tools)
            errors += result["is_error"]
            print(f"step {step}: {call['name']}({call['args']}) -> "
                  f"{'ERROR ' if result['is_error'] else ''}{result['content'][:70]}")
            messages.append({"role": "tool", "call_id": call["id"], "name": call["name"], **result})
    return {"answer": None, "stop": "step_limit", "steps": max_steps, "errors": errors, "messages": messages}

# %% [markdown]
# `ScriptedModel` (lesson 26) and the loop fingerprint (lesson 35).

# %%
class ScriptedModel35:
    def __init__(self, script: list):
        self.script, self.calls, self.next_id = script, 0, 1

    def __call__(self, messages: list[dict], tools: list[dict]) -> dict:
        self.calls += 1
        reply = self.script[min(self.calls, len(self.script)) - 1]
        reply = reply(messages) if callable(reply) else json.loads(json.dumps(reply))
        for call in reply.get("tool_calls", []):
            call["id"], self.next_id = f"call_{self.next_id}", self.next_id + 1
        return {"role": "assistant", **reply}

def fingerprint(*parts) -> str:
    return hashlib.sha256("".join(inspect.getsource(p) for p in parts).encode()).hexdigest()[:12]

registry = ToolRegistry()
loop_before = fingerprint(run_agent, run_tool)
print("loop fingerprint before:", loop_before)

# %% [markdown]
# The answer: one decorated function. Every unit goes through seconds, and an unknown unit raises an
# actionable `ValueError` that lists the allowed units.

# %%
SECONDS = {"seconds": 1, "minutes": 60, "hours": 3600, "days": 86400}

@registry.tool
def convert_time(value: Annotated[float, "the amount, e.g. 24.65"],
                 from_unit: Annotated[str, "one of: seconds, minutes, hours, days"],
                 to_unit: Annotated[str, "one of: seconds, minutes, hours, days"]) -> float:
    """Convert a length of time between seconds, minutes, hours and days. Returns the number."""
    for unit in (from_unit, to_unit):
        if unit not in SECONDS:
            raise ValueError(f"unknown unit '{unit}'. Use one of: {', '.join(SECONDS)}, e.g. 'hours'.")
    return round(value * SECONDS[from_unit] / SECONDS[to_unit], 6)

print(registry.schemas[0]["parameters"]["required"], convert_time(24.65, "hours", "minutes"))

# %% [markdown]
# A fake script: a wrong unit, the fix, then the answer from the result. Then the three checks.

# %%
def convert(unit): return {"tool_calls": [{"name": "convert_time",
                                           "args": {"value": 24.65, "from_unit": unit, "to_unit": "minutes"}}]}
def last_result(messages): return json.loads(messages[-1]["content"])

SCRIPT = [convert("hrs"), convert("hours"), lambda m: {"text": f"24.65 hours is {last_result(m):g} minutes."}]
run = run_agent("How many minutes is 24.65 hours?", ScriptedModel35(SCRIPT), registry.functions, registry.schemas)
print(run["answer"])
assert run["errors"] == 1 and "1479" in run["answer"]
assert fingerprint(run_agent, run_tool) == loop_before
print("errors:", run["errors"], "| loop unchanged:", fingerprint(run_agent, run_tool) == loop_before)

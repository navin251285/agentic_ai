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
# `run_tool` come from the Lesson 26 and 28 sections above).

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

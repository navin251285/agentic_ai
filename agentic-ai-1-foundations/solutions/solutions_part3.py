# %% [markdown]
# # Solutions · Part 3: Prompts, structured output and tools
# Answers to the "Try it" exercises. Try each one yourself first.
#
# Model calls here are recorded once with `llm_replay` (`../data/llm_cassettes/solutions_part3.yaml`)
# and replayed with no key.

# %%
import sys; sys.path.insert(0, "..")
import os
import re
import llm_replay
from dotenv import load_dotenv
from google import genai
from google.genai import types

llm_replay.start("solutions_part3")
load_dotenv("../.env")
MODEL = os.environ.get("TUT_LLM_MODEL", "gemini-3.5-flash-lite")
client = genai.Client(vertexai=True, api_key=os.environ.get("GOOGLE_CLOUD_API_KEY") or "replay-no-key-needed")
NO_AFC = types.AutomaticFunctionCallingConfig(disable=True)

# %% [markdown]
# ## Lesson 19
# Setup from lesson 19: the test notes, `check_card`, `score`, `ask`, `ROLE` and `INSTRUCTIONS`, unchanged.

# %%
TEST_NOTES = [
    {"id": 1, "text": "Mars has two small moons, Phobos and Deimos."},
    {"id": 2, "text": "Venus spins backwards compared with most planets."},
    {"id": 3, "text": "A day on Mars lasts about 24 hours and 39 minutes."},
    {"id": 4, "text": "Jupiter is the largest planet in the solar system."},
    {"id": 5, "text": "The rover Perseverance landed on Mars in February 2021."},
]
PLANETS = {"Mercury", "Venus", "Earth", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Other"}

def check_card(text: str) -> list[str]:
    text = (text or "").strip()
    if "\n" in text:
        return ["more than one line"]
    m = re.fullmatch(r"(\w+) \| (.+)", text)
    if not m:
        return ["not 'Planet | summary'"]
    problems = []
    if m.group(1) not in PLANETS:
        problems.append(f"unknown label {m.group(1)!r}")
    if len(m.group(2).split()) > 10:
        problems.append("summary over 10 words")
    if text.endswith("."):
        problems.append("ends with a full stop")
    return problems

def score(results):
    passed = 0
    for n, (text, _) in zip(TEST_NOTES, results):
        problems = check_card(text)
        passed += not problems
        print(f"note {n['id']}: {text!r} -> {'PASS' if not problems else 'FAIL ' + ', '.join(problems)}")
    print(f"=> {passed}/{len(results)} usable cards")
    return passed

def ask(prompt, system=None):
    config = types.GenerateContentConfig(system_instruction=system, max_output_tokens=200,
                                         automatic_function_calling=NO_AFC)
    resp = client.models.generate_content(model=MODEL, contents=prompt, config=config)
    return (resp.text or "").strip(), resp.usage_metadata.prompt_token_count

ROLE = ("You are Scout's note indexer. You turn a user's research notes into short, exact index "
        "cards. You never add facts that are not in the note.")
INSTRUCTIONS = """Write one card for the note above, for a list in Scout's notes app.
Format: the planet the note is about, then " | ", then a summary of at most 10 words.
- Use one of: Mercury, Venus, Earth, Mars, Jupiter, Saturn, Uranus, Neptune, Other.
- No full stop at the end, no quotes, no text before or after the card.
The app splits each line on " | ", so anything else breaks the list."""

# %% [markdown]
# The answer: the strong prompt with the `<examples>` block removed. Note first, instructions last.

# %% tags=["needs-llm"]
def no_examples_prompt(note: dict) -> str:
    return f"<note>{note['text']}</note>\n\n<instructions>\n{INSTRUCTIONS}\n</instructions>"

no_examples = [ask(no_examples_prompt(n), system=ROLE) for n in TEST_NOTES]
no_examples_score = score(no_examples)
print(f"~{sum(t for _, t in no_examples) / 5:.0f} input tokens per call (strong prompt in lesson 19: ~312)")

# %% [markdown]
# Still 5/5, at about half the input tokens (165 vs 312). For this simple format the clear instructions did
# the work and the examples mostly cost tokens. Examples earn their place when the format is hard to
# describe in words, or on smaller models. Only measuring tells you which case you are in. (A bonus here:
# without the examples, note 5's card kept the rover's name.)

# %% [markdown]
# ## Lesson 20
# Setup from lesson 20: `NOTE_SCHEMA`, `STRICTER`, `ANTHROPIC_BAD` and `lint`, unchanged (no model calls).

# %%
import copy

NOTE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "short title, under 8 words"},
        "topics": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 3,
                   "description": "lowercase topic words"},
        "date": {"anyOf": [{"type": "string"}, {"type": "null"}],
                 "description": "month the note mentions, YYYY-MM, else null"},
    },
    "required": ["title", "topics", "date"],
    "additionalProperties": False,
}
STRICTER = copy.deepcopy(NOTE_SCHEMA)
STRICTER["properties"]["title"]["maxLength"] = 60
ANTHROPIC_BAD = {"minimum", "maximum", "multipleOf", "minLength", "maxLength", "maxItems"}

def lint(schema: dict, vendor: str, path: str = "$") -> list[str]:
    issues = [f"{path}: '{k}' not supported" for k in schema if vendor == "anthropic" and k in ANTHROPIC_BAD]
    if vendor == "anthropic" and schema.get("type") == "object" and schema.get("additionalProperties") is not False:
        issues.append(f"{path}: object needs additionalProperties: false")
    for name, sub in schema.get("properties", {}).items():
        issues += lint(sub, vendor, f"{path}.{name}")
    if isinstance(schema.get("items"), dict):
        issues += lint(schema["items"], vendor, f"{path}[]")
    return issues

# %% [markdown]
# The answer: walk the schema recursively. Move each unsupported keyword into the description, and close
# every object. The limits are now only requests to the model, so check them after the reply (lesson 21).

# %%
def to_anthropic(schema: dict) -> dict:
    out = copy.deepcopy(schema)
    moved = [f"{k}: {out.pop(k)}" for k in sorted(ANTHROPIC_BAD) if k in out]
    if moved:
        out["description"] = (out.get("description", "") + f" ({', '.join(moved)})").strip()
    if out.get("type") == "object":
        out["additionalProperties"] = False
        out["properties"] = {name: to_anthropic(sub) for name, sub in out.get("properties", {}).items()}
    if isinstance(out.get("items"), dict):
        out["items"] = to_anthropic(out["items"])
    return out

fixed = to_anthropic(STRICTER)
print("lint before:", lint(STRICTER, "anthropic"))
print("lint after: ", lint(fixed, "anthropic") or "ok")
print("title:", fixed["properties"]["title"])
print("topics:", fixed["properties"]["topics"]["description"])

# %% [markdown]
# ## Lesson 21
# Setup from lesson 21: the notes, the rules class, `explain`, the fake model and `extract` exactly as in
# the lesson (no model calls).

# %%
from pydantic import BaseModel, Field, ValidationError, ValidationInfo, field_validator

NOTES = [{"id": 1, "text": "Mars has two small moons, Phobos and Deimos."}]

class CheckedRecord(BaseModel):
    title: str = Field(min_length=1)
    topics: list[str] = Field(min_length=1, max_length=3)
    date: str | None = Field(pattern=r"^\d{4}-\d{2}$")

    @field_validator("date")
    @classmethod
    def year_in_note(cls, date, info: ValidationInfo):
        if date and date[:4] not in (info.context or {}).get("note", ""):
            raise ValueError(f"year {date[:4]} does not appear in the note")
        return date

def explain(e: ValidationError) -> str:
    return "\n".join(f"- {'.'.join(map(str, err['loc'])) or 'reply'}: {err['msg']} (got {err['input']!r})"
                     for err in e.errors(include_url=False))

class ScriptedModel:
    def __init__(self, replies): self.replies, self.seen = list(replies), []
    def __call__(self, messages):
        self.seen.append([dict(m) for m in messages]); return self.replies.pop(0)

class ExtractionFailed(Exception):
    pass

def extract(note, model, schema=CheckedRecord, max_attempts=3):
    messages = [{"role": "user", "text": f"Extract the title, topics and date from this note as JSON: {note['text']}"}]
    for attempt in range(1, max_attempts + 1):
        reply = model(messages)
        try:
            return schema.model_validate_json(reply, context={"note": note["text"]}), attempt
        except ValidationError as e:
            messages += [{"role": "assistant", "text": reply},
                         {"role": "user", "text": f"Your JSON failed validation:\n{explain(e)}\n"
                                                  "Reply again with the corrected JSON only."}]
    raise ExtractionFailed(f"note {note['id']}: no valid record after {max_attempts} attempts")

# %% [markdown]
# The answer: a subclass of `CheckedRecord` adds the title rule (and keeps the date rule), and `extract`
# takes it through its `schema` parameter.

# %%
class ShortTitleRecord(CheckedRecord):
    @field_validator("title")
    @classmethod
    def at_most_6_words(cls, title: str) -> str:
        if len(title.split()) > 6:
            raise ValueError(f"title must have at most 6 words, it has {len(title.split())}")
        return title

# %% [markdown]
# A 10-word title first, then a fixed one.

# %%
long_title = '{"title": "The planet Mars has two small moons, Phobos and Deimos", "topics": ["mars"], "date": null}'
short_title = '{"title": "Two moons of Mars", "topics": ["mars"], "date": null}'
fake = ScriptedModel([long_title, short_title])
record, attempts = extract(NOTES[0], fake, schema=ShortTitleRecord)
print(record, "| attempts:", attempts)
print("feedback sent:", fake.seen[1][-1]["text"].splitlines()[1])

# %% [markdown]
# ## Lesson 22
# The answer: two schemas in one `Tool`, and the result goes back under whichever name and id Gemini
# used. Setup from lesson 22 first: the six notes and both tools.

# %%
import json

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

def count_notes() -> dict:
    return {"count": len(NOTES)}

TOOLS = {"search_notes": search_notes, "count_notes": count_notes}

# %% [markdown]
# Both schemas. `count_notes` takes no arguments, so its parameters are an empty object.

# %%
DECLS = [
    types.FunctionDeclaration(name="search_notes", description="Search the user's notes for one word; "
        "returns matching notes as a list of {id, text}.", parameters_json_schema={
        "type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}),
    types.FunctionDeclaration(name="count_notes", description="Return how many notes the user has, "
        "as {count}.", parameters_json_schema={"type": "object", "properties": {}}),
]
CFG2 = types.GenerateContentConfig(tools=[types.Tool(function_declarations=DECLS)],
                                   automatic_function_calling=NO_AFC, max_output_tokens=300)

# %% [markdown]
# The round trip: call, run the tool Gemini chose, answer with its id, call again.

# %%
contents = [types.Content(role="user", parts=[types.Part(text="How many notes do I have?")])]
resp1 = client.models.generate_content(model=MODEL, contents=contents, config=CFG2)
fc = resp1.function_calls[0]
output = TOOLS[fc.name](**(fc.args or {}))
result = output if isinstance(output, dict) else {"result": output}
print("tool call:", fc.id, fc.name, fc.args, "->", result)
contents.append(resp1.candidates[0].content)
contents.append(types.Content(role="user", parts=[types.Part(function_response=types.FunctionResponse(
    id=fc.id, name=fc.name, response=result))]))
resp2 = client.models.generate_content(model=MODEL, contents=contents, config=CFG2)
print(resp2.text)

# %% [markdown]
# ## Lesson 25
# `return_exceptions=True` makes `gather` hand back the exception object in that call's slot instead of
# raising it, so every call still gets a result with its id. No model calls here: the two tool calls are
# the ones the fake model made in the lesson.

# %%
import asyncio, time

def flaky_search(query: str) -> list[dict]:
    time.sleep(0.5)
    if query == "Venus":
        raise RuntimeError("search backend down")
    return search_notes(query)

async def run_tool_calls(tool_calls: list[dict], tools: dict) -> list[dict]:
    outputs = await asyncio.gather(*(asyncio.to_thread(tools[c["name"]], **c["args"]) for c in tool_calls),
                                   return_exceptions=True)
    return [{"call_id": c["id"], "name": c["name"],
             "content": json.dumps({"error": str(out)} if isinstance(out, Exception) else out)}
            for c, out in zip(tool_calls, outputs)]

calls = [{"id": "call_1", "name": "search_notes", "args": {"query": "Mars"}},
         {"id": "call_2", "name": "search_notes", "args": {"query": "Venus"}}]
for r in await run_tool_calls(calls, {"search_notes": flaky_search}):
    print(r["call_id"], r["content"])

# %%
llm_replay.stop()

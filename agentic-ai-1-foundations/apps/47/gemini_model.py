"""Scout's Gemini adapter (lesson 35) as a file. Pinned model, temperature 0, prompts in code."""
import json, os
from google import genai
from google.genai import types
from scout_tools import TOOLS

MODEL = "gemini-3.5-flash-lite"                     # pinned: a new model means a new recording
QUESTION = "How many minutes long is a day on Mars?"
SYSTEM = ("You are Scout, a research assistant over the user's notes. Look facts up with search_notes "
          "and do every calculation with the calculator tool. Answer in one sentence.")
FULL_SCHEMAS = [
    {"name": "search_notes", "description": TOOLS["search_notes"].__doc__,
     "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "calculator", "description": TOOLS["calculator"].__doc__,
     "parameters": {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]}},
]
# No key in replay: the cassette answers, so a placeholder is enough.
client = genai.Client(vertexai=True, api_key=os.environ.get("GOOGLE_CLOUD_API_KEY") or "replay-no-key-needed")

def to_contents(messages: list[dict]) -> list[types.Content]:
    contents = []
    for m in messages:
        if m["role"] == "user":
            contents.append(types.Content(role="user", parts=[types.Part(text=m["text"])]))
        elif m["role"] == "assistant":
            contents.append(m["raw"])                            # keeps the thought signature
        else:
            response = {"error": m["content"]} if m["is_error"] else {"output": json.loads(m["content"])}
            part = types.Part(function_response=types.FunctionResponse(id=m["call_id"], name=m["name"], response=response))
            if contents[-1].role == "user" and contents[-1].parts[0].function_response:
                contents[-1].parts.append(part)
            else:
                contents.append(types.Content(role="user", parts=[part]))
    return contents

class GeminiModel:
    def __init__(self, system: str = SYSTEM):
        self.system = system

    def __call__(self, messages: list[dict], tools: list[dict]) -> dict:
        decls = [types.Tool(function_declarations=[types.FunctionDeclaration(
            name=s["name"], description=s["description"], parameters_json_schema=s["parameters"]) for s in tools])]
        cfg = types.GenerateContentConfig(system_instruction=self.system, temperature=0, max_output_tokens=300,
                                          tools=decls, automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
        resp = client.models.generate_content(model=MODEL, contents=to_contents(messages), config=cfg)
        raw = resp.candidates[0].content
        calls = [{"id": fc.id, "name": fc.name, "args": dict(fc.args)} for fc in resp.function_calls or []]
        if calls:
            return {"role": "assistant", "tool_calls": calls, "raw": raw}
        return {"role": "assistant", "text": resp.text, "raw": raw}

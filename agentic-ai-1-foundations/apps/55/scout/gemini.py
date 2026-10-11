"""The real model behind Scout: Gemini on Vertex, async, with the pinned settings (lessons 35, 40, 53)."""
import asyncio, json, time
from google.genai import types
from .config import MODEL, PROMPT

def to_contents(messages: list[dict]) -> list[types.Content]:
    contents = []
    for m in messages:
        if m["role"] == "user":
            contents.append(types.Content(role="user", parts=[types.Part(text=m["text"])]))
        elif m["role"] == "assistant":
            contents.append(m["raw"])                                   # keeps thought signatures
        else:
            response = {"error": m["content"]} if m["is_error"] else {"output": json.loads(m["content"])}
            part = types.Part(function_response=types.FunctionResponse(id=m["call_id"], name=m["name"],
                                                                       response=response))
            if contents[-1].role == "user" and contents[-1].parts[0].function_response:
                contents[-1].parts.append(part)
            else:
                contents.append(types.Content(role="user", parts=[part]))
    return contents

class GeminiModel:
    """`pause_s` waits before the clock starts (for the course's recorder); 0 in production."""
    def __init__(self, client, settings: dict = MODEL, pause_s: float = 0.0, timeout_s: int = 30):
        self.client, self.settings, self.pause_s = client, settings, pause_s
        self.name, self.max_out, self.timeout_ms = settings["model"], settings["max_output_tokens"], timeout_s * 1000

    def config(self, schemas: list[dict]) -> types.GenerateContentConfig:
        s = self.settings
        decls = [types.FunctionDeclaration(name=x["name"], description=x["description"],
                                           parameters_json_schema=x["parameters"]) for x in schemas]
        return types.GenerateContentConfig(system_instruction=PROMPT, temperature=s["temperature"],
            max_output_tokens=s["max_output_tokens"], tools=[types.Tool(function_declarations=decls)],
            thinking_config=types.ThinkingConfig(thinking_level=s["thinking_level"]),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            http_options=types.HttpOptions(timeout=self.timeout_ms))

    async def __call__(self, messages: list[dict], schemas: list[dict]) -> dict:
        await asyncio.sleep(self.pause_s)
        t0 = time.perf_counter()
        resp = await self.client.aio.models.generate_content(model=self.name, contents=to_contents(messages),
                                                             config=self.config(schemas))
        u = resp.usage_metadata
        usage = {"in": u.prompt_token_count or 0, "seconds": round(time.perf_counter() - t0, 3),
                 "out": (u.candidates_token_count or 0) + (u.thoughts_token_count or 0)}   # thinking = output
        raw = resp.candidates[0].content
        calls = [{"id": fc.id, "name": fc.name, "args": dict(fc.args)} for fc in resp.function_calls or []]
        if calls:
            return {"role": "assistant", "tool_calls": calls, "raw": raw, "usage": usage}
        return {"role": "assistant", "text": resp.text or "", "raw": raw, "usage": usage}

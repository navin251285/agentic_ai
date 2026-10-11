"""Fake models for tests and load tests: scripted replies with usage, and a provider that fails."""
import asyncio, json

class ProviderError(Exception):
    """Looks like an SDK error: a status `code` and, for a 429, a `retry_after` in seconds."""
    def __init__(self, code: int, message: str = "", retry_after: float = 0.0):
        super().__init__(f"{code} {message}".strip())
        self.code, self.retry_after = code, retry_after

class ScriptedModel:
    """Plays `script` in order (the last reply repeats). Items may be replies, functions or exceptions."""
    def __init__(self, script: list, name: str = "gemini-3.5-flash-lite", max_out: int = 300,
                 usage=(400, 30), latency: float = 0.0):
        self.script, self.name, self.max_out, self.usage, self.latency = script, name, max_out, usage, latency
        self.calls = 0

    async def __call__(self, messages: list[dict], schemas: list[dict]) -> dict:
        self.calls += 1
        item = self.script[min(self.calls, len(self.script)) - 1]
        await asyncio.sleep(self.latency)
        if isinstance(item, Exception):
            raise item
        reply = item(messages) if callable(item) else json.loads(json.dumps(item))
        for i, call in enumerate(reply.get("tool_calls", [])):
            call["id"] = f"call_{self.calls}_{i}"
        return {"role": "assistant", **reply,
                "usage": {"in": self.usage[0] + 50 * len(messages), "out": self.usage[1], "seconds": self.latency}}

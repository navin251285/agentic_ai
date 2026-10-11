"""The scripted fake model from lesson 35: a list of replies, played in order (the last one repeats)."""
import json

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

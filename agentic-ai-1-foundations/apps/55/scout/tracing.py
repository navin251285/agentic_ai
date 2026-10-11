"""One JSON line per event, OpenTelemetry GenAI names, personal data redacted (lesson 49)."""
import json, re
from pathlib import Path

REDACTIONS = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[EMAIL]"),
    (re.compile(r"(?<![\w.+-])(?:\+|0)\d[\d ()-]{7,}\d(?![\w-]|\.\d)"), "[PHONE]"),
    (re.compile(r"(?i)\bbearer\s+[\w.-]+|\bsk-[\w-]{20,}|\bAIza[\w-]{30,}"), "[SECRET]"),
]
ID_KEYS = {"gen_ai.response.id", "gen_ai.tool.call.id", "scout.run_id"}

def redact(value):
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        for pattern, placeholder in REDACTIONS:
            value = pattern.sub(placeholder, value)
    return value

class Tracer:
    """Appends to one file shared by many runs; every line carries its run id and sequence number."""
    def __init__(self, path, run_id: str):
        self.path, self.run_id, self.seq = Path(path), run_id, 0
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def event(self, operation: str, **attrs) -> None:
        self.seq += 1
        record = {"gen_ai.operation.name": operation, "scout.run_id": self.run_id, "scout.seq": self.seq,
                  **{k: (v if k in ID_KEYS else redact(v)) for k, v in attrs.items()}}
        with self.path.open("a") as f:
            f.write(json.dumps(record) + "\n")

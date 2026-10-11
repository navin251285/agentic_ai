"""Shared test setup: one user's tools in a temporary folder, a trace file, and one run."""
import asyncio, json
from scout import NOTES, Guard, RunBudget, Tracer, make_tools, run_scout

SEARCH = {"tool_calls": [{"name": "search_notes", "args": {"query": "day on Mars"}}]}
CALC = {"tool_calls": [{"name": "calculator", "args": {"expression": "24*60+39"}}]}
ANSWER = {"text": "A day on Mars is 1479 minutes."}

def run(tmp_path, model, task="answer", notes=NOTES, approver=None, budget=None, question="Mars day?"):
    tools = make_tools(notes, tmp_path / "files")
    guard = Guard(task, approver, audit=tmp_path / "audit.jsonl", run_id="t1")
    out = asyncio.run(run_scout(question, model, tools, guard, Tracer(tmp_path / "trace.jsonl", "t1"),
                                budget or RunBudget(0.01)))
    return out

def trace(tmp_path) -> list[dict]:
    return [json.loads(line) for line in (tmp_path / "trace.jsonl").read_text().splitlines()]

"""Try it (lesson 46): one failing call must not stop the other calls in the same turn."""
import json
from fake_model import ScriptedModel
from scout_loop import run_agent
from scout_tools import SCHEMAS, TOOLS

def run(script, question="?", **kw):
    model = ScriptedModel(script)
    return run_agent(question, model, TOOLS, SCHEMAS, **kw), model

def test_one_failing_call_does_not_stop_the_others():
    both = {"tool_calls": [{"name": "calculator", "args": {"expression": "2^10"}},
                           {"name": "search_notes", "args": {"query": "Venus"}}]}
    result, model = run([both, {"text": "Venus spins backwards."}])
    results = [m for m in result["messages"] if m["role"] == "tool"]
    assert result["errors"] == 1
    assert [m["is_error"] for m in results] == [True, False]
    assert [m["call_id"] for m in results] == ["call_1", "call_2"]
    assert json.loads(results[1]["content"])[0]["id"] == 2
    assert result["stop"] == "end_of_turn" and model.calls == 2

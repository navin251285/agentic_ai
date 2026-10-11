"""Unit tests for Scout's loop. No key, no network: every model reply is scripted."""
import json
from fake_model import ScriptedModel
from scout_loop import run_agent
from scout_tools import SCHEMAS, TOOLS

def run(script, question="?", **kw):
    model = ScriptedModel(script)                             # a fresh fake for every test
    return run_agent(question, model, TOOLS, SCHEMAS, **kw), model

def last(messages): return json.loads(messages[-1]["content"])

def test_answer_without_tools():
    result, model = run([{"text": "Mars has two moons."}])
    assert result["answer"] == "Mars has two moons."
    assert result["stop"] == "end_of_turn" and result["steps"] == 1
    assert model.calls == 1

HAPPY = [{"tool_calls": [{"name": "search_notes", "args": {"query": "day on Mars"}}]},
         {"tool_calls": [{"name": "calculator", "args": {"expression": "24*60+39"}}]},
         lambda m: {"text": f"A day on Mars is {last(m)} minutes."}]

def test_tool_results_reach_the_model():
    result, model = run(HAPPY)
    assert result["answer"] == "A day on Mars is 1479 minutes."
    assert "24 hours and 39 minutes" in result["messages"][2]["content"]
    assert result["errors"] == 0 and result["steps"] == 3 and model.calls == 3

def test_step_limit_stops_a_model_that_never_answers():
    stubborn = [{"tool_calls": [{"name": "search_notes", "args": {"query": "Pluto"}}]}]
    result, model = run(stubborn, max_steps=3)
    assert result["stop"] == "step_limit" and result["answer"] is None
    assert result["steps"] == 3 and model.calls == 3

def test_raising_tool_becomes_an_error_and_the_model_recovers():
    calc = lambda e: {"tool_calls": [{"name": "calculator", "args": {"expression": e}}]}
    result, _ = run([calc("2^10"), calc("2**10"), lambda m: {"text": f"2^10 is {last(m)}."}])
    error = result["messages"][2]
    assert error["is_error"] and error["content"].startswith("ValueError: '2 ^ 10' is not plain")
    assert result["errors"] == 1 and result["answer"] == "2^10 is 1024."
    assert result["stop"] == "end_of_turn"

def test_unknown_tool_lists_the_real_tools():
    result, _ = run([{"tool_calls": [{"name": "web_search", "args": {"q": "Mars"}}]},
                     {"text": "I can only search your notes."}])
    error = result["messages"][2]
    assert error["is_error"] and "search_notes, calculator" in error["content"]
    assert result["stop"] == "end_of_turn" and result["errors"] == 1

def test_parallel_calls_each_get_their_result():
    both = {"tool_calls": [{"name": "search_notes", "args": {"query": "moons"}},
                           {"name": "search_notes", "args": {"query": "Venus"}}]}
    result, model = run([both, {"text": "Mars has two moons; Venus spins backwards."}])
    results = [m for m in result["messages"] if m["role"] == "tool"]
    assert [m["call_id"] for m in results] == ["call_1", "call_2"]
    assert [json.loads(m["content"])[0]["id"] for m in results] == [1, 2]
    assert model.calls == 2 and result["steps"] == 2

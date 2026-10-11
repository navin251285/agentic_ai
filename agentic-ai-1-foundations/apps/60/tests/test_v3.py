import asyncio
from scout import NOTES, SCHEMAS, Guard, RunBudget, Tracer, make_tools, run_scout
from scout.fake import ScriptedModel
from helpers import ANSWER, SEARCH, run

def days(start: str) -> dict:
    return {"tool_calls": [{"name": "days_between", "args": {"start": start, "end": "2026-10-09"}}]}

def flaky(tool, failures: int = 1):
    left = [failures]
    def wrapper(**args):
        if left[0] > 0:
            left[0] -= 1
            raise OSError("the notes index is being rebuilt. Retry the same call in a moment.")
        return tool(**args)
    return wrapper

def test_new_tool_is_offered_and_runs(tmp_path):
    out = run(tmp_path, ScriptedModel([days("2021-02-18"), {"text": "2059 days."}]))
    assert "days_between" in [s["name"] for s in SCHEMAS]
    assert (out["stop"], out["errors"], out["messages"][2]["content"]) == ("end_of_turn", 0, "2059")

def test_bad_date_is_an_error_the_model_can_fix(tmp_path):
    out = run(tmp_path, ScriptedModel([days("February 2021"), days("2021-02-18"), {"text": "2059 days."}]))
    assert (out["stop"], out["errors"]) == ("end_of_turn", 1)
    assert "YYYY-MM-DD" in out["messages"][2]["content"] and out["messages"][4]["content"] == "2059"

def test_a_tool_that_crashes_once_does_not_end_the_run(tmp_path):
    tools = make_tools(NOTES, tmp_path / "files")
    tools["search_notes"] = flaky(tools["search_notes"])
    out = asyncio.run(run_scout("Mars day?", ScriptedModel([SEARCH, SEARCH, ANSWER]), tools, Guard("answer"),
                                Tracer(tmp_path / "t.jsonl", "t"), RunBudget(0.01)))
    assert (out["stop"], out["errors"], out["steps"]) == ("end_of_turn", 1, 3)
    assert "Retry" in out["messages"][2]["content"] and "Mars" in out["messages"][4]["content"]

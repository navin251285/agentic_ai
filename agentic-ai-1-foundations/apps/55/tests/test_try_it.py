from scout.fake import ScriptedModel
from helpers import ANSWER, run

def test_unknown_tool_is_an_error_not_a_crash(tmp_path):
    weather = {"tool_calls": [{"name": "get_weather", "args": {"city": "Jezero"}}]}
    out = run(tmp_path, ScriptedModel([weather, ANSWER]))
    assert (out["stop"], out["errors"], out["denied"]) == ("end_of_turn", 1, 1)
    assert "not allowed" in out["messages"][2]["content"]

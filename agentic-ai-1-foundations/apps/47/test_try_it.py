"""Try it (lesson 47): the replayed run's calculator result reached the model."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "46"))
from recording import make_vcr
from gemini_model import FULL_SCHEMAS, QUESTION, GeminiModel
from scout_loop import run_agent
from scout_tools import TOOLS

def test_calculator_ran_once_and_gave_1479():
    with make_vcr().use_cassette("mars_day.yaml", allow_playback_repeats=False) as cassette:
        result = run_agent(QUESTION, GeminiModel(), TOOLS, FULL_SCHEMAS)
    calc = [m for m in result["messages"] if m["role"] == "tool" and m["name"] == "calculator"]
    assert len(calc) == 1 and not calc[0]["is_error"]
    assert json.loads(calc[0]["content"]) == 1479
    assert cassette.all_played

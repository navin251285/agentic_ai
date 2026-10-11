"""End-to-end test: Scout with the real Gemini model, recorded once to cassettes/mars_day.yaml."""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "46"))   # Scout's loop and tools (lesson 46)
from recording import CASSETTES, make_vcr
from gemini_model import FULL_SCHEMAS, QUESTION, GeminiModel
from scout_loop import run_agent
from scout_tools import TOOLS

def test_scout_answers_mars_day_with_the_real_model():
    with make_vcr().use_cassette("mars_day.yaml", allow_playback_repeats=False) as cassette:
        result = run_agent(QUESTION, GeminiModel(), TOOLS, FULL_SCHEMAS)
    tools = [c["name"] for m in result["messages"] for c in m.get("tool_calls", [])]
    assert tools == ["search_notes", "calculator"]
    assert "1479" in result["answer"].replace(",", "")
    assert result["stop"] == "end_of_turn" and result["errors"] == 0
    assert len(cassette) == 3                                   # three model calls recorded
    if cassette.record_mode == "none":
        assert cassette.all_played                              # ...and all three replayed, in order

def test_cassettes_hold_no_secrets():
    key = os.environ.get("GOOGLE_CLOUD_API_KEY")
    for path in CASSETTES.glob("*.yaml"):
        text = path.read_text()
        assert "x-goog-api-key" not in text.lower(), f"{path.name} holds the key header"
        assert not key or key not in text, f"{path.name} holds the key"

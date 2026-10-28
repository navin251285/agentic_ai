"""Tests run offline. Model calls replay the recordings in tests/cassettes (made once with llm_replay)."""
import os
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
TOPIC = APP.parent  # llm_replay.py lives in the topic folder, next to the lessons
sys.path.insert(0, str(TOPIC))

os.environ.setdefault("TUT_LLM_MODE", "replay")  # replay only: a call with no recording fails, it never goes out
os.environ.setdefault("TUT_CASSETTE_DIR", str(APP / "tests" / "cassettes"))
if os.environ["TUT_LLM_MODE"] == "replay":
    # A placeholder key lets the client be built with no real key. No request leaves the machine in replay mode.
    os.environ.setdefault("GOOGLE_CLOUD_API_KEY", "replay-no-key-needed")

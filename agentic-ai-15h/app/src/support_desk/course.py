"""The bridge to the course folder: the shared model helper, the recorder and the .env reader.

The app lives in <course>/app/ and reuses the course's own helpers (llm_setup.py, llm_replay.py,
tut_env.py) so every model call follows the same rules as the lessons: get_llm() under llm_replay.
Nothing here reads or prints a key: tut_env reads the course's .env, and llm_setup never prints it.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]      # <course>/app
COURSE_ROOT = APP_ROOT.parent                        # <course>, where llm_setup.py and .env live

if str(COURSE_ROOT) not in sys.path:
    sys.path.insert(0, str(COURSE_ROOT))
# Recordings for the app's own model calls live beside its tests; the course's data/ folder is not touched.
os.environ.setdefault("TUT_CASSETTE_DIR", str(APP_ROOT / "tests" / "cassettes"))

import llm_replay  # noqa: E402  (course helper: records and replays model calls)
from llm_setup import get_llm  # noqa: E402  (course helper: the default Gemini model, no key while replaying)
from tut_env import env  # noqa: E402  (course helper: one setting from the environment or the course .env)

__all__ = ["APP_ROOT", "COURSE_ROOT", "env", "get_llm", "llm_replay"]

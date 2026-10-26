"""Test setup: the course folder on sys.path (for tut_env, llm_setup, llm_replay) and the app's own cassettes."""
import os
import sys
import tempfile
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
COURSE = APP.parent

for path in (APP / "src", COURSE):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

# llm_replay keeps the app's model recordings next to the tests, not in the course's data folder.
os.environ.setdefault("TUT_CASSETTE_DIR", str(APP / "tests" / "cassettes"))
# The tests never write the course's real cases file: every run gets its own empty store (step 2).
os.environ["TRIAGE_STORE_FILE"] = str(Path(tempfile.mkdtemp(prefix="triage-tests-")) / "issues.csv")
# Step 3: the tests use their own service token (never the course's) and their own trace file.
os.environ["TRIAGE_SERVICE_TOKEN"] = "test-service-token-not-real"
os.environ["TRIAGE_TRACE_FILE"] = str(Path(tempfile.mkdtemp(prefix="triage-traces-")) / "traces.jsonl")

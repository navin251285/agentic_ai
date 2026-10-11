import os
import sys

import pytest
from fastapi.testclient import TestClient

# The repo under test: POCKET_TRACKER_REPO, default the original app next to this folder.
REPO = os.environ.get("POCKET_TRACKER_REPO", os.path.join(os.path.dirname(__file__), "..", "pocket_tracker"))
sys.path.insert(0, os.path.abspath(REPO))
from app import app  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("POCKET_TRACKER_DB", str(tmp_path / "hidden.db"))
    with TestClient(app) as test_client:
        yield test_client

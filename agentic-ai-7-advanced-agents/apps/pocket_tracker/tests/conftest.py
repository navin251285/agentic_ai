import pytest
from fastapi.testclient import TestClient

from app import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A test client on a fresh database seeded from issues.json."""
    monkeypatch.setenv("POCKET_TRACKER_DB", str(tmp_path / "test.db"))
    with TestClient(app) as test_client:   # the with-block runs startup (creates and seeds the db)
        yield test_client

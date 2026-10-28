"""Step 4: one run command, the settings it reads, and the whole app started as a server.

No model call is made here: /health and the page need no key, and the replayed recordings of steps 1 to 3 cover the
model. The end-to-end test starts the real server on a free local port and stops it again.
"""
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient

import brightside_desk.__main__ as entry
from brightside_desk.api import app
from brightside_desk.config import load_settings

APP = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_health_and_the_page_are_served():
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}
    page = client.get("/")
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    assert "Brightside support desk" in page.text


def test_port_and_host_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("APP_PORT", "8991")
    monkeypatch.setenv("APP_HOST", "127.0.0.1")
    settings = load_settings()
    assert (settings.port, settings.host) == (8991, "127.0.0.1")


def test_the_default_port_is_the_course_port(monkeypatch):
    monkeypatch.delenv("APP_PORT", raising=False)
    monkeypatch.delenv("APP_HOST", raising=False)
    settings = load_settings()
    assert (settings.port, settings.host) == (8980, "127.0.0.1")


@pytest.mark.parametrize("bad", ["abc", "0", "70000", "-5"])
def test_a_bad_port_is_refused_and_the_message_names_the_setting(monkeypatch, bad):
    monkeypatch.setenv("APP_PORT", bad)
    with pytest.raises(ValueError) as err:
        load_settings()
    assert "APP_PORT" in str(err.value)  # the message names the setting, not the value


def test_the_one_command_starts_uvicorn_with_the_settings(monkeypatch):
    calls = []
    monkeypatch.setattr(uvicorn, "run", lambda target, **kw: calls.append((target, kw)))
    monkeypatch.setenv("APP_PORT", "8985")
    monkeypatch.delenv("APP_HOST", raising=False)
    assert entry.main([]) == 0
    target, kw = calls[-1]
    assert target == "brightside_desk.api:app"
    assert (kw["host"], kw["port"], kw["reload"]) == ("127.0.0.1", 8985, False)


def test_the_port_flag_overrides_the_setting(monkeypatch):
    calls = []
    monkeypatch.setattr(uvicorn, "run", lambda target, **kw: calls.append(kw))
    monkeypatch.setenv("APP_PORT", "8985")
    entry.main(["--port", "8999", "--reload"])
    assert (calls[-1]["port"], calls[-1]["reload"]) == (8999, True)


def test_python_dash_m_serves_health_end_to_end():
    port = _free_port()
    proc = subprocess.Popen([sys.executable, "-m", "brightside_desk", "--port", str(port)], cwd=APP,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        body = None
        deadline = time.time() + 30
        while time.time() < deadline and body is None:
            if proc.poll() is not None:
                pytest.fail("the server exited before it answered")
            try:
                body = httpx.get(f"http://127.0.0.1:{port}/health", timeout=1).json()
            except httpx.HTTPError:
                time.sleep(0.2)
        assert body == {"status": "ok"}
        assert "Brightside support desk" in httpx.get(f"http://127.0.0.1:{port}/", timeout=5).text
    finally:
        proc.terminate()
        proc.wait(timeout=15)


def test_the_readme_names_the_one_command_and_the_health_check():
    readme = (APP / "README.md").read_text(encoding="utf-8")
    assert "python -m brightside_desk" in readme
    assert "/health" in readme
    assert "pytest" in readme

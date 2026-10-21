"""Step 4: the one run command, and the whole app checked end to end (offline, FastAPI's TestClient).

The run command is `python -m support_desk`. These tests check that it starts uvicorn on the configured port
(without starting a server), that every route the page calls exists, and that the finished app answers.
"""
import re

from fastapi.testclient import TestClient

import support_desk.__main__ as entry
from support_desk.api import STATIC_DIR, app
from support_desk.settings import load_settings

client = TestClient(app)

ROUTES = {
    "/", "/health", "/api/chat", "/api/desk/memory", "/api/desk/memory/{customer_id}", "/api/desk/chat",
    "/api/desk/decision", "/api/desk/runs/{thread_id}", "/api/traces", "/api/traces/{thread_id}",
}


def test_the_run_command_starts_uvicorn_on_the_configured_port(monkeypatch):
    started = {}
    monkeypatch.setenv("SUPPORT_PORT", "8991")
    monkeypatch.setattr(entry.uvicorn, "run", lambda app_path, **kwargs: started.update(app=app_path, **kwargs))
    entry.main()
    assert started == {"app": "support_desk.api:app", "host": "127.0.0.1", "port": 8991, "reload": False}


def test_the_default_port_is_8980(monkeypatch):
    monkeypatch.delenv("SUPPORT_PORT", raising=False)
    assert load_settings().port == 8980


def test_every_route_of_the_app_is_one_the_guide_names():
    paths = {route.path for route in app.routes if hasattr(route, "methods")}
    assert ROUTES <= paths, f"missing routes: {sorted(ROUTES - paths)}"


def test_every_api_call_in_the_page_is_a_real_route():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    paths = {route.path for route in app.routes if hasattr(route, "methods")}
    literals = set(re.findall(r'"(/api/[^"]*)"', html))
    assert literals, "the page calls no API"
    for literal in literals:
        assert literal in paths or any(p.startswith(literal + "{") for p in paths), f"the page calls {literal}"


def test_health_answers_for_the_finished_app():
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["tools"] == ["lookup_order", "calculator"]
    assert body["desk_tools"] == ["lookup_order", "search_policy", "refund_order"]


def test_the_page_is_served_at_the_root():
    response = client.get("/")
    assert response.status_code == 200
    assert "Brightside support desk" in response.text
    assert "Traces and cost" in response.text


def test_the_dashboard_answers_with_its_summary():
    body = client.get("/api/traces").json()
    assert set(body["summary"]) >= {"tickets", "cost_per_ticket_usd", "p95_latency_ms", "slo_breached"}

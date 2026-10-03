import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import API_DIR, Settings
from app.main import build_repository, create_app


def make_settings(**kw) -> Settings:
    return Settings(_env_file=None, **kw)


def test_blank_values_become_none():
    s = make_settings(sim_seed="", google_cloud_api_key=" ")
    assert s.sim_seed is None and s.google_cloud_api_key is None


def test_relative_data_dir_is_under_api():
    assert make_settings(data_dir="./data").data_dir == API_DIR / "data"


def test_api_key_is_not_shown_in_repr():
    s = make_settings(google_cloud_api_key="super-secret")
    assert "super-secret" not in repr(s) and "super-secret" not in str(s.model_dump())


@pytest.mark.parametrize(
    "kw", [dict(llm_max_calls_per_min=11), dict(llm_min_gap_s=5), dict(agent_interval_s=0)]
)
def test_llm_budget_cannot_be_raised(kw):
    with pytest.raises(ValidationError):
        make_settings(**kw)


def test_app_starts_and_saves_on_shutdown(data_dir):
    settings = make_settings(data_dir=data_dir, agent_mode="gemini")
    app = create_app(settings, build_repository(settings))
    with TestClient(app) as client:
        assert client.get("/api/health").json() == {"status": "ok"}
        assert len(app.state.data.products) == 10
    assert (data_dir / "products.csv").exists()
    assert (data_dir / "orders.csv").exists()
    assert '"agent_mode": "gemini"' in (data_dir / "runtime.json").read_text(encoding="utf-8")


def test_app_always_starts_paused_and_remembers_speed(data_dir):
    settings = make_settings(data_dir=data_dir)
    repo = build_repository(settings)
    repo.save_runtime({"speed": 5, "last_speed": 5, "sim_s": 30})

    app = create_app(settings, repo)
    with TestClient(app):
        rt = app.state.data.runtime
        assert (rt.speed, rt.last_speed, rt.sim_s) == (0, 5, 30)
    saved = json.loads((data_dir / "runtime.json").read_text(encoding="utf-8"))
    assert (saved["speed"], saved["last_speed"]) == (0, 5)

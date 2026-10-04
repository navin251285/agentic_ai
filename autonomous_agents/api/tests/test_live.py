"""Opt-in smoke test against the real Gemini API: pytest -m live -s

Makes exactly ONE call. Never run it while the demo is running (that limiter cannot see this process).
"""

import asyncio

import pytest

from app.config import get_settings
from app.domain.rules import Zone, product_zone
from app.services.engines.base import AgentContext
from app.services.engines.llm_engine import GeminiEngine, make_llm
from app.services.engines.rate_limiter import LlmRateLimiter
from tests.conftest import make_product

pytestmark = pytest.mark.live

FIRST_CALL_TIMEOUT_S = 30  # the first API-key call can take ~10s


def test_gemini_decides_on_two_products():
    settings = get_settings()
    if settings.google_cloud_api_key is None:
        pytest.skip("GOOGLE_CLOUD_API_KEY is not set")
    limiter = LlmRateLimiter(settings.llm_max_calls_per_min, settings.llm_min_gap_s)
    assert limiter.try_acquire()  # the one call this test makes
    secret = settings.google_cloud_api_key.get_secret_value()
    engine = GeminiEngine(make_llm(settings), secret=secret)
    context = AgentContext(
        sim_s=120,
        products=[
            make_product(stock=12),  # milk: must-order
            make_product(id="eggs", name="Eggs", stock=17, max_stock=40, reorder_point=13),  # watch
        ],
        rush_hour=True,
        sales_last_60s={"milk": 14, "eggs": 10},
    )
    assert [product_zone(p, []) for p in context.products] == [Zone.MUST_ORDER, Zone.WATCH]

    decisions = asyncio.run(asyncio.wait_for(engine.decide(context), FIRST_CALL_TIMEOUT_S))

    print("\nGemini reply:")
    for d in decisions:
        print(f"  {d.product_id:<5} {d.action:<5} qty={d.qty:<3} {d.reason}")
    assert limiter.total == 1
    assert {d.product_id for d in decisions} <= {"milk", "eggs"}
    assert decisions and all(d.source == "gemini" and d.reason for d in decisions)
    assert all(len(d.reason.split()) <= 20 for d in decisions)

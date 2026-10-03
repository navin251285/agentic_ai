import asyncio
import json

import pytest
from pydantic import SecretStr

from app.config import Settings
from app.services.engines.base import AgentContext
from app.services.engines.llm_engine import GeminiEngine, LlmDecision, LlmError, LlmPlan, make_llm
from app.services.engines.prompts import SYSTEM_PROMPT, build_context
from tests.conftest import make_order, make_product
from tests.fakes import FakeChat


def context(**kw) -> AgentContext:
    base = dict(
        sim_s=100,
        products=[make_product(stock=12), make_product(id="eggs", name="Eggs", stock=15, reorder_point=13)],
        orders=[make_order(product_id="bread", qty=10, due_at_s=130)],
        rush_hour=True,
        sales_last_60s={"milk": 9},
    )
    return AgentContext(**{**base, **kw})


def test_context_json_is_compact_and_complete():
    data = json.loads(build_context(context()))
    assert (data["rush_hour"], data["supplier_delay"], data["agent_interval_s"]) == (True, False, 5)
    milk, eggs = data["products"]
    assert milk == {
        "product_id": "milk",
        "name": "Milk",
        "zone": "must_order",
        "stock": 12,
        "max_stock": 30,
        "reorder_point": 12,
        "watch_up_to": 18,
        "room": 18,
        "lead_time_s": 60,
        "sales_last_60s": 9,
    }
    assert eggs["zone"] == "watch" and eggs["sales_last_60s"] == 0
    assert data["open_orders"] == [{"product_id": "bread", "qty": 10, "arrives_in_s": 30}]


def test_engine_maps_structured_output_to_decisions():
    long_reason = " ".join(["word"] * 30)
    chat = FakeChat(
        LlmPlan(
            decisions=[
                LlmDecision(product_id="milk", action="order", qty=18, reason="Rush hour, 60s lead time."),
                LlmDecision(product_id="eggs", action="wait", qty=7, reason=long_reason),
            ]
        )
    )
    milk, eggs = asyncio.run(GeminiEngine(chat).decide(context()))
    assert chat.schema is LlmPlan
    [(role, system), (_, human)] = chat.messages[0]
    assert (role, system) == ("system", SYSTEM_PROMPT) and json.loads(human)["rush_hour"] is True
    assert (milk.action, milk.qty, milk.source, milk.reason) == (
        "order",
        18,
        "gemini",
        "Rush hour, 60s lead time.",
    )
    assert (eggs.action, eggs.qty) == ("wait", 0)
    assert len(eggs.reason.split()) == 20


@pytest.mark.parametrize("reply", [None, {"decisions": []}, "text"])
def test_invalid_output_raises(reply):
    with pytest.raises(LlmError, match="invalid output"):
        asyncio.run(GeminiEngine(FakeChat(reply)).decide(context()))


def test_errors_are_short_and_never_contain_the_key():
    chat = FakeChat(RuntimeError("403 bad key AIza-SECRET for project\nlong trace " + "x" * 500))
    with pytest.raises(LlmError) as err:
        asyncio.run(GeminiEngine(chat, secret="AIza-SECRET").decide(context()))
    msg = str(err.value)
    assert "AIza-SECRET" not in msg and "***" in msg and len(msg) <= 120 and "\n" not in msg


def test_make_llm_uses_api_key_without_project_and_no_retries():
    settings = Settings(_env_file=None, google_cloud_api_key=SecretStr("test-key"))
    llm = make_llm(settings)  # constructing makes no network call
    assert (llm.model.removeprefix("models/"), llm.vertexai, llm.temperature) == (
        "gemini-2.5-flash-lite",
        True,
        0,
    )
    assert (llm.max_output_tokens, llm.max_retries, llm.project) == (1024, 0, None)

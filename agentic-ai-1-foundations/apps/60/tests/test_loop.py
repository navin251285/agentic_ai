import asyncio
from scout import LIMITS, NOTES, DailyBudget, Guard, RunBudget, Tracer, make_tools, serve
from scout.fake import ProviderError, ScriptedModel
from helpers import ANSWER, CALC, SEARCH, run

def test_happy_path_uses_both_tools(tmp_path):
    out = run(tmp_path, ScriptedModel([SEARCH, CALC, ANSWER]))
    assert (out["stop"], out["steps"], out["errors"]) == ("end_of_turn", 3, 0)
    assert "1479" in out["messages"][-2]["content"]               # the calculator's result reached the model

def test_step_limit_stops_a_model_that_never_answers(tmp_path):
    out = run(tmp_path, ScriptedModel([SEARCH]))
    assert (out["stop"], out["steps"]) == ("step_limit", LIMITS["max_steps"])

def test_429_is_retried_then_succeeds(tmp_path):
    busy = ProviderError(429, "RESOURCE_EXHAUSTED", retry_after=0.01)
    out = run(tmp_path, ScriptedModel([busy, busy, ANSWER]))
    assert (out["stop"], out["retries"]) == ("end_of_turn", 2)

def test_400_and_spend_cap_are_never_retried(tmp_path):
    for error in (ProviderError(400, "INVALID_ARGUMENT"), ProviderError(429, "enforced_spend_limit_reached")):
        model = ScriptedModel([error, ANSWER])
        out = run(tmp_path, model)
        assert (out["stop"], model.calls) == ("provider_error", 1)

def test_budget_stops_before_overspending(tmp_path):
    out = run(tmp_path, ScriptedModel([SEARCH], usage=(3000, 300)), budget=RunBudget(0.005))
    assert out["stop"] == "budget" and out["cost_usd"] <= 0.005

def test_daily_budget_is_per_user(tmp_path):
    daily, tools = DailyBudget(0.0013), make_tools(NOTES, tmp_path / "files")
    async def ask(user):
        return await serve(user, "Mars day?", ScriptedModel([ANSWER]), tools, Guard("answer"),
                           Tracer(tmp_path / "trace.jsonl", user), daily)
    stops = [asyncio.run(ask(u))["stop"] for u in ("ana", "ana", "ana", "ben")]
    assert stops == ["end_of_turn", "end_of_turn", "daily_budget", "end_of_turn"]

def test_ten_requests_at_once_cannot_overspend_the_day(tmp_path):
    daily, tools = DailyBudget(0.0013), make_tools(NOTES, tmp_path / "files")
    async def burst():
        return await asyncio.gather(*(serve("ana", "Mars day?", ScriptedModel([ANSWER], latency=0.01), tools,
                                            Guard("answer"), Tracer(tmp_path / "t.jsonl", f"r{i}"), daily)
                                      for i in range(10)))
    stops = [r["stop"] for r in asyncio.run(burst())]
    assert "end_of_turn" in stops and daily.max_usd - daily.left("ana") <= 0.0013

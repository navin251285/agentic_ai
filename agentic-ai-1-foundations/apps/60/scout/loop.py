"""Scout v2's loop: lesson 35's loop, async (38), with retries (14), budget (54), guard (51-52), trace (49)."""
import asyncio, random
from .budget import RunBudget
from .config import LIMITS
from .tools import SCHEMAS

RETRYABLE = {429, 500, 502, 503, 504}

def retryable(e: Exception) -> bool:
    code = getattr(e, "code", None) or getattr(e, "status_code", None)
    spend_cap = "enforced_spend_limit_reached" in f"{e} {getattr(e, 'body', '')}"
    return code in RETRYABLE and not spend_cap          # a spend cap or a 400 never gets better

async def call_model(model, messages, schemas, tracer, step, rng, max_attempts):
    for attempt in range(1, max_attempts + 1):
        try:
            return await model(messages, schemas), attempt - 1
        except Exception as e:
            again = retryable(e) and attempt < max_attempts
            tracer.event("model_error", **{"scout.step": step, "error.type": type(e).__name__,
                         "scout.status": getattr(e, "code", None), "scout.attempt": attempt, "scout.retry": again})
            if not again:
                raise
            wait = getattr(e, "retry_after", 0) + rng.uniform(0, min(4.0, 0.25 * 2 ** attempt))
            await asyncio.sleep(wait)                     # honour retry-after, plus jittered backoff

async def run_scout(question: str, model, tools: dict, guard, tracer, budget: RunBudget,
                    max_steps: int = LIMITS["max_steps"], seed: int = 0) -> dict:
    rng, schemas = random.Random(seed), guard.schemas(SCHEMAS)
    messages, calls, n = [{"role": "user", "text": question}], [], {"errors": 0, "retries": 0}
    tracer.event("invoke_agent", **{"gen_ai.agent.name": "Scout", "scout.question": question,
                                    "scout.task": guard.task, "gen_ai.request.model": model.name})
    def finish(stop, steps, answer=None, error=None):
        tracer.event("run_end", **{"scout.stop": stop, "scout.steps": steps, "scout.answer": answer,
                     "scout.cost_usd": round(budget.spent_usd, 8), "scout.retries": n["retries"],
                     "scout.denied": guard.denied, **({"error.type": error} if error else {})})
        return {"answer": answer, "stop": stop, "steps": steps, **n, "denied": guard.denied, "error": error,
                "cost_usd": budget.spent_usd, "tokens": budget.tokens, "calls": calls, "messages": messages}
    for step in range(1, max_steps + 1):
        if not budget.can_afford(model.name, model.max_out):            # check before paying
            return finish("budget", step - 1)
        try:
            reply, retries = await call_model(model, messages, schemas, tracer, step, rng, LIMITS["max_attempts"])
        except Exception as e:
            return finish("provider_error", step - 1, error=type(e).__name__)
        usage, n["retries"] = reply.pop("usage"), n["retries"] + retries
        budget.charge(model.name, usage["in"], usage["out"])
        calls.append(usage)
        tracer.event("chat", **{"scout.step": step, "gen_ai.usage.input_tokens": usage["in"],
                     "gen_ai.usage.output_tokens": usage["out"], "scout.duration_ms": round(usage["seconds"] * 1000),
                     "scout.tool_calls": [c["name"] for c in reply.get("tool_calls", [])]})
        messages.append(reply)
        if not reply.get("tool_calls"):
            return finish("end_of_turn", step, reply.get("text") or "")
        for call in reply["tool_calls"]:
            result = await asyncio.to_thread(guard, call, tools)        # tools never block the loop
            n["errors"] += result["is_error"]
            tracer.event("execute_tool", **{"scout.step": step, "gen_ai.tool.name": call["name"],
                         "gen_ai.tool.call.id": call["id"], "scout.tool.args": call["args"],
                         **({"error.type": result["content"].split(":")[0]} if result["is_error"] else {})})
            messages.append({"role": "tool", "call_id": call["id"], "name": call["name"], **result})
    return finish("step_limit", max_steps)

async def serve(user: str, question: str, model, tools: dict, guard, tracer, daily) -> dict:
    """One request. Reserve the run's limit from the user's day first, so concurrent runs can't overspend."""
    left = daily.left(user)
    limit = max(0.0, min(LIMITS["run_usd"], left))
    daily.add(user, limit)                                    # reserve now (no await in between) ...
    budget = RunBudget(limit, LIMITS["run_tokens"])
    run = await run_scout(question, model, tools, guard, tracer, budget)
    daily.add(user, budget.spent_usd - limit)                 # ... and refund what was not spent
    if run["stop"] == "budget" and left < LIMITS["run_usd"]:
        run["stop"] = "daily_budget"
    return run

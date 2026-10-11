"""Scout's loop from lesson 35, unchanged: run_tool never raises; run_agent stops on an answer or max_steps."""
import json

MAX_RESULT_CHARS = 1500

def run_tool(call: dict, tools: dict) -> dict:
    """Run one tool call. Returns {"content": str, "is_error": bool}; never raises."""
    fn = tools.get(call["name"])
    if fn is None:
        return {"content": f"unknown tool '{call['name']}'. Available tools: {', '.join(tools)}.",
                "is_error": True}
    try:
        result = {"content": json.dumps(fn(**call["args"])), "is_error": False}
    except Exception as e:                                    # any failure becomes an observation
        result = {"content": f"{type(e).__name__}: {e}", "is_error": True}
    extra = len(result["content"]) - MAX_RESULT_CHARS
    if extra > 0:
        result["content"] = (result["content"][:MAX_RESULT_CHARS] + f"... [truncated {extra} "
                             "characters: ask for a smaller page or a narrower query]")
    return result

def run_agent(question: str, model, tools: dict, schemas: list[dict], max_steps: int = 8) -> dict:
    messages, errors = [{"role": "user", "text": question}], 0
    for step in range(1, max_steps + 1):
        reply = model(messages, schemas)
        messages.append(reply)
        calls = reply.get("tool_calls", [])
        if not calls:
            print(f"step {step}: answer")
            return {"answer": reply["text"], "stop": "end_of_turn", "steps": step,
                    "errors": errors, "messages": messages}
        for call in calls:
            result = run_tool(call, tools)
            errors += result["is_error"]
            print(f"step {step}: {call['name']}({call['args']}) -> "
                  f"{'ERROR ' if result['is_error'] else ''}{result['content'][:70]}")
            messages.append({"role": "tool", "call_id": call["id"], "name": call["name"], **result})
    return {"answer": None, "stop": "step_limit", "steps": max_steps, "errors": errors, "messages": messages}

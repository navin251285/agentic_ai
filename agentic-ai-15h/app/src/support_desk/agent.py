"""The order-lookup agent: the lesson 06 loop with step and cost caps, and the lesson 10 checks.

One model call per pass. The caps are checked after each reply and before any tool runs, and every
exit names its stop reason. Each chat turn is one llm_replay session: a recording per question, so a
question that was recorded replays with no key, and a new one is recorded once when a key is set.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from support_desk.course import get_llm, llm_replay
from support_desk.settings import Settings, load_settings
from support_desk.tools import TOOLS, load_orders, run_tool

logger = logging.getLogger(__name__)

SYSTEM = "You are the order-lookup assistant for Brightside Outfitters. Use the tools, then answer in two sentences."
PRICE_IN, PRICE_OUT = 0.25, 1.50  # USD per 1M input and output tokens, as checked for lesson 02 on 2026-10-20
_SESSION_LOCK = threading.Lock()  # llm_replay keeps one recording at a time, so turns run one after another


class ModelUnavailable(RuntimeError):
    """The model could not answer: no recording for this question and no key, or the call failed."""


@dataclass
class ChatResult:
    answer: str
    stop: str                                   # answered, step cap, spend cap or repeated call
    steps: int
    cost_usd: float
    calls: list[dict[str, Any]] = field(default_factory=list)


def over_cap(steps: int, usd: float, max_steps: int, max_usd: float) -> str | None:
    """The two stop rules that use numbers (lesson 06)."""
    if steps >= max_steps:
        return "step cap"
    if usd > max_usd:
        return "spend cap"
    return None


def reply_cost(reply: AIMessage) -> float:
    """What one reply cost, from the usage it already carries: no extra request."""
    usage = reply.usage_metadata or {}
    return (usage.get("input_tokens", 0) * PRICE_IN + usage.get("output_tokens", 0) * PRICE_OUT) / 1_000_000


def recording_name(question: str) -> str:
    return "chat-" + hashlib.sha1(question.encode("utf-8")).hexdigest()[:12]


@contextmanager
def recorded(name: str) -> Iterator[None]:
    with _SESSION_LOCK:
        try:
            llm_replay.start(name)
        except RuntimeError as err:
            raise ModelUnavailable(str(err)) from err
        try:
            yield
        finally:
            llm_replay.stop()


def run_chat(question: str, settings: Settings | None = None) -> ChatResult:
    settings = settings or load_settings()
    orders = load_orders(settings.orders_file)
    tool_specs = [tool.spec() for tool in TOOLS.values()]
    counts: Counter = Counter()
    calls: list[dict[str, Any]] = []
    messages: list[BaseMessage] = [SystemMessage(SYSTEM), HumanMessage(question)]
    steps, usd = 0, 0.0

    with recorded(recording_name(question)):
        llm = get_llm().bind_tools(tool_specs)
        while True:
            try:
                reply = llm.invoke(messages)
            except Exception as err:  # the message can hold request details: log only the error type
                logger.error("model call failed (%s)", type(err).__name__)
                raise ModelUnavailable("the model call could not be made or replayed") from err
            steps += 1
            usd += reply_cost(reply)
            if not reply.tool_calls:
                return ChatResult(answer=reply.text, stop="answered", steps=steps, cost_usd=usd, calls=calls)
            if stop := over_cap(steps, usd, settings.max_steps, settings.max_usd):
                logger.info("stopped: %s after %d steps", stop, steps)
                return ChatResult(answer="", stop=stop, steps=steps, cost_usd=usd, calls=calls)

            messages.append(reply)
            for call in reply.tool_calls:
                key = (call["name"], json.dumps(call["args"], sort_keys=True))
                counts[key] += 1
                if counts[key] > 1:  # the same call again: stop rather than loop
                    return ChatResult(answer="", stop="repeated call", steps=steps, cost_usd=usd, calls=calls)
                result = run_tool(call["name"], dict(call["args"]), orders)
                calls.append({"name": call["name"], "args": dict(call["args"]), "result": result})
                messages.append(ToolMessage(content=json.dumps(result), tool_call_id=call.get("id") or call["name"]))

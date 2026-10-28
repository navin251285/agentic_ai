"""The desk loop: one model call per turn, caps that stop it, and a stuck check that reads its own steps.

Lessons 03 to 08 in one module. Each reply is counted once (turns, tokens, dollars). Caps are checked
after each reply, before its tools run. The stuck check runs before and after the tools. Every run ends
with one stop reason: answered, turn_cap, over_budget_tokens, over_budget_usd or stuck.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from collections.abc import Callable
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from pydantic import ValidationError

from .tools import REFUND_TOOL, SCHEMAS, propose_refund, run_tool

log = logging.getLogger(__name__)

SYSTEM = (
    "You are the support desk for Brightside Outfitters. Look up the order with get_order before you "
    "answer about it. Use calculator for any arithmetic. For a refund, call issue_refund once and never "
    "refund more than was paid. Answer in two sentences or fewer."
)
# USD per 1M text tokens, Gemini list price read 2026-10-27 (the same price as lessons 05 and 08).
PRICE_PER_MILLION = {"input": 0.10, "output": 0.40}


@dataclass(frozen=True)
class Caps:
    """Limits for one run. None switches a cap off. max_turns counts model replies."""
    max_turns: int = 6
    max_tokens: int | None = None
    max_usd: float | None = None

    def __post_init__(self) -> None:
        if self.max_turns < 1:
            raise ValueError(f"max_turns must be at least 1, got {self.max_turns}")
        for name in ("max_tokens", "max_usd"):
            value = getattr(self, name)
            if value is not None and value <= 0:
                raise ValueError(f"{name} must be more than 0, got {value}")


@dataclass
class Budget:
    caps: Caps
    turns: int = 0
    tokens: int = 0
    usd: float = 0.0

    def count(self, reply: Any) -> None:
        """Add one model reply: its turn, its tokens and its dollars."""
        usage = reply.usage_metadata or {}
        self.turns += 1
        self.tokens += usage.get("total_tokens", 0)
        self.usd += (usage.get("input_tokens", 0) * PRICE_PER_MILLION["input"]
                     + usage.get("output_tokens", 0) * PRICE_PER_MILLION["output"]) / 1_000_000

    def exceeded(self) -> str | None:
        """The first cap reached, or None. Called after every reply."""
        if self.turns >= self.caps.max_turns:
            return "turn_cap"
        if self.caps.max_tokens is not None and self.tokens >= self.caps.max_tokens:
            return "over_budget_tokens"
        if self.caps.max_usd is not None and self.usd >= self.caps.max_usd:
            return "over_budget_usd"
        return None


@dataclass
class Step:
    """What one model reply asked for, and what the tools answered."""
    calls: list[tuple[str, str]] = field(default_factory=list)    # (tool name, arguments as text)
    results: list[tuple[str, str]] = field(default_factory=list)  # (tool name, observation text)

    def to_dict(self) -> dict[str, Any]:
        return {"calls": [{"name": n, "args": a} for n, a in self.calls],
                "results": [{"name": n, "text": t} for n, t in self.results]}


def canon(name: str, args: dict[str, Any]) -> str:
    """The call as text after its schema fixed the types, so 40 and 40.0 compare equal."""
    schema = SCHEMAS.get(name)
    try:
        args = schema(**args).model_dump() if schema else args
    except ValidationError:
        pass  # the tool returns the error text, so the raw arguments are compared
    return json.dumps(args, sort_keys=True, default=str)


def stuck_reason(steps: list[Step], repeats: int = 3) -> str | None:
    """Why the run is stuck, or None. It reads only the steps so far."""
    if repeats < 2:
        raise ValueError(f"repeats must be at least 2, got {repeats}")
    last = steps[-repeats:]
    if len(last) == repeats and last[0].calls and all(s.calls == last[0].calls for s in last):
        return f"the same call {repeats} times in a row"
    errors = [text for s in steps for _, text in s.results if text.startswith("error")]
    if len(errors) >= 2 and errors[-1] == errors[-2]:
        return "the same error twice, even with a success between"
    return None


@dataclass
class RunResult:
    stop: str
    answer: str | None
    why: str | None
    turns: int
    tokens: int
    usd: float
    steps: list[Step]
    proposals: list[dict[str, Any]] = field(default_factory=list)  # refunds the maker proposed, for the checker

    def to_dict(self) -> dict[str, Any]:
        return {"stop": self.stop, "answer": self.answer, "why": self.why, "turns": self.turns,
                "tokens": self.tokens, "usd": round(self.usd, 6), "steps": [s.to_dict() for s in self.steps],
                "proposals": self.proposals}


def _finish(stop: str, answer: str | None, why: str | None, budget: Budget, steps: list[Step],
            proposals: list[dict[str, Any]] | None = None) -> RunResult:
    log.info("desk run stopped: %s after %d turn(s)", stop, budget.turns)
    return RunResult(stop=stop, answer=answer, why=why, turns=budget.turns, tokens=budget.tokens,
                     usd=budget.usd, steps=steps, proposals=proposals or [])


def run_desk(question: str, caps: Caps, model: Any, system: str = SYSTEM,
             allowed: Callable[[str], tuple[bool, str]] | None = None) -> RunResult:
    """Run the loop on one question. `model` is a chat model with the tools already bound.

    `allowed` is the run's grant check (lesson 23): called with the tool name before each call runs. A refused
    call gets a "denied" tool message, so the model reads why, and the tool never runs.
    """
    budget = Budget(caps)
    messages: list[Any] = [SystemMessage(content=system), HumanMessage(content=question)]
    steps: list[Step] = []
    while True:
        reply = model.invoke(messages)  # one paid model call: the whole message list is sent again
        messages.append(reply)
        budget.count(reply)
        step = Step(calls=[(c["name"], canon(c["name"], c["args"])) for c in reply.tool_calls])
        steps.append(step)
        if not reply.tool_calls:
            return _finish("answered", reply.text, None, budget, steps)
        if cap := budget.exceeded():
            return _finish(cap, None, None, budget, steps)  # the reply was paid for; its tools do not run
        if why := stuck_reason(steps):
            return _finish("stuck", None, why, budget, steps)
        proposals: list[dict[str, Any]] = []
        for call in reply.tool_calls:
            ok, why = allowed(call["name"]) if allowed else (True, "granted")
            if not ok:  # the grant list for this run does not include the tool
                message = ToolMessage(content=f"denied: {why}", tool_call_id=call["id"])
            elif call["name"] == REFUND_TOOL:  # a write: the desk only proposes it (lesson 14)
                message, proposal = propose_refund(call)
                if proposal is not None:
                    proposals.append(proposal)
            else:
                message = run_tool(call)
            messages.append(message)
            step.results.append((call["name"], message.content))
        if proposals:  # the maker is done; the checker and the payment service decide the rest
            return _finish("refund_proposed", None, None, budget, steps, proposals)
        if why := stuck_reason(steps):
            return _finish("stuck", None, why, budget, steps)

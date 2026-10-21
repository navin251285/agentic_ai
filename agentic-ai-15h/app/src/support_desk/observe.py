"""Traces and the cost meter of the desk: lesson 29's spans, written to a JSON-lines file and read back as a dashboard.

Each call to the desk (a question, or a decision on a refund) is one root span, `invoke_agent support-desk`. Its model
calls are `chat` spans with the token counts, and its tool calls are `execute_tool` spans. The conversation id is the
thread id, so the question and the decision of one ticket group into one dashboard row.

The spans hold ids, counts, a hash of the question, tool names and statuses. They never hold the customer's words:
tool arguments are not logged, and the one search query stays out of the trace.
"""
from __future__ import annotations

import json
import logging
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

from support_desk.agent import PRICE_IN, PRICE_OUT

logger = logging.getLogger(__name__)
OP = "gen_ai.operation.name"        # the OpenTelemetry GenAI attribute names (Development status: pin the version)
SLO_ANSWERED = 0.95                 # lesson 29: alert when fewer finished tickets are answered than this
WAITING = "waiting for approval"


def make_tracer(path: Path) -> tuple[TracerProvider, Any]:
    """A tracer that appends every span to `path` as soon as the span ends (lesson 29, step 1)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    provider = TracerProvider()  # its own provider, not the global one: each desk keeps its own spans
    out = ConsoleSpanExporter(out=path.open("a", encoding="utf-8"),
                              formatter=lambda span: span.to_json(indent=None) + "\n")
    provider.add_span_processor(SimpleSpanProcessor(out))
    return provider, provider.get_tracer("brightside-support-desk")


def load_spans(path: Path) -> list[dict[str, Any]]:
    """Every span saved so far. A damaged line is skipped and logged by its position, never by its text."""
    if not path.exists():
        return []
    spans = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            spans.append(json.loads(line))
        except json.JSONDecodeError:
            logger.warning("trace file line %d is damaged: skipped", number)
    return spans


def _ms(span: dict[str, Any]) -> float:
    start, end = datetime.fromisoformat(span["start_time"]), datetime.fromisoformat(span["end_time"])
    return (end - start).total_seconds() * 1000


def cost_usd(attributes: dict[str, Any]) -> float:
    """The cost of one model call from its token counts (the prices of lesson 06)."""
    return (attributes.get("gen_ai.usage.input_tokens", 0) * PRICE_IN
            + attributes.get("gen_ai.usage.output_tokens", 0) * PRICE_OUT) / 1_000_000


def p95(values: list[float]) -> float:
    """Nearest rank: the value that 95 out of 100 tasks are at or below."""
    return sorted(values)[math.ceil(0.95 * len(values)) - 1]


def is_root(span: dict[str, Any]) -> bool:
    return span["parent_id"] is None and span["attributes"].get(OP) == "invoke_agent"


def task_rows(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per ticket (conversation id), newest first. A row adds up every root span of its ticket."""
    by_trace: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for span in spans:
        by_trace[span["context"]["trace_id"]].append(span)
    tasks: dict[str, dict[str, Any]] = {}
    for root in sorted((s for s in spans if is_root(s)), key=lambda s: s["start_time"]):
        task = root["attributes"]["gen_ai.conversation.id"]
        row = tasks.setdefault(task, {"task": task, "runs": 0, "answered": False, "outcome": "", "model_calls": 0,
                                      "tool_calls": 0, "refused": 0, "tool_errors": 0, "cost_usd": 0.0,
                                      "latency_ms": 0.0})
        row["runs"] += 1
        row["latency_ms"] += _ms(root)
        row["answered"] = root["status"]["status_code"] == "OK"   # the latest call decides the outcome
        row["outcome"] = root["attributes"].get("support.outcome", "")
        for span in by_trace[root["context"]["trace_id"]]:
            attrs = span["attributes"]
            if attrs.get(OP) == "chat":
                row["model_calls"] += 1
                row["cost_usd"] += cost_usd(attrs)
            elif attrs.get(OP) == "execute_tool":
                row["tool_calls"] += 1
                row["refused"] += attrs.get("support.decision") == "refused"
                row["tool_errors"] += span["status"]["status_code"] == "ERROR"
    for row in tasks.values():
        row["cost_usd"] = round(row["cost_usd"], 6)
        row["latency_ms"] = round(row["latency_ms"], 1)
    return list(reversed(list(tasks.values())))


def summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The dashboard's totals. Tickets still waiting for a person are not counted as answered or failed yet."""
    finished = [r for r in rows if r["outcome"] != WAITING]
    rate = sum(r["answered"] for r in finished) / len(finished) if finished else None
    return {
        "tickets": len(rows),
        "waiting": len(rows) - len(finished),
        "answered_rate": None if rate is None else round(rate, 4),
        "cost_per_ticket_usd": round(sum(r["cost_usd"] for r in rows) / len(rows), 6) if rows else None,
        "p95_latency_ms": round(p95([r["latency_ms"] for r in rows]), 1) if rows else None,
        "slo_answered": SLO_ANSWERED,
        "slo_breached": None if rate is None else rate < SLO_ANSWERED,
    }


def trace_view(spans: list[dict[str, Any]], task: str) -> list[dict[str, Any]]:
    """The spans of one ticket as a list in tree order, each with its depth (the root is depth 0)."""
    roots = sorted((s for s in spans if is_root(s) and s["attributes"]["gen_ai.conversation.id"] == task),
                   key=lambda s: s["start_time"])
    if not roots:
        return []
    trace_ids = {r["context"]["trace_id"] for r in roots}
    members = [s for s in spans if s["context"]["trace_id"] in trace_ids]
    children: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for span in members:
        children[span["parent_id"]].append(span)
    out: list[dict[str, Any]] = []

    def walk(span: dict[str, Any], depth: int) -> None:
        out.append({"name": span["name"], "status": span["status"]["status_code"], "depth": depth,
                    "ms": round(_ms(span), 1), "attributes": span["attributes"]})
        for child in sorted(children[span["context"]["span_id"]], key=lambda s: s["start_time"]):
            walk(child, depth + 1)

    for root in roots:
        walk(root, 0)
    return out

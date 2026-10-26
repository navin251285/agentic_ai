"""Triage one customer message: the model asks for the order, fills the form, then the check decides (lesson 06).

Two model calls per message: call 1 asks for the order lookup (a tool call), call 2 fills the
CaseRecord form from the lookup result. The model never reads the orders file itself.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from opentelemetry import trace
from tenacity.wait import WaitBaseT

from .models import CaseRecord, TriageResult
from .orders import Orders, check_record
from .retries import call_with_retries
from .tenants import Tenant

logger = logging.getLogger(__name__)

SYSTEM = "You help Basket Bazaar's support team. Look up the order when the message gives an order number."
FORM_REQUEST = "Fill the case record from the message and the lookup result."


def make_lookup_tool(orders: Orders):
    """The tool the model may call. Its docstring is what the model reads to decide when to call it."""

    @tool
    def lookup_order(order_id: str) -> str:
        """Look up one Basket Bazaar order by its order number, such as BB-1108. Returns its lines as JSON, or says it is not found."""
        lines = orders.get(order_id)
        return json.dumps(lines) if lines else f"order {order_id} not found"

    return lookup_order


def triage_message(
    message: str,
    orders: Orders,
    llm: Any,
    *,
    tenant: Tenant | None = None,
    attempts: int = 4,
    wait: WaitBaseT | None = None,
    tracer: trace.Tracer | None = None,
) -> TriageResult:
    """Read one customer message, fill the case form, check it against the orders, and say whether the case opens.

    Each model call is retried on the failures a later try can fix (retries.py). The result has no case id
    yet: the API stores it, so the id and the duplicate flag are set there. Each step gets its own span
    (step 3): the message text is never put in a span.
    """
    tracer = tracer or trace.get_tracer(__name__)
    lookup = make_lookup_tool(orders)
    asked = [("system", SYSTEM), ("human", message)]

    with tracer.start_as_current_span("model.lookup_call"):
        # model call 1: the model asks for the order
        first = call_with_retries(lambda: llm.bind_tools([lookup]).invoke(asked), attempts=attempts, wait=wait)
    history = asked + [first]
    for call in first.tool_calls:
        history.append(ToolMessage(content=lookup.invoke(call["args"]), tool_call_id=call["id"]))

    form = llm.with_structured_output(CaseRecord, method="json_schema")
    with tracer.start_as_current_span("model.fill_form"):
        # model call 2: the model fills the form
        record = call_with_retries(
            lambda: form.invoke(history + [("human", FORM_REQUEST)]), attempts=attempts, wait=wait
        )

    with tracer.start_as_current_span("check.record") as span:
        problems = check_record(record, orders, tenant)
        status = "needs_review" if problems else "opened"
        span.set_attribute("triage.status", status)
        span.set_attribute("triage.problem_count", len(problems))
    logger.info("triaged order=%s issue=%s status=%s problems=%d", record.order_id, record.issue, status, len(problems))
    return TriageResult(status=status, case_id="", duplicate=False, record=record, problems=problems)

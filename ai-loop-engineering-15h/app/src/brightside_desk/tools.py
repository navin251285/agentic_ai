"""The desk's two tools: an order lookup and an exact calculator (lessons 04 and 05).

Every argument is checked by a pydantic schema before the tool body runs. A failure never escapes:
run_tool turns it into a tool message, so the model reads the error on its next turn.
"""
from __future__ import annotations

import ast
import json
import logging
import operator
from typing import Any

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from pydantic import BaseModel, Field, ValidationError

log = logging.getLogger(__name__)

# Invented orders for the Brightside Outfitters stand-in (no real customer data).
ORDERS: dict[str, dict[str, Any]] = {
    "BS-1042": {"customer": "C-17", "item": "Trail jacket", "paid_usd": 120.0, "status": "delivered"},
    "BS-1043": {"customer": "C-22", "item": "Rain shell", "paid_usd": 85.0, "status": "delivered"},
    "BS-1044": {"customer": "C-17", "item": "Merino socks", "paid_usd": 18.0, "status": "shipped"},
    "BS-1045": {"customer": "C-22", "item": "Rain shell", "paid_usd": 40.0, "status": "delivered"},
}


class OrderArgs(BaseModel):
    order_id: str = Field(pattern=r"^BS-\d{4}$", description="Order id in the form BS-1042")


class CalcArgs(BaseModel):
    expression: str = Field(min_length=1, max_length=100,
                            description="Arithmetic with numbers, + - * / and parentheses, such as (120 - 18) * 2")


@tool(args_schema=OrderArgs)
def get_order(order_id: str) -> str:
    """Look up one order: customer, item, amount paid and delivery status."""
    order = ORDERS.get(order_id)
    if order is None:
        return f"error: no order {order_id}"
    return json.dumps({"order_id": order_id, **order})


_BINARY = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        return _BINARY[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval_node(node.operand))
    raise ValueError("only numbers, + - * / and parentheses are allowed")


def safe_eval(expression: str) -> float:
    """Evaluate arithmetic only. The expression is parsed, never passed to eval(), so names and calls fail."""
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError("the expression is not valid arithmetic") from exc
    return _eval_node(tree.body)


@tool(args_schema=CalcArgs)
def calculator(expression: str) -> str:
    """Work out an arithmetic expression exactly, for example a refund total. Only numbers and + - * / work."""
    try:
        return f"{safe_eval(expression):.10g}"
    except (ValueError, ZeroDivisionError) as exc:
        return f"error: {exc}"


REFUND_TOOL = "issue_refund"


class RefundArgs(BaseModel):
    order_id: str = Field(pattern=r"^BS-\d{4}$", description="Order id in the form BS-1042")
    amount_usd: float = Field(gt=0, le=10000, description="Amount to refund in US dollars")


@tool(args_schema=RefundArgs)
def issue_refund(order_id: str, amount_usd: float) -> str:
    """Propose a refund on one order. A checker approves it and the payment service pays it; the desk never pays directly."""
    return "proposed: the checker decides after this reply"


def propose_refund(call: dict[str, Any]) -> tuple[ToolMessage, dict[str, Any] | None]:
    """Turn the model's refund call into a proposal for the checker (lesson 14). Bad arguments come back as text."""
    try:
        args = RefundArgs.model_validate(call["args"])
    except ValidationError as exc:
        return ToolMessage(content=observation(exc), tool_call_id=call["id"]), None
    message = ToolMessage(content="proposed: the checker decides after this reply", tool_call_id=call["id"])
    return message, args.model_dump()


TOOLS = [get_order, calculator, issue_refund]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}
SCHEMAS: dict[str, type[BaseModel]] = {"get_order": OrderArgs, "calculator": CalcArgs, REFUND_TOOL: RefundArgs}


def observation(exc: ValidationError) -> str:
    """One line per broken field: where, which rule, which value. The model reads it on its next turn."""
    parts = [f"error: {'.'.join(str(p) for p in e['loc'])}: {e['msg']} (got {e['input']!r})"
             for e in exc.errors(include_url=False, include_context=False)]
    return "; ".join(parts) + ". Fix the arguments and call the tool again."


def run_tool(call: dict[str, Any]) -> ToolMessage:
    """Run one tool call the model asked for. Every failure becomes text the model can read."""
    tool_fn = TOOLS_BY_NAME.get(call["name"])
    if tool_fn is None:
        result = f"error: unknown tool {call['name']}"
    else:
        try:
            result = str(tool_fn.invoke(call["args"]))
        except ValidationError as exc:  # the schema said no: the tool body never ran
            result = observation(exc)
        except Exception as exc:  # anything else: log it, and give the model the text
            log.warning("tool %s failed: %s", call["name"], type(exc).__name__)
            result = f"error: {exc}"
    return ToolMessage(content=result, tool_call_id=call["id"])

"""The tools the order-lookup agent may call: lookup_order (lesson 07) and calculator (lesson 07).

Both are read-only, so neither changes anything in the world. Each tool checks its arguments with a
pydantic model that refuses unknown keys; a bad call comes back as a result the model can read.
"""
from __future__ import annotations

import ast
import json
import operator
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class LookupArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")  # a key the schema does not name is refused
    order_id: str = Field(description="The order number as the customer wrote it, digits only, such as 1002.")


class CalculatorArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expression: str = Field(description="An arithmetic expression with + - * / and brackets, such as (60 - 15) / 3.")


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args: type[BaseModel]
    fn: Callable[..., dict[str, Any]]

    def spec(self) -> dict[str, Any]:
        """The name, description and argument schema the model reads."""
        return {"name": self.name, "description": self.description,
                "parameters": _gemini_schema(self.args.model_json_schema())}


def _gemini_schema(node: Any) -> Any:
    """Gemini's schema keeps a subset of JSON Schema: drop the key it ignores (the model still sees the rest)."""
    if isinstance(node, dict):
        return {k: _gemini_schema(v) for k, v in node.items() if k != "additionalProperties"}
    if isinstance(node, list):
        return [_gemini_schema(v) for v in node]
    return node


def load_orders(path: Path) -> dict[str, dict[str, Any]]:
    """The orders of the course's small world: {order_id: {status, days_late, total}}."""
    return json.loads(path.read_text(encoding="utf-8"))["world"]["orders"]


def lookup_order(orders: dict[str, dict[str, Any]], order_id: str) -> dict[str, Any]:
    if order_id not in orders:  # lesson 07: the error names the next step
        return {"error": f"no order {order_id}",
                "next_step": "Ask for the number in the confirmation email. Do not guess other numbers."}
    return dict(orders[order_id])


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


def _evaluate(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_evaluate(node.left), _evaluate(node.right))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        return _evaluate(node.operand) * (1 if isinstance(node.op, ast.UAdd) else -1)
    raise ValueError("only numbers, + - * / and brackets are allowed")


def calculator(orders: dict[str, dict[str, Any]], expression: str) -> dict[str, Any]:
    """Evaluate plain arithmetic. ast, not eval: a model's text never runs as Python."""
    if len(expression) > 100:
        return {"error": "the expression is too long", "next_step": "Send a shorter expression."}
    try:
        value = _evaluate(ast.parse(expression, mode="eval").body)
    except ZeroDivisionError:
        return {"error": "division by zero", "next_step": "Check the divisor."}
    except (SyntaxError, ValueError) as err:
        return {"error": str(err), "next_step": "Send plain arithmetic such as (60 - 15) / 3."}
    return {"result": round(value, 2)}


TOOLS: dict[str, Tool] = {
    "lookup_order": Tool(
        name="lookup_order",
        description="Look up one customer order: its status, days late and total. Use it when the customer gives an order number.",
        args=LookupArgs, fn=lookup_order),
    "calculator": Tool(
        name="calculator",
        description="Do plain arithmetic on money or days, such as a total minus a discount. Use it instead of doing sums in your head.",
        args=CalculatorArgs, fn=calculator),
}


def run_tool(name: str, args: dict[str, Any], orders: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The one door for every tool request: unknown names and bad arguments come back as results."""
    tool = TOOLS.get(name)
    if tool is None:
        return {"error": f"no tool named {name}", "next_step": f"Call one of: {', '.join(TOOLS)}."}
    try:
        checked = tool.args.model_validate(args).model_dump()
    except ValidationError as err:
        return {"error": "the arguments are not valid", "problems": [e["msg"] for e in err.errors()],
                "next_step": "Fix the named fields and call again."}
    return tool.fn(orders, **checked)

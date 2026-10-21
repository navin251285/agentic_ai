"""Step 1: the order-lookup and calculator tools, and the caps. No model call here."""
from support_desk.agent import over_cap
from support_desk.settings import load_settings
from support_desk.tools import TOOLS, load_orders, run_tool


def orders():
    return load_orders(load_settings().orders_file)


def test_tool_names_are_the_two_read_only_tools():
    assert list(TOOLS) == ["lookup_order", "calculator"]


def test_lookup_returns_the_order():
    result = run_tool("lookup_order", {"order_id": "1002"}, orders())
    assert result["status"] == "in transit"
    assert result["days_late"] == 4
    assert result["total"] == 45.0


def test_lookup_unknown_order_names_the_next_step():
    result = run_tool("lookup_order", {"order_id": "9999"}, orders())
    assert result["error"] == "no order 9999"
    assert "Do not guess" in result["next_step"]


def test_tool_refuses_a_key_the_schema_does_not_name():
    result = run_tool("lookup_order", {"order_id": "1002", "refund": True}, orders())
    assert result["error"] == "the arguments are not valid"


def test_unknown_tool_is_a_result_not_a_crash():
    result = run_tool("issue_refund", {"order_id": "1002"}, orders())
    assert "no tool named issue_refund" in result["error"]


def test_calculator_does_plain_arithmetic():
    assert run_tool("calculator", {"expression": "(60 - 15) / 3"}, orders()) == {"result": 15.0}


def test_calculator_refuses_code_and_division_by_zero():
    assert "error" in run_tool("calculator", {"expression": "__import__('os')"}, orders())
    assert run_tool("calculator", {"expression": "1 / 0"}, orders())["error"] == "division by zero"


def test_step_and_spend_caps_stop_with_a_reason():
    assert over_cap(steps=4, usd=0.0, max_steps=4, max_usd=0.01) == "step cap"
    assert over_cap(steps=1, usd=0.02, max_steps=4, max_usd=0.01) == "spend cap"
    assert over_cap(steps=1, usd=0.001, max_steps=4, max_usd=0.01) is None

"""What each run may do, fixed in code before the run starts (lesson 23).

A grant list names the tools one kind of run may call. The desk shows the model only those tools, and `permit`
checks every call again in the runner, because the model's choice is not a control. An unknown run gets nothing.
"""
from __future__ import annotations

CHAT_RUN = "desk-chat"          # a person types in the chat page: the step 2 behaviour, unchanged
SCHEDULED_RUN = "scheduled-desk"  # started by the heartbeat, with nobody watching: its refunds wait at the gate

# Read tools, plus issue_refund. That tool only proposes: the checker and the approval gate decide the payment.
GRANTS: dict[str, frozenset[str]] = {
    CHAT_RUN: frozenset({"get_order", "calculator", "issue_refund"}),
    SCHEDULED_RUN: frozenset({"get_order", "calculator", "issue_refund"}),
}


def permit(run: str, tool: str) -> tuple[bool, str]:
    """True and "granted", or False and the reason. Fails closed for an unknown run or tool."""
    grants = GRANTS.get(run)
    if grants is None:
        return False, f"no run named {run}"
    if tool not in grants:
        return False, f"{tool} is not granted to {run}"
    return True, "granted"


def granted_tools(run: str) -> list[str]:
    """The tool names the model is shown for this run (the runner still checks each call)."""
    return sorted(GRANTS.get(run, frozenset()))

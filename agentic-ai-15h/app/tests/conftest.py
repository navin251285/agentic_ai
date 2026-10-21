"""Tests run offline: model calls replay the recordings in tests/cassettes (no key, no cost)."""
import contextlib
import os

import pytest
from langchain_core.messages import AIMessage

os.environ.setdefault("TUT_LLM_MODE", "replay")  # replay only: a call with no recording fails instead of calling out


class ScriptedModel:
    """A stand-in for the desk's model in the guard tests: it gives the scripted replies in order. No network, no key.
    The tests use it to ask for what an attacker would ask for; the guard, not the model, is what is being tested."""

    def __init__(self, replies: list[AIMessage]) -> None:
        self.replies = list(replies)

    def bind_tools(self, specs) -> "ScriptedModel":
        return self

    def invoke(self, messages) -> AIMessage:
        if not self.replies:
            raise AssertionError("the desk asked the model more often than the script allows")
        return self.replies.pop(0)


def tool_turn(name: str, args: dict, call_id: str = "c1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}])


def text_turn(text: str) -> AIMessage:
    return AIMessage(content=text)


@pytest.fixture
def scripted(monkeypatch):
    """Use a scripted model for the desk's next questions, with no recording: `scripted(reply, reply, ...)`."""
    def use(*replies: AIMessage) -> ScriptedModel:
        model = ScriptedModel(list(replies))
        monkeypatch.setattr("support_desk.desk.get_llm", lambda: model)
        monkeypatch.setattr("support_desk.desk.recorded", lambda name: contextlib.nullcontext())
        return model
    return use

"""Gemini engine: one structured-output call decides on all listed products.

Errors are re-raised as LlmError with a short, key-free reason; the agent turns them into a fallback.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.config import Settings
from app.domain.models import Decision
from app.services.engines.base import AgentContext
from app.services.engines.prompts import SYSTEM_PROMPT, build_context

MAX_REASON_WORDS = 20
WARMUP_PROMPT = "Reply with the single word: ready"


class LlmDecision(BaseModel):
    product_id: str = Field(description="One of the product_id values given")
    action: Literal["order", "wait"]
    qty: int = Field(description="Units to order; 0 when waiting")
    reason: str = Field(description="At most 20 words, plain English")


class LlmPlan(BaseModel):
    decisions: list[LlmDecision]


class LlmError(Exception):
    """Short, printable reason (never contains the API key)."""


def make_llm(settings: Settings) -> Any:
    """The client exactly as in CLAUDE.md (no project/location), plus max_retries=0: every call counts."""
    from langchain_google_genai import ChatGoogleGenerativeAI  # lazy: tests never need it

    return ChatGoogleGenerativeAI(
        model=settings.llm_model,
        vertexai=True,
        api_key=settings.google_cloud_api_key.get_secret_value(),
        max_output_tokens=1024,
        temperature=0,
        max_retries=0,
    )


def short_reason(exc: BaseException, secret: str | None = None, limit: int = 120) -> str:
    text = f"{type(exc).__name__}: {exc}".splitlines()[0] if str(exc) else type(exc).__name__
    if secret:
        text = text.replace(secret, "***")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def trim_words(text: str, n: int = MAX_REASON_WORDS) -> str:
    words = text.split()
    return " ".join(words[:n]) + ("…" if len(words) > n else "")


class GeminiEngine:
    def __init__(self, llm: Any, secret: str | None = None):
        self.llm = llm
        self._structured = llm.with_structured_output(LlmPlan)
        self._secret = secret

    async def decide(self, context: AgentContext) -> list[Decision]:
        messages = [("system", SYSTEM_PROMPT), ("human", build_context(context))]
        try:
            plan = await self._structured.ainvoke(messages)
        except Exception as exc:
            raise LlmError(short_reason(exc, self._secret)) from exc
        if not isinstance(plan, LlmPlan):
            raise LlmError(f"invalid output: {type(plan).__name__}")
        return [
            Decision(
                product_id=d.product_id,
                action=d.action,
                qty=max(0, d.qty) if d.action == "order" else 0,
                reason=trim_words(d.reason.strip()) or "No reason given.",
                source="gemini",
            )
            for d in plan.decisions
        ]

    async def warm_up(self) -> None:
        try:
            await self.llm.ainvoke(WARMUP_PROMPT)
        except Exception as exc:
            raise LlmError(short_reason(exc, self._secret)) from exc

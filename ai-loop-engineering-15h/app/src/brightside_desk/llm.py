"""The chat model for the desk: Gemini, through the course .env (an API key, or a Vertex AI project).

The same provider as the course's llm_setup.get_llm(). Lessons use that helper; the app builds the model
here so it does not depend on notebook files.
"""
from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from .config import MissingSettingError, Settings


@contextmanager
def _hidden(names: tuple[str, ...]) -> Iterator[None]:
    """Hide environment variables while the client is built: an API key wins over a project id."""
    saved = {n: os.environ.pop(n) for n in names if n in os.environ}
    try:
        yield
    finally:
        os.environ.update(saved)


def build_chat_model(settings: Settings) -> Any:
    """A Gemini chat model with temperature 0. Raises MissingSettingError if no key or project is set."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    common: dict[str, Any] = {"model": settings.model, "vertexai": True, "temperature": 0,
                              "max_output_tokens": 1024}
    if settings.api_key:
        with _hidden(("GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION", "GOOGLE_API_KEY", "GEMINI_API_KEY")):
            return ChatGoogleGenerativeAI(api_key=settings.api_key, **common)
    if settings.project:
        with _hidden(("GOOGLE_API_KEY", "GEMINI_API_KEY")):
            return ChatGoogleGenerativeAI(project=settings.project, location=settings.location, **common)
    raise MissingSettingError(
        "No model key is set. Add GOOGLE_CLOUD_API_KEY (or GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION) "
        "to the course .env file, then restart the app."
    )

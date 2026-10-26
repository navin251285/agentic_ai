"""Retries for the model call (lesson 04, step 5): retry only the failures a later try can fix.

A 429 (rate limit), 502, 503 or 504, and a timeout or dropped connection, may succeed later, so they are
retried with exponential backoff and jitter. A 400, 401 or 422 will fail the same way again, so it is
raised at once and the request has to change. The model client is Google's; its errors carry the HTTP
status in `code`.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

import httpx
from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_exponential_jitter
from tenacity.wait import WaitBaseT

RETRYABLE_STATUS = {429, 502, 503, 504}
T = TypeVar("T")


def is_transient(exc: BaseException) -> bool:
    """True when a later try may succeed: a retryable HTTP status, a timeout, or a dropped connection."""
    code = getattr(exc, "code", None)
    if not isinstance(code, int):
        code = getattr(exc, "status_code", None)
    if isinstance(code, int):
        return code in RETRYABLE_STATUS
    return isinstance(exc, (TimeoutError, ConnectionError, httpx.TransportError))


def call_with_retries(call: Callable[[], T], *, attempts: int = 4, wait: WaitBaseT | None = None) -> T:
    """Run call(). Retry transient failures up to `attempts` tries; re-raise the last error otherwise."""
    retrying = Retrying(
        retry=retry_if_exception(is_transient),
        wait=wait or wait_exponential_jitter(initial=0.2, max=5),
        stop=stop_after_attempt(attempts),
        reraise=True,
    )
    return retrying(call)

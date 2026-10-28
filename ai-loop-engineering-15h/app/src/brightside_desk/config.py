"""Settings come from the environment and the course .env file, never from the code.

The course .env (topics/ai-loop-engineering-15h/.env) holds the key or the Vertex AI project. This module
reads the names it needs and treats an empty value or a placeholder ("<...>", "your-...") as not set.
Values are never printed or logged: the error messages name the setting, not its value.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

TOPIC_DIR = Path(__file__).resolve().parents[3]  # app/src/brightside_desk/config.py -> the topic folder
DEFAULT_MODEL = "gemini-2.5-flash-lite"  # the course default (llm_setup.py); TUT_LLM_MODEL overrides it
PLACEHOLDER = re.compile(r"^(<.*>|your.*|replace.*|changeme.*|todo|tbd)$", re.IGNORECASE)
STATE_DIR = TOPIC_DIR / "data" / "app"  # run-time state: the refund ledger, the task queue, the desk's git repo
LEDGER_PATH = STATE_DIR / "ledger.db"  # the refund ledger: made on the first refund


class MissingSettingError(RuntimeError):
    """A setting the app needs is not set. The message names the setting; it never shows a value."""


@dataclass(frozen=True)
class Settings:
    api_key: str
    project: str
    location: str
    model: str
    approval_limit_usd: float = 50.0  # a scheduled refund above this waits for a person (lesson 22)
    lease_s: float = 90.0             # a claim lasts this long without a renewal (lesson 20)
    review_window_s: float = 3600.0   # a parked run keeps its lease this long while a person decides (lesson 24)
    tick_s: float = 0.0               # seconds between scheduled ticks; 0 means no timer: call POST /api/tick
    host: str = "127.0.0.1"           # where the one run command listens: this machine only by default
    port: int = 8980                  # the course port for this app (progress.py --ports app starts at 8980)


def _setting(name: str, default: str = "") -> str:
    value = os.environ.get(name, "").strip()
    if not value or PLACEHOLDER.match(value):
        return default
    return value


def _number(name: str, default: float) -> float:
    raw = _setting(name)
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number (see the course .env file)") from exc
    if value < 0:
        raise ValueError(f"{name} must not be negative (see the course .env file)")
    return value


def _port(name: str, default: int) -> int:
    raw = _setting(name)
    if not raw:
        return default
    if not raw.isdigit() or not 1 <= int(raw) <= 65535:
        raise ValueError(f"{name} must be a port number from 1 to 65535 (see the course .env file)")
    return int(raw)


def load_settings() -> Settings:
    """Read the course .env once (existing environment variables win), then the settings the app uses."""
    load_dotenv(TOPIC_DIR / ".env", override=False)
    return Settings(
        api_key=_setting("GOOGLE_CLOUD_API_KEY"),
        project=_setting("GOOGLE_CLOUD_PROJECT"),
        location=_setting("GOOGLE_CLOUD_LOCATION", "global"),
        model=_setting("TUT_LLM_MODEL", DEFAULT_MODEL),
        approval_limit_usd=_number("APP_APPROVAL_LIMIT_USD", 50.0),
        lease_s=_number("APP_LEASE_S", 90.0),
        review_window_s=_number("APP_REVIEW_WINDOW_S", 3600.0),
        tick_s=_number("APP_TICK_S", 0.0),
        host=_setting("APP_HOST", "127.0.0.1"),
        port=_port("APP_PORT", 8980),
    )

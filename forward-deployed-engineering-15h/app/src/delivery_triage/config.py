"""Settings for the triage app. Every value comes from the course .env or the environment.

The app lives inside the course folder, so it reuses the course's own tut_env.py (the .env reader)
and llm_setup.py (the model setup from lesson 06). Nothing secret is typed in this file.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

# src/delivery_triage/config.py -> app/src/delivery_triage -> app -> the course folder
COURSE_DIR = Path(__file__).resolve().parents[3]
APP_DIR = COURSE_DIR / "app"
if not (COURSE_DIR / "tut_env.py").exists():
    raise RuntimeError("delivery_triage must sit inside the course folder (it reads the course's tut_env.py)")
if str(COURSE_DIR) not in sys.path:
    sys.path.insert(0, str(COURSE_DIR))

from tut_env import env, is_set  # noqa: E402  (needs the course folder on sys.path, set above)

DEFAULT_ORDERS = COURSE_DIR / "data" / "05" / "orders_clean.csv"  # lesson 05's cleaned orders (invented data)
DEFAULT_STORE = COURSE_DIR / "data" / "app" / "issues.csv"  # the stored delivery issues (step 2), written on first triage
DEFAULT_TENANTS = APP_DIR / "config" / "tenants.json"  # per-store limits, no secrets (step 3, lesson 23)
DEFAULT_TRACE_FILE = COURSE_DIR / "data" / "app" / "traces.jsonl"  # one line per span (step 3, lesson 16)
DEFAULT_EVAL_SET = COURSE_DIR / "data" / "11" / "eval_set.csv"  # lesson 11's twelve labelled cases
DEFAULT_EVAL_RESULTS = COURSE_DIR / "data" / "11" / "scored_v2.json"  # lesson 11's labels for the candidate prompt
DEFAULT_EVAL_MIN_PASS = 0.9  # the gate's bar: at least 90% of the labelled cases must pass
DEFAULT_PORT = 8980  # the first port of this course's app range (progress.py --ports app)
DEFAULT_MODEL_ATTEMPTS = 4  # lesson 04: up to four tries for a model call that fails in a way a later try can fix


@dataclass(frozen=True)
class Settings:
    orders_file: Path
    store_file: Path
    tenants_file: Path
    trace_file: Path
    eval_set_file: Path
    eval_results_file: Path
    eval_min_pass_rate: float
    port: int
    model_attempts: int
    service_token: str  # "" means not set: every /api route then answers 503 (step 3, lesson 13)


def setting_is_set(name: str) -> bool:
    """True when a setting is filled in. The value itself is never returned or printed."""
    return is_set(name)


def _course_path(raw: str) -> Path:
    """A relative path in the .env is relative to the course folder."""
    path = Path(raw)
    return path if path.is_absolute() else COURSE_DIR / path


def load_settings() -> Settings:
    attempts = int(env("TRIAGE_MODEL_ATTEMPTS", str(DEFAULT_MODEL_ATTEMPTS)))
    if attempts < 1:
        raise ValueError("TRIAGE_MODEL_ATTEMPTS must be at least 1")
    min_pass = float(env("TRIAGE_EVAL_MIN_PASS_RATE", str(DEFAULT_EVAL_MIN_PASS)))
    if not 0 < min_pass <= 1:
        raise ValueError("TRIAGE_EVAL_MIN_PASS_RATE must be above 0 and at most 1")
    return Settings(
        orders_file=_course_path(env("TRIAGE_ORDERS_FILE", str(DEFAULT_ORDERS))),
        store_file=_course_path(env("TRIAGE_STORE_FILE", str(DEFAULT_STORE))),
        tenants_file=_course_path(env("TRIAGE_TENANTS_FILE", str(DEFAULT_TENANTS))),
        trace_file=_course_path(env("TRIAGE_TRACE_FILE", str(DEFAULT_TRACE_FILE))),
        eval_set_file=_course_path(env("TRIAGE_EVAL_SET_FILE", str(DEFAULT_EVAL_SET))),
        eval_results_file=_course_path(env("TRIAGE_EVAL_RESULTS_FILE", str(DEFAULT_EVAL_RESULTS))),
        eval_min_pass_rate=min_pass,
        port=int(env("TRIAGE_PORT", str(DEFAULT_PORT))),
        model_attempts=attempts,
        service_token=env("TRIAGE_SERVICE_TOKEN", ""),
    )

"""Settings for the app, read from the course's .env or the environment (never typed in the code)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from support_desk.course import APP_ROOT, COURSE_ROOT, env


@dataclass(frozen=True)
class Settings:
    max_steps: int      # model calls per chat turn (lesson 06: the step cap)
    max_usd: float      # money per chat turn, estimated from each reply's usage (lesson 06: the spend cap)
    orders_file: Path   # the small order world the tools read (the course's data, kept offline)
    port: int           # the port `python -m support_desk` listens on
    # step 2: the policy passages (lessons 17, 18), and the folder of the desk's saved state (memory, refunds, runs)
    policy_file: Path = COURSE_ROOT / "data" / "ftc_chunks_embeddings.json"
    state_dir: Path = APP_ROOT / "state"


def load_settings() -> Settings:
    return Settings(
        max_steps=int(env("SUPPORT_MAX_STEPS", "4")),
        max_usd=float(env("SUPPORT_MAX_USD", "0.01")),
        orders_file=Path(env("SUPPORT_ORDERS_FILE", str(COURSE_ROOT / "data" / "support_eval.json"))),
        port=int(env("SUPPORT_PORT", "8980")),
        policy_file=Path(env("SUPPORT_POLICY_FILE", str(COURSE_ROOT / "data" / "ftc_chunks_embeddings.json"))),
        state_dir=Path(env("SUPPORT_STATE_DIR", str(APP_ROOT / "state"))),
    )

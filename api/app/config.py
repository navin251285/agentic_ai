"""Settings from environment / .env (pydantic-settings)."""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

API_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = API_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Root .env (shared with Compose) first, then an optional api/.env override.
        env_file=(ROOT_DIR / ".env", API_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    sim_seed: int | None = None
    data_dir: Path = Path("./data")
    default_scenario: str = "normal_day"
    agent_interval_s: int = Field(5, ge=1, le=60)
    save_interval_s: float = Field(3, gt=0)
    api_port: int = 8000

    agent_mode: Literal["rules", "gemini"] = "rules"
    google_cloud_api_key: SecretStr | None = None
    llm_model: str = "gemini-2.5-flash-lite"
    llm_timeout_s: float = Field(8, gt=0)
    # Hard budget: may be lowered, never raised.
    llm_max_calls_per_min: int = Field(10, ge=1, le=10)
    llm_min_gap_s: float = Field(6, ge=6)

    @field_validator("sim_seed", "google_cloud_api_key", mode="before")
    @classmethod
    def _blank_is_none(cls, v):
        return None if isinstance(v, str) and not v.strip() else v

    @field_validator("data_dir")
    @classmethod
    def _resolve_data_dir(cls, v: Path) -> Path:
        # Relative paths are relative to api/, so it works from any cwd and in Docker (/app).
        return v if v.is_absolute() else (API_DIR / v).resolve()


def get_settings() -> Settings:
    return Settings()

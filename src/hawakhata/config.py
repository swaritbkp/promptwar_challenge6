"""Central configuration — the ONLY module that reads environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """Typed, validated application settings loaded from env vars / .env."""

    # extra="ignore" (deliberately not "forbid"): Cloud Run injects ambient env vars such as
    # PORT, K_SERVICE, K_REVISION and K_CONFIGURATION that this app does not declare; "forbid"
    # would crash the container at boot. Request bodies stay strict: every API schema uses
    # StrictBaseModel(extra="forbid") in api/schemas.py.
    model_config = SettingsConfigDict(
        env_file=(_ENV_FILE, ".env"), env_file_encoding="utf-8", extra="ignore", frozen=True
    )

    app_env: Literal["dev", "test", "prod"] = "dev"
    port: int = Field(default=8080, ge=1, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    google_maps_api_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None
    gemini_model_primary: str = Field(default="", max_length=80)
    gemini_model_fallback: str = Field(default="", max_length=80)
    llm_timeout_s: float = Field(default=15.0, gt=0, le=60)
    aq_timeout_s: float = Field(default=4.0, gt=0, le=30)

    redis_url: str | None = None
    gcp_project_id: str | None = Field(default=None, max_length=64)
    # Proxies that append to X-Forwarded-For (Cloud Run GFE = 1); 0 trusts only the socket peer.
    trusted_proxy_hops: int = Field(default=1, ge=0, le=10)
    cache_max_entries: int = Field(default=2048, ge=16, le=100_000)
    aq_cache_ttl_s: int = Field(default=1800, ge=60, le=86_400)

    session_max: int = Field(default=1000, ge=10, le=100_000)
    session_ttl_s: int = Field(default=3600, ge=60, le=86_400)
    session_max_turns: int = Field(default=20, ge=2, le=100)
    # Prompt memory: newest N stored turns, then oldest dropped until within the char budget.
    chat_history_turns: int = Field(default=8, ge=0, le=100)
    chat_history_max_chars: int = Field(default=6_000, ge=0, le=50_000)

    rate_limit_per_min: int = Field(default=60, ge=1, le=10_000)
    rate_limit_max_clients: int = Field(default=5000, ge=10, le=1_000_000)
    max_body_bytes: int = Field(default=65_536, ge=1024, le=1_048_576)
    chat_max_chars: int = Field(default=1000, ge=50, le=8000)
    ai_limit_per_min: int = Field(default=6, ge=1, le=600)
    ai_limit_per_day: int = Field(default=60, ge=1, le=10_000)

    monte_carlo_samples: int = Field(default=200, ge=10, le=5000)
    monte_carlo_seed: int = 42
    planner_robust_lambda: float = Field(default=0.5, ge=0, le=5)
    forecast_shift_replan_threshold_ug_m3: float = Field(default=40.0, ge=1, le=500)
    demo_clock_iso: str | None = None
    # When set, GET /metrics requires "Authorization: Bearer <token>" (unset = open, local dev).
    metrics_auth_token: SecretStr | None = None

    @field_validator(
        "google_maps_api_key",
        "gemini_api_key",
        "redis_url",
        "gcp_project_id",
        "demo_clock_iso",
        "metrics_auth_token",
        mode="before",
    )
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @property
    def has_live_air_data(self) -> bool:
        """Keyless Open-Meteo AQ is live everywhere except the offline test environment."""
        return self.app_env != "test"

    @property
    def has_llm(self) -> bool:
        return self.gemini_api_key is not None and bool(self.gemini_model_primary)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()

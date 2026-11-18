"""Central configuration — the ONLY module that reads environment variables.

Every other module receives a :class:`Settings` instance through :func:`get_settings`
or a FastAPI dependency. Values are validated and bounded at start-up so a bad
deployment fails fast instead of misbehaving at request time.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed, validated application settings loaded from env vars / ``.env``."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", frozen=True
    )

    # Runtime
    app_env: Literal["dev", "test", "prod"] = "dev"
    port: int = Field(default=8080, ge=1, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Google services (optional: the app runs in fixture + fallback mode without keys)
    google_maps_api_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None
    gemini_model_primary: str = Field(default="", max_length=80)
    gemini_model_fallback: str = Field(default="", max_length=80)
    llm_timeout_s: float = Field(default=8.0, gt=0, le=60)
    aq_timeout_s: float = Field(default=4.0, gt=0, le=30)

    # Caching (always bounded)
    redis_url: str | None = None
    cache_max_entries: int = Field(default=2048, ge=16, le=100_000)
    aq_cache_ttl_s: int = Field(default=1800, ge=60, le=86_400)

    # Chat sessions (always bounded)
    session_max: int = Field(default=1000, ge=10, le=100_000)
    session_ttl_s: int = Field(default=3600, ge=60, le=86_400)
    session_max_turns: int = Field(default=20, ge=2, le=100)

    # Abuse limits
    rate_limit_per_min: int = Field(default=60, ge=1, le=10_000)
    rate_limit_max_clients: int = Field(default=5000, ge=10, le=1_000_000)
    max_body_bytes: int = Field(default=65_536, ge=1024, le=1_048_576)
    chat_max_chars: int = Field(default=1000, ge=50, le=8000)
    ai_limit_per_min: int = Field(default=6, ge=1, le=600)
    ai_limit_per_day: int = Field(default=60, ge=1, le=10_000)

    # Engine
    monte_carlo_samples: int = Field(default=200, ge=10, le=5000)
    monte_carlo_seed: int = 42
    planner_robust_lambda: float = Field(default=0.5, ge=0, le=5)
    forecast_shift_replan_threshold_ug_m3: float = Field(default=40.0, ge=1, le=500)

    # Story / demo mode: a fixed ISO-8601 clock makes recorded demos reproducible.
    demo_clock_iso: str | None = None

    @field_validator(
        "google_maps_api_key", "gemini_api_key", "redis_url", "demo_clock_iso", mode="before"
    )
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        """Treat empty strings from ``KEY=`` lines in ``.env`` as "not configured"."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def has_live_air_data(self) -> bool:
        """Return True when a Google Maps Platform key is configured."""
        return self.google_maps_api_key is not None

    @property
    def has_llm(self) -> bool:
        """Return True when Gemini can be called (key and a primary model id)."""
        return self.gemini_api_key is not None and bool(self.gemini_model_primary)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance (cached, immutable)."""
    return Settings()

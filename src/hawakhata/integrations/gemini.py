"""Gemini API integration with model cascade, timeouts, and abuse quotas."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from google.genai import Client, types

from hawakhata.core.errors import RateLimitedError
from hawakhata.core.logging import get_logger
from hawakhata.core.rate_limit import DailyQuota, TokenBucketLimiter

if TYPE_CHECKING:
    from hawakhata.config import Settings

logger = get_logger(__name__)


class GeminiUnavailableError(Exception):
    """Raised when Gemini is unconfigured, unreachable, or all cascade models fail."""


@dataclass(frozen=True, slots=True)
class GeminiResponse:
    """Standardized response from Gemini model cascade."""

    text: str
    model_used: str
    structured_data: object | None = None
    fallback_used: bool = False
    degraded: bool = False


class GeminiCascadeClient:
    """Manages Gemini model cascade (primary -> fallback) with rate limits and timeouts."""

    def __init__(
        self,
        settings: Settings,
        genai_client: object | None = None,
    ) -> None:
        """Initialize cascade client with settings, limiters, and optional SDK client."""
        self._settings = settings
        self.primary_model = settings.gemini_model_primary or "gemini-2.5-flash"
        self.fallback_model = settings.gemini_model_fallback or "gemini-2.5-flash-lite"
        self.timeout_s = settings.llm_timeout_s

        self.min_limiter = TokenBucketLimiter(
            per_minute=settings.ai_limit_per_min,
            max_clients=settings.rate_limit_max_clients,
        )
        self.daily_quota = DailyQuota(
            max_per_day=settings.ai_limit_per_day,
            max_clients=settings.rate_limit_max_clients,
        )

        if genai_client is not None:
            self._client: object = genai_client
        elif settings.gemini_api_key:
            self._client = Client(api_key=settings.gemini_api_key.get_secret_value())
        else:
            self._client = None

    def check_rate_limit(self, client_id: str) -> None:
        """Verify per-minute and daily quotas for the client identifier."""
        hashed_id = TokenBucketLimiter.client_key(client_id)

        if not self.min_limiter.allow(hashed_id):
            wait_s = self.min_limiter.retry_after_s(hashed_id)
            raise RateLimitedError(
                f"AI rate limit reached. Please wait {wait_s}s before sending another prompt."
            )

        if not self.daily_quota.try_consume(hashed_id):
            raise RateLimitedError(
                "Daily AI quota reached (60/day). You can continue using all passbook, "
                "clean window planning, and swap features without interruption."
            )

    async def _call_model(
        self,
        model_name: str,
        prompt: str,
        system_instruction: str,
        response_schema: object | None = None,
    ) -> str:
        """Execute single generate_content call against specified model."""
        if self._client is None or not hasattr(self._client, "aio"):
            raise GeminiUnavailableError("Gemini client not initialized")

        config_kwargs: dict[str, object] = {}
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction
        if response_schema is not None:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_schema"] = response_schema

        config = types.GenerateContentConfig(**config_kwargs)

        res = await asyncio.wait_for(
            self._client.aio.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config,
            ),
            timeout=self.timeout_s,
        )
        return str(getattr(res, "text", "") or "")

    async def generate_content(
        self,
        prompt: str,
        *,
        system_instruction: str = "",
        client_id: str | None = None,
        response_schema: object | None = None,
    ) -> GeminiResponse:
        """Generate content attempting primary model then cascading to fallback on failure."""
        if client_id is not None:
            self.check_rate_limit(client_id)

        if self._client is None:
            raise GeminiUnavailableError("Gemini API key is not configured")

        # 1. Attempt primary model
        try:
            text = await self._call_model(
                self.primary_model,
                prompt,
                system_instruction,
                response_schema=response_schema,
            )
            return GeminiResponse(
                text=text,
                model_used=self.primary_model,
                fallback_used=False,
            )
        except (TimeoutError, Exception) as exc:
            logger.warning(
                "Primary model %s failed (%s). Cascading to fallback %s",
                self.primary_model,
                exc,
                self.fallback_model,
            )

        # 2. Attempt fallback model
        try:
            text = await self._call_model(
                self.fallback_model,
                prompt,
                system_instruction,
                response_schema=response_schema,
            )
            return GeminiResponse(
                text=text,
                model_used=self.fallback_model,
                fallback_used=True,
            )
        except Exception as exc:
            logger.error("Fallback model %s also failed (%s)", self.fallback_model, exc)
            msg = (
                f"Both primary ({self.primary_model}) and fallback "
                f"({self.fallback_model}) failed: {exc}"
            )
            raise GeminiUnavailableError(msg) from exc

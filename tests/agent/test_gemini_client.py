from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import SecretStr

from hawakhata.config import Settings
from hawakhata.core.errors import RateLimitedError
from hawakhata.integrations.gemini import (
    GeminiCascadeClient,
    GeminiResponse,
    GeminiUnavailableError,
)


def _make_settings(
    has_key: bool = True,
    primary: str = "gemini-2.5-flash",
    fallback: str = "gemini-2.5-flash-lite",
    ai_limit_per_min: int = 5,
    ai_limit_per_day: int = 10,
) -> Settings:
    return Settings(
        gemini_api_key=SecretStr("fake-api-key") if has_key else None,
        gemini_model_primary=primary,
        gemini_model_fallback=fallback,
        ai_limit_per_min=ai_limit_per_min,
        ai_limit_per_day=ai_limit_per_day,
        llm_timeout_s=0.5,
    )


@pytest.mark.asyncio
async def test_gemini_unconfigured_raises_unavailable() -> None:
    client = GeminiCascadeClient(_make_settings(has_key=False))
    with pytest.raises(GeminiUnavailableError, match="not configured"):
        await client.generate_content("Hello")


@pytest.mark.asyncio
async def test_gemini_primary_success() -> None:
    settings = _make_settings()
    mock_genai = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = "Air quality advice"
    mock_genai.aio.models.generate_content = AsyncMock(return_value=mock_resp)

    client = GeminiCascadeClient(settings, genai_client=mock_genai)
    resp = await client.generate_content("Hello")

    assert isinstance(resp, GeminiResponse)
    assert resp.text == "Air quality advice"
    assert resp.model_used == "gemini-2.5-flash"
    assert resp.fallback_used is False


@pytest.mark.asyncio
async def test_gemini_cascade_on_timeout() -> None:
    settings = _make_settings()
    mock_genai = MagicMock()

    # Primary hangs and times out; fallback succeeds
    async def _mock_generate(model: str, contents: object, config: object) -> MagicMock:
        if model == "gemini-2.5-flash":
            await asyncio.sleep(2.0)
        res = MagicMock()
        res.text = "Fallback response"
        return res

    mock_genai.aio.models.generate_content = AsyncMock(side_effect=_mock_generate)

    client = GeminiCascadeClient(settings, genai_client=mock_genai)
    resp = await client.generate_content("Hello")

    assert resp.text == "Fallback response"
    assert resp.model_used == "gemini-2.5-flash-lite"
    assert resp.fallback_used is True


@pytest.mark.asyncio
async def test_gemini_cascade_on_500_server_error() -> None:
    settings = _make_settings()
    mock_genai = MagicMock()

    # Primary raises RuntimeError; fallback succeeds
    call_count = 0

    async def _mock_generate(model: str, contents: object, config: object) -> MagicMock:
        nonlocal call_count
        call_count += 1
        if model == "gemini-2.5-flash":
            raise RuntimeError("503 Service Unavailable")
        res = MagicMock()
        res.text = "Fallback after error"
        return res

    mock_genai.aio.models.generate_content = AsyncMock(side_effect=_mock_generate)

    client = GeminiCascadeClient(settings, genai_client=mock_genai)
    resp = await client.generate_content("Hello")

    assert resp.text == "Fallback after error"
    assert resp.fallback_used is True
    assert call_count == 2


@pytest.mark.asyncio
async def test_gemini_both_fail_raises_unavailable() -> None:
    settings = _make_settings()
    mock_genai = MagicMock()
    mock_genai.aio.models.generate_content = AsyncMock(
        side_effect=RuntimeError("Google upstream down")
    )

    client = GeminiCascadeClient(settings, genai_client=mock_genai)
    with pytest.raises(GeminiUnavailableError, match=r"Both primary .* and fallback"):
        await client.generate_content("Hello")


@pytest.mark.asyncio
async def test_gemini_per_minute_rate_limit() -> None:
    settings = _make_settings(ai_limit_per_min=2, ai_limit_per_day=100)
    mock_genai = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = "OK"
    mock_genai.aio.models.generate_content = AsyncMock(return_value=mock_resp)

    client = GeminiCascadeClient(settings, genai_client=mock_genai)
    client_id = "test-client-1"

    # 1 and 2 succeed
    await client.generate_content("msg1", client_id=client_id)
    await client.generate_content("msg2", client_id=client_id)

    # 3 fails with RateLimitedError
    with pytest.raises(RateLimitedError, match="rate limit"):
        await client.generate_content("msg3", client_id=client_id)


@pytest.mark.asyncio
async def test_gemini_daily_quota() -> None:
    settings = _make_settings(ai_limit_per_min=100, ai_limit_per_day=3)
    mock_genai = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = "OK"
    mock_genai.aio.models.generate_content = AsyncMock(return_value=mock_resp)

    client = GeminiCascadeClient(settings, genai_client=mock_genai)
    client_id = "test-client-quota"

    # 3 succeed
    for i in range(3):
        await client.generate_content(f"msg{i}", client_id=client_id)

    # 4th fails with RateLimitedError mentioning quota
    with pytest.raises(RateLimitedError, match="Daily AI quota reached"):
        await client.generate_content("msg4", client_id=client_id)


@pytest.mark.asyncio
async def test_gemini_system_instruction_and_schema_and_init() -> None:
    settings = _make_settings()
    mock_genai = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = '{"answer": "ok"}'
    mock_genai.aio.models.generate_content = AsyncMock(return_value=mock_resp)

    client = GeminiCascadeClient(settings, genai_client=mock_genai)
    resp = await client.generate_content(
        "Generate JSON",
        system_instruction="You are a helpful assistant",
        response_schema={"type": "object"},
    )
    assert resp.text == '{"answer": "ok"}'

    # Test initialization with real key (constructs Client)
    real_client = GeminiCascadeClient(settings)
    assert real_client._client is not None

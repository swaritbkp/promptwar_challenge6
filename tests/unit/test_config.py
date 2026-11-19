from __future__ import annotations

import pytest
from pydantic import ValidationError

from hawakhata.config import Settings, get_settings


def test_defaults_run_without_any_keys() -> None:
    cfg = Settings(_env_file=None)
    assert cfg.has_live_air_data is False and cfg.has_llm is False


def test_blank_env_values_are_treated_as_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "")
    monkeypatch.setenv("REDIS_URL", "   ")
    cfg = Settings(_env_file=None)
    assert cfg.google_maps_api_key is None and cfg.redis_url is None


def test_llm_requires_key_and_model() -> None:
    assert Settings(_env_file=None, gemini_api_key="k").has_llm is False
    assert Settings(_env_file=None, gemini_api_key="k", gemini_model_primary="m").has_llm is True


def test_secret_is_never_rendered_in_repr() -> None:
    assert "super-secret-value" not in repr(
        Settings(_env_file=None, google_maps_api_key="super-secret-value")
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [("port", 0), ("cache_max_entries", 1), ("rate_limit_per_min", 0), ("llm_timeout_s", 0)],
)
def test_out_of_bounds_values_fail_fast(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()

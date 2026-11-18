from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from hawakhata.core.rate_limit import DailyQuota, TokenBucketLimiter
from tests.conftest import FakeClock


def test_allows_burst_up_to_capacity_then_blocks(clock: FakeClock) -> None:
    limiter = TokenBucketLimiter(per_minute=3, max_clients=10, clock=clock)
    assert [limiter.allow("c") for _ in range(4)] == [True, True, True, False]
    assert limiter.retry_after_s("c") >= 1


def test_tokens_refill_over_time(clock: FakeClock) -> None:
    limiter = TokenBucketLimiter(per_minute=60, max_clients=10, clock=clock)
    for _ in range(60):
        limiter.allow("c")
    assert limiter.allow("c") is False
    clock.advance(1.0)
    assert limiter.allow("c") is True
    assert limiter.retry_after_s("unknown") == 0


def test_client_key_hides_raw_identifier() -> None:
    key = TokenBucketLimiter.client_key("203.0.113.9")
    assert "203" not in key
    assert len(key) == 16


def test_invalid_configuration_rejected() -> None:
    with pytest.raises(ValueError, match="positive"):
        TokenBucketLimiter(per_minute=0, max_clients=1)


@given(st.lists(st.text(min_size=1, max_size=6), max_size=300), st.integers(1, 25))
def test_client_table_is_bounded(clients: list[str], bound: int) -> None:
    limiter = TokenBucketLimiter(per_minute=10, max_clients=bound)
    for client in clients:
        limiter.allow(client)
    assert limiter.tracked_clients <= bound


def test_daily_quota_blocks_after_limit_and_resets_next_day() -> None:
    clock = FakeClock(start=10 * 86_400 + 100)
    quota = DailyQuota(max_per_day=2, max_clients=5, clock=clock)
    assert [quota.try_consume("c") for _ in range(3)] == [True, True, False]
    assert quota.remaining("c") == 0
    clock.advance(86_400)
    assert quota.remaining("c") == 2
    assert quota.try_consume("c") is True


def test_daily_quota_rejects_invalid_configuration() -> None:
    with pytest.raises(ValueError, match="positive"):
        DailyQuota(max_per_day=0, max_clients=1)


@given(st.lists(st.text(min_size=1, max_size=6), max_size=300), st.integers(1, 25))
def test_daily_quota_client_table_is_bounded(clients: list[str], bound: int) -> None:
    quota = DailyQuota(max_per_day=3, max_clients=bound)
    for client in clients:
        quota.try_consume(client)
    assert len(quota._usage) <= bound  # verifying the memory bound

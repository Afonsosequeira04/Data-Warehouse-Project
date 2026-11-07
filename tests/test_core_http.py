"""Tests for the shared HTTP session, rate limiter and redaction helpers."""

import logging

import pytest
import requests
from urllib3.util.retry import Retry

from ingestion.core.http import (
    DEFAULT_STATUS_FORCELIST,
    RateLimiter,
    RedactingFilter,
    build_session,
    install_log_redaction,
    redact,
)

SECRET = "test_secret_key"


class FakeTime:
    """Deterministic clock and sleep recorder for RateLimiter."""

    def __init__(self, now: float = 0.0):
        self.now = now
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def test_redact_replaces_secret() -> None:
    assert redact(f"https://api.example?key={SECRET}", SECRET) == (
        "https://api.example?key=***"
    )


def test_redact_is_noop_without_secret() -> None:
    text = "nothing to hide"
    assert redact(text, "") == text


def test_redacting_filter_masks_message_and_args() -> None:
    record = logging.LogRecord(
        name="ingestion.core.http",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="request failed for %s",
        args=(f"https://api.example?key={SECRET}",),
        exc_info=None,
    )

    RedactingFilter(SECRET).filter(record)

    assert SECRET not in record.getMessage()
    assert record.getMessage() == "request failed for https://api.example?key=***"
    assert record.args == ()


def test_redacting_filter_keeps_unrelated_message() -> None:
    record = logging.LogRecord(
        name="ingestion.core.http",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="all good",
        args=(),
        exc_info=None,
    )

    assert RedactingFilter(SECRET).filter(record) is True
    assert record.getMessage() == "all good"


def test_install_log_redaction_rejects_empty_secret() -> None:
    with pytest.raises(ValueError, match="secret must be a non-empty string"):
        install_log_redaction("")


def test_install_log_redaction_covers_module_and_urllib3_loggers() -> None:
    install_log_redaction(SECRET)

    for name in (
        "ingestion.core.http",
        "urllib3",
        "urllib3.connectionpool",
        "urllib3.util.retry",
        "urllib3.poolmanager",
    ):
        filters = logging.getLogger(name).filters
        assert any(
            isinstance(item, RedactingFilter) and item.secret == SECRET
            for item in filters
        ), name


def test_install_log_redaction_is_idempotent() -> None:
    install_log_redaction(SECRET)
    install_log_redaction(SECRET)

    filters = [
        item
        for item in logging.getLogger("urllib3").filters
        if isinstance(item, RedactingFilter) and item.secret == SECRET
    ]
    assert len(filters) == 1


def test_rate_limiter_rejects_non_positive_rate() -> None:
    with pytest.raises(ValueError, match="requests_per_second must be greater than zero"):
        RateLimiter(0)


def test_rate_limiter_sleeps_when_needed() -> None:
    clock = FakeTime()
    limiter = RateLimiter(2, clock=clock.monotonic, sleep=clock.sleep)

    limiter.wait()  # first request is immediately allowed
    clock.now += 0.1
    limiter.wait()  # only 0.1s of the 0.5s interval elapsed

    assert clock.sleeps == [pytest.approx(0.4)]


def test_rate_limiter_skips_sleep_when_within_limit() -> None:
    clock = FakeTime()
    limiter = RateLimiter(2, clock=clock.monotonic, sleep=clock.sleep)

    limiter.wait()
    clock.now += 1.0
    limiter.wait()

    assert clock.sleeps == []


def test_build_session_mounts_retrying_adapters() -> None:
    session = build_session(max_retries=2, backoff_factor=0.5)

    assert isinstance(session, requests.Session)
    for scheme in ("https://", "http://"):
        adapter = session.get_adapter(f"{scheme}api.example")
        retries = adapter.max_retries
        assert isinstance(retries, Retry)
        assert retries.total == 2
        assert retries.backoff_factor == 0.5
        assert retries.status_forcelist == DEFAULT_STATUS_FORCELIST
        assert set(retries.allowed_methods) == {"GET"}
        assert retries.raise_on_status is False

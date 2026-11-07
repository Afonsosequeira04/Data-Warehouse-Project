"""Shared HTTP session, rate limiting and secret redaction helpers.

Outbound ingestion requests frequently carry an API key in a header or query
string. Every URL, error message and log record derived from a response must
be redacted before it is logged, raised or written to quarantine. The helpers
here centralise that behaviour so every source applies it the same way.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

DEFAULT_STATUS_FORCELIST = (429, 500, 502, 503, 504)

_URLLIB3_LOGGERS = (
    "urllib3",
    "urllib3.connectionpool",
    "urllib3.util.retry",
    "urllib3.poolmanager",
)


def redact(text: str, secret: str) -> str:
    """Replace ``secret`` in ``text`` so it never leaks."""
    if not secret:
        return text
    return text.replace(secret, "***")


class RedactingFilter(logging.Filter):
    """Logging filter that replaces a secret in formatted log messages."""

    def __init__(self, secret: str):
        super().__init__()
        self._secret = secret

    @property
    def secret(self) -> str:
        return self._secret

    def filter(self, record: logging.LogRecord) -> bool:
        if self._secret and self._secret in record.getMessage():
            record.msg = record.getMessage().replace(self._secret, "***")
            record.args = ()
        return True


def install_log_redaction(secret: str) -> None:
    """Mask ``secret`` in this module's logs and in urllib3 retry logs.

    urllib3 emits request URLs (which may carry the API key) from several
    loggers, notably ``urllib3.connectionpool`` and ``urllib3.util.retry``
    during retries. Every one of them needs the redacting filter.
    """
    if not secret:
        raise ValueError("secret must be a non-empty string")
    targets = (logger, *(logging.getLogger(name) for name in _URLLIB3_LOGGERS))
    for target in targets:
        already_installed = any(
            isinstance(existing, RedactingFilter) and existing.secret == secret
            for existing in target.filters
        )
        if not already_installed:
            target.addFilter(RedactingFilter(secret))


class RateLimiter:
    """Enforce a minimum interval between consecutive requests."""

    def __init__(
        self,
        requests_per_second: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if requests_per_second <= 0:
            raise ValueError("requests_per_second must be greater than zero")
        self._min_interval = 1.0 / requests_per_second
        self._clock = clock
        self._sleep = sleep
        self._last_request_time: float | None = None

    def wait(self) -> None:
        """Sleep only as long as needed to respect the configured rate."""
        if self._last_request_time is not None:
            elapsed = self._clock() - self._last_request_time
            if elapsed < self._min_interval:
                self._sleep(self._min_interval - elapsed)
        self._last_request_time = self._clock()


def build_session(
    *,
    max_retries: int = 3,
    backoff_factor: float = 1.0,
    status_forcelist: tuple[int, ...] = DEFAULT_STATUS_FORCELIST,
) -> requests.Session:
    """Create a requests session with bounded, GET-only retries."""
    session = requests.Session()
    retry_strategy = Retry(
        total=max_retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=("GET",),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

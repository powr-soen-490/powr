# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""When and how long to wait before retrying a Toast request.

Toast answers HTTP 429 when a rate limit is hit (20 requests/second and 10,000 per 15 minutes
per location, lower for some endpoints) and says when to come back through ``Retry-After``
(seconds) or ``X-Toast-RateLimit-Reset`` (UNIX epoch seconds). Server errors and network
failures are usually short-lived, so they are retried with exponential backoff.
See https://doc.toasttab.com/doc/devguide/apiRateLimiting.html
"""

import math
import random
from dataclasses import dataclass
from datetime import UTC
from email.utils import parsedate_to_datetime

import httpx2

RATE_LIMITED_STATUS = 429
RETRYABLE_STATUSES = frozenset({RATE_LIMITED_STATUS, 500, 502, 503, 504})
RETRY_AFTER_HEADER = "Retry-After"
RATE_LIMIT_RESET_HEADER = "X-Toast-RateLimit-Reset"
RATE_LIMIT_BY_HEADER = "X-Toast-RateLimit-By"


@dataclass(frozen=True)
class RetryPolicy:
    """How many times a request is tried and how long to wait in between.

    ``max_wait_seconds`` caps every wait. When Toast asks for a longer wait (for example after
    the 15-minute limit is used up), the request is not retried: blocking that long would hold
    the caller, so the error is raised with the wait Toast asked for.
    """

    max_attempts: int = 4
    base_delay_seconds: float = 1.0
    max_wait_seconds: float = 30.0

    def backoff_seconds(self, failed_attempts: int) -> float:
        """Exponential backoff with full jitter: random in [0, base * 2^(n-1)], capped."""
        ceiling = min(self.max_wait_seconds, self.base_delay_seconds * 2 ** (failed_attempts - 1))
        return random.uniform(0, ceiling)


def is_retryable(response: httpx2.Response) -> bool:
    return response.status_code in RETRYABLE_STATUSES


def server_wait_seconds(response: httpx2.Response, now: float) -> float | None:
    """The wait Toast asked for, from ``Retry-After`` or else ``X-Toast-RateLimit-Reset``."""
    retry_after = _retry_after_seconds(response.headers.get(RETRY_AFTER_HEADER), now)
    if retry_after is not None:
        return max(0.0, retry_after)
    reset_at = _as_number(response.headers.get(RATE_LIMIT_RESET_HEADER))
    if reset_at is not None:
        return max(0.0, reset_at - now)
    return None


def _retry_after_seconds(value: str | None, now: float) -> float | None:
    """``Retry-After`` is seconds (what Toast documents) or, per RFC 9110, an HTTP date."""
    seconds = _as_number(value)
    if seconds is not None or value is None:
        return seconds
    try:
        retry_at = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if retry_at.tzinfo is None:  # RFC 9110 dates are GMT; "-0000" parses without a zone.
        retry_at = retry_at.replace(tzinfo=UTC)
    return retry_at.timestamp() - now


def _as_number(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None

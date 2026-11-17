# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""HTTP access to the Toast API: login, token refresh, retries, error handling and decoding."""

import json
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx2
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.integrations.pos.toast.retry import (
    RATE_LIMIT_BY_HEADER,
    RATE_LIMITED_STATUS,
    RetryPolicy,
    is_retryable,
    server_wait_seconds,
)
from app.integrations.pos.toast.token_store import MemoryTokenStore, ToastToken, ToastTokenStore

logger = logging.getLogger(__name__)

LOGIN_PATH = "/authentication/v1/authentication/login"
MACHINE_CLIENT_ACCESS_TYPE = "TOAST_MACHINE_CLIENT"
REQUEST_TIMEOUT_SECONDS = 30.0
REJECTED_CREDENTIALS_STATUSES = frozenset({401, 403})
EXPIRED_TOKEN_STATUS = 401


class ToastCredentials(BaseModel):
    """Client ID and secret of a Toast Standard API access credential."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    client_id: str = Field(min_length=1)
    # SecretStr prints as '**********', so the secret cannot leak through logs or reprs.
    client_secret: SecretStr


class ToastApiError(Exception):
    """Toast could not be reached or answered with an error."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ToastAuthenticationError(ToastApiError):
    """Toast rejected the client ID or secret, or a freshly issued access token."""


class ToastRateLimitError(ToastApiError):
    """Toast kept answering HTTP 429; ``retry_after_seconds`` is the wait it asked for, if any."""

    def __init__(self, message: str, retry_after_seconds: float | None = None) -> None:
        super().__init__(message, status_code=RATE_LIMITED_STATUS)
        self.retry_after_seconds = retry_after_seconds


class ToastClient:
    """Sends requests to Toast for one restaurant location, reusing a saved access token.

    Toast asks for at most two logins per hour, so the client logs in only when it has no
    token, when the token has expired, or when Toast rejects it (HTTP 401). It never renews
    early: until the last minute Toast hands back the same token, so an early login would be
    wasted. ``token_store`` keeps the token between clients (see ``token_store.py``); without
    one it lives only as long as this client.

    Rate limits, server errors and network failures are retried with backoff (see
    ``retry.py``), except a rate-limited login: retrying it would only ask for more logins.

    ``restaurant_guid`` is None only for endpoints that are not about one restaurant, such
    as listing the restaurants a login can access; requests then skip the restaurant header.
    """

    def __init__(
        self,
        credentials: ToastCredentials,
        restaurant_guid: str | None,
        *,
        base_url: str,
        transport: httpx2.BaseTransport | None = None,
        retry_policy: RetryPolicy | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.time,
        token_store: ToastTokenStore | None = None,
    ) -> None:
        self._credentials = credentials
        self._restaurant_guid = restaurant_guid
        self._retry_policy = retry_policy or RetryPolicy()
        self._sleep = sleep
        self._clock = clock
        self._token_store = token_store or MemoryTokenStore()
        self._token: ToastToken | None = None
        self._http = httpx2.Client(
            base_url=base_url, timeout=REQUEST_TIMEOUT_SECONDS, transport=transport
        )

    @property
    def is_closed(self) -> bool:
        return self._http.is_closed

    def close(self) -> None:
        """Close the connections kept open for reuse between requests."""
        self._http.close()

    def ensure_token(self) -> None:
        """Make sure there is an unexpired token, logging in only when there is none.

        Raises ToastAuthenticationError when Toast rejects the credentials, and
        ToastRateLimitError when Toast is limiting logins.
        """
        if self._token is None:
            self._token = self._token_store.load()
        if self._token is None:
            self.login()
        elif self._token.is_expired(self._now()):
            logger.info("The Toast access token expired; logging in again")
            self.login()

    def login(self) -> None:
        """Exchange the client ID and secret for an access token, and save it.

        Prefer ``ensure_token``: every call is one of the few logins Toast allows per hour.
        """
        response = self._send(
            "POST",
            LOGIN_PATH,
            json={
                "clientId": self._credentials.client_id,
                "clientSecret": self._credentials.client_secret.get_secret_value(),
                "userAccessType": MACHINE_CLIENT_ACCESS_TYPE,
            },
            retry_rate_limits=False,
        )
        if response.status_code in REJECTED_CREDENTIALS_STATUSES:
            logger.warning("Toast rejected the credentials (HTTP %s)", response.status_code)
            self._token = None
            self._token_store.credentials_rejected()
            raise ToastAuthenticationError(
                "Toast rejected the credentials.", status_code=response.status_code
            )
        if response.status_code == RATE_LIMITED_STATUS:
            logger.warning("Toast is limiting logins (HTTP 429); not retrying the login")
            # No wait time: callers must not retry the login on their own either.
            raise ToastRateLimitError("Toast is limiting logins right now.")
        body = self._decode(response, LOGIN_PATH)
        token = body.get("token") if isinstance(body, dict) else None
        access_token = token.get("accessToken") if isinstance(token, dict) else None
        if not isinstance(access_token, str) or not access_token:
            raise ToastApiError("Toast login response has no access token.")
        self._token = ToastToken(access_token=access_token, expires_at=self._expiry(token))
        self._token_store.save(self._token)

    def get(self, path: str, params: dict[str, str | int] | None = None) -> Any:
        """GET a Toast endpoint for this location, logging in first only if needed."""
        self.ensure_token()
        response = self._get_with_token(path, params)
        if response.status_code == EXPIRED_TOKEN_STATUS:
            logger.info("Toast rejected the access token for %s; logging in again", path)
            self.login()
            response = self._get_with_token(path, params)
            if response.status_code == EXPIRED_TOKEN_STATUS:
                logger.error("Toast rejected a freshly issued access token for %s", path)
                raise ToastAuthenticationError(
                    "Toast rejected a freshly issued access token.",
                    status_code=EXPIRED_TOKEN_STATUS,
                )
        return self._decode(response, path)

    def _get_with_token(self, path: str, params: dict[str, str | int] | None) -> httpx2.Response:
        if self._token is None:  # pragma: no cover - ensure_token and login always set it
            raise AssertionError("no Toast access token")
        headers = {"Authorization": f"Bearer {self._token.access_token}"}
        if self._restaurant_guid is not None:
            headers["Toast-Restaurant-External-ID"] = self._restaurant_guid
        return self._send("GET", path, params=params, headers=headers)

    def _now(self) -> datetime:
        return datetime.fromtimestamp(self._clock(), UTC)

    def _expiry(self, token: Any) -> datetime | None:
        """When the new token stops working; None when Toast does not say how long it lasts."""
        expires_in = token.get("expiresIn") if isinstance(token, dict) else None
        if isinstance(expires_in, bool) or not isinstance(expires_in, int | Decimal):
            logger.info("Authenticated with Toast; Toast did not say how long the token lasts")
            return None
        if expires_in <= 0:
            return None
        # Only the lifetime is logged, never the token, so the real lifetime can be checked.
        logger.info("Authenticated with Toast; the access token lasts %s seconds", expires_in)
        return self._now() + timedelta(seconds=float(expires_in))

    def _send(
        self, method: str, path: str, *, retry_rate_limits: bool = True, **kwargs: Any
    ) -> httpx2.Response:
        """Send a request, retrying server errors, network failures and (unless turned off)
        rate limits."""
        attempts = self._retry_policy.max_attempts
        for attempt in range(1, attempts + 1):
            try:
                response = self._http.request(method, path, **kwargs)
            except httpx2.TransportError as exc:
                if attempt == attempts:
                    logger.error(
                        "Could not reach Toast for %s %s after %d attempts: %s",
                        method,
                        path,
                        attempts,
                        type(exc).__name__,
                    )
                    raise ToastApiError(f"Could not reach Toast for {method} {path}.") from exc
                reason = type(exc).__name__
                wait = self._retry_policy.backoff_seconds(attempt)
            except httpx2.HTTPError as exc:
                logger.warning(
                    "Could not reach Toast for %s %s: %s", method, path, type(exc).__name__
                )
                raise ToastApiError(f"Could not reach Toast for {method} {path}.") from exc
            else:
                if response.status_code == RATE_LIMITED_STATUS and not retry_rate_limits:
                    return response
                response_wait = self._wait_before_retry(response, method, path, attempt)
                if response_wait is None:
                    return response
                reason = f"HTTP {response.status_code}"
                wait = response_wait
            logger.warning(
                "Toast %s for %s %s; retrying in %.1fs (attempt %d of %d)",
                reason,
                method,
                path,
                wait,
                attempt + 1,
                attempts,
            )
            self._sleep(wait)
        raise AssertionError("unreachable: the last attempt returns or raises")  # pragma: no cover

    def _wait_before_retry(
        self, response: httpx2.Response, method: str, path: str, attempt: int
    ) -> float | None:
        """Seconds to wait before retrying this response, or None to hand it back as is."""
        if not is_retryable(response):
            return None
        policy = self._retry_policy
        if attempt == policy.max_attempts:
            logger.error(
                "Toast still returned HTTP %s for %s %s after %d attempts; giving up",
                response.status_code,
                method,
                path,
                attempt,
            )
            return None
        requested = server_wait_seconds(response, now=self._clock())
        if requested is None:
            return policy.backoff_seconds(attempt)
        if requested > policy.max_wait_seconds:
            logger.error(
                "Toast asked to wait %.0fs before retrying %s %s (limit: %s), longer than %.0fs;"
                " giving up",
                requested,
                method,
                path,
                response.headers.get(RATE_LIMIT_BY_HEADER, "unknown"),
                policy.max_wait_seconds,
            )
            return None
        return requested

    def _decode(self, response: httpx2.Response, path: str) -> Any:
        if response.status_code == RATE_LIMITED_STATUS:
            raise ToastRateLimitError(
                f"Toast rate limit reached for {path}.",
                retry_after_seconds=server_wait_seconds(response, now=self._clock()),
            )
        if not response.is_success:
            logger.warning("Toast returned HTTP %s for %s", response.status_code, path)
            raise ToastApiError(
                f"Toast returned HTTP {response.status_code} for {path}.",
                status_code=response.status_code,
            )
        try:
            # parse_float keeps prices and quantities exact instead of turning them into floats.
            return json.loads(response.text, parse_float=Decimal)
        except json.JSONDecodeError as exc:
            raise ToastApiError(f"Toast returned invalid JSON for {path}.") from exc

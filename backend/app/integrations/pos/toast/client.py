# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""HTTP access to the Toast API: login, headers, error handling and JSON decoding."""

import json
import logging
from decimal import Decimal
from typing import Any

import httpx2
from pydantic import BaseModel, ConfigDict, Field, SecretStr

logger = logging.getLogger(__name__)

LOGIN_PATH = "/authentication/v1/authentication/login"
MACHINE_CLIENT_ACCESS_TYPE = "TOAST_MACHINE_CLIENT"
REQUEST_TIMEOUT_SECONDS = 30.0
REJECTED_CREDENTIALS_STATUSES = frozenset({401, 403})


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
    """Toast rejected the client ID or secret."""


class ToastClient:
    """Sends requests to Toast for one restaurant location and keeps its access token."""

    def __init__(
        self,
        credentials: ToastCredentials,
        restaurant_guid: str,
        *,
        base_url: str,
        transport: httpx2.BaseTransport | None = None,
    ) -> None:
        self._credentials = credentials
        self._restaurant_guid = restaurant_guid
        self._access_token: str | None = None
        self._http = httpx2.Client(
            base_url=base_url, timeout=REQUEST_TIMEOUT_SECONDS, transport=transport
        )

    def login(self) -> None:
        """Exchange the client ID and secret for an access token."""
        response = self._send(
            "POST",
            LOGIN_PATH,
            json={
                "clientId": self._credentials.client_id,
                "clientSecret": self._credentials.client_secret.get_secret_value(),
                "userAccessType": MACHINE_CLIENT_ACCESS_TYPE,
            },
        )
        if response.status_code in REJECTED_CREDENTIALS_STATUSES:
            logger.warning("Toast rejected the credentials (HTTP %s)", response.status_code)
            raise ToastAuthenticationError(
                "Toast rejected the credentials.", status_code=response.status_code
            )
        body = self._decode(response, LOGIN_PATH)
        token = body.get("token") if isinstance(body, dict) else None
        access_token = token.get("accessToken") if isinstance(token, dict) else None
        if not isinstance(access_token, str) or not access_token:
            raise ToastApiError("Toast login response has no access token.")
        self._access_token = access_token
        logger.info("Authenticated with Toast")

    def get(self, path: str, params: dict[str, str | int] | None = None) -> Any:
        """GET a Toast endpoint for this location, logging in first if needed."""
        if self._access_token is None:
            self.login()
        response = self._send(
            "GET",
            path,
            params=params,
            headers={
                "Authorization": f"Bearer {self._access_token}",
                "Toast-Restaurant-External-ID": self._restaurant_guid,
            },
        )
        return self._decode(response, path)

    def _send(self, method: str, path: str, **kwargs: Any) -> httpx2.Response:
        try:
            return self._http.request(method, path, **kwargs)
        except httpx2.HTTPError as exc:
            logger.warning("Could not reach Toast for %s %s: %s", method, path, type(exc).__name__)
            raise ToastApiError(f"Could not reach Toast for {method} {path}.") from exc

    @staticmethod
    def _decode(response: httpx2.Response, path: str) -> Any:
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

# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Where a ToastClient keeps its access token between requests, so it logs in as rarely as possible.

Toast asks integrations to request a new token at most twice per hour and to reuse each one
until it expires (https://doc.toasttab.com/doc/devguide/apiAuthenticationRateLimit.html).
The client loads the saved token before its first request and saves every new one, so the
next request, import or process reuses it instead of logging in again.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class ToastToken:
    """An access token and when it stops working (UTC), or None when Toast did not say."""

    # repr=False keeps the token out of logs and error messages that print this object.
    access_token: str = field(repr=False)
    expires_at: datetime | None

    def is_expired(self, now: datetime) -> bool:
        return self.expires_at is not None and now >= self.expires_at


class ToastTokenStore(Protocol):
    """Keeps the token of one Toast client ID. Implementations must not raise: a token that
    could not be saved only costs a login later, so they log the problem and carry on."""

    def load(self) -> ToastToken | None:
        """The saved token, or None when there is none."""
        ...

    def save(self, token: ToastToken) -> None:
        """Keep the token from a successful login."""
        ...

    def credentials_rejected(self) -> None:
        """Toast rejected the client ID or secret: forget the token, the owner must reconnect."""
        ...


class MemoryTokenStore:
    """Keeps the token only as long as this object lives.

    Used when there is nowhere to save it: checking new credentials before they are saved,
    and tests. ``token`` is the last token saved and ``rejected`` whether Toast rejected the
    credentials.
    """

    def __init__(self, token: ToastToken | None = None) -> None:
        self.token = token
        self.rejected = False

    def load(self) -> ToastToken | None:
        return self.token

    def save(self, token: ToastToken) -> None:
        self.token = token

    def credentials_rejected(self) -> None:
        self.token = None
        self.rejected = True

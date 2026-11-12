# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""A pretend Toast server for unit tests, so CI never calls the real Toast API."""

import json
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx2

from app.integrations.pos.models import PosConnection
from app.integrations.pos.toast.adapter import ToastAdapter
from app.integrations.pos.toast.client import LOGIN_PATH, ToastCredentials
from app.integrations.pos.toast.retry import RetryPolicy

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "toast"
BASE_URL = "https://toast.test"
RESTAURANT_GUID = "restaurant-guid-1"
CLIENT_SECRET = "test-client-secret"
ACCESS_TOKEN = "test-access-token"
# 2026-01-01T00:00:00Z, a fixed starting time for the fake clock.
FAKE_NOW = 1_767_225_600.0
CONNECTION = PosConnection(
    id=UUID("00000000-0000-0000-0000-000000000001"),
    restaurant_id=UUID("00000000-0000-0000-0000-000000000002"),
    provider="TOAST",
    location_id=RESTAURANT_GUID,
)


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURES_DIR / name).read_text())


def load_response(name: str) -> httpx2.Response:
    """A saved Toast error response: ``{"status": ..., "headers": {...}, "body": {...}}``.

    token_expired.json is a real Toast reply to a request with an invalid token (captured
    2026-11-09). Toast cannot safely be made to return 429 or 503, so those files hold only the
    status and the headers ToastClient reads, with header names from
    https://doc.toasttab.com/doc/devguide/apiRateLimiting.html.
    """
    saved = load_fixture(name)
    return httpx2.Response(
        saved["status"], headers=saved.get("headers", {}), json=saved.get("body")
    )


class FakeToast:
    """Answers each path with queued responses; the last one repeats once the queue runs out.

    It also stands in for the clock and for ``time.sleep``: waits are recorded in ``sleeps``
    and move ``now`` forward, so retry tests run instantly.
    """

    def __init__(self) -> None:
        self.requests: list[httpx2.Request] = []
        self.sleeps: list[float] = []
        self.now = FAKE_NOW
        self._replies: dict[str, list[httpx2.Response | Exception]] = {
            LOGIN_PATH: [httpx2.Response(200, json=load_fixture("login_success.json"))]
        }

    def reply(self, path: str, *replies: httpx2.Response | Exception) -> None:
        self._replies[path] = list(replies)

    def requests_to(self, path: str) -> list[httpx2.Request]:
        return [request for request in self.requests if request.url.path == path]

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def clock(self) -> float:
        return self.now

    def adapter(self, retry_policy: RetryPolicy | None = None) -> ToastAdapter:
        credentials = ToastCredentials(client_id="test-client-id", client_secret=CLIENT_SECRET)
        return ToastAdapter(
            CONNECTION,
            credentials,
            currency="CAD",
            base_url=BASE_URL,
            transport=httpx2.MockTransport(self._handle),
            retry_policy=retry_policy,
            sleep=self.sleep,
            clock=self.clock,
        )

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        queue = self._replies.get(request.url.path)
        if not queue:
            return httpx2.Response(404)
        reply = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(reply, Exception):
            raise reply
        return reply

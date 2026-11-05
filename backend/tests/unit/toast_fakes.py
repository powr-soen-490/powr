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

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "toast"
BASE_URL = "https://toast.test"
RESTAURANT_GUID = "restaurant-guid-1"
CLIENT_SECRET = "test-client-secret"
CONNECTION = PosConnection(
    id=UUID("00000000-0000-0000-0000-000000000001"),
    restaurant_id=UUID("00000000-0000-0000-0000-000000000002"),
    provider="TOAST",
    location_id=RESTAURANT_GUID,
)


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURES_DIR / name).read_text())


class FakeToast:
    """Answers each path with queued responses; the last one repeats once the queue runs out."""

    def __init__(self) -> None:
        self.requests: list[httpx2.Request] = []
        self._replies: dict[str, list[httpx2.Response | Exception]] = {
            LOGIN_PATH: [httpx2.Response(200, json=load_fixture("login_success.json"))]
        }

    def reply(self, path: str, *replies: httpx2.Response | Exception) -> None:
        self._replies[path] = list(replies)

    def requests_to(self, path: str) -> list[httpx2.Request]:
        return [request for request in self.requests if request.url.path == path]

    def adapter(self) -> ToastAdapter:
        credentials = ToastCredentials(client_id="test-client-id", client_secret=CLIENT_SECRET)
        return ToastAdapter(
            CONNECTION,
            credentials,
            currency="CAD",
            base_url=BASE_URL,
            transport=httpx2.MockTransport(self._handle),
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

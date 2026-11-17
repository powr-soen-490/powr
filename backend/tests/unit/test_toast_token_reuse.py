# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""The Toast client reuses a saved access token and logs in only when it must (issue #173)."""

import logging
from datetime import UTC, datetime, timedelta

import httpx2
import pytest

from app.integrations.pos.toast.client import (
    LOGIN_PATH,
    ToastAuthenticationError,
    ToastCredentials,
    ToastRateLimitError,
)
from app.integrations.pos.toast.locations import RESTAURANTS_PATH, find_toast_locations
from app.integrations.pos.toast.token_store import MemoryTokenStore, ToastToken
from tests.unit.toast_fakes import (
    ACCESS_TOKEN,
    BASE_URL,
    CLIENT_SECRET,
    FAKE_NOW,
    FakeToast,
    load_fixture,
    load_response,
)

MENUS_PATH = "/menus/v2/menus"
NOW = datetime.fromtimestamp(FAKE_NOW, UTC)
TOKEN_LIFETIME_SECONDS = load_fixture("login_success.json")["token"]["expiresIn"]


@pytest.fixture
def toast() -> FakeToast:
    toast = FakeToast()
    toast.reply(MENUS_PATH, httpx2.Response(200, json={"ok": True}))
    return toast


def saved(token: str, expires_in: timedelta | None) -> MemoryTokenStore:
    expires_at = NOW + expires_in if expires_in is not None else None
    return MemoryTokenStore(ToastToken(access_token=token, expires_at=expires_at))


def bearer(request: httpx2.Request) -> str:
    return request.headers["Authorization"]


def test_an_unexpired_saved_token_is_used_without_logging_in(toast: FakeToast) -> None:
    store = saved("saved-token", timedelta(hours=1))

    toast.client(store).get(MENUS_PATH)

    assert toast.logins() == 0
    [request] = toast.requests_to(MENUS_PATH)
    assert bearer(request) == "Bearer saved-token"


def test_an_expired_saved_token_costs_one_login_and_the_new_token_is_saved(
    toast: FakeToast,
) -> None:
    store = saved("old-token", timedelta(seconds=0))

    toast.client(store).get(MENUS_PATH)

    assert toast.logins() == 1
    assert store.token == ToastToken(
        access_token=ACCESS_TOKEN, expires_at=NOW + timedelta(seconds=TOKEN_LIFETIME_SECONDS)
    )


def test_a_saved_token_toast_rejects_is_replaced_with_one_login(toast: FakeToast) -> None:
    store = saved("revoked-token", timedelta(hours=1))
    toast.reply(MENUS_PATH, load_response("token_expired.json"), httpx2.Response(200, json={}))

    toast.client(store).get(MENUS_PATH)

    assert toast.logins() == 1
    assert [bearer(r) for r in toast.requests_to(MENUS_PATH)] == [
        "Bearer revoked-token",
        f"Bearer {ACCESS_TOKEN}",
    ]
    assert store.token is not None
    assert store.token.access_token == ACCESS_TOKEN


def test_a_token_without_an_expiry_is_used_until_toast_rejects_it(toast: FakeToast) -> None:
    store = saved("saved-token", expires_in=None)
    client = toast.client(store)

    client.get(MENUS_PATH)
    toast.now += 30 * 24 * 3600
    client.get(MENUS_PATH)

    assert toast.logins() == 0


def test_a_token_expiring_during_an_import_costs_one_login_and_the_import_goes_on(
    toast: FakeToast,
) -> None:
    store = saved("first-token", timedelta(minutes=10))
    client = toast.client(store)

    client.get(MENUS_PATH)
    toast.now += 10 * 60
    client.get(MENUS_PATH)
    client.get(MENUS_PATH)

    assert toast.logins() == 1
    assert [bearer(r) for r in toast.requests_to(MENUS_PATH)] == [
        "Bearer first-token",
        f"Bearer {ACCESS_TOKEN}",
        f"Bearer {ACCESS_TOKEN}",
    ]


def test_rejected_credentials_are_reported_to_the_store(toast: FakeToast) -> None:
    store = saved("old-token", timedelta(seconds=0))
    toast.reply(LOGIN_PATH, httpx2.Response(401))

    assert toast.adapter(token_store=store).authenticate() is False

    assert store.rejected is True
    assert store.token is None


def test_a_rate_limited_login_leaves_the_credentials_alone(toast: FakeToast) -> None:
    store = MemoryTokenStore()
    toast.reply(LOGIN_PATH, load_response("rate_limited.json"))

    with pytest.raises(ToastRateLimitError):
        toast.client(store).get(MENUS_PATH)

    assert toast.logins() == 1
    assert store.rejected is False


def test_a_freshly_issued_token_rejected_too_does_not_flag_the_credentials(
    toast: FakeToast,
) -> None:
    store = MemoryTokenStore()
    toast.reply(MENUS_PATH, load_response("token_expired.json"))

    with pytest.raises(ToastAuthenticationError):
        toast.client(store).get(MENUS_PATH)

    assert store.rejected is False


def test_connect_then_import_logs_in_once(toast: FakeToast) -> None:
    """The token from checking the credentials is handed to the next client."""
    toast.reply(RESTAURANTS_PATH, httpx2.Response(200, json=[{"restaurantGuid": "guid-1"}]))
    store = MemoryTokenStore()

    find_toast_locations(
        ToastCredentials(client_id="test-client-id", client_secret=CLIENT_SECRET),
        base_url=BASE_URL,
        transport=httpx2.MockTransport(toast._handle),
        sleep=toast.sleep,
        clock=toast.clock,
        token_store=store,
    )
    with toast.adapter(token_store=store) as adapter:
        assert adapter.authenticate() is True
        adapter.fetch_menu_items()

    assert toast.logins() == 1


def test_the_token_never_appears_in_logs_or_reprs(
    toast: FakeToast, caplog: pytest.LogCaptureFixture
) -> None:
    store = saved("old-token", timedelta(seconds=0))

    with caplog.at_level(logging.DEBUG):
        toast.client(store).get(MENUS_PATH)

    assert "lasts 86400 seconds" in caplog.text
    assert ACCESS_TOKEN not in caplog.text
    assert CLIENT_SECRET not in caplog.text
    assert ACCESS_TOKEN not in repr(store.token)

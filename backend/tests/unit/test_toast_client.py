# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Toast login, request headers and error handling against a fake Toast server."""

import json
import logging
from decimal import Decimal

import httpx2
import pytest

from app.integrations.pos.toast.client import LOGIN_PATH, ToastApiError, ToastCredentials
from tests.unit.toast_fakes import CLIENT_SECRET, RESTAURANT_GUID, FakeToast

MENUS_PATH = "/menus/v2/menus"


@pytest.fixture
def toast() -> FakeToast:
    return FakeToast()


class TestAuthenticate:
    def test_sends_machine_client_login(self, toast: FakeToast) -> None:
        assert toast.adapter().authenticate() is True

        [login] = toast.requests_to(LOGIN_PATH)
        assert login.method == "POST"
        assert json.loads(login.content) == {
            "clientId": "test-client-id",
            "clientSecret": CLIENT_SECRET,
            "userAccessType": "TOAST_MACHINE_CLIENT",
        }

    @pytest.mark.parametrize("status", [401, 403])
    def test_returns_false_when_credentials_are_rejected(
        self, toast: FakeToast, status: int
    ) -> None:
        toast.reply(LOGIN_PATH, httpx2.Response(status))

        assert toast.adapter().authenticate() is False

    def test_raises_when_toast_fails(self, toast: FakeToast) -> None:
        toast.reply(LOGIN_PATH, httpx2.Response(500))

        with pytest.raises(ToastApiError) as error:
            toast.adapter().authenticate()
        assert error.value.status_code == 500

    def test_raises_when_response_has_no_token(self, toast: FakeToast) -> None:
        toast.reply(LOGIN_PATH, httpx2.Response(200, json={"status": "SUCCESS"}))

        with pytest.raises(ToastApiError, match="no access token"):
            toast.adapter().authenticate()


class TestGet:
    def test_logs_in_first_and_sends_location_headers(self, toast: FakeToast) -> None:
        toast.reply(MENUS_PATH, httpx2.Response(200, json={}))

        toast.adapter()._client.get(MENUS_PATH)

        assert [request.url.path for request in toast.requests] == [LOGIN_PATH, MENUS_PATH]
        [menus] = toast.requests_to(MENUS_PATH)
        assert menus.headers["Authorization"] == "Bearer test-access-token"
        assert menus.headers["Toast-Restaurant-External-ID"] == RESTAURANT_GUID

    def test_reuses_the_token_for_later_requests(self, toast: FakeToast) -> None:
        toast.reply(MENUS_PATH, httpx2.Response(200, json={}))
        client = toast.adapter()._client

        client.get(MENUS_PATH)
        client.get(MENUS_PATH)

        assert len(toast.requests_to(LOGIN_PATH)) == 1

    def test_sends_query_parameters(self, toast: FakeToast) -> None:
        toast.reply(MENUS_PATH, httpx2.Response(200, json={}))

        toast.adapter()._client.get(MENUS_PATH, params={"page": 2})

        [menus] = toast.requests_to(MENUS_PATH)
        assert menus.url.params["page"] == "2"

    def test_reads_numbers_as_decimal(self, toast: FakeToast) -> None:
        toast.reply(MENUS_PATH, httpx2.Response(200, text='{"price": 1.10}'))

        body = toast.adapter()._client.get(MENUS_PATH)

        assert body == {"price": Decimal("1.10")}
        assert isinstance(body["price"], Decimal)

    def test_raises_with_status_code_on_error_response(self, toast: FakeToast) -> None:
        toast.reply(MENUS_PATH, httpx2.Response(503))

        with pytest.raises(ToastApiError) as error:
            toast.adapter()._client.get(MENUS_PATH)
        assert error.value.status_code == 503

    def test_raises_when_toast_cannot_be_reached(self, toast: FakeToast) -> None:
        toast.reply(MENUS_PATH, httpx2.ConnectError("connection refused"))

        with pytest.raises(ToastApiError, match="Could not reach Toast"):
            toast.adapter()._client.get(MENUS_PATH)

    def test_raises_on_invalid_json(self, toast: FakeToast) -> None:
        toast.reply(MENUS_PATH, httpx2.Response(200, text="<html>maintenance</html>"))

        with pytest.raises(ToastApiError, match="invalid JSON"):
            toast.adapter()._client.get(MENUS_PATH)


class TestSecrets:
    def test_credentials_hide_the_secret_when_printed(self) -> None:
        credentials = ToastCredentials(client_id="test-client-id", client_secret=CLIENT_SECRET)

        assert CLIENT_SECRET not in repr(credentials)
        assert CLIENT_SECRET not in str(credentials)

    def test_secret_and_token_are_never_logged(
        self, toast: FakeToast, caplog: pytest.LogCaptureFixture
    ) -> None:
        toast.reply(MENUS_PATH, httpx2.Response(500))
        adapter = toast.adapter()

        with caplog.at_level(logging.DEBUG):
            adapter.authenticate()
            with pytest.raises(ToastApiError):
                adapter._client.get(MENUS_PATH)

        assert caplog.text
        assert CLIENT_SECRET not in caplog.text
        assert "test-access-token" not in caplog.text

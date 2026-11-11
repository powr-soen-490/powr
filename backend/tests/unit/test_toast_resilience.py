# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Rate limits, server errors, network failures and expired tokens, against saved responses."""

import asyncio
import logging

import httpx2
import pytest

from app.integrations.pos.toast.client import (
    LOGIN_PATH,
    TOKEN_REFRESH_MARGIN_SECONDS,
    ToastApiError,
    ToastAuthenticationError,
    ToastClient,
    ToastCredentials,
    ToastRateLimitError,
)
from app.integrations.pos.toast.retry import RetryPolicy
from tests.unit.toast_fakes import (
    ACCESS_TOKEN,
    CLIENT_SECRET,
    FakeToast,
    load_fixture,
    load_response,
)

MENUS_PATH = "/menus/v2/menus"
TOKEN_LIFETIME_SECONDS = load_fixture("login_success.json")["token"]["expiresIn"]


@pytest.fixture
def toast() -> FakeToast:
    return FakeToast()


def client(toast: FakeToast, retry_policy: RetryPolicy | None = None) -> ToastClient:
    return toast.adapter(retry_policy)._client


def ok() -> httpx2.Response:
    return httpx2.Response(200, json={"ok": True})


class TestRateLimits:
    def test_waits_as_long_as_toast_asks_then_succeeds(self, toast: FakeToast) -> None:
        toast.reply(MENUS_PATH, load_response("rate_limited.json"), ok())

        assert client(toast).get(MENUS_PATH) == {"ok": True}

        assert len(toast.requests_to(MENUS_PATH)) == 2
        assert toast.sleeps == [1.0]

    def test_uses_rate_limit_reset_when_there_is_no_retry_after(self, toast: FakeToast) -> None:
        reset_in_five = httpx2.Response(
            429, headers={"X-Toast-RateLimit-Reset": str(int(toast.now) + 5)}
        )
        toast.reply(MENUS_PATH, reset_in_five, ok())

        client(toast).get(MENUS_PATH)

        assert toast.sleeps == [5.0]

    def test_reads_retry_after_given_as_an_http_date(self, toast: FakeToast) -> None:
        # FAKE_NOW is Thu, 01 Jan 2026 00:00:00 GMT.
        in_seven = httpx2.Response(429, headers={"Retry-After": "Thu, 01 Jan 2026 00:00:07 GMT"})
        toast.reply(MENUS_PATH, in_seven, ok())

        client(toast).get(MENUS_PATH)

        assert toast.sleeps == [7.0]

    def test_unreadable_retry_after_falls_back_to_rate_limit_reset(self, toast: FakeToast) -> None:
        unreadable = httpx2.Response(
            429,
            headers={
                "Retry-After": "soon",
                "X-Toast-RateLimit-Reset": str(int(toast.now) + 3),
            },
        )
        toast.reply(MENUS_PATH, unreadable, ok())

        client(toast).get(MENUS_PATH)

        assert toast.sleeps == [3.0]

    def test_raises_rate_limit_error_once_attempts_run_out(self, toast: FakeToast) -> None:
        toast.reply(MENUS_PATH, load_response("rate_limited.json"))

        with pytest.raises(ToastRateLimitError) as error:
            client(toast).get(MENUS_PATH)

        assert error.value.status_code == 429
        assert len(toast.requests_to(MENUS_PATH)) == RetryPolicy().max_attempts
        assert len(toast.sleeps) == RetryPolicy().max_attempts - 1

    def test_does_not_wait_longer_than_the_policy_allows(self, toast: FakeToast) -> None:
        fifteen_minutes = httpx2.Response(429, headers={"Retry-After": "900"})
        toast.reply(MENUS_PATH, fifteen_minutes)

        with pytest.raises(ToastRateLimitError) as error:
            client(toast).get(MENUS_PATH)

        assert len(toast.requests_to(MENUS_PATH)) == 1
        assert toast.sleeps == []
        assert error.value.retry_after_seconds == 900.0

    def test_backs_off_when_toast_gives_no_wait(self, toast: FakeToast) -> None:
        policy = RetryPolicy(max_attempts=3, base_delay_seconds=2.0)
        toast.reply(MENUS_PATH, httpx2.Response(429), httpx2.Response(429), ok())

        client(toast, policy).get(MENUS_PATH)

        first, second = toast.sleeps
        assert 0 <= first <= 2.0
        assert 0 <= second <= 4.0

    def test_login_is_retried_when_rate_limited(self, toast: FakeToast) -> None:
        toast.reply(
            LOGIN_PATH,
            load_response("rate_limited.json"),
            httpx2.Response(200, json=load_fixture("login_success.json")),
        )

        assert toast.adapter().authenticate() is True
        assert len(toast.requests_to(LOGIN_PATH)) == 2


class TestServerErrors:
    def test_retries_a_server_error_then_succeeds(self, toast: FakeToast) -> None:
        toast.reply(MENUS_PATH, load_response("service_unavailable.json"), ok())

        assert client(toast).get(MENUS_PATH) == {"ok": True}
        assert len(toast.sleeps) == 1

    def test_raises_with_status_once_attempts_run_out(self, toast: FakeToast) -> None:
        toast.reply(MENUS_PATH, load_response("service_unavailable.json"))

        with pytest.raises(ToastApiError) as error:
            client(toast).get(MENUS_PATH)

        assert error.value.status_code == 503
        assert len(toast.requests_to(MENUS_PATH)) == RetryPolicy().max_attempts

    @pytest.mark.parametrize("status", [400, 403, 404])
    def test_client_errors_are_not_retried(self, toast: FakeToast, status: int) -> None:
        toast.reply(MENUS_PATH, httpx2.Response(status))

        with pytest.raises(ToastApiError) as error:
            client(toast).get(MENUS_PATH)

        assert error.value.status_code == status
        assert len(toast.requests_to(MENUS_PATH)) == 1
        assert toast.sleeps == []


class TestNetworkErrors:
    @pytest.mark.parametrize(
        "failure", [httpx2.ConnectError("refused"), httpx2.ReadTimeout("timed out")]
    )
    def test_retries_a_network_failure_then_succeeds(
        self, toast: FakeToast, failure: Exception
    ) -> None:
        toast.reply(MENUS_PATH, failure, ok())

        assert client(toast).get(MENUS_PATH) == {"ok": True}
        assert len(toast.sleeps) == 1

    def test_raises_once_attempts_run_out(self, toast: FakeToast) -> None:
        toast.reply(MENUS_PATH, httpx2.ConnectError("refused"))

        with pytest.raises(ToastApiError, match="Could not reach Toast"):
            client(toast).get(MENUS_PATH)

        assert len(toast.requests_to(MENUS_PATH)) == RetryPolicy().max_attempts


class TestExpiredTokens:
    def test_logs_in_again_and_retries_when_the_token_is_rejected(self, toast: FakeToast) -> None:
        toast.reply(MENUS_PATH, load_response("token_expired.json"), ok())

        assert client(toast).get(MENUS_PATH) == {"ok": True}

        assert [request.url.path for request in toast.requests] == [
            LOGIN_PATH,
            MENUS_PATH,
            LOGIN_PATH,
            MENUS_PATH,
        ]

    def test_raises_when_a_fresh_token_is_rejected_too(self, toast: FakeToast) -> None:
        toast.reply(MENUS_PATH, load_response("token_expired.json"))

        with pytest.raises(ToastAuthenticationError):
            client(toast).get(MENUS_PATH)

        assert len(toast.requests_to(LOGIN_PATH)) == 2
        assert len(toast.requests_to(MENUS_PATH)) == 2

    def test_raises_when_credentials_are_rejected_on_the_new_login(self, toast: FakeToast) -> None:
        toast.reply(MENUS_PATH, load_response("token_expired.json"))
        toast_client = client(toast)
        toast_client.login()
        toast.reply(LOGIN_PATH, httpx2.Response(401))

        with pytest.raises(ToastAuthenticationError, match="rejected the credentials"):
            toast_client.get(MENUS_PATH)

    def test_rejected_credentials_are_not_retried(self, toast: FakeToast) -> None:
        toast.reply(LOGIN_PATH, httpx2.Response(401))

        assert toast.adapter().authenticate() is False
        assert len(toast.requests_to(LOGIN_PATH)) == 1

    def test_logs_in_again_shortly_before_the_token_expires(self, toast: FakeToast) -> None:
        toast.reply(MENUS_PATH, ok())
        toast_client = client(toast)
        toast_client.get(MENUS_PATH)

        toast.now += TOKEN_LIFETIME_SECONDS - TOKEN_REFRESH_MARGIN_SECONDS - 1
        toast_client.get(MENUS_PATH)
        assert len(toast.requests_to(LOGIN_PATH)) == 1

        toast.now += 1
        toast_client.get(MENUS_PATH)
        assert len(toast.requests_to(LOGIN_PATH)) == 2

    def test_keeps_the_token_when_toast_gives_no_lifetime(self, toast: FakeToast) -> None:
        login = load_fixture("login_success.json")
        del login["token"]["expiresIn"]
        toast.reply(LOGIN_PATH, httpx2.Response(200, json=login))
        toast.reply(MENUS_PATH, ok())
        toast_client = client(toast)

        toast_client.get(MENUS_PATH)
        toast.now += 10 * TOKEN_LIFETIME_SECONDS
        toast_client.get(MENUS_PATH)

        assert len(toast.requests_to(LOGIN_PATH)) == 1


class TestLogs:
    def test_each_retry_and_the_final_failure_are_logged(
        self, toast: FakeToast, caplog: pytest.LogCaptureFixture
    ) -> None:
        toast.reply(MENUS_PATH, load_response("rate_limited.json"))

        with caplog.at_level(logging.INFO), pytest.raises(ToastRateLimitError):
            client(toast).get(MENUS_PATH)

        retries = [r for r in caplog.records if "retrying in" in r.getMessage()]
        assert len(retries) == RetryPolicy().max_attempts - 1
        assert "HTTP 429 for GET /menus/v2/menus" in retries[0].getMessage()
        assert "attempt 2 of 4" in retries[0].getMessage()
        [give_up] = [r for r in caplog.records if "giving up" in r.getMessage()]
        assert give_up.levelno == logging.ERROR

    def test_no_secret_or_token_appears_in_retry_and_refresh_logs(
        self, toast: FakeToast, caplog: pytest.LogCaptureFixture
    ) -> None:
        toast.reply(
            MENUS_PATH,
            load_response("rate_limited.json"),
            httpx2.ConnectError("refused"),
            load_response("token_expired.json"),
            ok(),
        )

        with caplog.at_level(logging.DEBUG):
            client(toast).get(MENUS_PATH)

        assert "logging in again" in caplog.text
        assert CLIENT_SECRET not in caplog.text
        assert ACCESS_TOKEN not in caplog.text


class TestNoRealToastCalls:
    def test_a_real_toast_request_fails_the_test_run(self) -> None:
        credentials = ToastCredentials(client_id="test-client-id", client_secret=CLIENT_SECRET)
        real = ToastClient(credentials, "restaurant-guid", base_url="https://ws-api.toasttab.com")

        with pytest.raises(RuntimeError, match="must not call the real Toast API"):
            real.login()

    def test_a_real_async_toast_request_fails_the_test_run(self) -> None:
        async def call_toast() -> None:
            async with httpx2.AsyncClient() as http:
                await http.get("https://ws-api.toasttab.com/menus/v2/menus")

        with pytest.raises(RuntimeError, match="must not call the real Toast API"):
            asyncio.run(call_toast())


class TestRetryPolicy:
    def test_backoff_doubles_and_is_capped(self) -> None:
        policy = RetryPolicy(base_delay_seconds=1.0, max_wait_seconds=5.0)

        for failed_attempts, ceiling in [(1, 1.0), (2, 2.0), (3, 4.0), (4, 5.0), (10, 5.0)]:
            assert 0 <= policy.backoff_seconds(failed_attempts) <= ceiling

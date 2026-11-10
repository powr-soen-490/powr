# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Unit tests for app/core/security.py: password policy, Argon2id hashing, session tokens and
the failed-login rate limiter. No database or HTTP involved."""

import time
from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from argon2 import Type, extract_parameters
from itsdangerous import TimestampSigner

from app.core import security
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    clear_failed_logins,
    create_session_token,
    hash_password,
    is_login_rate_limited,
    record_failed_login,
    revoke_session_token,
    validate_password_policy,
    verify_password,
    verify_session_token,
)

VALID_PASSWORD = "Str0ng!Password"
SECRET = "unit-test-secret"
OTHER_SECRET = "another-secret"
USER_ID = "8f6c1a52-0d1e-4c3f-9a57-2b7f3c1e9d10"
RESTAURANT_ID = "1b2d3c4e-5f60-4718-8a9b-0c1d2e3f4a5b"

# OWASP minimums for Argon2id: 19 MiB of memory and 2 iterations.
OWASP_MIN_MEMORY_KIB = 19 * 1024
OWASP_MIN_TIME_COST = 2


# --- Password policy -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "password",
    [VALID_PASSWORD, "Aa1!aaaa", "Aa1!" + "a" * 124],
    ids=["typical", "shortest-allowed-8", "longest-allowed-128"],
)
def test_policy_accepts_passwords_that_meet_every_rule(password: str) -> None:
    validate_password_policy(password)


@pytest.mark.parametrize(
    ("password", "reason"),
    [
        ("Aa1!aaa", "at least 8 characters"),
        ("Aa1!" + "a" * 125, "must not exceed 128 characters"),
        ("str0ng!password", "uppercase letter"),
        ("STR0NG!PASSWORD", "lowercase letter"),
        ("Strong!Password", "number"),
        ("Str0ngPassword", "special character"),
        ("", "at least 8 characters"),
    ],
    ids=["7-chars", "129-chars", "no-uppercase", "no-lowercase", "no-digit", "no-special", "empty"],
)
def test_policy_rejects_passwords_that_break_a_rule(password: str, reason: str) -> None:
    with pytest.raises(ValueError, match=reason):
        validate_password_policy(password)


# --- Argon2id hashing ------------------------------------------------------------------------


def test_hash_is_argon2id_with_at_least_owasp_strength() -> None:
    parameters = extract_parameters(hash_password(VALID_PASSWORD))

    assert parameters.type is Type.ID
    assert parameters.memory_cost >= OWASP_MIN_MEMORY_KIB
    assert parameters.time_cost >= OWASP_MIN_TIME_COST


def test_hash_never_contains_the_password() -> None:
    assert VALID_PASSWORD not in hash_password(VALID_PASSWORD)


def test_same_password_hashes_differently_each_time() -> None:
    # A random salt per hash: equal passwords cannot be spotted by comparing hashes.
    assert hash_password(VALID_PASSWORD) != hash_password(VALID_PASSWORD)


def test_verify_accepts_the_right_password() -> None:
    assert verify_password(VALID_PASSWORD, hash_password(VALID_PASSWORD)) is True


@pytest.mark.parametrize(
    "attempt",
    ["Wr0ng!Password", "str0ng!password", VALID_PASSWORD + " ", ""],
    ids=["different", "different-case", "trailing-space", "empty"],
)
def test_verify_rejects_any_other_password(attempt: str) -> None:
    assert verify_password(attempt, hash_password(VALID_PASSWORD)) is False


@pytest.mark.parametrize("stored_hash", ["not-a-hash", "", "$argon2id$v=19$broken"])
def test_verify_returns_false_for_a_corrupt_stored_hash(stored_hash: str) -> None:
    assert verify_password(VALID_PASSWORD, stored_hash) is False


def test_dummy_hash_costs_as_much_as_a_real_one() -> None:
    # Login verifies against this hash for unknown emails, so both cases take the same time.
    dummy = extract_parameters(DUMMY_PASSWORD_HASH)
    real = extract_parameters(hash_password(VALID_PASSWORD))

    assert dummy == real
    assert verify_password(VALID_PASSWORD, DUMMY_PASSWORD_HASH) is False


# --- Session tokens --------------------------------------------------------------------------


def make_token(secret: str = SECRET) -> str:
    return create_session_token(USER_ID, RESTAURANT_ID, role="owner", secret_key=secret)


def verify(token: str, secret: str = SECRET) -> dict[str, object] | None:
    return verify_session_token(token, secret_key=secret, max_age=60)


def test_token_round_trips_user_restaurant_and_role() -> None:
    data = verify(make_token())

    assert data is not None
    assert (data["user_id"], data["restaurant_id"], data["role"]) == (
        USER_ID,
        RESTAURANT_ID,
        "owner",
    )


def test_every_token_is_unique() -> None:
    assert make_token() != make_token()


def test_token_signed_with_another_secret_is_rejected() -> None:
    assert verify(make_token(secret=OTHER_SECRET)) is None


def test_token_with_a_swapped_payload_is_rejected() -> None:
    # Tokens end in ".timestamp.signature"; a payload cannot be moved under another signature.
    forged = create_session_token(USER_ID, "another-restaurant", secret_key=SECRET)
    payload = forged.rsplit(".", 2)[0]
    _, timestamp, signature = make_token().rsplit(".", 2)

    assert verify(f"{payload}.{timestamp}.{signature}") is None


@pytest.mark.parametrize("token", ["", "garbage", "a.b.c"])
def test_malformed_token_is_rejected(token: str) -> None:
    assert verify(token) is None


def test_expired_token_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    token = make_token()
    an_hour_later = int(time.time()) + 3600
    monkeypatch.setattr(TimestampSigner, "get_timestamp", lambda _self: an_hour_later)

    assert verify(token) is None


def test_revoked_token_is_rejected() -> None:
    token = make_token()
    revoke_session_token(token)

    assert verify(token) is None
    assert verify(make_token()) is not None


# --- Failed-login rate limiter ---------------------------------------------------------------

MAX_ATTEMPTS = 5
WINDOW_SECONDS = 60
IP = "203.0.113.7"
EMAIL = "john@example.com"


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeClock]:
    fake = FakeClock()
    # Only the security module sees the fake clock; the real time module is untouched.
    monkeypatch.setattr(security, "time", SimpleNamespace(monotonic=fake.monotonic))
    security._failed_login_attempts.clear()
    yield fake
    security._failed_login_attempts.clear()


def fail(times: int, ip: str = IP, email: str = EMAIL) -> None:
    for _ in range(times):
        record_failed_login(ip, email, window_seconds=WINDOW_SECONDS)


def is_limited(ip: str = IP, email: str = EMAIL) -> bool:
    return is_login_rate_limited(
        ip, email, max_attempts=MAX_ATTEMPTS, window_seconds=WINDOW_SECONDS
    )


def test_allows_attempts_below_the_limit(clock: FakeClock) -> None:
    fail(MAX_ATTEMPTS - 1)
    assert not is_limited()


def test_blocks_once_the_limit_is_reached(clock: FakeClock) -> None:
    fail(MAX_ATTEMPTS)
    assert is_limited()


def test_failures_expire_after_the_window(clock: FakeClock) -> None:
    fail(MAX_ATTEMPTS)
    clock.now += WINDOW_SECONDS + 1

    assert not is_limited()


def test_limit_is_per_ip_and_email(clock: FakeClock) -> None:
    # Kitchen staff share one Wi-Fi: one person's typos must not lock out the others.
    fail(MAX_ATTEMPTS)

    assert not is_limited(ip="198.51.100.9")
    assert not is_limited(email="maria@example.com")


def test_email_case_and_spaces_do_not_bypass_the_limit(clock: FakeClock) -> None:
    fail(MAX_ATTEMPTS, email=" John@Example.com ")
    assert is_limited(email="john@example.com")


def test_successful_login_clears_the_failures(clock: FakeClock) -> None:
    fail(MAX_ATTEMPTS)
    clear_failed_logins(IP, EMAIL)

    assert not is_limited()

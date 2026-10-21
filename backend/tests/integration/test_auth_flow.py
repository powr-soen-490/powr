# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Integration tests for issue #44: the account rules of user story #38, through the real API
and a real database (sign-up, EULA, hashing at rest, cookies, generic errors, rate limit,
logout)."""

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.core import security
from app.core.config import Settings, get_settings

ClientFactory = Callable[[], TestClient]
SignUp = Callable[[TestClient, str], dict[str, Any]]

PASSWORD = "Str0ng!Password"
EMAIL = "john@example.com"


@pytest.fixture(autouse=True)
def fresh_rate_limiter() -> Iterator[None]:
    # The limiter lives in process memory, so one test's failures would leak into the next.
    security._failed_login_attempts.clear()
    yield
    security._failed_login_attempts.clear()


def signup_payload(**overrides: Any) -> dict[str, Any]:
    return {
        "restaurant_name": "Mykonos Grill",
        "email": EMAIL,
        "password": PASSWORD,
        "eula_accepted": True,
        **overrides,
    }


def count_users(engine: Engine) -> int:
    with engine.connect() as connection:
        return int(connection.execute(text("SELECT count(*) FROM users")).scalar_one())


# --- Sign-up ---------------------------------------------------------------------------------


def test_signup_creates_the_owner_and_signs_them_in(
    make_client: ClientFactory, migrated_engine: Engine
) -> None:
    client = make_client()

    response = client.post("/api/auth/signup", json=signup_payload())

    assert response.status_code == 201
    assert response.json()["role"] == "owner"
    me = client.get("/api/auth/me").json()
    assert (me["email"], me["restaurant_name"]) == (EMAIL, "Mykonos Grill")


def test_password_is_stored_as_an_argon2id_hash(
    make_client: ClientFactory, sign_up_owner: SignUp, migrated_engine: Engine
) -> None:
    sign_up_owner(make_client(), EMAIL)

    with migrated_engine.connect() as connection:
        stored = connection.execute(text("SELECT password_hash FROM users")).scalar_one()
    assert stored.startswith("$argon2id$")
    assert PASSWORD not in stored


def test_eula_acceptance_is_stored_with_version_and_time(
    make_client: ClientFactory, migrated_engine: Engine
) -> None:
    make_client().post("/api/auth/signup", json=signup_payload(eula_version="2.1"))

    with migrated_engine.connect() as connection:
        version, accepted_at = connection.execute(
            text("SELECT eula_version, accepted_at FROM eula_acceptances")
        ).one()
    assert version == "2.1"
    assert accepted_at.tzinfo is not None


def test_signup_is_blocked_until_the_eula_is_accepted(
    make_client: ClientFactory, migrated_engine: Engine
) -> None:
    response = make_client().post("/api/auth/signup", json=signup_payload(eula_accepted=False))

    assert response.status_code == 400
    assert "EULA" in response.json()["detail"]
    assert count_users(migrated_engine) == 0


def test_password_policy_is_enforced_by_the_server(
    make_client: ClientFactory, migrated_engine: Engine
) -> None:
    # Sent straight to the API: a client that skips the form's checks is still refused.
    response = make_client().post("/api/auth/signup", json=signup_payload(password="password"))

    assert response.status_code == 400
    assert "Password must" in response.json()["detail"]
    assert count_users(migrated_engine) == 0


def test_duplicate_email_is_refused_without_saying_why(
    make_client: ClientFactory, sign_up_owner: SignUp
) -> None:
    sign_up_owner(make_client(), EMAIL)

    response = make_client().post("/api/auth/signup", json=signup_payload(email="JOHN@example.com"))

    assert response.status_code == 409
    assert "exist" not in response.json()["detail"].lower()


# --- Session cookie --------------------------------------------------------------------------


def test_session_cookie_is_httponly_and_samesite(make_client: ClientFactory) -> None:
    response = make_client().post("/api/auth/signup", json=signup_payload())

    cookie = response.headers["set-cookie"].lower()
    assert cookie.startswith(f"{get_settings().session_cookie_name}=")
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "path=/" in cookie


def test_session_cookie_is_secure_when_configured(
    make_client: ClientFactory, api_app: FastAPI, migrated_engine: Engine
) -> None:
    url = migrated_engine.url.render_as_string(hide_password=False)
    production_like = Settings(_env_file=None, database_url=url, cookie_secure=True)
    api_app.dependency_overrides[get_settings] = lambda: production_like

    response = make_client().post("/api/auth/signup", json=signup_payload())

    assert "; secure" in response.headers["set-cookie"].lower()


# --- Login -----------------------------------------------------------------------------------


def test_owner_can_log_back_in(make_client: ClientFactory, sign_up_owner: SignUp) -> None:
    restaurant_id = sign_up_owner(make_client(), EMAIL)["restaurant_id"]
    client = make_client()

    response = client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})

    assert response.status_code == 200
    assert client.get("/api/auth/me").json()["restaurant_id"] == restaurant_id


def test_login_errors_do_not_reveal_whether_the_email_exists(
    make_client: ClientFactory, sign_up_owner: SignUp
) -> None:
    sign_up_owner(make_client(), EMAIL)
    client = make_client()

    wrong_password = client.post("/api/auth/login", json={"email": EMAIL, "password": "Wr0ng!pw"})
    unknown_email = client.post(
        "/api/auth/login", json={"email": "nobody@example.com", "password": PASSWORD}
    )

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


def test_repeated_failed_logins_are_rate_limited(
    make_client: ClientFactory, sign_up_owner: SignUp
) -> None:
    sign_up_owner(make_client(), EMAIL)
    client = make_client()
    for _ in range(get_settings().login_max_failed_attempts):
        client.post("/api/auth/login", json={"email": EMAIL, "password": "Wr0ng!pw"})

    # Even the right password is refused while the limit is active.
    response = client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})

    assert response.status_code == 429


# --- Logout ----------------------------------------------------------------------------------


def test_logout_ends_the_session_even_if_the_cookie_is_replayed(
    make_client: ClientFactory, sign_up_owner: SignUp
) -> None:
    client = make_client()
    sign_up_owner(client, EMAIL)
    cookie_name = get_settings().session_cookie_name
    stolen_token = client.cookies[cookie_name]

    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401

    replay = make_client()
    replay.cookies.set(cookie_name, stolen_token)
    assert replay.get("/api/auth/me").status_code == 401

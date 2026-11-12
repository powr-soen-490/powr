# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""POS HTTP contracts with real session authentication and a stubbed database."""

import base64
from datetime import UTC, datetime
from typing import Any
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Response
from itsdangerous import TimestampSigner
from pydantic import PostgresDsn, SecretStr
from pydantic_settings import SettingsConfigDict
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core import encryption
from app.core.auth import CurrentUser
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.security import create_session_token, revoke_session_token

ENDPOINT = "/api/pos/credentials"
ENDPOINTS = [
    ("POST", ENDPOINT),
    ("GET", f"{ENDPOINT}?pos_name=TOAST"),
    ("GET", f"{ENDPOINT}/all"),
    ("PATCH", ENDPOINT),
    ("DELETE", f"{ENDPOINT}?pos_name=TOAST"),
]
PAYLOAD = {
    "pos_name": "TOAST",
    "client_id": "test-client",
    "client_secret": "test-secret",
    "access_token": "test-token",
    "expires_at": "2026-10-26T12:00:00Z",
}
EXPIRY = datetime(2026, 10, 26, 12, tzinfo=UTC)


class PosRequestTestSettings(Settings):
    """Prevent request tests from depending on local credentials or encryption keys."""

    model_config = SettingsConfigDict(env_file=None)


@pytest.fixture
def settings() -> Settings:
    return PosRequestTestSettings(
        database_url=PostgresDsn("postgresql://powr:powr@localhost/powr_test"),
        pos_credentials_encryption_key=SecretStr(
            base64.urlsafe_b64encode(bytes(range(32))).decode()
        ),
    )


@pytest.fixture
def db(app: FastAPI, settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Mock:
    session = Mock(spec=Session)
    session.execute.return_value.first.return_value = None
    session.execute.return_value.fetchone.return_value = None
    session.execute.return_value.mappings.return_value.first.return_value = None
    session.execute.return_value.mappings.return_value.all.return_value = []
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_settings] = lambda: settings
    monkeypatch.setattr(encryption, "get_settings", lambda: settings)
    return session


def session_token(settings: Settings, user: CurrentUser | None = None) -> str:
    # Claiming owner in a signed token must never override a current database role.
    return create_session_token(
        str(user.user_id if user else uuid4()),
        str(user.restaurant_id if user else uuid4()),
        role="owner",
        secret_key=settings.session_secret_key,
    )


def authenticate(
    client: TestClient, settings: Settings, db: Mock, role: str = "owner"
) -> CurrentUser:
    user = CurrentUser(uuid4(), "member@example.com", uuid4(), "Test restaurant", role)
    db.execute.return_value.first.return_value = user
    client.cookies.set(settings.session_cookie_name, session_token(settings, user))
    return user


@pytest.fixture
def owner_client(client: TestClient, settings: Settings, db: Mock) -> TestClient:
    authenticate(client, settings, db)
    return client


def request(client: TestClient, method: str, path: str) -> Response:
    if method in {"POST", "PATCH"}:
        return client.request(method, path, json=PAYLOAD)
    return client.request(method, path)


def stored_credentials() -> dict[str, Any]:
    return {
        "id": uuid4(),
        "pos_name": "TOAST",
        "client_id": "test-client",
        "client_secret": encryption.encrypt_secret(
            "test-secret", context="pos_credentials:TOAST:client_secret"
        ),
        "access_token": encryption.encrypt_secret(
            "test-token", context="pos_credentials:TOAST:access_token"
        ),
        "expires_at": EXPIRY,
    }


@pytest.mark.parametrize("method, path", ENDPOINTS)
@pytest.mark.parametrize("cookie_state", ["missing", "tampered", "expired", "revoked"])
def test_invalid_sessions_cannot_access_credentials(
    client: TestClient,
    settings: Settings,
    db: Mock,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    cookie_state: str,
) -> None:
    if cookie_state == "tampered":
        client.cookies.set(settings.session_cookie_name, "not-a-valid-token")
    elif cookie_state == "expired":
        with monkeypatch.context() as patch:
            patch.setattr(TimestampSigner, "get_timestamp", lambda self: 0)
            token = session_token(settings)
        client.cookies.set(settings.session_cookie_name, token)
    elif cookie_state == "revoked":
        token = session_token(settings)
        revoke_session_token(token)
        client.cookies.set(settings.session_cookie_name, token)

    response = request(client, method, path)

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated."}
    db.execute.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.parametrize("method, path", ENDPOINTS)
def test_removed_membership_cannot_access_credentials(
    client: TestClient, settings: Settings, db: Mock, method: str, path: str
) -> None:
    client.cookies.set(settings.session_cookie_name, session_token(settings))

    response = request(client, method, path)

    assert response.status_code == 401
    assert db.execute.call_count == 1
    db.commit.assert_not_called()


@pytest.mark.parametrize("method, path", ENDPOINTS)
def test_database_role_overrides_owner_claim_in_cookie(
    client: TestClient, settings: Settings, db: Mock, method: str, path: str
) -> None:
    user = authenticate(client, settings, db, role="kitchen_manager")

    response = request(client, method, path)

    assert response.status_code == 403
    assert response.json() == {"detail": "You do not have permission to do this."}
    assert db.execute.call_args.args[1] == {
        "user_id": user.user_id,
        "restaurant_id": user.restaurant_id,
    }
    assert db.execute.call_count == 1
    db.commit.assert_not_called()


@pytest.mark.parametrize("method, path", ENDPOINTS)
def test_logged_out_cookie_cannot_be_replayed(
    client: TestClient, settings: Settings, db: Mock, method: str, path: str
) -> None:
    token = session_token(settings)
    client.cookies.set(settings.session_cookie_name, token)
    assert client.post("/api/auth/logout").status_code == 200
    client.cookies.set(settings.session_cookie_name, token)

    assert request(client, method, path).status_code == 401
    db.execute.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.parametrize(
    "method, message",
    [
        ("POST", "POS credentials set successfully."),
        ("PATCH", "POS credentials updated successfully."),
    ],
)
def test_owner_writes_encrypt_secrets(
    owner_client: TestClient, db: Mock, method: str, message: str
) -> None:
    db.execute.return_value.fetchone.return_value = None if method == "POST" else (uuid4(),)

    response = request(owner_client, method, ENDPOINT)

    assert response.status_code == 200
    assert response.json() == {"message": message}
    written = db.execute.call_args.args[1]
    assert written["pos_name"] == "TOAST" and written["client_id"] == "test-client"
    assert written["expires_at"] == EXPIRY
    for field in ("client_secret", "access_token"):
        assert written[field] != PAYLOAD[field]
        assert (
            encryption.decrypt_secret(written[field], context=f"pos_credentials:TOAST:{field}")
            == PAYLOAD[field]
        )
        assert PAYLOAD[field] not in response.text
    db.commit.assert_called_once_with()
    db.rollback.assert_not_called()


def test_owner_get_returns_metadata_without_secrets(owner_client: TestClient, db: Mock) -> None:
    row = stored_credentials()
    db.execute.return_value.mappings.return_value.first.return_value = row

    response = owner_client.get(ENDPOINT, params={"pos_name": "TOAST"})

    assert response.status_code == 200
    assert response.json() == {
        "id": str(row["id"]),
        "pos_name": "TOAST",
        "client_id": "test-client",
        "expires_at": PAYLOAD["expires_at"],
    }
    db.commit.assert_not_called()


@pytest.mark.parametrize("empty", [False, True])
def test_owner_list_returns_all_metadata_or_empty_list(
    owner_client: TestClient, db: Mock, empty: bool
) -> None:
    row = stored_credentials()
    db.execute.return_value.mappings.return_value.all.return_value = [] if empty else [row]

    response = owner_client.get(f"{ENDPOINT}/all")

    assert response.status_code == 200
    assert response.json() == (
        []
        if empty
        else [
            {
                "id": str(row["id"]),
                "pos_name": "TOAST",
                "client_id": "test-client",
                "expires_at": PAYLOAD["expires_at"],
            }
        ]
    )
    db.commit.assert_not_called()


def test_owner_can_delete_credentials(owner_client: TestClient, db: Mock) -> None:
    db.execute.return_value.fetchone.return_value = (uuid4(),)

    response = owner_client.delete(ENDPOINT, params={"pos_name": "TOAST"})

    assert response.status_code == 200
    assert response.json() == {"message": "POS credentials deleted successfully."}
    assert db.execute.call_args.args[1] == {"pos_name": "TOAST"}
    db.commit.assert_called_once_with()


@pytest.mark.parametrize("method", ["GET", "PATCH", "DELETE"])
def test_missing_provider_returns_404(owner_client: TestClient, db: Mock, method: str) -> None:
    response = request(owner_client, method, f"{ENDPOINT}?pos_name=TOAST")

    assert response.status_code == 404
    assert response.json() == {"detail": "POS credentials not found for this provider."}
    assert db.execute.call_count == 2
    db.commit.assert_not_called()


def test_duplicate_provider_returns_400_without_writing(owner_client: TestClient, db: Mock) -> None:
    db.execute.return_value.fetchone.return_value = (uuid4(),)

    response = owner_client.post(ENDPOINT, json=PAYLOAD)

    assert response.status_code == 400
    assert response.json() == {"detail": "POS credentials already exist for this provider."}
    assert db.execute.call_count == 2
    db.commit.assert_not_called()
    db.rollback.assert_called_once_with()


@pytest.mark.parametrize("method", ["POST", "PATCH"])
@pytest.mark.parametrize(
    "field, value",
    [
        ("pos_name", "toast"),
        ("pos_name", "UNKNOWN"),
        ("client_id", ""),
        ("client_secret", ""),
        ("access_token", ""),
        ("expires_at", "not-a-date"),
    ],
)
def test_invalid_write_requests_return_422(
    owner_client: TestClient, db: Mock, method: str, field: str, value: str
) -> None:
    response = owner_client.request(method, ENDPOINT, json={**PAYLOAD, field: value})

    assert response.status_code == 422
    db.commit.assert_not_called()
    assert db.execute.call_count == 1


@pytest.mark.parametrize("params", [{}, {"pos_name": "UNKNOWN"}])
def test_single_provider_query_is_validated(
    owner_client: TestClient, db: Mock, params: dict[str, str]
) -> None:
    assert owner_client.get(ENDPOINT, params=params).status_code == 422
    db.commit.assert_not_called()
    assert db.execute.call_count == 1


@pytest.mark.parametrize("method, path", ENDPOINTS)
def test_database_errors_return_safe_500_and_rollback(
    owner_client: TestClient, db: Mock, method: str, path: str
) -> None:
    db.execute.side_effect = [
        db.execute.return_value,
        SQLAlchemyError("private database details"),
    ]

    response = request(owner_client, method, path)

    assert response.status_code == 500
    assert "private" not in response.text
    assert "test-secret" not in response.text
    db.rollback.assert_called_once_with()
    db.commit.assert_not_called()


@pytest.mark.parametrize("method", ["POST", "PATCH"])
@pytest.mark.parametrize("stage", ["write", "commit"])
def test_integrity_errors_return_safe_400_and_rollback(
    owner_client: TestClient, db: Mock, method: str, stage: str
) -> None:
    db.execute.return_value.fetchone.return_value = None if method == "POST" else (uuid4(),)
    error = IntegrityError("INSERT/UPDATE", {}, Exception("private constraint details"))
    if stage == "write":
        db.execute.side_effect = [db.execute.return_value, db.execute.return_value, error]
    else:
        db.commit.side_effect = error

    response = request(owner_client, method, ENDPOINT)

    assert response.status_code == 400
    assert "private" not in response.text
    db.rollback.assert_called_once_with()
    if stage == "write":
        db.commit.assert_not_called()


@pytest.mark.parametrize("method", ["POST", "PATCH"])
def test_missing_encryption_key_prevents_writes(
    owner_client: TestClient, db: Mock, settings: Settings, method: str
) -> None:
    db.execute.return_value.fetchone.return_value = None if method == "POST" else (uuid4(),)
    settings.pos_credentials_encryption_key = None

    response = request(owner_client, method, ENDPOINT)

    assert response.status_code == 500
    assert db.execute.call_count == 2
    db.commit.assert_not_called()
    db.rollback.assert_called_once_with()


@pytest.mark.parametrize("value", ["plaintext-secret", "aes256gcm:v1:AAAA"])
def test_unverified_secrets_are_not_returned_by_get(
    owner_client: TestClient, db: Mock, value: str
) -> None:
    row = stored_credentials()
    row["client_secret"] = value
    db.execute.return_value.mappings.return_value.first.return_value = row

    response = owner_client.get(ENDPOINT, params={"pos_name": "TOAST"})

    assert response.status_code == 500
    assert value not in response.text
    db.rollback.assert_called_once_with()


def test_openapi_has_dedicated_read_models_and_no_list_request_body(app: FastAPI) -> None:
    schema = app.openapi()
    listing = schema["paths"][f"{ENDPOINT}/all"]["get"]
    assert "requestBody" not in listing and not listing.get("parameters")
    response = listing["responses"]["200"]["content"]["application/json"]["schema"]
    assert response["type"] == "array"
    assert response["items"]["$ref"].endswith("/PosCredentialsResponse")
    fields = schema["components"]["schemas"]["PosCredentialsResponse"]["properties"]
    assert set(fields) == {"id", "pos_name", "client_id", "expires_at"}

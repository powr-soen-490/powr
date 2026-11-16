# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Unit tests for the invite service (issue #42): tokens, request checks and database errors."""

from collections.abc import Callable
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_owner
from app.core.database import get_db
from app.modules.invites.service import (
    InvitePolicyError,
    InviteStorageError,
    accept_invite,
    create_invite,
    generate_invite_token,
    hash_invite_token,
    revoke_invite,
)


def test_tokens_are_long_url_safe_and_unique() -> None:
    tokens = {generate_invite_token() for _ in range(100)}
    assert len(tokens) == 100
    for token in tokens:
        # 32 random bytes encode to 43 URL-safe base64 characters.
        assert len(token) >= 43
        assert all(ch.isalnum() or ch in "-_" for ch in token)


def test_hash_is_sha256_hex_and_never_the_token_itself() -> None:
    token = generate_invite_token()
    digest = hash_invite_token(token)
    assert len(digest) == 64
    assert digest != token
    assert hash_invite_token(token) == digest
    assert hash_invite_token(token + "x") != digest


def test_accept_refuses_missing_eula_before_touching_the_database() -> None:
    # db=None: the check must fail before any query is made.
    with pytest.raises(InvitePolicyError, match="EULA"):
        accept_invite(
            None,  # type: ignore[arg-type]
            token="t",
            password="Str0ng!Password",
            eula_accepted=False,
            eula_version="1.0",
        )


def test_accept_refuses_weak_password_before_touching_the_database() -> None:
    with pytest.raises(InvitePolicyError, match="at least 8 characters"):
        accept_invite(
            None,  # type: ignore[arg-type]
            token="t",
            password="short",
            eula_accepted=True,
            eula_version="1.0",
        )


class BrokenSession:
    """A database session whose every query fails, as if PostgreSQL went down."""

    def __init__(self) -> None:
        self.rolled_back = False

    def execute(self, *args: object, **kwargs: object) -> None:
        raise OperationalError("SELECT 1", {}, Exception("database is down"))

    def rollback(self) -> None:
        self.rolled_back = True


def test_database_failures_become_storage_errors_and_roll_back() -> None:
    calls: list[Callable[[Session], object]] = [
        lambda db: create_invite(db, restaurant_id=uuid4(), email="marco@example.com"),
        lambda db: revoke_invite(db, restaurant_id=uuid4(), invite_id=uuid4()),
        lambda db: accept_invite(
            db, token="t", password="Str0ng!Password", eula_accepted=True, eula_version="1.0"
        ),
    ]
    for call in calls:
        db = BrokenSession()
        with pytest.raises(InviteStorageError):
            call(db)  # type: ignore[arg-type]
        assert db.rolled_back


def test_api_returns_500_when_the_database_fails(app: FastAPI) -> None:
    owner = CurrentUser(
        user_id=uuid4(),
        email="john@example.com",
        restaurant_id=uuid4(),
        restaurant_name="Mykonos Grill",
        role="owner",
    )
    app.dependency_overrides[get_db] = BrokenSession
    app.dependency_overrides[require_owner] = lambda: owner
    with TestClient(app) as client:
        responses = [
            client.post("/api/invites", json={"email": "marco@example.com"}),
            client.delete(f"/api/invites/{uuid4()}"),
            client.post(
                "/api/invites/accept",
                json={"token": "t", "password": "Str0ng!Password", "eula_accepted": True},
            ),
        ]
    for response in responses:
        assert response.status_code == 500
        assert response.json()["detail"] == "Could not process the invite. Try again."

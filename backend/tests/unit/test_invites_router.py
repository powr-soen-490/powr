# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Unit tests for the invite endpoints (issue #42), with the database and service stubbed."""

from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.auth import CurrentUser, require_owner
from app.core.database import get_db
from app.modules.invites import service

OWNER = CurrentUser(uuid4(), "john@example.com", uuid4(), "Mykonos Grill", "owner")


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[require_owner] = lambda: OWNER
    with TestClient(app) as test_client:
        yield test_client


def fail_with(error: Exception) -> object:
    def stub(*_args: object, **_kwargs: object) -> None:
        raise error

    return stub


def test_create_returns_the_link(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    invite = service.CreatedInvite(
        uuid4(), "marco@example.com", "kitchen_manager", datetime.now(UTC), "abc"
    )
    monkeypatch.setattr(service, "create_invite", lambda *_a, **_k: invite)
    response = client.post("/api/invites", json={"email": "marco@example.com"})
    assert response.status_code == 201
    assert response.json()["accept_path"] == "/accept-invite?token=abc"


def test_create_for_existing_account_is_409(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service, "create_invite", fail_with(service.AccountAlreadyExistsError()))
    assert client.post("/api/invites", json={"email": "marco@example.com"}).status_code == 409


def test_revoke(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "revoke_invite", lambda *_a, **_k: None)
    assert client.delete(f"/api/invites/{uuid4()}").status_code == 200
    monkeypatch.setattr(service, "revoke_invite", fail_with(service.InviteNotFoundError()))
    assert client.delete(f"/api/invites/{uuid4()}").status_code == 404


def test_accept_creates_the_account(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    accepted = service.AcceptedInvite(uuid4(), uuid4(), "marco@example.com", "kitchen_manager")
    monkeypatch.setattr(service, "accept_invite", lambda *_a, **_k: accepted)
    response = client.post(
        "/api/invites/accept",
        json={"token": "abc", "password": "Str0ng!Password", "eula_accepted": True},
    )
    assert response.status_code == 201
    assert response.json()["role"] == "kitchen_manager"


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (service.InvitePolicyError("EULA acceptance is required."), 400),
        (service.InvalidInviteError(), 400),
        (service.AccountAlreadyExistsError(), 409),
    ],
)
def test_accept_errors(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, error: Exception, status_code: int
) -> None:
    monkeypatch.setattr(service, "accept_invite", fail_with(error))
    response = client.post(
        "/api/invites/accept",
        json={"token": "abc", "password": "Str0ng!Password", "eula_accepted": True},
    )
    assert response.status_code == status_code
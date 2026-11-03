# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Integration tests for issue #41: the current-user dependency and the owner guard.

Each test runs in a throwaway database on the DATABASE_URL server and signs up real accounts
through /api/auth/signup. Skipped when that user cannot create databases.
"""

from collections.abc import Callable, Iterator

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.core.auth import CurrentUserDep, OwnerDep
from app.core.config import Settings, get_settings
from app.core.database import migrate_up
from app.core.security import create_session_token
from app.main import create_app

PASSWORD = "Str0ng!Password"
ClientFactory = Callable[[], TestClient]

# Test-only routes that stand in for real restaurant endpoints.
probe = APIRouter(prefix="/probe")


@probe.get("/me")
def whoami(user: CurrentUserDep) -> dict[str, str]:
    return {"restaurant_id": str(user.restaurant_id), "role": user.role}


@probe.post("/owner-only")
def owner_only(user: OwnerDep, body: dict[str, str] | None = None) -> dict[str, str]:
    return {"restaurant_id": str(user.restaurant_id)}


@pytest.fixture
def engine(scratch_engine: Engine) -> Engine:
    migrate_up(scratch_engine)
    return scratch_engine


@pytest.fixture
def new_client(engine: Engine) -> Iterator[Callable[[], TestClient]]:
    url = engine.url.render_as_string(hide_password=False)
    app = create_app(Settings(_env_file=None, database_url=url))
    app.include_router(probe)
    clients: list[TestClient] = []

    def make() -> TestClient:
        client = TestClient(app)
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.close()


def sign_up(client: TestClient, email: str) -> str:
    response = client.post(
        "/api/auth/signup",
        json={
            "restaurant_name": f"Restaurant of {email}",
            "email": email,
            "password": PASSWORD,
            "eula_accepted": True,
        },
    )
    assert response.status_code == 201, response.text
    restaurant_id: str = response.json()["restaurant_id"]
    return restaurant_id


def test_requests_without_a_session_get_401(new_client: ClientFactory) -> None:
    response = new_client().get("/probe/me")
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated."}


def test_tampered_session_cookie_gets_401(new_client: ClientFactory) -> None:
    client = new_client()
    client.cookies.set(get_settings().session_cookie_name, "not-a-real-token")
    assert client.get("/probe/me").status_code == 401


def test_signed_in_owner_gets_their_restaurant(new_client: ClientFactory) -> None:
    client = new_client()
    restaurant_id = sign_up(client, "john@example.com")

    assert client.get("/probe/me").json() == {"restaurant_id": restaurant_id, "role": "owner"}
    assert client.post("/probe/owner-only").status_code == 200
    assert client.get("/api/auth/me").json()["email"] == "john@example.com"


def test_restaurant_comes_from_the_session_not_the_request(new_client: ClientFactory) -> None:
    john, maria = new_client(), new_client()
    johns_restaurant = sign_up(john, "john@example.com")
    marias_restaurant = sign_up(maria, "maria@example.com")

    response = john.post("/probe/owner-only", json={"restaurant_id": marias_restaurant})

    assert response.json() == {"restaurant_id": johns_restaurant}


def test_kitchen_manager_is_refused_owner_only_routes(
    new_client: ClientFactory, engine: Engine
) -> None:
    restaurant_id = sign_up(new_client(), "john@example.com")
    with engine.begin() as connection:
        manager_id = connection.execute(
            text(
                "INSERT INTO users (email, password_hash) "
                "VALUES ('kim@example.com', 'x') RETURNING id"
            )
        ).scalar_one()
        connection.execute(
            text(
                "INSERT INTO restaurant_memberships (user_id, restaurant_id, role) "
                "VALUES (:user_id, :restaurant_id, 'kitchen_manager')"
            ),
            {"user_id": manager_id, "restaurant_id": restaurant_id},
        )
    manager = new_client()
    # Even a token that claims "owner" is refused: the role comes from the database.
    token = create_session_token(str(manager_id), restaurant_id, role="owner")
    manager.cookies.set(get_settings().session_cookie_name, token)

    assert manager.get("/probe/me").json()["role"] == "kitchen_manager"
    response = manager.post("/probe/owner-only")
    assert response.status_code == 403
    assert response.json() == {"detail": "You do not have permission to do this."}


def test_removed_membership_loses_access(new_client: ClientFactory, engine: Engine) -> None:
    client = new_client()
    sign_up(client, "john@example.com")
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM restaurant_memberships"))

    assert client.get("/probe/me").status_code == 401

# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Integration tests for issue #42: create, accept, expire and revoke invite links.

Each test runs in a throwaway database on the DATABASE_URL server and goes through the real API.
"""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.modules.invites.service import hash_invite_token
from tests.conftest import TEST_PASSWORD

ClientFactory = Callable[[], TestClient]
SignUp = Callable[[TestClient, str], dict[str, Any]]

MANAGER_PASSWORD = "Kitch3n!Manager"


def create_invite(owner: TestClient, email: str) -> dict[str, Any]:
    response = owner.post("/api/invites", json={"email": email})
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def accept(client: TestClient, token: str, **overrides: Any) -> Any:
    payload = {
        "token": token,
        "password": MANAGER_PASSWORD,
        "eula_accepted": True,
        **overrides,
    }
    return client.post("/api/invites/accept", json=payload)


def test_owner_creates_an_invite_that_expires_in_72_hours(
    make_client: ClientFactory, sign_up_owner: SignUp, migrated_engine: Engine
) -> None:
    owner = make_client()
    sign_up_owner(owner, "john@mykonos.example.com")

    invite = create_invite(owner, "Marco@Mykonos.example.com")

    assert invite["email"] == "marco@mykonos.example.com"
    assert invite["role"] == "kitchen_manager"
    assert invite["accept_path"].startswith("/accept-invite?token=")
    with migrated_engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT token_hash, expires_at - created_at AS valid_for FROM invites "
                "WHERE id = :id"
            ),
            {"id": invite["invite_id"]},
        ).one()
    # Only the hash is stored, never the token itself.
    assert row.token_hash == hash_invite_token(invite["token"])
    assert row.token_hash != invite["token"]
    assert abs(row.valid_for.total_seconds() - 72 * 3600) < 60


def test_accepting_creates_a_kitchen_manager_who_can_log_in(
    make_client: ClientFactory, sign_up_owner: SignUp, migrated_engine: Engine
) -> None:
    owner = make_client()
    restaurant_id = sign_up_owner(owner, "john@mykonos.example.com")["restaurant_id"]
    invite = create_invite(owner, "marco@mykonos.example.com")

    response = accept(make_client(), invite["token"])
    assert response.status_code == 201, response.text
    assert response.json()["role"] == "kitchen_manager"
    assert response.json()["restaurant_id"] == restaurant_id

    manager = make_client()
    login = manager.post(
        "/api/auth/login", json={"email": "marco@mykonos.example.com", "password": MANAGER_PASSWORD}
    )
    assert login.status_code == 200, login.text
    assert login.json()["role"] == "kitchen_manager"
    assert login.json()["restaurant_id"] == restaurant_id

    with migrated_engine.connect() as connection:
        eula = connection.execute(
            text(
                "SELECT COUNT(*) FROM eula_acceptances e JOIN users u ON u.id = e.user_id "
                "WHERE u.email = 'marco@mykonos.example.com'"
            )
        ).scalar_one()
    assert eula == 1


def test_a_link_works_only_once(make_client: ClientFactory, sign_up_owner: SignUp) -> None:
    owner = make_client()
    sign_up_owner(owner, "john@mykonos.example.com")
    invite = create_invite(owner, "marco@mykonos.example.com")

    assert accept(make_client(), invite["token"]).status_code == 201
    second = accept(make_client(), invite["token"], password="An0ther!Password")
    assert second.status_code == 400
    assert second.json()["detail"] == "This invite link is invalid, expired or already used."


def test_an_expired_link_is_refused(
    make_client: ClientFactory, sign_up_owner: SignUp, migrated_engine: Engine
) -> None:
    owner = make_client()
    sign_up_owner(owner, "john@mykonos.example.com")
    invite = create_invite(owner, "marco@mykonos.example.com")
    with migrated_engine.begin() as connection:
        connection.execute(
            text("UPDATE invites SET expires_at = NOW() - INTERVAL '1 minute' WHERE id = :id"),
            {"id": invite["invite_id"]},
        )

    assert accept(make_client(), invite["token"]).status_code == 400


def test_an_unknown_link_is_refused(make_client: ClientFactory) -> None:
    assert accept(make_client(), "not-a-real-token").status_code == 400


def test_owner_revokes_a_pending_invite(make_client: ClientFactory, sign_up_owner: SignUp) -> None:
    owner = make_client()
    sign_up_owner(owner, "john@mykonos.example.com")
    invite = create_invite(owner, "marco@mykonos.example.com")

    revoke = owner.delete(f"/api/invites/{invite['invite_id']}")
    assert revoke.status_code == 200, revoke.text
    assert accept(make_client(), invite["token"]).status_code == 400
    # Revoking twice: there is no pending invite left.
    assert owner.delete(f"/api/invites/{invite['invite_id']}").status_code == 404


def test_a_new_invite_replaces_the_previous_link(
    make_client: ClientFactory, sign_up_owner: SignUp
) -> None:
    owner = make_client()
    sign_up_owner(owner, "john@mykonos.example.com")
    first = create_invite(owner, "marco@mykonos.example.com")
    second = create_invite(owner, "marco@mykonos.example.com")

    assert accept(make_client(), first["token"]).status_code == 400
    assert accept(make_client(), second["token"]).status_code == 201


def test_owner_cannot_revoke_another_restaurants_invite(
    make_client: ClientFactory, sign_up_owner: SignUp
) -> None:
    owner_a = make_client()
    sign_up_owner(owner_a, "a@restaurant-a.example.com")
    invite = create_invite(owner_a, "marco@restaurant-a.example.com")

    owner_b = make_client()
    sign_up_owner(owner_b, "b@restaurant-b.example.com")
    assert owner_b.delete(f"/api/invites/{invite['invite_id']}").status_code == 404
    # The invite still works for restaurant A.
    assert accept(make_client(), invite["token"]).status_code == 201


def test_kitchen_manager_cannot_create_or_revoke_invites(
    make_client: ClientFactory, sign_up_owner: SignUp
) -> None:
    owner = make_client()
    sign_up_owner(owner, "john@mykonos.example.com")
    invite = create_invite(owner, "marco@mykonos.example.com")
    pending = create_invite(owner, "sofia@mykonos.example.com")
    assert accept(make_client(), invite["token"]).status_code == 201

    manager = make_client()
    manager.post(
        "/api/auth/login", json={"email": "marco@mykonos.example.com", "password": MANAGER_PASSWORD}
    )
    assert manager.post("/api/invites", json={"email": "x@mykonos.example.com"}).status_code == 403
    assert manager.delete(f"/api/invites/{pending['invite_id']}").status_code == 403


def test_creating_an_invite_requires_a_session(make_client: ClientFactory) -> None:
    response = make_client().post("/api/invites", json={"email": "marco@mykonos.example.com"})
    assert response.status_code == 401


def test_cannot_invite_an_email_that_already_has_an_account(
    make_client: ClientFactory, sign_up_owner: SignUp
) -> None:
    owner = make_client()
    sign_up_owner(owner, "john@mykonos.example.com")
    sign_up_owner(make_client(), "taken@other.example.com")

    response = owner.post("/api/invites", json={"email": "taken@other.example.com"})
    assert response.status_code == 409


def test_weak_password_or_missing_eula_does_not_use_up_the_link(
    make_client: ClientFactory, sign_up_owner: SignUp
) -> None:
    owner = make_client()
    sign_up_owner(owner, "john@mykonos.example.com")
    invite = create_invite(owner, "marco@mykonos.example.com")

    weak = accept(make_client(), invite["token"], password="weak")
    assert weak.status_code == 400
    no_eula = accept(make_client(), invite["token"], eula_accepted=False)
    assert no_eula.status_code == 400
    assert "EULA" in no_eula.json()["detail"]

    assert accept(make_client(), invite["token"]).status_code == 201


def test_link_is_refused_if_the_email_got_an_account_meanwhile(
    make_client: ClientFactory, sign_up_owner: SignUp, migrated_engine: Engine
) -> None:
    owner = make_client()
    sign_up_owner(owner, "john@mykonos.example.com")
    invite = create_invite(owner, "marco@mykonos.example.com")
    sign_up_owner(make_client(), "marco@mykonos.example.com")

    response = accept(make_client(), invite["token"])
    assert response.status_code == 409
    # The failed attempt rolled back, so the link was not marked as used.
    with migrated_engine.connect() as connection:
        accepted_at = connection.execute(
            text("SELECT accepted_at FROM invites WHERE id = :id"), {"id": invite["invite_id"]}
        ).scalar_one()
    assert accepted_at is None


def test_password_is_hashed_with_argon2id(
    make_client: ClientFactory, sign_up_owner: SignUp, migrated_engine: Engine
) -> None:
    owner = make_client()
    sign_up_owner(owner, "john@mykonos.example.com")
    invite = create_invite(owner, "marco@mykonos.example.com")
    assert accept(make_client(), invite["token"]).status_code == 201

    with migrated_engine.connect() as connection:
        password_hash = connection.execute(
            text("SELECT password_hash FROM users WHERE email = 'marco@mykonos.example.com'")
        ).scalar_one()
    assert password_hash.startswith("$argon2id$")
    assert MANAGER_PASSWORD not in password_hash
    assert TEST_PASSWORD not in password_hash


def test_two_simultaneous_accepts_create_only_one_account(
    make_client: ClientFactory, sign_up_owner: SignUp, migrated_engine: Engine
) -> None:
    owner = make_client()
    sign_up_owner(owner, "john@mykonos.example.com")
    invite = create_invite(owner, "marco@mykonos.example.com")
    clients = [make_client() for _ in range(4)]

    with ThreadPoolExecutor(max_workers=len(clients)) as pool:
        statuses = list(pool.map(lambda c: accept(c, invite["token"]).status_code, clients))

    assert sorted(statuses) == [201, 400, 400, 400]
    with migrated_engine.connect() as connection:
        accounts = connection.execute(
            text("SELECT COUNT(*) FROM users WHERE email = 'marco@mykonos.example.com'")
        ).scalar_one()
    assert accounts == 1

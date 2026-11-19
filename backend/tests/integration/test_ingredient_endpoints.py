# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Units, vendors and ingredients through the API, on a real database."""

import uuid
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.core.config import get_settings
from app.core.security import create_session_token

ClientFactory = Callable[[], TestClient]
SignUp = Callable[[TestClient, str], dict[str, Any]]


def create(client: TestClient, path: str, body: dict[str, Any]) -> dict[str, Any]:
    response = client.post(path, json=body)
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


def test_units_are_grouped_by_kind(make_client: ClientFactory) -> None:
    groups = make_client().get("/api/units").json()
    count = next(group for group in groups if group["kind"] == "count")
    assert (count["base_unit"], count["units"]) == ("each", ["each", "dozen"])
    assert {code: Decimal(factor) for code, factor in count["factors"].items()} == {
        "each": 1,
        "dozen": 12,
    }


def test_owner_builds_vendors_and_ingredients(
    make_client: ClientFactory, sign_up_owner: SignUp
) -> None:
    owner = make_client()
    sign_up_owner(owner, "owner@mykonos.example")
    sysco = create(owner, "/api/vendors", {"name": "Sysco"})
    # A pack of 24 pitas for $10.32 costs $0.43 a pita.
    pita = create(
        owner,
        "/api/ingredients",
        {
            "name": "Pita",
            "base_unit": "each",
            "vendor_id": sysco["id"],
            "pack_size": "2",
            "pack_unit": "dozen",
            "pack_price": "10.32",
        },
    )
    assert pita["vendor_name"] == "Sysco"
    assert Decimal(pita["pack_size"]) == 24
    assert Decimal(pita["unit_cost"]) == Decimal("0.43")
    # Created inline with just a name and a unit: kg means mass, stored in grams.
    chicken = create(owner, "/api/ingredients", {"name": "Chicken breast", "base_unit": "kg"})
    assert (chicken["kind"], chicken["base_unit"], chicken["unit_cost"]) == ("mass", "g", None)

    found = owner.get("/api/ingredients", params={"q": "chick"}).json()
    assert [i["name"] for i in found] == ["Chicken breast"]
    assert [v["name"] for v in owner.get("/api/vendors").json()] == ["Sysco"]

    changed = owner.patch(
        f"/api/ingredients/{chicken['id']}",
        json={"pack_size": "5", "pack_unit": "kg", "pack_price": "86.25", "is_active": False},
    ).json()
    assert Decimal(changed["unit_cost"]) == Decimal("0.01725")  # $86.25 for 5000 g
    assert owner.get("/api/ingredients", params={"q": "chick"}).json() == []
    archived = owner.get("/api/ingredients", params={"q": "chick", "include_inactive": True})
    assert archived.json()[0]["is_active"] is False


def test_ingredient_errors_are_clear(make_client: ClientFactory, sign_up_owner: SignUp) -> None:
    owner = make_client()
    sign_up_owner(owner, "owner@mykonos.example")
    create(owner, "/api/ingredients", {"name": "Feta", "base_unit": "g"})

    duplicate = owner.post("/api/ingredients", json={"name": "FETA", "base_unit": "g"})
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "An ingredient named 'FETA' already exists."
    unknown = owner.post("/api/ingredients", json={"name": "Oil", "base_unit": "jug"})
    assert unknown.status_code == 422
    assert unknown.json()["detail"].startswith("Unknown unit 'jug'. Supported units:")
    wrong_kind = owner.post(
        "/api/ingredients",
        json={"name": "Oil", "base_unit": "ml", "pack_size": "1", "pack_unit": "kg"},
    )
    assert wrong_kind.status_code == 422
    assert "Oil is measured by volume" in wrong_kind.json()["detail"]
    missing = owner.patch(f"/api/ingredients/{uuid.uuid4()}", json={"name": "Salt"})
    assert missing.status_code == 404


def test_restaurants_and_roles(
    make_client: ClientFactory, sign_up_owner: SignUp, migrated_engine: Engine
) -> None:
    owner, other = make_client(), make_client()
    restaurant_id = sign_up_owner(owner, "owner@mykonos.example")["restaurant_id"]
    sign_up_owner(other, "owner@athens.example")
    feta = create(owner, "/api/ingredients", {"name": "Feta", "base_unit": "g"})
    vendor = create(owner, "/api/vendors", {"name": "Costco"})

    # Another restaurant cannot see, change or link to this restaurant's data.
    assert other.get("/api/ingredients").json() == []
    assert other.patch(f"/api/ingredients/{feta['id']}", json={}).status_code == 404
    stolen = other.post(
        "/api/ingredients", json={"name": "Feta", "base_unit": "g", "vendor_id": vendor["id"]}
    )
    assert stolen.status_code == 422

    # Kitchen managers may edit (RECIPE_EDITOR_ROLES).
    manager = make_client()
    with migrated_engine.begin() as connection:
        manager_id = connection.execute(
            text(
                "INSERT INTO users (email, password_hash) VALUES ('marco@x.example', 'x') "
                "RETURNING id"
            )
        ).scalar_one()
        connection.execute(
            text("""
                INSERT INTO restaurant_memberships (user_id, restaurant_id, role)
                VALUES (:user_id, :restaurant_id, 'kitchen_manager')
            """),
            {"user_id": manager_id, "restaurant_id": restaurant_id},
        )
    token = create_session_token(str(manager_id), str(restaurant_id), role="kitchen_manager")
    manager.cookies.set(get_settings().session_cookie_name, token)
    renamed = manager.patch(f"/api/ingredients/{feta['id']}", json={"name": "Greek feta"})
    assert renamed.json()["name"] == "Greek feta"

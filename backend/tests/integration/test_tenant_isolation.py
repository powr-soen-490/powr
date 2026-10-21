# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Integration tests for issue #44: a user of restaurant A is refused restaurant B's data.

No real restaurant-owned endpoints exist yet, so a test-only table and router stand in for
them. The router follows the rules every real endpoint must follow: the restaurant comes from
CurrentUserDep, every query filters by it, and another restaurant's row looks like a missing row.
"""

from collections.abc import Callable
from typing import Annotated, Any
from uuid import UUID

import pytest
from fastapi import APIRouter, Depends, FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.core.auth import CurrentUserDep
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import create_session_token

ClientFactory = Callable[[], TestClient]
SignUp = Callable[[TestClient, str], dict[str, Any]]
DbSession = Annotated[Session, Depends(get_db)]

probe = APIRouter(prefix="/probe/items")


class NewItem(BaseModel):
    name: str
    # Sent by a malicious client; the endpoint must ignore it.
    restaurant_id: UUID | None = None


@probe.get("")
def list_items(user: CurrentUserDep, db: DbSession) -> list[str]:
    rows = db.execute(
        text("SELECT name FROM tenant_probe_items WHERE restaurant_id = :rid ORDER BY name"),
        {"rid": user.restaurant_id},
    )
    return list(rows.scalars())


@probe.get("/{item_id}")
def get_item(item_id: UUID, user: CurrentUserDep, db: DbSession) -> dict[str, str]:
    name = db.execute(
        text("SELECT name FROM tenant_probe_items WHERE id = :id AND restaurant_id = :rid"),
        {"id": item_id, "rid": user.restaurant_id},
    ).scalar_one_or_none()
    if name is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
    return {"name": name}


@probe.post("", status_code=status.HTTP_201_CREATED)
def create_item(item: NewItem, user: CurrentUserDep, db: DbSession) -> dict[str, str]:
    item_id = db.execute(
        text(
            "INSERT INTO tenant_probe_items (restaurant_id, name) VALUES (:rid, :name) RETURNING id"
        ),
        {"rid": user.restaurant_id, "name": item.name},
    ).scalar_one()
    db.commit()
    return {"id": str(item_id)}


@pytest.fixture
def engine(migrated_engine: Engine, api_app: FastAPI) -> Engine:
    with migrated_engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE tenant_probe_items ("
                " id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),"
                " restaurant_id UUID NOT NULL REFERENCES restaurants(id),"
                " name TEXT NOT NULL)"
            )
        )
    api_app.include_router(probe)
    return migrated_engine


def add_item(engine: Engine, restaurant_id: str, name: str) -> str:
    with engine.begin() as connection:
        item_id = connection.execute(
            text(
                "INSERT INTO tenant_probe_items (restaurant_id, name) "
                "VALUES (:rid, :name) RETURNING id"
            ),
            {"rid": restaurant_id, "name": name},
        ).scalar_one()
    return str(item_id)


Restaurants = tuple[TestClient, dict[str, Any], TestClient, dict[str, Any]]


@pytest.fixture
def two_restaurants(
    engine: Engine, make_client: ClientFactory, sign_up_owner: SignUp
) -> Restaurants:
    """John owns restaurant A (with Feta), Maria owns restaurant B (with Basil)."""
    john, maria = make_client(), make_client()
    johns = sign_up_owner(john, "john@example.com")
    marias = sign_up_owner(maria, "maria@example.com")
    johns["item_id"] = add_item(engine, johns["restaurant_id"], "Feta")
    marias["item_id"] = add_item(engine, marias["restaurant_id"], "Basil")
    return john, johns, maria, marias


def test_each_restaurant_lists_only_its_own_data(two_restaurants: Restaurants) -> None:
    john, _, maria, _ = two_restaurants

    assert john.get("/probe/items").json() == ["Feta"]
    assert maria.get("/probe/items").json() == ["Basil"]


def test_restaurant_id_in_the_query_string_is_ignored(two_restaurants: Restaurants) -> None:
    john, _, _, marias = two_restaurants

    response = john.get("/probe/items", params={"restaurant_id": marias["restaurant_id"]})

    assert response.json() == ["Feta"]


def test_another_restaurants_item_looks_like_it_does_not_exist(
    two_restaurants: Restaurants,
) -> None:
    john, johns, _, marias = two_restaurants

    refused = john.get(f"/probe/items/{marias['item_id']}")
    missing = john.get("/probe/items/00000000-0000-0000-0000-000000000000")

    # Same answer as a missing item, so John cannot even learn that Maria's item exists.
    assert refused.status_code == missing.status_code == 404
    assert refused.json() == missing.json()
    assert john.get(f"/probe/items/{johns['item_id']}").json() == {"name": "Feta"}


def test_restaurant_id_in_the_body_cannot_write_into_another_restaurant(
    two_restaurants: Restaurants, engine: Engine
) -> None:
    john, johns, maria, marias = two_restaurants

    response = john.post(
        "/probe/items", json={"name": "Olives", "restaurant_id": marias["restaurant_id"]}
    )

    assert response.status_code == 201
    with engine.connect() as connection:
        owner = connection.execute(
            text("SELECT restaurant_id FROM tenant_probe_items WHERE name = 'Olives'")
        ).scalar_one()
    assert str(owner) == johns["restaurant_id"]
    assert maria.get("/probe/items").json() == ["Basil"]


def test_signed_session_for_a_restaurant_without_membership_is_refused(
    two_restaurants: Restaurants, make_client: ClientFactory
) -> None:
    _, johns, _, marias = two_restaurants
    # A genuinely signed token naming Maria's restaurant, as if the secret had leaked or a
    # stale session survived: John has no membership there, so the database check refuses it.
    token = create_session_token(johns["user_id"], marias["restaurant_id"], role="owner")
    intruder = make_client()
    intruder.cookies.set(get_settings().session_cookie_name, token)

    assert intruder.get("/probe/items").status_code == 401
    assert intruder.get(f"/probe/items/{marias['item_id']}").status_code == 401
    assert intruder.get("/api/auth/me").status_code == 401


def test_requests_without_a_session_see_nothing(
    two_restaurants: Restaurants, make_client: ClientFactory
) -> None:
    anonymous = make_client()

    assert anonymous.get("/probe/items").status_code == 401
    assert anonymous.post("/probe/items", json={"name": "Olives"}).status_code == 401

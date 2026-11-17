# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Recipes through the API on a real database: the U-S #5 demo and its error cases.

1. Map the souvlaki plate with an "extra feta" modifier.
2. Change the recipe.
3. Show both versions with their effective dates.
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

ClientFactory = Callable[[], TestClient]
SignUp = Callable[[TestClient, str], dict[str, Any]]


class Kitchen:
    """An owner's session and the ids of their seeded menu and ingredients."""

    def __init__(self, client: TestClient, ids: dict[str, str]) -> None:
        self.client = client
        self.ids = ids

    def recipe_path(self, suffix: str = "") -> str:
        return f"/api/menu-items/{self.ids['souvlaki']}/recipe{suffix}"


@pytest.fixture
def kitchen(make_client: ClientFactory, sign_up_owner: SignUp, migrated_engine: Engine) -> Kitchen:
    owner = make_client()
    restaurant_id = sign_up_owner(owner, "owner@mykonos.example")["restaurant_id"]
    ids: dict[str, str] = {}
    with migrated_engine.begin() as connection:
        keys = {"restaurant_id": restaurant_id}
        ids["souvlaki"] = str(
            connection.execute(
                text("""
                    INSERT INTO menu_items (restaurant_id, provider, pos_item_id, name, price,
                                            currency)
                    VALUES (:restaurant_id, 'TOAST', 'item-souvlaki', 'Souvlaki plate', 18.50,
                            'USD')
                    RETURNING id
                """),
                keys,
            ).scalar_one()
        )
        ids["extra_feta"] = str(
            connection.execute(
                text("""
                    INSERT INTO menu_modifiers (restaurant_id, provider, pos_modifier_id, name,
                                                group_name, price)
                    VALUES (:restaurant_id, 'TOAST', 'mod-feta', 'Extra feta', 'Add-ons', 2.00)
                    RETURNING id
                """),
                keys,
            ).scalar_one()
        )
    for name, unit, pack in [
        ("Chicken breast", "g", {"pack_size": "5", "pack_unit": "kg", "pack_price": "86.25"}),
        ("Pita", "each", {"pack_size": "24", "pack_price": "10.32"}),
        ("Feta", "g", {}),
    ]:
        response = owner.post("/api/ingredients", json={"name": name, "base_unit": unit, **pack})
        ids[name] = response.json()["id"]
    return Kitchen(owner, ids)


def recipe(kitchen: Kitchen, chicken: str, **extra: Any) -> dict[str, Any]:
    ids = kitchen.ids
    return {
        "lines": [
            {"ingredient_id": ids["Chicken breast"], "quantity": chicken, "unit": "g"},
            {"ingredient_id": ids["Pita"], "quantity": "1", "unit": "each"},
        ],
        "modifier_lines": [
            {
                "menu_modifier_id": ids["extra_feta"],
                "ingredient_id": ids["Feta"],
                "effect": "add",
                "quantity": "30",
                "unit": "g",
            }
        ],
        **extra,
    }


def test_map_change_and_show_versions(kitchen: Kitchen) -> None:
    client = kitchen.client
    assert client.get(kitchen.recipe_path()).status_code == 404  # not mapped yet
    assert client.get(kitchen.recipe_path("/versions")).json() == []

    # 1. Map the souvlaki plate with "extra feta: +30 g".
    first = client.put(kitchen.recipe_path(), json=recipe(kitchen, "200"))
    assert first.status_code == 201, first.text
    body = first.json()
    costs = [(line["ingredient_name"], Decimal(line["cost"])) for line in body["lines"]]
    # 200 g of chicken at $86.25 per 5 kg, and one pita at $10.32 for 24
    assert costs == [("Chicken breast", Decimal("3.45")), ("Pita", Decimal("0.43"))]
    assert Decimal(body["total_cost"]) == Decimal("3.88")
    [extra] = body["modifier_lines"]
    assert (extra["modifier_name"], extra["effect"], Decimal(extra["quantity"])) == (
        "Extra feta",
        "add",
        Decimal(30),
    )
    assert extra["cost"] is None  # feta has no price yet


def test_saving_a_change_keeps_the_old_version_for_past_sales(kitchen: Kitchen) -> None:
    client = kitchen.client
    first = client.put(kitchen.recipe_path(), json=recipe(kitchen, "200")).json()["version"]
    unchanged = client.put(kitchen.recipe_path(), json=recipe(kitchen, "200"))
    assert unchanged.status_code == 200
    assert unchanged.json()["version"]["id"] == first["id"]

    # 2. Change the recipe, starting next week.
    next_week = (datetime.now(UTC) + timedelta(days=7)).isoformat()
    scheduled = client.put(
        kitchen.recipe_path(), json=recipe(kitchen, "220", effective_from=next_week)
    )
    assert scheduled.status_code == 201

    # 3. Both versions with their effective dates.
    versions = client.get(kitchen.recipe_path("/versions")).json()
    assert [v["status"] for v in versions] == ["scheduled", "current"]
    assert versions[1]["effective_from"] == first["effective_from"]
    now = client.get(kitchen.recipe_path()).json()
    assert Decimal(now["lines"][0]["quantity"]) == 200
    later = client.get(kitchen.recipe_path(), params={"at": next_week})
    assert Decimal(later.json()["lines"][0]["quantity"]) == 220

    # A change starting now replaces the scheduled one; sales made under the first version
    # still use it.
    client.put(kitchen.recipe_path(), json=recipe(kitchen, "210"))
    versions = client.get(kitchen.recipe_path("/versions")).json()
    assert [v["status"] for v in versions] == ["current", "past"]
    past = client.get(kitchen.recipe_path(), params={"at": first["effective_from"]}).json()
    assert past["version"]["id"] == first["id"]
    assert Decimal(past["lines"][0]["quantity"]) == 200


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"lines": [{"quantity": "0"}]}, "greater than 0"),
        ({"lines": [{"unit": "jug"}]}, "Unknown unit 'jug'"),
        ({"lines": [{"unit": "ml"}]}, "Chicken breast is measured by mass"),
        ({"effective_from": "2020-01-01T00:00:00Z"}, "cannot start in the past"),
    ],
)
def test_invalid_recipes_are_refused_clearly(
    kitchen: Kitchen, change: dict[str, Any], message: str
) -> None:
    body = recipe(kitchen, "200")
    if "lines" in change:
        body["lines"][0].update(change["lines"][0])
    else:
        body.update(change)
    response = kitchen.client.put(kitchen.recipe_path(), json=body)
    assert response.status_code == 422
    assert message in response.json()["detail"]


def test_duplicate_lines_and_unknown_items(kitchen: Kitchen) -> None:
    body = recipe(kitchen, "200")
    body["lines"].append(dict(body["lines"][0]))
    response = kitchen.client.put(kitchen.recipe_path(), json=body)
    assert response.json()["detail"] == (
        "Chicken breast is listed twice; combine it into one line."
    )
    missing = f"/api/menu-items/{uuid.uuid4()}/recipe"
    assert kitchen.client.put(missing, json=recipe(kitchen, "200")).status_code == 404


def test_modifiers_offered_for_an_item(kitchen: Kitchen) -> None:
    path = f"/api/menu-items/{kitchen.ids['souvlaki']}/modifiers"
    [modifier] = kitchen.client.get(path).json()
    assert (modifier["name"], modifier["sold_with_item"]) == ("Extra feta", 0)

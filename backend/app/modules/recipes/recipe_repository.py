# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Database reads and writes of recipes and their versions. Nothing here commits.

Quantities are in the ingredient's base unit. unit_cost is the ingredient's current price of
one base unit (pack_price / pack_size), or None when its pack is unknown.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class MenuItem:
    id: UUID
    provider: str
    pos_item_id: str
    name: str
    price: Decimal | None
    is_active: bool


@dataclass(frozen=True)
class Modifier:
    id: UUID
    name: str
    group_name: str
    price: Decimal | None
    sold_with_item: int = 0  # times sold with a given item, when asked for


@dataclass(frozen=True)
class Version:
    id: UUID
    effective_from: datetime
    menu_item_name: str
    menu_item_price: Decimal | None
    created_by_email: str | None
    created_at: datetime


@dataclass(frozen=True)
class Line:
    ingredient_id: UUID
    ingredient_name: str
    base_unit: str
    quantity: Decimal
    entered_quantity: Decimal
    entered_unit: str
    unit_cost: Decimal | None


@dataclass(frozen=True)
class ModifierLine:
    menu_modifier_id: UUID
    modifier_name: str
    effect: str
    ingredient_id: UUID
    ingredient_name: str
    base_unit: str
    quantity: Decimal
    entered_quantity: Decimal
    entered_unit: str
    unit_cost: Decimal | None


def get_menu_item(db: Session, *, restaurant_id: UUID, menu_item_id: UUID) -> MenuItem | None:
    row = db.execute(
        text("""
            SELECT id, provider, pos_item_id, name, price, is_active FROM menu_items
            WHERE id = :id AND restaurant_id = :restaurant_id
        """),
        {"id": menu_item_id, "restaurant_id": restaurant_id},
    ).first()
    if row is None:
        return None
    return MenuItem(
        id=row.id,
        provider=row.provider,
        pos_item_id=row.pos_item_id,
        name=row.name,
        price=row.price,
        is_active=row.is_active,
    )


def get_modifier_names(
    db: Session, *, restaurant_id: UUID, modifier_ids: list[UUID]
) -> dict[UUID, str]:
    rows = db.execute(
        text("""
            SELECT id, name FROM menu_modifiers
            WHERE restaurant_id = :restaurant_id AND id = ANY(:ids)
        """),
        {"restaurant_id": restaurant_id, "ids": modifier_ids},
    )
    return {row.id: row.name for row in rows}


def modifiers_for_item(
    db: Session, *, restaurant_id: UUID, item: MenuItem, since: date
) -> list[Modifier]:
    """Active modifiers, those sold most often with ``item`` since ``since`` first.

    The POS menu does not record which modifiers each item offers, so sales are the guide.
    """
    rows = db.execute(
        text("""
            WITH sold AS (
                SELECT m ->> 'pos_item_id' AS pos_modifier_id, count(*) AS times
                FROM sales_order_lines AS line,
                     jsonb_array_elements(line.modifiers) AS m
                WHERE line.restaurant_id = :restaurant_id AND line.pos_item_id = :pos_item_id
                  AND line.business_date >= :since AND NOT line.is_voided
                GROUP BY 1
            )
            SELECT mm.id, mm.name, mm.group_name, mm.price, coalesce(sold.times, 0) AS times
            FROM menu_modifiers AS mm
            LEFT JOIN sold ON sold.pos_modifier_id = mm.pos_modifier_id
            WHERE mm.restaurant_id = :restaurant_id AND mm.provider = :provider
              AND (mm.is_active OR sold.times IS NOT NULL)
            ORDER BY coalesce(sold.times, 0) DESC, lower(mm.group_name), lower(mm.name)
        """),
        {
            "restaurant_id": restaurant_id,
            "provider": item.provider,
            "pos_item_id": item.pos_item_id,
            "since": since,
        },
    )
    return [
        Modifier(
            id=row.id,
            name=row.name,
            group_name=row.group_name,
            price=row.price,
            sold_with_item=row.times,
        )
        for row in rows
    ]


def find_recipe_id(db: Session, *, restaurant_id: UUID, menu_item_id: UUID) -> UUID | None:
    recipe_id: UUID | None = db.execute(
        text("""
            SELECT id FROM recipes
            WHERE restaurant_id = :restaurant_id AND menu_item_id = :menu_item_id
        """),
        {"restaurant_id": restaurant_id, "menu_item_id": menu_item_id},
    ).scalar_one_or_none()
    return recipe_id


def get_or_create_recipe(db: Session, *, restaurant_id: UUID, menu_item_id: UUID) -> UUID:
    db.execute(
        text("""
            INSERT INTO recipes (restaurant_id, menu_item_id)
            VALUES (:restaurant_id, :menu_item_id)
            ON CONFLICT (restaurant_id, menu_item_id) DO NOTHING
        """),
        {"restaurant_id": restaurant_id, "menu_item_id": menu_item_id},
    )
    recipe_id = find_recipe_id(db, restaurant_id=restaurant_id, menu_item_id=menu_item_id)
    assert recipe_id is not None  # inserted just above, or already there
    return recipe_id


_SELECT_VERSIONS = """
    SELECT v.id, v.effective_from, v.menu_item_name, v.menu_item_price,
           u.email AS created_by_email, v.created_at
    FROM recipe_versions AS v
    LEFT JOIN users AS u ON u.id = v.created_by
    WHERE v.restaurant_id = :restaurant_id AND v.recipe_id = :recipe_id
"""


def list_versions(db: Session, *, restaurant_id: UUID, recipe_id: UUID) -> list[Version]:
    """Every version, newest effective_from first."""
    rows = db.execute(
        text(f"{_SELECT_VERSIONS} ORDER BY v.effective_from DESC"),
        {"restaurant_id": restaurant_id, "recipe_id": recipe_id},
    )
    return [_version(row) for row in rows]


def version_at(
    db: Session, *, restaurant_id: UUID, recipe_id: UUID, at: datetime
) -> Version | None:
    """The version in effect at ``at``: the last one that started at or before it."""
    row = db.execute(
        text(f"{_SELECT_VERSIONS} AND v.effective_from <= :at ORDER BY v.effective_from DESC"),
        {"restaurant_id": restaurant_id, "recipe_id": recipe_id, "at": at},
    ).first()
    return None if row is None else _version(row)


def lines(db: Session, *, restaurant_id: UUID, version_id: UUID) -> list[Line]:
    rows = db.execute(
        text("""
            SELECT l.ingredient_id, i.name AS ingredient_name, i.base_unit, l.quantity,
                   l.entered_quantity, l.entered_unit, i.pack_price / i.pack_size AS unit_cost
            FROM recipe_lines AS l
            JOIN ingredients AS i ON i.id = l.ingredient_id AND i.restaurant_id = l.restaurant_id
            WHERE l.restaurant_id = :restaurant_id AND l.recipe_version_id = :version_id
            ORDER BY lower(i.name)
        """),
        {"restaurant_id": restaurant_id, "version_id": version_id},
    )
    return [Line(**row._asdict()) for row in rows]


def modifier_lines(db: Session, *, restaurant_id: UUID, version_id: UUID) -> list[ModifierLine]:
    rows = db.execute(
        text("""
            SELECT l.menu_modifier_id, mm.name AS modifier_name, l.effect, l.ingredient_id,
                   i.name AS ingredient_name, i.base_unit, l.quantity, l.entered_quantity,
                   l.entered_unit, i.pack_price / i.pack_size AS unit_cost
            FROM recipe_modifier_lines AS l
            JOIN ingredients AS i ON i.id = l.ingredient_id AND i.restaurant_id = l.restaurant_id
            JOIN menu_modifiers AS mm
              ON mm.id = l.menu_modifier_id AND mm.restaurant_id = l.restaurant_id
            WHERE l.restaurant_id = :restaurant_id AND l.recipe_version_id = :version_id
            ORDER BY lower(mm.name), l.effect DESC, lower(i.name)
        """),
        {"restaurant_id": restaurant_id, "version_id": version_id},
    )
    return [ModifierLine(**row._asdict()) for row in rows]


def delete_versions_from(
    db: Session, *, restaurant_id: UUID, recipe_id: UUID, start: datetime
) -> None:
    """Deletes versions starting at or after ``start`` (only ever future ones); their lines
    go with them."""
    db.execute(
        text("""
            DELETE FROM recipe_versions
            WHERE restaurant_id = :restaurant_id AND recipe_id = :recipe_id
              AND effective_from >= :start
        """),
        {"restaurant_id": restaurant_id, "recipe_id": recipe_id, "start": start},
    )


def insert_version(
    db: Session,
    *,
    restaurant_id: UUID,
    recipe_id: UUID,
    effective_from: datetime,
    item: MenuItem,
    created_by: UUID,
    lines: list[dict[str, Any]],
    modifier_lines: list[dict[str, Any]],
) -> UUID:
    """Inserts a version and its lines. Line dicts hold the columns of recipe_lines and
    recipe_modifier_lines, without ids."""
    version_id: UUID = db.execute(
        text("""
            INSERT INTO recipe_versions (
                restaurant_id, recipe_id, effective_from, menu_item_name, menu_item_price,
                created_by
            )
            VALUES (
                :restaurant_id, :recipe_id, :effective_from, :name, :price, :created_by
            )
            RETURNING id
        """),
        {
            "restaurant_id": restaurant_id,
            "recipe_id": recipe_id,
            "effective_from": effective_from,
            "name": item.name,
            "price": item.price,
            "created_by": created_by,
        },
    ).scalar_one()
    keys = {"restaurant_id": restaurant_id, "version_id": version_id}
    db.execute(
        text("""
            INSERT INTO recipe_lines (
                restaurant_id, recipe_version_id, ingredient_id, quantity, entered_quantity,
                entered_unit
            )
            VALUES (
                :restaurant_id, :version_id, :ingredient_id, :quantity, :entered_quantity,
                :entered_unit
            )
        """),
        [{**keys, **line} for line in lines],
    )
    if modifier_lines:
        db.execute(
            text("""
                INSERT INTO recipe_modifier_lines (
                    restaurant_id, recipe_version_id, menu_modifier_id, ingredient_id, effect,
                    quantity, entered_quantity, entered_unit
                )
                VALUES (
                    :restaurant_id, :version_id, :menu_modifier_id, :ingredient_id, :effect,
                    :quantity, :entered_quantity, :entered_unit
                )
            """),
            [{**keys, **line} for line in modifier_lines],
        )
    return version_id


def _version(row: Any) -> Version:
    return Version(
        id=row.id,
        effective_from=row.effective_from,
        menu_item_name=row.menu_item_name,
        menu_item_price=row.menu_item_price,
        created_by_email=row.created_by_email,
        created_at=row.created_at,
    )

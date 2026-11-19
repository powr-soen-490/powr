# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Database reads and writes of vendors and ingredients. Nothing here commits."""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

SEARCH_LIMIT = 50
# The only columns update_ingredient may set; keys come from the service, never the request.
UPDATABLE_COLUMNS = frozenset({"name", "vendor_id", "pack_size", "pack_price", "is_active"})


@dataclass(frozen=True)
class Vendor:
    id: UUID
    name: str
    contact_email: str | None


@dataclass(frozen=True)
class Ingredient:
    id: UUID
    name: str
    kind: str
    base_unit: str
    vendor_id: UUID | None
    vendor_name: str | None
    pack_size: Decimal | None  # in base_unit
    pack_price: Decimal | None
    is_active: bool

    @property
    def unit_cost(self) -> Decimal | None:
        """The price of one base unit (one g, ml or each), when the pack is known."""
        if self.pack_size is None or self.pack_price is None:
            return None
        return self.pack_price / self.pack_size


def list_vendors(db: Session, *, restaurant_id: UUID) -> list[Vendor]:
    rows = db.execute(
        text("""
            SELECT id, name, contact_email FROM vendors
            WHERE restaurant_id = :restaurant_id ORDER BY lower(name)
        """),
        {"restaurant_id": restaurant_id},
    )
    return [Vendor(id=row.id, name=row.name, contact_email=row.contact_email) for row in rows]


def insert_vendor(
    db: Session, *, restaurant_id: UUID, name: str, contact_email: str | None
) -> Vendor:
    row = db.execute(
        text("""
            INSERT INTO vendors (restaurant_id, name, contact_email)
            VALUES (:restaurant_id, :name, :contact_email)
            RETURNING id, name, contact_email
        """),
        {"restaurant_id": restaurant_id, "name": name, "contact_email": contact_email},
    ).one()
    return Vendor(id=row.id, name=row.name, contact_email=row.contact_email)


def vendor_exists(db: Session, *, restaurant_id: UUID, vendor_id: UUID) -> bool:
    found = db.execute(
        text("SELECT 1 FROM vendors WHERE id = :id AND restaurant_id = :restaurant_id"),
        {"id": vendor_id, "restaurant_id": restaurant_id},
    ).first()
    return found is not None


_SELECT_INGREDIENTS = """
    SELECT i.id, i.name, i.kind, i.base_unit, i.vendor_id, v.name AS vendor_name,
           i.pack_size, i.pack_price, i.is_active
    FROM ingredients AS i
    LEFT JOIN vendors AS v ON v.id = i.vendor_id AND v.restaurant_id = i.restaurant_id
    WHERE i.restaurant_id = :restaurant_id
"""


def search_ingredients(
    db: Session, *, restaurant_id: UUID, query: str, include_inactive: bool
) -> list[Ingredient]:
    """Ingredients whose name contains ``query`` (any capitals), names starting with it first.

    Postgres LIKE escapes with a backslash by default, which _escape_like relies on.
    """
    pattern = _escape_like(query.strip())
    rows = db.execute(
        text(f"""{_SELECT_INGREDIENTS}
              AND i.name ILIKE :contains
              AND (i.is_active OR :include_inactive)
            ORDER BY i.name NOT ILIKE :prefix, lower(i.name)
            LIMIT {SEARCH_LIMIT}
        """),
        {
            "restaurant_id": restaurant_id,
            "contains": f"%{pattern}%",
            "prefix": f"{pattern}%",
            "include_inactive": include_inactive,
        },
    )
    return [_ingredient(row) for row in rows]


def get_ingredients(
    db: Session, *, restaurant_id: UUID, ingredient_ids: Iterable[UUID]
) -> dict[UUID, Ingredient]:
    rows = db.execute(
        text(f"{_SELECT_INGREDIENTS} AND i.id = ANY(:ids)"),
        {"restaurant_id": restaurant_id, "ids": list(ingredient_ids)},
    )
    return {row.id: _ingredient(row) for row in rows}


def insert_ingredient(
    db: Session,
    *,
    restaurant_id: UUID,
    name: str,
    kind: str,
    base_unit: str,
    vendor_id: UUID | None,
    pack_size: Decimal | None,
    pack_price: Decimal | None,
) -> UUID:
    ingredient_id: UUID = db.execute(
        text("""
            INSERT INTO ingredients (
                restaurant_id, name, kind, base_unit, vendor_id, pack_size, pack_price
            )
            VALUES (
                :restaurant_id, :name, :kind, :base_unit, :vendor_id, :pack_size, :pack_price
            )
            RETURNING id
        """),
        {
            "restaurant_id": restaurant_id,
            "name": name,
            "kind": kind,
            "base_unit": base_unit,
            "vendor_id": vendor_id,
            "pack_size": pack_size,
            "pack_price": pack_price,
        },
    ).scalar_one()
    return ingredient_id


def update_ingredient(
    db: Session, *, restaurant_id: UUID, ingredient_id: UUID, values: dict[str, Any]
) -> bool:
    """Sets the given columns; False when the ingredient is not in this restaurant."""
    unknown = values.keys() - UPDATABLE_COLUMNS
    if unknown:
        raise ValueError(f"Cannot update ingredient columns: {sorted(unknown)}")
    assignments = "".join(f"{column} = :{column}, " for column in values)
    result = db.execute(
        text(f"""
            UPDATE ingredients SET {assignments}updated_at = CURRENT_TIMESTAMP
            WHERE id = :id AND restaurant_id = :restaurant_id
            RETURNING id
        """),
        {**values, "id": ingredient_id, "restaurant_id": restaurant_id},
    )
    return result.first() is not None


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _ingredient(row: Any) -> Ingredient:
    return Ingredient(
        id=row.id,
        name=row.name,
        kind=row.kind,
        base_unit=row.base_unit,
        vendor_id=row.vendor_id,
        vendor_name=row.vendor_name,
        pack_size=row.pack_size,
        pack_price=row.pack_price,
        is_active=row.is_active,
    )

# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Business rules for vendors and ingredients.

An ingredient is measured in one kind (mass, volume or count) and stored in that kind's base
unit (g, ml or each). People may type any unit of the right kind; it is converted here.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, NoReturn
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.units import base_unit_for, convert, parse_unit
from app.modules.recipes import ingredient_repository as repository
from app.modules.recipes.ingredient_repository import Ingredient, Vendor

# Base quantities are stored with 4 decimals (NUMERIC(12, 4)).
BASE_QUANTITY_STEP = Decimal("0.0001")
NAME_CONSTRAINT = "uq_ingredients_name"


class IngredientError(Exception):
    """A rule was broken; the message is written for the kitchen manager."""


class InvalidQuantityError(IngredientError):
    pass


class DuplicateIngredientError(IngredientError):
    pass


class IngredientNotFoundError(IngredientError):
    pass


class VendorNotFoundError(IngredientError):
    pass


@dataclass(frozen=True)
class NewIngredient:
    name: str
    unit: str  # any unit; its kind decides the ingredient's kind
    vendor_id: UUID | None = None
    pack_size: Decimal | None = None
    pack_unit: str | None = None  # the unit of pack_size; the base unit when omitted
    pack_price: Decimal | None = None


def to_base(quantity: Decimal, unit: str, base_unit: str, *, subject: str) -> Decimal:
    """``quantity`` of ``unit`` in ``base_unit``, rounded to the stored 4 decimals."""
    base = convert(quantity, unit, base_unit, subject=subject).quantize(BASE_QUANTITY_STEP)
    if base <= 0:
        raise InvalidQuantityError(f"{quantity} {unit} of {subject} is too small to store.")
    return base


def list_vendors(db: Session, *, restaurant_id: UUID) -> list[Vendor]:
    return repository.list_vendors(db, restaurant_id=restaurant_id)


def create_vendor(
    db: Session, *, restaurant_id: UUID, name: str, contact_email: str | None
) -> Vendor:
    vendor = repository.insert_vendor(
        db, restaurant_id=restaurant_id, name=name, contact_email=contact_email
    )
    db.commit()
    return vendor


def search_ingredients(
    db: Session, *, restaurant_id: UUID, query: str = "", include_inactive: bool = False
) -> list[Ingredient]:
    return repository.search_ingredients(
        db, restaurant_id=restaurant_id, query=query, include_inactive=include_inactive
    )


def get_ingredient(db: Session, *, restaurant_id: UUID, ingredient_id: UUID) -> Ingredient:
    found = repository.get_ingredients(
        db, restaurant_id=restaurant_id, ingredient_ids=[ingredient_id]
    )
    if ingredient_id not in found:
        raise IngredientNotFoundError("This ingredient does not exist.")
    return found[ingredient_id]


def create_ingredient(db: Session, *, restaurant_id: UUID, new: NewIngredient) -> Ingredient:
    kind = parse_unit(new.unit).kind
    base_unit = base_unit_for(kind).code
    _check_vendor(db, restaurant_id, new.vendor_id)
    pack_size = _pack_size(new.pack_size, new.pack_unit, base_unit, new.name)
    try:
        ingredient_id = repository.insert_ingredient(
            db,
            restaurant_id=restaurant_id,
            name=new.name,
            kind=kind.value,
            base_unit=base_unit,
            vendor_id=new.vendor_id,
            pack_size=pack_size,
            pack_price=new.pack_price,
        )
        db.commit()
    except IntegrityError as exc:
        _raise_if_duplicate(db, exc, new.name)
    return get_ingredient(db, restaurant_id=restaurant_id, ingredient_id=ingredient_id)


def update_ingredient(
    db: Session, *, restaurant_id: UUID, ingredient_id: UUID, changes: dict[str, Any]
) -> Ingredient:
    """Applies the given changes. Keys: name, is_active (skipped when None), vendor_id,
    pack_size, pack_unit and pack_price (None clears them)."""
    current = get_ingredient(db, restaurant_id=restaurant_id, ingredient_id=ingredient_id)
    values = {key: changes[key] for key in ("name", "is_active") if changes.get(key) is not None}
    values.update({key: changes[key] for key in ("vendor_id", "pack_price") if key in changes})
    if "vendor_id" in values:
        _check_vendor(db, restaurant_id, values["vendor_id"])
    if "pack_size" in changes:
        values["pack_size"] = _pack_size(
            changes["pack_size"], changes.get("pack_unit"), current.base_unit, current.name
        )
    if values:
        try:
            repository.update_ingredient(
                db, restaurant_id=restaurant_id, ingredient_id=ingredient_id, values=values
            )
            db.commit()
        except IntegrityError as exc:
            _raise_if_duplicate(db, exc, str(values.get("name", current.name)))
    return get_ingredient(db, restaurant_id=restaurant_id, ingredient_id=ingredient_id)


def _pack_size(size: Decimal | None, unit: str | None, base_unit: str, name: str) -> Decimal | None:
    if size is None:
        return None
    return to_base(size, unit or base_unit, base_unit, subject=name)


def _check_vendor(db: Session, restaurant_id: UUID, vendor_id: UUID | None) -> None:
    if vendor_id is not None and not repository.vendor_exists(
        db, restaurant_id=restaurant_id, vendor_id=vendor_id
    ):
        raise VendorNotFoundError("This vendor does not exist.")


def _raise_if_duplicate(db: Session, exc: IntegrityError, name: str) -> NoReturn:
    db.rollback()
    if NAME_CONSTRAINT in str(exc.orig):
        raise DuplicateIngredientError(f"An ingredient named '{name}' already exists.") from exc
    raise exc

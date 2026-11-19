# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Recipe validation without a database: lines, modifier lines, effective dates, changes."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.core.units import IncompatibleUnitsError
from app.modules.recipes.ingredient_repository import Ingredient
from app.modules.recipes.recipe_service import (
    InvalidRecipeError,
    LineInput,
    ModifierLineInput,
    base_lines,
    base_modifier_lines,
    effective_start,
    same_content,
)

NOW = datetime(2026, 11, 17, 12, tzinfo=UTC)
EXTRA_FETA = uuid.uuid4()


def ingredient(name: str, base_unit: str = "g", *, is_active: bool = True) -> Ingredient:
    kind = {"g": "mass", "ml": "volume", "each": "count"}[base_unit]
    return Ingredient(
        id=uuid.uuid4(),
        name=name,
        kind=kind,
        base_unit=base_unit,
        vendor_id=None,
        vendor_name=None,
        pack_size=None,
        pack_price=None,
        is_active=is_active,
    )


FETA = ingredient("Feta")
PITA = ingredient("Pita", "each")
INGREDIENTS = {FETA.id: FETA, PITA.id: PITA}


def line(item: Ingredient, quantity: str, unit: str) -> LineInput:
    return LineInput(ingredient_id=item.id, quantity=Decimal(quantity), unit=unit)


def test_lines_are_stored_in_base_units_with_what_was_typed() -> None:
    [converted] = base_lines([line(FETA, "0.06", "KG")], INGREDIENTS)
    assert (converted.quantity, converted.entered_quantity, converted.entered_unit) == (
        Decimal(60),
        Decimal("0.06"),
        "kg",
    )


@pytest.mark.parametrize(
    ("lines", "message"),
    [
        ([], "at least one ingredient"),
        ([line(FETA, "30", "g"), line(FETA, "1", "oz")], "Feta is listed twice"),
        ([line(ingredient("Ghost"), "1", "g")], "does not exist"),
    ],
)
def test_bad_lines_are_refused(lines: list[LineInput], message: str) -> None:
    with pytest.raises(InvalidRecipeError, match=message):
        base_lines(lines, INGREDIENTS)


def test_archived_ingredients_are_refused() -> None:
    old = ingredient("Old feta", is_active=False)
    with pytest.raises(InvalidRecipeError, match="Old feta is archived"):
        base_lines([line(old, "30", "g")], {old.id: old})


def test_unit_must_match_the_ingredient_kind() -> None:
    with pytest.raises(IncompatibleUnitsError, match="Pita is measured by count"):
        base_lines([line(PITA, "30", "g")], INGREDIENTS)


def modifier_line(modifier_id: uuid.UUID, quantity: str = "30") -> ModifierLineInput:
    return ModifierLineInput(
        menu_modifier_id=modifier_id,
        ingredient_id=FETA.id,
        effect="add",
        quantity=Decimal(quantity),
        unit="g",
    )


def test_modifier_lines_refuse_duplicates_and_unknown_modifiers() -> None:
    names = {EXTRA_FETA: "Extra feta"}
    with pytest.raises(InvalidRecipeError, match="Feta is listed twice for “Extra feta”"):
        twice = [modifier_line(EXTRA_FETA), modifier_line(EXTRA_FETA)]
        base_modifier_lines(twice, INGREDIENTS, names)
    with pytest.raises(InvalidRecipeError, match="modifier in this recipe does not exist"):
        base_modifier_lines([modifier_line(uuid.uuid4())], INGREDIENTS, names)


def test_effective_start_is_now_or_later_never_the_past() -> None:
    assert effective_start(None, NOW) == NOW
    assert effective_start(NOW - timedelta(minutes=1), NOW) == NOW  # a slow client clock
    tomorrow = NOW + timedelta(days=1)
    assert effective_start(tomorrow, NOW) == tomorrow
    with pytest.raises(InvalidRecipeError, match="cannot start in the past"):
        effective_start(NOW - timedelta(days=1), NOW)


def test_same_content_ignores_how_units_were_typed() -> None:
    names = {EXTRA_FETA: "Extra feta"}
    grams = base_lines([line(FETA, "60", "g")], INGREDIENTS)
    kilos = base_lines([line(FETA, "0.06", "kg")], INGREDIENTS)
    extra = base_modifier_lines([modifier_line(EXTRA_FETA)], INGREDIENTS, names)
    more = base_modifier_lines([modifier_line(EXTRA_FETA, "40")], INGREDIENTS, names)
    assert same_content(grams, extra, kilos, extra)
    assert not same_content(grams, extra, grams, more)

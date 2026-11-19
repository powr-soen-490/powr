# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Unit conversion: same-kind conversions, cross-kind refusals and unknown units."""

from decimal import Decimal

import pytest

from app.core.units import (
    IncompatibleUnitsError,
    UnitKind,
    UnknownUnitError,
    base_unit_for,
    convert,
    parse_unit,
    units_by_kind,
)


@pytest.mark.parametrize(
    ("quantity", "from_unit", "to_unit", "expected"),
    [
        ("0.2", "kg", "g", "200"),
        ("1", "lb", "g", "453.59237"),
        ("2", "L", "ml", "2000"),
        ("1", "dozen", "each", "12"),
        ("500", "g", "kg", "0.5"),
    ],
)
def test_converts_between_units_of_the_same_kind(
    quantity: str, from_unit: str, to_unit: str, expected: str
) -> None:
    assert convert(Decimal(quantity), from_unit, to_unit) == Decimal(expected)


def test_refuses_to_convert_across_kinds_and_names_the_ingredient() -> None:
    with pytest.raises(IncompatibleUnitsError, match="'ml' is a volume unit, but Feta is"):
        convert(Decimal(30), "ml", "g", subject="Feta")


def test_refuses_cross_kind_without_a_subject() -> None:
    message = "'kg' is a mass unit, but 'each' is measured by count"
    with pytest.raises(IncompatibleUnitsError, match=message):
        convert(Decimal(1), "kg", "each")


def test_unknown_unit_lists_the_supported_ones() -> None:
    with pytest.raises(UnknownUnitError, match=r"Unknown unit 'kgs'\. Supported units: mg, g"):
        parse_unit("kgs")


def test_accepts_capitals_spaces_and_aliases() -> None:
    assert parse_unit(" Grams ").code == "g"
    assert parse_unit("PCS").code == "each"


def test_base_units_and_grouping() -> None:
    assert base_unit_for(UnitKind.VOLUME).code == "ml"
    grouped = units_by_kind()
    assert grouped[UnitKind.COUNT] == ["each", "dozen"]
    assert "g" in grouped[UnitKind.MASS]

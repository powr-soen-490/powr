# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Units of measure: the single source of truth for every quantity powr stores.

Each unit has a kind (mass, volume or count) and a factor to its kind's base unit (g, ml or
each). Quantities are always stored in the base unit; conversion only happens between units of
the same kind, because grams of feta cannot be turned into millilitres without a density.
Factors are exact Decimals, so conversions never pick up float rounding.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class UnitKind(StrEnum):
    MASS = "mass"
    VOLUME = "volume"
    COUNT = "count"


@dataclass(frozen=True)
class Unit:
    code: str
    kind: UnitKind
    factor: Decimal  # how many base units one of this unit is


BASE_UNITS: dict[UnitKind, str] = {
    UnitKind.MASS: "g",
    UnitKind.VOLUME: "ml",
    UnitKind.COUNT: "each",
}

UNITS: dict[str, Unit] = {
    unit.code: unit
    for unit in (
        Unit("mg", UnitKind.MASS, Decimal("0.001")),
        Unit("g", UnitKind.MASS, Decimal(1)),
        Unit("kg", UnitKind.MASS, Decimal(1000)),
        Unit("oz", UnitKind.MASS, Decimal("28.349523125")),
        Unit("lb", UnitKind.MASS, Decimal("453.59237")),
        Unit("ml", UnitKind.VOLUME, Decimal(1)),
        Unit("l", UnitKind.VOLUME, Decimal(1000)),
        Unit("tsp", UnitKind.VOLUME, Decimal("4.92892159375")),
        Unit("tbsp", UnitKind.VOLUME, Decimal("14.78676478125")),
        Unit("fl_oz", UnitKind.VOLUME, Decimal("29.5735295625")),
        Unit("cup", UnitKind.VOLUME, Decimal("236.5882365")),
        Unit("each", UnitKind.COUNT, Decimal(1)),
        Unit("dozen", UnitKind.COUNT, Decimal(12)),
    )
}

# Other spellings people type, all lower case. Anything else is refused, never guessed.
ALIASES: dict[str, str] = {
    "gram": "g",
    "grams": "g",
    "kilogram": "kg",
    "kilograms": "kg",
    "lbs": "lb",
    "pound": "lb",
    "pounds": "lb",
    "ounce": "oz",
    "ounces": "oz",
    "litre": "l",
    "liter": "l",
    "litres": "l",
    "liters": "l",
    "millilitre": "ml",
    "milliliter": "ml",
    "fl oz": "fl_oz",
    "cups": "cup",
    "ea": "each",
    "pc": "each",
    "pcs": "each",
    "unit": "each",
    "units": "each",
}


class UnitError(ValueError):
    """A unit problem, with a message written for the kitchen manager."""


class UnknownUnitError(UnitError):
    pass


class IncompatibleUnitsError(UnitError):
    pass


def parse_unit(name: str) -> Unit:
    """The unit called ``name`` (any capitals, common spellings), or UnknownUnitError."""
    key = name.strip().lower()
    unit = UNITS.get(ALIASES.get(key, key))
    if unit is None:
        supported = ", ".join(UNITS)
        raise UnknownUnitError(f"Unknown unit '{name}'. Supported units: {supported}.")
    return unit


def base_unit_for(kind: UnitKind) -> Unit:
    return UNITS[BASE_UNITS[kind]]


def convert(quantity: Decimal, from_unit: str, to_unit: str, *, subject: str = "") -> Decimal:
    """``quantity`` in ``from_unit``, expressed in ``to_unit``.

    ``subject`` names what is measured ("Chicken breast"), for a clearer error when the
    kinds differ.
    """
    source = parse_unit(from_unit)
    target = parse_unit(to_unit)
    if source.kind != target.kind:
        measured = subject or f"'{target.code}'"
        raise IncompatibleUnitsError(
            f"'{source.code}' is a {source.kind} unit, but {measured} is measured by "
            f"{target.kind} ({target.code})."
        )
    return quantity * source.factor / target.factor


def units_by_kind() -> dict[UnitKind, list[str]]:
    """Every supported unit code, grouped by kind, smallest first."""
    grouped: dict[UnitKind, list[str]] = {kind: [] for kind in UnitKind}
    for unit in UNITS.values():
        grouped[unit.kind].append(unit.code)
    return grouped

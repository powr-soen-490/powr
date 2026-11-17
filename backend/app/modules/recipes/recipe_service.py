# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Business rules for recipes: versioned saves, modifiers, and which version applies when.

A recipe is a list of versions. Each version is in effect from its effective_from until the
next one starts, so a sale uses the version in effect when its order was opened, and editing
a recipe never changes the ingredients worked out for past sales. A new version starts now or
later, never in the past; it replaces any version scheduled to start at or after it.
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal, Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.units import parse_unit
from app.modules.recipes import ingredient_repository
from app.modules.recipes import recipe_repository as repository
from app.modules.recipes.ingredient_repository import Ingredient
from app.modules.recipes.ingredient_service import to_base
from app.modules.recipes.recipe_repository import Line, MenuItem, Modifier, ModifierLine, Version

# A date "now" sent by a client whose clock is a little behind is still accepted.
CLOCK_TOLERANCE = timedelta(minutes=5)
MODIFIER_SALES_DAYS = 90

Effect = Literal["add", "remove"]
VersionStatus = Literal["past", "current", "scheduled"]


class RecipeError(Exception):
    """A rule was broken; the message is written for the kitchen manager."""


class MenuItemNotFoundError(RecipeError):
    pass


class RecipeNotFoundError(RecipeError):
    pass


class InvalidRecipeError(RecipeError):
    pass


@dataclass(frozen=True)
class LineInput:
    ingredient_id: UUID
    quantity: Decimal
    unit: str


@dataclass(frozen=True)
class ModifierLineInput:
    menu_modifier_id: UUID
    ingredient_id: UUID
    effect: Effect
    quantity: Decimal
    unit: str


@dataclass(frozen=True)
class BaseLine:
    """A line ready to store: the quantity in base units, plus what was typed."""

    ingredient_id: UUID
    quantity: Decimal
    entered_quantity: Decimal
    entered_unit: str


@dataclass(frozen=True)
class BaseModifierLine(BaseLine):
    menu_modifier_id: UUID
    effect: Effect


@dataclass(frozen=True)
class Recipe:
    menu_item: MenuItem
    version: Version
    lines: list[Line]
    modifier_lines: list[ModifierLine]

    @property
    def total_cost(self) -> Decimal | None:
        """The base dish's cost at today's prices; None when an ingredient has no price."""
        costs = [line_cost(line) for line in self.lines]
        return None if None in costs else sum((c for c in costs if c is not None), Decimal(0))


@dataclass(frozen=True)
class VersionSummary:
    version: Version
    status: VersionStatus


def line_cost(line: Line | ModifierLine) -> Decimal | None:
    return None if line.unit_cost is None else line.quantity * line.unit_cost


def base_lines(lines: list[LineInput], ingredients: dict[UUID, Ingredient]) -> list[BaseLine]:
    """Checks the base dish's lines and converts them to base units."""
    if not lines:
        raise InvalidRecipeError("A recipe needs at least one ingredient.")
    converted = [_base_line(line, _usable(ingredients, line.ingredient_id)) for line in lines]
    _refuse_duplicates(
        (line.ingredient_id for line in lines),
        lambda key: f"{ingredients[key].name} is listed twice; combine it into one line.",
    )
    return converted


def base_modifier_lines(
    lines: list[ModifierLineInput],
    ingredients: dict[UUID, Ingredient],
    modifier_names: dict[UUID, str],
) -> list[BaseModifierLine]:
    """Checks the modifier lines and converts them to base units."""
    for line in lines:
        if line.menu_modifier_id not in modifier_names:
            raise InvalidRecipeError("A modifier in this recipe does not exist.")
    converted = [
        BaseModifierLine(
            **asdict(_base_line(line, _usable(ingredients, line.ingredient_id))),
            menu_modifier_id=line.menu_modifier_id,
            effect=line.effect,
        )
        for line in lines
    ]
    _refuse_duplicates(
        ((line.menu_modifier_id, line.ingredient_id) for line in lines),
        lambda key: (
            f"{ingredients[key[1]].name} is listed twice for “{modifier_names[key[0]]}”; "
            "combine it into one line."
        ),
    )
    return converted


class _QuantityLine(Protocol):
    @property
    def ingredient_id(self) -> UUID: ...
    @property
    def quantity(self) -> Decimal: ...


class _ModifierQuantityLine(_QuantityLine, Protocol):
    @property
    def menu_modifier_id(self) -> UUID: ...
    @property
    def effect(self) -> str: ...


def same_content(
    new_lines: Sequence[_QuantityLine],
    new_modifier_lines: Sequence[_ModifierQuantityLine],
    old_lines: Sequence[_QuantityLine],
    old_modifier_lines: Sequence[_ModifierQuantityLine],
) -> bool:
    """True when both versions use the same ingredients in the same base quantities,
    however the units were typed."""

    def lines(found: Sequence[_QuantityLine]) -> set[tuple[UUID, Decimal]]:
        return {(line.ingredient_id, line.quantity) for line in found}

    def modifiers(found: Sequence[_ModifierQuantityLine]) -> set[tuple[UUID, UUID, str, Decimal]]:
        return {(m.menu_modifier_id, m.ingredient_id, m.effect, m.quantity) for m in found}

    return lines(new_lines) == lines(old_lines) and modifiers(new_modifier_lines) == modifiers(
        old_modifier_lines
    )


def effective_start(requested: datetime | None, now: datetime) -> datetime:
    """When a new version starts: now by default, or a later time; never in the past."""
    if requested is None:
        return now
    if requested < now - CLOCK_TOLERANCE:
        raise InvalidRecipeError("A recipe change cannot start in the past; pick now or later.")
    return max(requested, now)


def save_recipe(
    db: Session,
    *,
    restaurant_id: UUID,
    menu_item_id: UUID,
    user_id: UUID,
    lines: list[LineInput],
    modifier_lines: list[ModifierLineInput],
    effective_from: datetime | None,
    now: datetime,
) -> tuple[Recipe, bool]:
    """Saves the recipe as a new version. Returns the version and whether it is new: a recipe
    identical to the latest version is not saved again."""
    item = _menu_item(db, restaurant_id, menu_item_id)
    start = effective_start(effective_from, now)
    ingredients = ingredient_repository.get_ingredients(
        db,
        restaurant_id=restaurant_id,
        ingredient_ids={line.ingredient_id for line in lines}
        | {line.ingredient_id for line in modifier_lines},
    )
    modifier_names = repository.get_modifier_names(
        db,
        restaurant_id=restaurant_id,
        modifier_ids=list({line.menu_modifier_id for line in modifier_lines}),
    )
    new_lines = base_lines(lines, ingredients)
    new_modifier_lines = base_modifier_lines(modifier_lines, ingredients, modifier_names)

    recipe_id = repository.get_or_create_recipe(
        db, restaurant_id=restaurant_id, menu_item_id=menu_item_id
    )
    latest = _latest(db, restaurant_id, recipe_id)
    if latest is not None and same_content(
        new_lines, new_modifier_lines, latest.lines, latest.modifier_lines
    ):
        db.rollback()
        return Recipe(item, latest.version, latest.lines, latest.modifier_lines), False

    repository.delete_versions_from(
        db, restaurant_id=restaurant_id, recipe_id=recipe_id, start=start
    )
    repository.insert_version(
        db,
        restaurant_id=restaurant_id,
        recipe_id=recipe_id,
        effective_from=start,
        item=item,
        created_by=user_id,
        lines=[asdict(line) for line in new_lines],
        modifier_lines=[asdict(line) for line in new_modifier_lines],
    )
    db.commit()
    return get_recipe(db, restaurant_id=restaurant_id, menu_item_id=menu_item_id, at=start), True


def get_recipe(db: Session, *, restaurant_id: UUID, menu_item_id: UUID, at: datetime) -> Recipe:
    """The version of the item's recipe in effect at ``at`` (a sale's opened_at, or now)."""
    item = _menu_item(db, restaurant_id, menu_item_id)
    recipe_id = repository.find_recipe_id(db, restaurant_id=restaurant_id, menu_item_id=item.id)
    version = None
    if recipe_id is not None:
        version = repository.version_at(db, restaurant_id=restaurant_id, recipe_id=recipe_id, at=at)
    if version is None:
        raise RecipeNotFoundError(f"{item.name} has no recipe in effect at that time.")
    return _with_lines(db, restaurant_id, item, version)


def list_versions(
    db: Session, *, restaurant_id: UUID, menu_item_id: UUID, now: datetime
) -> list[VersionSummary]:
    """Every version, newest first, marked past, current (in effect now) or scheduled."""
    item = _menu_item(db, restaurant_id, menu_item_id)
    recipe_id = repository.find_recipe_id(db, restaurant_id=restaurant_id, menu_item_id=item.id)
    if recipe_id is None:
        return []
    summaries = []
    current_found = False
    for version in repository.list_versions(db, restaurant_id=restaurant_id, recipe_id=recipe_id):
        status: VersionStatus = "scheduled"
        if version.effective_from <= now:
            status = "past" if current_found else "current"
            current_found = True
        summaries.append(VersionSummary(version=version, status=status))
    return summaries


def modifiers_for_item(
    db: Session, *, restaurant_id: UUID, menu_item_id: UUID, now: datetime
) -> list[Modifier]:
    """Modifiers Marco can map for this item, the ones sold with it lately first."""
    item = _menu_item(db, restaurant_id, menu_item_id)
    since = (now - timedelta(days=MODIFIER_SALES_DAYS)).date()
    return repository.modifiers_for_item(db, restaurant_id=restaurant_id, item=item, since=since)


@dataclass(frozen=True)
class _Content:
    version: Version
    lines: list[Line]
    modifier_lines: list[ModifierLine]


def _latest(db: Session, restaurant_id: UUID, recipe_id: UUID) -> _Content | None:
    versions = repository.list_versions(db, restaurant_id=restaurant_id, recipe_id=recipe_id)
    if not versions:
        return None
    latest = versions[0]
    return _Content(
        latest,
        repository.lines(db, restaurant_id=restaurant_id, version_id=latest.id),
        repository.modifier_lines(db, restaurant_id=restaurant_id, version_id=latest.id),
    )


def _with_lines(db: Session, restaurant_id: UUID, item: MenuItem, version: Version) -> Recipe:
    return Recipe(
        menu_item=item,
        version=version,
        lines=repository.lines(db, restaurant_id=restaurant_id, version_id=version.id),
        modifier_lines=repository.modifier_lines(
            db, restaurant_id=restaurant_id, version_id=version.id
        ),
    )


def _menu_item(db: Session, restaurant_id: UUID, menu_item_id: UUID) -> MenuItem:
    item = repository.get_menu_item(db, restaurant_id=restaurant_id, menu_item_id=menu_item_id)
    if item is None:
        raise MenuItemNotFoundError("This menu item does not exist.")
    return item


def _usable(ingredients: dict[UUID, Ingredient], ingredient_id: UUID) -> Ingredient:
    ingredient = ingredients.get(ingredient_id)
    if ingredient is None:
        raise InvalidRecipeError("An ingredient in this recipe does not exist.")
    if not ingredient.is_active:
        raise InvalidRecipeError(
            f"{ingredient.name} is archived; restore it or pick another ingredient."
        )
    return ingredient


def _base_line(line: LineInput | ModifierLineInput, ingredient: Ingredient) -> BaseLine:
    return BaseLine(
        ingredient_id=ingredient.id,
        quantity=to_base(line.quantity, line.unit, ingredient.base_unit, subject=ingredient.name),
        entered_quantity=line.quantity,
        entered_unit=parse_unit(line.unit).code,
    )


def _refuse_duplicates[K](keys: Iterable[K], message: Callable[[K], str]) -> None:
    seen: set[K] = set()
    for key in keys:
        if key in seen:
            raise InvalidRecipeError(message(key))
        seen.add(key)

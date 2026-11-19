# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""The recipe of each POS menu item: read it, save a new version, see its history.

Everyone in the restaurant can read recipes; RECIPE_EDITOR_ROLES (app/core/auth.py) can save
them.
"""

from datetime import UTC, datetime
from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import AwareDatetime
from sqlalchemy.orm import Session

from app.core.auth import CurrentUserDep, RecipeEditorDep
from app.core.database import get_db
from app.core.units import UnitError
from app.modules.recipes import coverage_service, ingredient_service
from app.modules.recipes import recipe_service as service
from app.modules.recipes.recipe_repository import Line, ModifierLine, Version
from app.schemas.recipes import (
    CoverageResponse,
    MenuItemModifierResponse,
    MenuItemSummaryResponse,
    MenuOverviewResponse,
    ModifierLineResponse,
    RecipeLineResponse,
    RecipeResponse,
    RecipeSaveRequest,
    RecipeVersionResponse,
)

router = APIRouter(prefix="/api/menu-items", tags=["recipes"])
DbSession = Annotated[Session, Depends(get_db)]

# The message of each error is written for the kitchen manager, so it is sent as the detail.
RECIPE_ERRORS: dict[type[Exception], int] = {
    UnitError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ingredient_service.InvalidQuantityError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    service.InvalidRecipeError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    service.MenuItemNotFoundError: status.HTTP_404_NOT_FOUND,
    service.RecipeNotFoundError: status.HTTP_404_NOT_FOUND,
}
HANDLED = (UnitError, ingredient_service.IngredientError, service.RecipeError)


@router.get("", response_model=MenuOverviewResponse)
def menu_overview(
    user: CurrentUserDep, db: DbSession, status: coverage_service.Status | None = None
) -> MenuOverviewResponse:
    """The menu mapping list: each item's status, and coverage by items and 90-day revenue.

    Unmapped items come first, highest revenue first. ``status`` filters the items only;
    coverage always covers the whole menu.
    """
    coverage, items = coverage_service.menu_overview(
        db, restaurant_id=user.restaurant_id, now=datetime.now(UTC), status=status
    )
    return MenuOverviewResponse(
        coverage=CoverageResponse(
            items_total=coverage.items_total,
            items_mapped=coverage.items_mapped,
            item_share=coverage.item_share,
            revenue_total=coverage.revenue_total,
            revenue_mapped=coverage.revenue_mapped,
            revenue_share=coverage.revenue_share,
        ),
        items=[
            MenuItemSummaryResponse(
                id=item.facts.id,
                name=item.facts.name,
                price=item.facts.price,
                is_active=item.facts.is_active,
                status=item.status,
                review_reasons=item.review_reasons,
                unmapped_modifiers=item.facts.unmapped_modifiers,
                revenue_90d=item.facts.revenue,
                recipe_effective_from=item.facts.effective_from,
            )
            for item in items
        ],
    )


@router.get("/{menu_item_id}/recipe", response_model=RecipeResponse)
def get_recipe(
    menu_item_id: UUID,
    user: CurrentUserDep,
    db: DbSession,
    at: AwareDatetime | None = None,
) -> RecipeResponse:
    """The version in effect now, or at ``at`` (404 when there is none)."""
    try:
        recipe = service.get_recipe(
            db,
            restaurant_id=user.restaurant_id,
            menu_item_id=menu_item_id,
            at=at or datetime.now(UTC),
        )
    except HANDLED as exc:
        _error(exc)
    return _recipe(recipe)


@router.put("/{menu_item_id}/recipe", response_model=RecipeResponse)
def save_recipe(
    menu_item_id: UUID,
    payload: RecipeSaveRequest,
    response: Response,
    user: RecipeEditorDep,
    db: DbSession,
) -> RecipeResponse:
    """Save the recipe as a new version (201). Past sales keep the version they used.

    A recipe identical to the latest version is not saved again (200, that version).
    """
    try:
        recipe, created = service.save_recipe(
            db,
            restaurant_id=user.restaurant_id,
            menu_item_id=menu_item_id,
            user_id=user.user_id,
            lines=[service.LineInput(**line.model_dump()) for line in payload.lines],
            modifier_lines=[
                service.ModifierLineInput(**line.model_dump()) for line in payload.modifier_lines
            ],
            effective_from=payload.effective_from,
            now=datetime.now(UTC),
        )
    except HANDLED as exc:
        _error(exc)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return _recipe(recipe)


@router.get("/{menu_item_id}/recipe/versions", response_model=list[RecipeVersionResponse])
def list_versions(
    menu_item_id: UUID, user: CurrentUserDep, db: DbSession
) -> list[RecipeVersionResponse]:
    """Every version with its effective date, newest first; empty when never mapped."""
    try:
        summaries = service.list_versions(
            db, restaurant_id=user.restaurant_id, menu_item_id=menu_item_id, now=datetime.now(UTC)
        )
    except HANDLED as exc:
        _error(exc)
    return [_version(s.version, s.status) for s in summaries]


@router.get("/{menu_item_id}/modifiers", response_model=list[MenuItemModifierResponse])
def list_modifiers(
    menu_item_id: UUID, user: CurrentUserDep, db: DbSession
) -> list[MenuItemModifierResponse]:
    """POS modifiers to map for this item, those sold with it in the last 90 days first."""
    try:
        modifiers = service.modifiers_for_item(
            db, restaurant_id=user.restaurant_id, menu_item_id=menu_item_id, now=datetime.now(UTC)
        )
    except HANDLED as exc:
        _error(exc)
    return [
        MenuItemModifierResponse(
            id=m.id,
            name=m.name,
            group_name=m.group_name,
            price=m.price,
            sold_with_item=m.sold_with_item,
        )
        for m in modifiers
    ]


def _error(exc: Exception) -> NoReturn:
    code = next(code for kind, code in RECIPE_ERRORS.items() if isinstance(exc, kind))
    raise HTTPException(status_code=code, detail=str(exc)) from exc


def _recipe(recipe: service.Recipe) -> RecipeResponse:
    return RecipeResponse(
        menu_item_id=recipe.menu_item.id,
        menu_item_name=recipe.menu_item.name,
        version=_version(recipe.version),
        lines=[RecipeLineResponse(**_line(line)) for line in recipe.lines],
        modifier_lines=[
            ModifierLineResponse(
                **_line(line),
                menu_modifier_id=line.menu_modifier_id,
                modifier_name=line.modifier_name,
                effect=line.effect,  # the database only allows add and remove
            )
            for line in recipe.modifier_lines
        ],
        total_cost=recipe.total_cost,
    )


def _line(line: Line | ModifierLine) -> dict[str, object]:
    return {
        "ingredient_id": line.ingredient_id,
        "ingredient_name": line.ingredient_name,
        "quantity": line.quantity,
        "base_unit": line.base_unit,
        "entered_quantity": line.entered_quantity,
        "entered_unit": line.entered_unit,
        "cost": service.line_cost(line),
        "unit_cost": line.unit_cost,
        "vendor_name": line.vendor_name,
        "ingredient_active": line.ingredient_active,
    }


def _version(version: Version, status: str | None = None) -> RecipeVersionResponse:
    return RecipeVersionResponse(
        id=version.id,
        effective_from=version.effective_from,
        status=status,
        menu_item_name=version.menu_item_name,
        menu_item_price=version.menu_item_price,
        created_by_email=version.created_by_email,
        created_at=version.created_at,
    )

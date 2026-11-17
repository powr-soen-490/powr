# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Units, vendors and ingredients for the recipe editor.

Everyone in the restaurant can read them; RECIPE_EDITOR_ROLES (app/core/auth.py) can change
them.
"""

from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.auth import CurrentUserDep, RecipeEditorDep
from app.core.database import get_db
from app.core.units import BASE_UNITS, UnitError, units_by_kind
from app.modules.recipes import ingredient_service as service
from app.modules.recipes.ingredient_repository import Ingredient, Vendor
from app.schemas.recipes import (
    IngredientCreateRequest,
    IngredientResponse,
    IngredientUpdateRequest,
    UnitGroupResponse,
    VendorCreateRequest,
    VendorResponse,
)

router = APIRouter(prefix="/api", tags=["ingredients"])
DbSession = Annotated[Session, Depends(get_db)]

# The message of each error is written for the kitchen manager, so it is sent as the detail.
INGREDIENT_ERRORS: dict[type[Exception], int] = {
    UnitError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    service.InvalidQuantityError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    service.VendorNotFoundError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    service.DuplicateIngredientError: status.HTTP_409_CONFLICT,
    service.IngredientNotFoundError: status.HTTP_404_NOT_FOUND,
}


@router.get("/units", response_model=list[UnitGroupResponse])
def list_units() -> list[UnitGroupResponse]:
    """Every supported unit, grouped by kind, with the kind's base unit."""
    return [
        UnitGroupResponse(kind=kind.value, base_unit=BASE_UNITS[kind], units=units)
        for kind, units in units_by_kind().items()
    ]


@router.get("/vendors", response_model=list[VendorResponse])
def list_vendors(user: CurrentUserDep, db: DbSession) -> list[VendorResponse]:
    return [_vendor(v) for v in service.list_vendors(db, restaurant_id=user.restaurant_id)]


@router.post("/vendors", status_code=status.HTTP_201_CREATED, response_model=VendorResponse)
def create_vendor(
    payload: VendorCreateRequest, user: RecipeEditorDep, db: DbSession
) -> VendorResponse:
    vendor = service.create_vendor(
        db, restaurant_id=user.restaurant_id, name=payload.name, contact_email=payload.contact_email
    )
    return _vendor(vendor)


@router.get("/ingredients", response_model=list[IngredientResponse])
def search_ingredients(
    user: CurrentUserDep,
    db: DbSession,
    q: Annotated[str, Query(max_length=255, description="Part of the name")] = "",
    include_inactive: bool = False,
) -> list[IngredientResponse]:
    """Ingredients whose name contains q, names starting with q first (at most 50)."""
    found = service.search_ingredients(
        db, restaurant_id=user.restaurant_id, query=q, include_inactive=include_inactive
    )
    return [_ingredient(i) for i in found]


@router.post("/ingredients", status_code=status.HTTP_201_CREATED, response_model=IngredientResponse)
def create_ingredient(
    payload: IngredientCreateRequest, user: RecipeEditorDep, db: DbSession
) -> IngredientResponse:
    """Create an ingredient; the editor also uses this to add a missing one inline."""
    new = service.NewIngredient(
        name=payload.name,
        unit=payload.base_unit,
        vendor_id=payload.vendor_id,
        pack_size=payload.pack_size,
        pack_unit=payload.pack_unit,
        pack_price=payload.pack_price,
    )
    try:
        ingredient = service.create_ingredient(db, restaurant_id=user.restaurant_id, new=new)
    except (service.IngredientError, UnitError) as exc:
        _error(exc)
    return _ingredient(ingredient)


@router.patch("/ingredients/{ingredient_id}", response_model=IngredientResponse)
def update_ingredient(
    ingredient_id: UUID, payload: IngredientUpdateRequest, user: RecipeEditorDep, db: DbSession
) -> IngredientResponse:
    """Change the fields sent. Send is_active=false to archive an ingredient."""
    try:
        ingredient = service.update_ingredient(
            db,
            restaurant_id=user.restaurant_id,
            ingredient_id=ingredient_id,
            changes=payload.model_dump(exclude_unset=True),
        )
    except (service.IngredientError, UnitError) as exc:
        _error(exc)
    return _ingredient(ingredient)


def _error(exc: Exception) -> NoReturn:
    code = next(code for kind, code in INGREDIENT_ERRORS.items() if isinstance(exc, kind))
    raise HTTPException(status_code=code, detail=str(exc)) from exc


def _vendor(vendor: Vendor) -> VendorResponse:
    return VendorResponse(id=vendor.id, name=vendor.name, contact_email=vendor.contact_email)


def _ingredient(ingredient: Ingredient) -> IngredientResponse:
    return IngredientResponse(
        id=ingredient.id,
        name=ingredient.name,
        kind=ingredient.kind,
        base_unit=ingredient.base_unit,
        vendor_id=ingredient.vendor_id,
        vendor_name=ingredient.vendor_name,
        pack_size=ingredient.pack_size,
        pack_price=ingredient.pack_price,
        unit_cost=ingredient.unit_cost,
        is_active=ingredient.is_active,
    )

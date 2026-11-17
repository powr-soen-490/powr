# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Pydantic request and response models for units, vendors, ingredients and recipes."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field, StringConstraints

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
UnitName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)]
# Above zero, and small enough that any unit still fits the database once in base units.
Quantity = Annotated[Decimal, Field(gt=0, le=100_000, decimal_places=4)]
Price = Annotated[Decimal, Field(ge=0, le=99_999_999, decimal_places=2)]


class UnitGroupResponse(BaseModel):
    kind: str
    base_unit: str
    units: list[str]


class VendorCreateRequest(BaseModel):
    name: Name
    contact_email: Name | None = None


class VendorResponse(BaseModel):
    id: UUID
    name: str
    contact_email: str | None


class IngredientCreateRequest(BaseModel):
    name: Name
    base_unit: UnitName = Field(
        description="Any unit of the ingredient's kind (kg, ml, each...); the ingredient is "
        "stored in that kind's base unit (g, ml or each)."
    )
    vendor_id: UUID | None = None
    pack_size: Quantity | None = Field(default=None, description="How much one pack holds.")
    pack_unit: UnitName | None = Field(
        default=None, description="The unit of pack_size; the base unit when omitted."
    )
    pack_price: Price | None = None


class IngredientUpdateRequest(BaseModel):
    """Only the fields sent are changed; null clears vendor_id, pack_size and pack_price."""

    name: Name | None = None
    is_active: bool | None = None
    vendor_id: UUID | None = None
    pack_size: Quantity | None = None
    pack_unit: UnitName | None = None
    pack_price: Price | None = None


class IngredientResponse(BaseModel):
    id: UUID
    name: str
    kind: str
    base_unit: str
    vendor_id: UUID | None
    vendor_name: str | None
    pack_size: Decimal | None = Field(description="In base_unit.")
    pack_price: Decimal | None
    unit_cost: Decimal | None = Field(description="Price of one base unit; null without a pack.")
    is_active: bool


class RecipeLineRequest(BaseModel):
    ingredient_id: UUID
    quantity: Quantity
    unit: UnitName = Field(description="Any unit of the ingredient's kind, e.g. g, kg, oz.")


class ModifierLineRequest(BaseModel):
    """What a POS modifier does to the dish: "Extra feta" adds 30 g of feta."""

    menu_modifier_id: UUID
    ingredient_id: UUID
    effect: Literal["add", "remove"]
    quantity: Quantity
    unit: UnitName


class RecipeSaveRequest(BaseModel):
    effective_from: AwareDatetime | None = Field(
        default=None, description="When this version starts: now when omitted, never the past."
    )
    lines: list[RecipeLineRequest] = Field(min_length=1, max_length=100)
    modifier_lines: list[ModifierLineRequest] = Field(default_factory=list, max_length=200)


class RecipeLineResponse(BaseModel):
    ingredient_id: UUID
    ingredient_name: str
    quantity: Decimal = Field(description="In base_unit.")
    base_unit: str
    entered_quantity: Decimal
    entered_unit: str
    cost: Decimal | None = Field(description="At today's prices; null when unpriced.")


class ModifierLineResponse(RecipeLineResponse):
    menu_modifier_id: UUID
    modifier_name: str
    effect: Literal["add", "remove"]


class RecipeVersionResponse(BaseModel):
    id: UUID
    effective_from: datetime
    status: Literal["past", "current", "scheduled"] | None = None
    menu_item_name: str = Field(description="The item's name when this version was saved.")
    menu_item_price: Decimal | None
    created_by_email: str | None
    created_at: datetime


class RecipeResponse(BaseModel):
    menu_item_id: UUID
    menu_item_name: str
    version: RecipeVersionResponse
    lines: list[RecipeLineResponse]
    modifier_lines: list[ModifierLineResponse]
    total_cost: Decimal | None = Field(
        description="Cost of the base dish at today's prices; null if an ingredient is unpriced."
    )


class MenuItemModifierResponse(BaseModel):
    id: UUID
    name: str
    group_name: str
    price: Decimal | None
    sold_with_item: int = Field(description="Times sold with this item in the last 90 days.")


class CoverageResponse(BaseModel):
    items_total: int
    items_mapped: int = Field(description="Items with a recipe in effect (mapped or review).")
    item_share: Decimal | None = Field(description="items_mapped / items_total, 0 to 1.")
    revenue_total: Decimal = Field(description="Revenue over the last 90 days.")
    revenue_mapped: Decimal
    revenue_share: Decimal | None = Field(description="revenue_mapped / revenue_total, 0 to 1.")


class MenuItemSummaryResponse(BaseModel):
    id: UUID
    name: str
    price: Decimal | None
    is_active: bool
    status: Literal["unmapped", "needs_review", "mapped"]
    review_reasons: list[Literal["inactive_ingredient", "menu_item_changed", "unmapped_modifier"]]
    unmapped_modifiers: list[str] = Field(description="Sold with the item, without lines.")
    revenue_90d: Decimal
    recipe_effective_from: datetime | None = Field(description="Of the version in effect now.")


class MenuOverviewResponse(BaseModel):
    coverage: CoverageResponse
    items: list[MenuItemSummaryResponse] = Field(
        description="Unmapped first, then needs review, then mapped; by revenue in each."
    )

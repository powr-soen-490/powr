# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Pydantic request and response models for units, vendors, ingredients and recipes."""

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints

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

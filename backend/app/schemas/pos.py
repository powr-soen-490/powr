# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Pydantic request and response models for POS credentials endpoints."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

PosProvider = Literal["TOAST", "SQUARE"]


class PosCredentialsRequest(BaseModel):
    pos_name: PosProvider
    client_id: str = Field(..., min_length=1)
    client_secret: str = Field(..., min_length=1)
    # On PATCH, omitted/null token and expiry leave the stored values unchanged.
    access_token: str | None = Field(default=None, min_length=1)
    expires_at: datetime | None = None


class PosCredentialsResponse(BaseModel):
    id: UUID
    pos_name: str
    client_id: str
    expires_at: datetime | None


class SetPosResponse(BaseModel):
    message: str


class DailySalesStats(BaseModel):
    """Daily sales summary for a specific business date."""

    date: str = Field(..., description="Business date in YYYY-MM-DD format")
    orders: int = Field(..., ge=0, description="Number of orders on this date")
    items: Decimal = Field(..., ge=0, description="Total quantity of items sold")
    revenue: Decimal = Field(..., ge=0, description="Total revenue for the date")


class SalesSummaryResponse(BaseModel):
    """30-day (or custom window) sales summary by date."""

    days: int = Field(..., ge=1, description="Number of days in the summary window")
    start_date: str = Field(..., description="Start date in YYYY-MM-DD format")
    end_date: str = Field(..., description="End date in YYYY-MM-DD format")
    total_orders: int = Field(..., ge=0, description="Total orders in the period")
    total_items: Decimal = Field(..., ge=0, description="Total quantity sold in the period")
    total_revenue: Decimal = Field(..., ge=0, description="Total revenue in the period")
    daily_stats: list[DailySalesStats] = Field(
        default_factory=list, description="Daily breakdown of sales"
    )


class MenuModifierOptionResponse(BaseModel):
    """One choice inside a modifier group."""

    option_id: str
    option_name: str
    price: Decimal | None = None


class MenuModifierGroupResponse(BaseModel):
    """A set of modifier options offered on a menu item."""

    group_id: str
    group_name: str
    min_selections: int
    max_selections: int | None = None
    options: list[MenuModifierOptionResponse]


class MenuItemResponse(BaseModel):
    """Menu item of POS System."""

    item_id: str
    item_name: str
    price: Decimal | None = None
    currency: str
    modifier_groups: list[MenuModifierGroupResponse]


class MenuResponse(BaseModel):
    """Complete menu with all items."""

    currency: str
    items: list[MenuItemResponse]

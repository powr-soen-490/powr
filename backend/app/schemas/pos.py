# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Pydantic request and response models for the POS endpoints."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

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


class ToastConnectRequest(BaseModel):
    """Toast credentials to check; the restaurant GUID is found from them, never typed."""

    client_id: str = Field(..., min_length=1, max_length=255)
    client_secret: str = Field(..., min_length=1, max_length=1024)


class ToastConnectionResponse(BaseModel):
    """The Toast restaurant linked to the caller's restaurant."""

    location_id: str
    # None for connections saved before the name was stored.
    location_name: str | None


class SalesImportRequest(BaseModel):
    """The business days to import; both are optional (see the import endpoint)."""

    model_config = ConfigDict(extra="forbid")

    start_date: date | None = None
    end_date: date | None = None


class SalesImportResponse(BaseModel):
    """A sales import job, as the Sales Import page shows it."""

    id: UUID
    status: Literal["running", "failed", "done"]
    start_date: date
    end_date: date
    # Every business day up to this one is saved; null before the first day is done.
    last_completed_date: date | None
    days_completed: int = Field(..., ge=0)
    total_days: int = Field(..., ge=1)
    percent: int = Field(..., ge=0, le=100, description="Business days done, out of 100")
    orders_imported: int = Field(..., ge=0)
    items_imported: int = Field(..., ge=0, description="Sale lines saved")
    # Why the import stopped, written for the owner; null unless it failed.
    error: str | None
    created_at: datetime
    finished_at: datetime | None

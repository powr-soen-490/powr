# Source-File AI Declaration
# AI contribution: 50% or more AI-generated

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator


class PosConnection(BaseModel):
    """Connection to a POS location"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    restaurant_id: UUID
    provider: str = Field(min_length=1, max_length=255)
    location_id: str = Field(min_length=1, max_length=255)


class MenuModifierOption(BaseModel):
    """One choice inside a modifier group, e.g. "Extra cheese"."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    option_id: str = Field(min_length=1, max_length=255)
    option_name: str = Field(min_length=1, max_length=255)
    # None when the POS prices the option by size or sequence instead of a fixed amount.
    price: Decimal | None = Field(default=None, ge=Decimal("0"), allow_inf_nan=False)


class MenuModifierGroup(BaseModel):
    """A set of modifier options offered on a menu item, e.g. "Toppings"."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    group_id: str = Field(min_length=1, max_length=255)
    group_name: str = Field(min_length=1, max_length=255)
    min_selections: int = Field(default=0, ge=0)
    # None means the guest may pick any number of options.
    max_selections: int | None = Field(default=None, ge=0)
    options: tuple[MenuModifierOption, ...] = ()


class MenuItem(BaseModel):
    """Menu item of POS System"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    connection_id: UUID
    restaurant_id: UUID
    item_id: str = Field(min_length=1, max_length=255)
    item_name: str = Field(min_length=1, max_length=255)
    # None when the price is only known at sale time (size-based or open price).
    price: Decimal | None = Field(default=None, ge=Decimal("0"), allow_inf_nan=False)
    currency: str = Field(min_length=1, max_length=3)
    modifier_groups: tuple[MenuModifierGroup, ...] = ()


class SaleModifier(BaseModel):
    """A modifier chosen on a sold item; ingredient usage depends on it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: str = Field(min_length=1, max_length=255)
    item_name: str = Field(min_length=1, max_length=255)
    quantity: Decimal = Field(gt=Decimal("0"), allow_inf_nan=False)


class SaleLine(BaseModel):
    """One sold menu item, normalized from a provider's order."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    connection_id: UUID
    restaurant_id: UUID
    order_id: str = Field(min_length=1, max_length=255)
    line_id: str = Field(min_length=1, max_length=255)
    item_id: str = Field(min_length=1, max_length=255)
    item_name: str = Field(min_length=1, max_length=255)
    quantity: Decimal = Field(gt=Decimal("0"), allow_inf_nan=False)
    timestamp: AwareDatetime
    # The restaurant's business day; a sale after midnight still counts for the night before.
    business_date: date
    # Net amount charged for the line after discounts, when the provider reports it.
    price: Decimal | None = Field(default=None, ge=Decimal("0"), allow_inf_nan=False)
    modifiers: tuple[SaleModifier, ...] = ()

    # True when the POS voided or deleted the line, its check or its order, so the importer
    # can undo a line it saved before the void.
    is_voided: bool = False

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)


class StockItem(BaseModel):
    """Stock item of POS System"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    connection_id: UUID
    restaurant_id: UUID
    item_id: str = Field(min_length=1, max_length=255)
    # Optional because some providers (Toast) report stock by item ID only.
    item_name: str | None = Field(default=None, min_length=1, max_length=255)
    quantity: Decimal | None = Field(default=None, allow_inf_nan=False)
    is_available: bool | None = None

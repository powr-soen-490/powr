# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Toast-specific API endpoints for fetching sales summaries and menus."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.auth import OwnerDep
from app.core.config import get_settings
from app.core.database import get_db
from app.integrations.pos.toast.adapter import ToastAdapter
from app.integrations.pos.toast.client import (
    ToastApiError,
    ToastAuthenticationError,
    ToastCredentials,
)
from app.modules.pos import service
from app.schemas.pos import (
    DailySalesStats,
    MenuItemResponse,
    MenuModifierGroupResponse,
    MenuModifierOptionResponse,
    MenuResponse,
    SalesSummaryResponse,
)

router = APIRouter(prefix="/api/pos/toast", tags=["toast"])
DbSession = Annotated[Session, Depends(get_db)]
logger = logging.getLogger(__name__)


def _get_toast_adapter(db: Session, restaurant_id: UUID) -> ToastAdapter:
    """Create a ToastAdapter instance for a restaurant, or raise HTTPException if not configured."""
    # Get Toast credentials
    try:
        credentials_data = service.get_credentials(db, "TOAST")
    except service.CredentialsStorageError as exc:
        logger.exception("Failed to retrieve Toast credentials")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve Toast credentials.",
        ) from exc

    if not credentials_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Toast credentials not configured.",
        )

    # Get Toast connection for this restaurant
    try:
        connection = service.get_connection(db, restaurant_id, "TOAST")
    except service.ConnectionStorageError as exc:
        logger.exception("Failed to retrieve Toast connection for restaurant %s", restaurant_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve Toast connection.",
        ) from exc
    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Toast connection not configured for this restaurant.",
        )

    credentials = ToastCredentials(
        client_id=credentials_data["client_id"],
        client_secret=credentials_data["client_secret"],
    )

    return ToastAdapter(
        connection,
        credentials,
        currency="USD",
        base_url=get_settings().toast_api_base_url,
    )


@router.get("/sales-summary", response_model=SalesSummaryResponse)
def get_sales_summary(
    user: OwnerDep,
    db: DbSession,
    days: int = Query(30, ge=1, le=365, description="Number of days to pull"),
) -> SalesSummaryResponse:
    """Fetch and summarize sales data for the past N days from Toast.

    Only owners may call this endpoint. Returns orders, items, and revenue aggregated by day.
    """
    adapter = _get_toast_adapter(db, user.restaurant_id)

    try:
        if not adapter.authenticate():
            raise ToastAuthenticationError("Toast rejected the credentials.")

        # Calculate time window
        end_time = datetime.now(UTC)
        start_time = end_time - timedelta(days=days)

        # Fetch orders
        orders = adapter.fetch_orders(start_time, end_time)

        # Aggregate by business date
        summary = service.aggregate_sales(orders, start_time.date(), end_time.date())

        # Build response
        daily_list: list[DailySalesStats] = []
        for date_str in sorted(summary.daily):
            stat = summary.daily[date_str]
            orders_set = stat["orders"]
            items_count = stat["items"]
            revenue_amount = stat["revenue"]
            daily_list.append(
                DailySalesStats(
                    date=date_str,
                    orders=len(orders_set),
                    items=items_count,
                    revenue=revenue_amount,
                )
            )
        return SalesSummaryResponse(
            days=days,
            start_date=str(start_time.date()),
            end_date=str(end_time.date()),
            total_orders=summary.total_orders,
            total_items=summary.total_items,
            total_revenue=summary.total_revenue,
            daily_stats=daily_list,
        )

    except ToastAuthenticationError as exc:
        logger.warning("Toast authentication failed for restaurant %s", user.restaurant_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Toast authentication failed. Check credentials.",
        ) from exc
    except ToastApiError as exc:
        logger.exception("Toast API error for restaurant %s", user.restaurant_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Toast API error. Please try again later.",
        ) from exc
    finally:
        adapter.close()


@router.get("/menu", response_model=MenuResponse)
def get_menu(
    user: OwnerDep,
    db: DbSession,
) -> MenuResponse:
    """Fetch the restaurant's menu items from Toast.

    Only owners may call this endpoint. Returns all menu items with prices and modifiers.
    """
    adapter = _get_toast_adapter(db, user.restaurant_id)

    try:
        if not adapter.authenticate():
            raise ToastAuthenticationError("Toast rejected the credentials.")

        # Fetch menu items
        menu_items = adapter.fetch_menu_items()

        # Convert to response models
        items_response: list[MenuItemResponse] = []
        currency = "USD"  # Default until currency is stored on the POS connection

        for item in menu_items:
            currency = item.currency
            modifier_groups: list[MenuModifierGroupResponse] = []
            for group in item.modifier_groups:
                options: list[MenuModifierOptionResponse] = []
                for option in group.options:
                    options.append(
                        MenuModifierOptionResponse(
                            option_id=option.option_id,
                            option_name=option.option_name,
                            price=option.price,
                        )
                    )
                modifier_groups.append(
                    MenuModifierGroupResponse(
                        group_id=group.group_id,
                        group_name=group.group_name,
                        min_selections=group.min_selections,
                        max_selections=group.max_selections,
                        options=options,
                    )
                )

            items_response.append(
                MenuItemResponse(
                    item_id=item.item_id,
                    item_name=item.item_name,
                    price=item.price,
                    currency=currency,
                    modifier_groups=modifier_groups,
                )
            )

        return MenuResponse(currency=currency, items=items_response)

    except ToastAuthenticationError as exc:
        logger.warning("Toast authentication failed for restaurant %s", user.restaurant_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Toast authentication failed. Check credentials.",
        ) from exc
    except ToastApiError as exc:
        logger.exception("Toast API error for restaurant %s", user.restaurant_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Toast API error. Please try again later.",
        ) from exc
    finally:
        adapter.close()

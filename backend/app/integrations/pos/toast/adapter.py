# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""PosAdapter implementation for Toast's read-only Standard API access."""

import logging
from collections.abc import Iterator
from datetime import datetime
from typing import Any

import httpx2

from app.integrations.pos.interface import PosAdapter
from app.integrations.pos.models import MenuItem, PosConnection, SaleLine, StockItem
from app.integrations.pos.toast.client import (
    ToastApiError,
    ToastAuthenticationError,
    ToastClient,
    ToastCredentials,
)
from app.integrations.pos.toast.menus import MENUS_PATH, menu_items_from_toast
from app.integrations.pos.toast.orders import (
    ORDERS_PAGE_SIZE,
    ORDERS_PATH,
    order_windows,
    sale_lines_from_order,
    toast_datetime,
)

logger = logging.getLogger(__name__)

# A safety stop: 1000 full pages is 100,000 orders in one week, far beyond one restaurant.
MAX_ORDER_PAGES_PER_WINDOW = 1000


class ToastAdapter(PosAdapter):
    """Reads one Toast location; ``connection.location_id`` is the Toast restaurant GUID."""

    def __init__(
        self,
        connection: PosConnection,
        credentials: ToastCredentials,
        *,
        currency: str,
        base_url: str,
        transport: httpx2.BaseTransport | None = None,
    ) -> None:
        super().__init__(connection)
        self.currency = currency
        self._client = ToastClient(
            credentials,
            restaurant_guid=connection.location_id,
            base_url=base_url,
            transport=transport,
        )

    def authenticate(self) -> bool:
        try:
            self._client.login()
        except ToastAuthenticationError:
            logger.warning("Toast authentication failed for connection %s", self.connection.id)
            return False
        return True

    def fetch_menu_items(self) -> list[MenuItem]:
        items = menu_items_from_toast(self._client.get(MENUS_PATH), self.connection, self.currency)
        logger.info("Fetched %d Toast menu items for connection %s", len(items), self.connection.id)
        return items

    def fetch_orders(self, start_time: datetime, end_time: datetime) -> list[SaleLine]:
        """Sale lines from orders modified in [start_time, end_time).

        Toast filters ordersBulk by modifiedDate, so an older order that was changed in the
        range (for example voided) is returned too; callers deduplicate by order and line ID.
        """
        lines: list[SaleLine] = []
        for window_start, window_end in order_windows(start_time, end_time):
            for order in self._orders_in_window(window_start, window_end):
                lines.extend(sale_lines_from_order(order, self.connection))
        logger.info("Fetched %d Toast sale lines for connection %s", len(lines), self.connection.id)
        return lines

    def fetch_stock_items(self) -> list[StockItem]:
        raise NotImplementedError("Toast stock is not implemented yet.")

    def _orders_in_window(self, start: datetime, end: datetime) -> Iterator[dict[str, Any]]:
        """Request pages until one comes back with fewer than ORDERS_PAGE_SIZE orders."""
        for page in range(1, MAX_ORDER_PAGES_PER_WINDOW + 1):
            orders = self._client.get(
                ORDERS_PATH,
                params={
                    "startDate": toast_datetime(start),
                    "endDate": toast_datetime(end),
                    "pageSize": ORDERS_PAGE_SIZE,
                    "page": page,
                },
            )
            if not isinstance(orders, list):
                raise ToastApiError("Toast orders response is not a JSON array.")
            yield from orders
            if len(orders) < ORDERS_PAGE_SIZE:
                return
        raise ToastApiError(f"Toast returned more than {MAX_ORDER_PAGES_PER_WINDOW} order pages.")

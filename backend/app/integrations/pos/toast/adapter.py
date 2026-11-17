# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""PosAdapter implementation for Toast's read-only Standard API access."""

import logging
import time
from collections.abc import Callable, Iterator
from datetime import date, datetime
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
    orders_on_business_date,
    sale_lines_from_order,
    toast_datetime,
)
from app.integrations.pos.toast.retry import RetryPolicy
from app.integrations.pos.toast.stock import STOCK_PATH, stock_items_from_toast
from app.integrations.pos.toast.token_store import ToastTokenStore

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
        retry_policy: RetryPolicy | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.time,
        token_store: ToastTokenStore | None = None,
    ) -> None:
        super().__init__(connection)
        self.currency = currency
        self._client = ToastClient(
            credentials,
            restaurant_guid=connection.location_id,
            base_url=base_url,
            transport=transport,
            retry_policy=retry_policy,
            sleep=sleep,
            clock=clock,
            token_store=token_store,
        )

    def authenticate(self) -> bool:
        """Make sure there is a usable token; logs in only when the saved one is missing or
        expired. Raises ToastRateLimitError when Toast is limiting logins."""
        try:
            self._client.ensure_token()
        except ToastAuthenticationError:
            logger.warning("Toast authentication failed for connection %s", self.connection.id)
            return False
        return True

    def close(self) -> None:
        self._client.close()

    def fetch_menu_items(self) -> list[MenuItem]:
        items = menu_items_from_toast(self._client.get(MENUS_PATH), self.connection, self.currency)
        logger.info("Fetched %d Toast menu items for connection %s", len(items), self.connection.id)
        return items

    def fetch_orders(self, start_time: datetime, end_time: datetime) -> list[SaleLine]:
        """Sale lines from orders modified in [start_time, end_time).

        Toast filters ordersBulk by modifiedDate, so an older order that was changed in the
        range (for example voided) is returned too, with is_voided set on its lines; callers
        upsert by order and line ID.
        """
        lines: list[SaleLine] = []
        for window_start, window_end in order_windows(start_time, end_time):
            for order in self._orders_in_window(window_start, window_end):
                lines.extend(sale_lines_from_order(order, self.connection))
        logger.info("Fetched %d Toast sale lines for connection %s", len(lines), self.connection.id)
        return lines

    def fetch_orders_for_business_date(self, business_date: date) -> list[SaleLine]:
        """Sale lines from orders of one business day, including voided ones (is_voided)."""
        lines = [
            line
            for order in orders_on_business_date(self._client, business_date)
            for line in sale_lines_from_order(order, self.connection)
        ]
        logger.info(
            "Fetched %d Toast sale lines for business date %s, connection %s",
            len(lines),
            business_date.isoformat(),
            self.connection.id,
        )
        return lines

    def fetch_stock_items(self) -> list[StockItem]:
        """Items that are out of stock or limited; see ``stock.py`` for what Toast omits."""
        items = stock_items_from_toast(self._client.get(STOCK_PATH), self.connection)
        logger.info(
            "Fetched %d Toast stock items for connection %s", len(items), self.connection.id
        )
        return items

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

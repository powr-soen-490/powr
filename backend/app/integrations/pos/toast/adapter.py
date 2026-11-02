# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""PosAdapter implementation for Toast's read-only Standard API access."""

import logging
from datetime import datetime

import httpx2

from app.integrations.pos.interface import PosAdapter
from app.integrations.pos.models import MenuItem, PosConnection, SaleLine, StockItem
from app.integrations.pos.toast.client import (
    ToastAuthenticationError,
    ToastClient,
    ToastCredentials,
)
from app.integrations.pos.toast.menus import MENUS_PATH, menu_items_from_toast

logger = logging.getLogger(__name__)


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
        raise NotImplementedError("Toast orders are not implemented yet.")

    def fetch_stock_items(self) -> list[StockItem]:
        raise NotImplementedError("Toast stock is not implemented yet.")

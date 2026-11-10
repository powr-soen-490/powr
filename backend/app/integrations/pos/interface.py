# Source-File AI Declaration
# AI contribution: 50% or more AI-generated

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Self

from app.integrations.pos.models import MenuItem, PosConnection, SaleLine, StockItem


class PosAdapter(ABC):
    """Abstract class for POS adapters"""

    def __init__(self, connection: PosConnection):
        self.connection = connection

    @abstractmethod
    def authenticate(self) -> bool:
        """Authenticate with the POS system"""
        pass

    @abstractmethod
    def fetch_menu_items(self) -> list[MenuItem]:
        """Fetch menu items from the POS system"""
        pass

    @abstractmethod
    def fetch_orders(self, start_time: datetime, end_time: datetime) -> list[SaleLine]:
        """Fetch orders from the POS system"""
        pass

    @abstractmethod
    def fetch_stock_items(self) -> list[StockItem]:
        """Fetch stock items from the POS system"""
        pass

    @abstractmethod
    def close(self) -> None:
        """Close any open connections to the POS system"""
        pass
    
    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

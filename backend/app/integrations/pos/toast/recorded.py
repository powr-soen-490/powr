# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""A stand-in for the Toast API that answers from the recorded week, so anyone can run powr
locally without Toast credentials (TOAST_USE_RECORDED_DATA=true, never when deployed).

It plugs in below ToastClient as its HTTP transport, so the real adapter, mappers and import
all run exactly as they do against Toast. Any client ID and secret are accepted.
"""

import re
from pathlib import Path

import httpx2

from app.integrations.pos.toast.client import LOGIN_PATH
from app.integrations.pos.toast.locations import RESTAURANTS_PATH
from app.integrations.pos.toast.menus import MENUS_PATH
from app.integrations.pos.toast.orders import ORDERS_PATH
from app.integrations.pos.toast.recording import FAKE_RESTAURANT_GUID
from app.integrations.pos.toast.stock import STOCK_PATH

# Recorded by scripts/record_toast_fixtures.py: the menu, and orders from Nov 9 to 15, 2026.
RECORDED_WEEK_DIR = Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "toast_week"
RECORDED_RESTAURANT_NAME = "Recorded Toast week (Nov 9-15, 2026)"
_BUSINESS_DATE = re.compile(r"(\d{4})(\d{2})(\d{2})")


def recorded_toast_transport(folder: Path = RECORDED_WEEK_DIR) -> httpx2.MockTransport:
    """Answers the Toast endpoints powr calls; other days and paths come back empty."""

    def handle(request: httpx2.Request) -> httpx2.Response:
        path = request.url.path
        if path == LOGIN_PATH:
            token = {"accessToken": "recorded-data", "expiresIn": 86400}
            return httpx2.Response(200, json={"token": token})
        if path == RESTAURANTS_PATH:
            restaurant = {
                "restaurantGuid": FAKE_RESTAURANT_GUID,
                "restaurantName": RECORDED_RESTAURANT_NAME,
            }
            return httpx2.Response(200, json=[restaurant])
        if path == MENUS_PATH:
            return _file(folder / "menus.json")
        if path == ORDERS_PATH:
            return _orders(folder, request.url.params)
        if path == STOCK_PATH:
            return httpx2.Response(200, json=[])
        return httpx2.Response(404, json={"message": "Not part of the recorded Toast data."})

    return httpx2.MockTransport(handle)


def _orders(folder: Path, params: httpx2.QueryParams) -> httpx2.Response:
    """One business day's orders, all on page 1. Date-range requests get no orders, since the
    recorded files are only split by business day."""
    match = _BUSINESS_DATE.fullmatch(params.get("businessDate", ""))
    if match is None or params.get("page", "1") != "1":
        return httpx2.Response(200, json=[])
    day_file = folder / "orders" / f"{match[1]}-{match[2]}-{match[3]}.json"
    return _file(day_file) if day_file.is_file() else httpx2.Response(200, json=[])


def _file(path: Path) -> httpx2.Response:
    # Sent as text, so prices keep their exact digits for the client's Decimal parsing.
    text = path.read_text(encoding="utf-8")
    return httpx2.Response(200, text=text, headers={"Content-Type": "application/json"})

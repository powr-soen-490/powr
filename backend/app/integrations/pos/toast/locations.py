# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Find the Toast restaurants a login can access, so the owner never types a restaurant GUID."""

import logging
import time
from collections.abc import Callable
from typing import Any

import httpx2

from app.integrations.pos.models import PosLocation
from app.integrations.pos.toast.client import ToastApiError, ToastClient, ToastCredentials
from app.integrations.pos.toast.menus import MISSING_NAME
from app.integrations.pos.toast.retry import RetryPolicy

logger = logging.getLogger(__name__)

# Lists every restaurant the login can access. Unlike the other endpoints, it is not about
# one restaurant, so it is called without the Toast-Restaurant-External-ID header.
RESTAURANTS_PATH = "/partners/v1/restaurants"


def find_toast_locations(
    credentials: ToastCredentials,
    *,
    base_url: str,
    transport: httpx2.BaseTransport | None = None,
    retry_policy: RetryPolicy | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.time,
) -> list[PosLocation]:
    """Log in with the credentials and list the restaurants they can access.

    Raises ToastAuthenticationError when Toast rejects the credentials, and ToastApiError when
    Toast cannot be reached or answers with an error.
    """
    client = ToastClient(
        credentials,
        restaurant_guid=None,
        base_url=base_url,
        transport=transport,
        retry_policy=retry_policy,
        sleep=sleep,
        clock=clock,
    )
    try:
        locations = locations_from_toast(client.get(RESTAURANTS_PATH))
    finally:
        client.close()
    logger.info("Toast login can access %d restaurant(s)", len(locations))
    return locations


def locations_from_toast(restaurants: Any) -> list[PosLocation]:
    """Convert Toast's restaurant list; entries without a GUID are skipped."""
    if not isinstance(restaurants, list):
        raise ToastApiError("Toast restaurants response is not a JSON array.")
    locations: list[PosLocation] = []
    for restaurant in restaurants:
        if not isinstance(restaurant, dict):
            continue
        guid = restaurant.get("restaurantGuid")
        if not isinstance(guid, str) or not guid:
            continue
        locations.append(PosLocation(location_id=guid, name=_display_name(restaurant)))
    return locations


def _display_name(restaurant: dict[str, Any]) -> str:
    """Join the restaurant and location names, e.g. "Chain - Downtown", skipping blank ones."""
    names = [
        name.strip()
        for name in (restaurant.get("restaurantName"), restaurant.get("locationName"))
        if isinstance(name, str) and name.strip()
    ]
    return " - ".join(names)[:255] or MISSING_NAME

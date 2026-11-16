# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Finding the Toast restaurants a login can access, against the fake Toast server."""

import httpx2
import pytest

from app.integrations.pos.models import PosLocation
from app.integrations.pos.toast.client import (
    LOGIN_PATH,
    ToastApiError,
    ToastAuthenticationError,
    ToastCredentials,
)
from app.integrations.pos.toast.locations import (
    RESTAURANTS_PATH,
    find_toast_locations,
    locations_from_toast,
)
from app.integrations.pos.toast.menus import MISSING_NAME
from tests.unit.toast_fakes import BASE_URL, FakeToast

CREDENTIALS = ToastCredentials(client_id="test-client-id", client_secret="test-client-secret")


def find(toast: FakeToast) -> list[PosLocation]:
    return find_toast_locations(
        CREDENTIALS,
        base_url=BASE_URL,
        transport=httpx2.MockTransport(toast._handle),
        sleep=toast.sleep,
        clock=toast.clock,
    )


def test_lists_restaurants_without_a_restaurant_header() -> None:
    toast = FakeToast()
    toast.reply(
        RESTAURANTS_PATH,
        httpx2.Response(
            200,
            json=[
                {
                    "restaurantGuid": "guid-1",
                    "restaurantName": "Mykonos Grill - Boca NEW",
                    "locationName": None,
                }
            ],
        ),
    )

    assert find(toast) == [PosLocation(location_id="guid-1", name="Mykonos Grill - Boca NEW")]
    [request] = toast.requests_to(RESTAURANTS_PATH)
    assert request.headers["Authorization"] == "Bearer test-access-token"
    assert "Toast-Restaurant-External-ID" not in request.headers
    assert len(toast.requests_to(LOGIN_PATH)) == 1


def test_names_join_restaurant_and_location_and_skip_entries_without_a_guid() -> None:
    restaurants = [
        {"restaurantGuid": "guid-1", "restaurantName": "Chain", "locationName": "Downtown"},
        {"restaurantGuid": "guid-2", "restaurantName": "  ", "locationName": None},
        {"restaurantGuid": "", "restaurantName": "No GUID"},
        {"restaurantName": "Missing GUID"},
        "not an object",
    ]

    assert locations_from_toast(restaurants) == [
        PosLocation(location_id="guid-1", name="Chain - Downtown"),
        PosLocation(location_id="guid-2", name=MISSING_NAME),
    ]


def test_rejected_credentials_raise_an_authentication_error() -> None:
    toast = FakeToast()
    toast.reply(LOGIN_PATH, httpx2.Response(401, json={"status": 401}))

    with pytest.raises(ToastAuthenticationError):
        find(toast)
    assert toast.requests_to(RESTAURANTS_PATH) == []


@pytest.mark.parametrize(
    "reply",
    [
        httpx2.Response(200, json={"not": "a list"}),
        httpx2.Response(403, json={"status": 403}),
    ],
)
def test_unexpected_answers_raise_a_toast_api_error(reply: httpx2.Response) -> None:
    toast = FakeToast()
    toast.reply(RESTAURANTS_PATH, reply)

    with pytest.raises(ToastApiError):
        find(toast)

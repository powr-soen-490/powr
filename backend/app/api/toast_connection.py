# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Owner-only endpoints to connect a restaurant to Toast, see the connection and disconnect."""

from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import OwnerDep
from app.core.config import get_settings
from app.core.database import get_db
from app.integrations.pos.models import PosLocation
from app.integrations.pos.toast.client import ToastCredentials
from app.integrations.pos.toast.locations import find_toast_locations
from app.modules.pos import service
from app.schemas.pos import SetPosResponse, ToastConnectionResponse, ToastConnectRequest

router = APIRouter(prefix="/api/pos/toast", tags=["toast"])
DbSession = Annotated[Session, Depends(get_db)]

# Each failure has its own status code, so the frontend can pick its own message without
# displaying text that came back from the server.
CONNECT_ERRORS: dict[type[service.ToastConnectError], tuple[int, str]] = {
    service.ToastLoginRejectedError: (
        status.HTTP_400_BAD_REQUEST,
        "Toast did not accept this client ID and secret.",
    ),
    service.NoToastRestaurantError: (
        status.HTTP_404_NOT_FOUND,
        "These Toast credentials cannot access any restaurant.",
    ),
    service.MultipleToastRestaurantsError: (
        status.HTTP_409_CONFLICT,
        "These Toast credentials can access more than one restaurant, which is not supported yet.",
    ),
    service.ToastBusyError: (
        status.HTTP_429_TOO_MANY_REQUESTS,
        "Toast is limiting logins right now. Wait a few minutes and try again.",
    ),
    service.ToastUnavailableError: (
        status.HTTP_502_BAD_GATEWAY,
        "Could not reach Toast. Try again later.",
    ),
}


def _find_locations(credentials: ToastCredentials) -> list[PosLocation]:
    return find_toast_locations(credentials, base_url=get_settings().toast_api_base_url)


def _storage_error(exc: Exception) -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Could not read or save the Toast connection due to a database error.",
    ) from exc


@router.get("/connection", response_model=ToastConnectionResponse)
def get_toast_connection(user: OwnerDep, db: DbSession) -> ToastConnectionResponse:
    """The Toast restaurant linked to the owner's restaurant, or 404 when not connected."""
    try:
        connection = service.get_toast_connection(db, user.restaurant_id)
    except service.ConnectionStorageError as exc:
        _storage_error(exc)
    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Toast is not connected.")
    return ToastConnectionResponse.model_validate(connection)


@router.put("/connection", response_model=ToastConnectionResponse)
def connect_toast(
    payload: ToastConnectRequest, user: OwnerDep, db: DbSession
) -> ToastConnectionResponse:
    """Check the credentials with Toast, then save them with the restaurant they can access."""
    try:
        location = service.connect_toast(
            db,
            restaurant_id=user.restaurant_id,
            client_id=payload.client_id.strip(),
            client_secret=payload.client_secret,
            find_locations=_find_locations,
        )
    except service.ToastConnectError as exc:
        status_code, message = CONNECT_ERRORS[type(exc)]
        raise HTTPException(status_code=status_code, detail=message) from exc
    except service.ConnectionStorageError as exc:
        _storage_error(exc)
    return ToastConnectionResponse(location_id=location.location_id, location_name=location.name)


@router.delete("/connection", response_model=SetPosResponse)
def disconnect_toast(user: OwnerDep, db: DbSession) -> SetPosResponse:
    """Remove the restaurant's Toast restaurant GUID and the saved Toast credentials."""
    try:
        service.disconnect_toast(db, restaurant_id=user.restaurant_id)
    except service.ConnectionStorageError as exc:
        _storage_error(exc)
    return SetPosResponse(message="Toast disconnected.")

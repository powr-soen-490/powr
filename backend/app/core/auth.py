# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Authorization: who is calling, which restaurant they act for, and what they may do.

Every endpoint that touches restaurant data takes CurrentUserDep (or OwnerDep) and scopes its
queries with user.restaurant_id. The restaurant is never read from the request body, query or
path, so a user cannot reach another restaurant's data by changing an id in the request.
"""

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.security import verify_session_token

OWNER = "owner"
KITCHEN_MANAGER = "kitchen_manager"

UNAUTHENTICATED_ERROR = "Not authenticated."
FORBIDDEN_ERROR = "You do not have permission to do this."


@dataclass(frozen=True)
class CurrentUser:
    user_id: UUID
    email: str
    restaurant_id: UUID
    restaurant_name: str
    role: str


def get_current_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CurrentUser:
    """Resolves the signed-in user and their restaurant from the session cookie, or returns 401.

    The cookie only identifies the user and restaurant. The role is read from the database on
    every request, so a changed role or a removed membership takes effect immediately.
    """
    token = request.cookies.get(settings.session_cookie_name, "")
    session_data = verify_session_token(
        token=token,
        secret_key=settings.session_secret_key,
        max_age=settings.session_max_age_seconds,
    )
    if not session_data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=UNAUTHENTICATED_ERROR)

    try:
        user_id = UUID(str(session_data["user_id"]))
        restaurant_id = UUID(str(session_data["restaurant_id"]))
    except (KeyError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=UNAUTHENTICATED_ERROR
        ) from error

    row = db.execute(
        text(
            """
            SELECT u.id AS user_id, u.email, r.id AS restaurant_id, r.name AS restaurant_name,
                   rm.role
            FROM users u
            JOIN restaurant_memberships rm ON rm.user_id = u.id
            JOIN restaurants r ON r.id = rm.restaurant_id
            WHERE u.id = :user_id AND r.id = :restaurant_id
            """
        ),
        {"user_id": user_id, "restaurant_id": restaurant_id},
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=UNAUTHENTICATED_ERROR)

    return CurrentUser(
        user_id=row.user_id,
        email=row.email,
        restaurant_id=row.restaurant_id,
        restaurant_name=row.restaurant_name,
        role=row.role,
    )


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


def require_owner(user: CurrentUserDep) -> CurrentUser:
    """Lets only owners through; kitchen managers get 403."""
    if user.role != OWNER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=FORBIDDEN_ERROR)
    return user


OwnerDep = Annotated[CurrentUser, Depends(require_owner)]

# Who may change recipes, ingredients and vendors. Remove KITCHEN_MANAGER to make these
# edits owner-only; everyone in the restaurant can still read them.
RECIPE_EDITOR_ROLES = frozenset({OWNER, KITCHEN_MANAGER})


def require_recipe_editor(user: CurrentUserDep) -> CurrentUser:
    """Lets only RECIPE_EDITOR_ROLES through; anyone else gets 403."""
    if user.role not in RECIPE_EDITOR_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=FORBIDDEN_ERROR)
    return user


RecipeEditorDep = Annotated[CurrentUser, Depends(require_recipe_editor)]

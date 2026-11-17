# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""The saved Toast login: every Toast client the app builds reuses the token in pos_credentials.

Toast asks for at most two logins per hour, so imports, the menu endpoint and anything else
that calls Toast must build their adapter with ``saved_toast_adapter`` instead of creating
a ToastAdapter or ToastClient themselves. See docs/toast-integration.md.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import create_session_factory
from app.integrations.pos.models import PosConnection
from app.integrations.pos.toast.adapter import ToastAdapter
from app.integrations.pos.toast.client import ToastCredentials
from app.integrations.pos.toast.token_store import MemoryTokenStore, ToastToken, ToastTokenStore
from app.modules.pos import service

logger = logging.getLogger(__name__)


class SavedToastTokenStore:
    """Keeps the Toast token of one client ID in pos_credentials.

    Saving commits ``db``, so callers only make Toast requests while ``db`` has no unsaved
    changes (the import saves each day after fetching it). A token that cannot be saved is
    logged and still used: it only costs a login later.
    """

    def __init__(self, db: Session, *, client_id: str, token: ToastToken | None) -> None:
        self._db = db
        self._client_id = client_id
        self._token = token

    def load(self) -> ToastToken | None:
        return self._token

    def save(self, token: ToastToken) -> None:
        self._token = token
        try:
            saved = service.save_access_token(
                self._db,
                pos_name=service.TOAST,
                client_id=self._client_id,
                access_token=token.access_token,
                expires_at=token.expires_at,
            )
        except service.CredentialsStorageError:
            logger.exception("Could not save the Toast access token; the next request logs in")
            return
        if not saved:
            logger.info("Toast was reconnected or disconnected; not saving the old login's token")

    def credentials_rejected(self) -> None:
        self._token = None
        try:
            marked = service.mark_needs_reconnect(
                self._db, pos_name=service.TOAST, client_id=self._client_id
            )
        except service.CredentialsStorageError:
            logger.exception("Could not mark the Toast connection as needing a reconnect")
            return
        if marked:
            logger.warning("Toast rejected the saved client ID or secret; it needs a reconnect")


def saved_toast_adapter(
    db: Session, connection: PosConnection, credentials: dict[str, Any], *, currency: str
) -> ToastAdapter:
    """A ToastAdapter that starts from the saved token and saves every new one.

    ``credentials`` is the decrypted row from ``service.get_credentials``.
    """
    return ToastAdapter(
        connection,
        ToastCredentials(
            client_id=credentials["client_id"], client_secret=credentials["client_secret"]
        ),
        currency=currency,
        base_url=get_settings().toast_api_base_url,
        transport=service.toast_transport(),
        token_store=SavedToastTokenStore(
            db, client_id=credentials["client_id"], token=_saved_token(credentials)
        ),
    )


@contextmanager
def script_token_store(client_id: str) -> Iterator[ToastTokenStore]:
    """For developer scripts that log in with the .env credentials.

    When the app is connected with the same client ID, the script reuses the app's saved token
    and saves any new one back, so running a script costs no extra login. Otherwise (another
    client ID, Toast never connected in the app, or no database running) the token is only
    kept in memory and the script logs in once, like before.
    """
    sessions = create_session_factory(str(get_settings().database_url))
    try:
        with sessions() as db:
            yield _script_store(db, client_id)
    finally:
        engine = sessions.kw["bind"]
        engine.dispose()


def _script_store(db: Session, client_id: str) -> ToastTokenStore:
    try:
        saved = service.get_credentials(db, service.TOAST)
    except service.CredentialsStorageError:
        logger.warning("Could not read the app's saved Toast login; the script logs in itself")
        return MemoryTokenStore()
    if saved is None or saved["client_id"] != client_id:
        return MemoryTokenStore()
    return SavedToastTokenStore(db, client_id=client_id, token=_saved_token(saved))


def _saved_token(credentials: dict[str, Any]) -> ToastToken | None:
    if credentials["access_token"] is None:
        return None
    return ToastToken(
        access_token=credentials["access_token"], expires_at=credentials["expires_at"]
    )

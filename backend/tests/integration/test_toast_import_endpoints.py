# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""The sales import endpoints end to end: owner sessions, a real database and a fake Toast.

TestClient runs background tasks before it returns the response, so each import has finished
by the time the next request is sent.
"""

import uuid
from collections.abc import Callable
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.integrations.pos.interface import PosAdapter
from app.integrations.pos.models import PosConnection
from app.integrations.pos.toast.menus import MENUS_PATH
from app.integrations.pos.toast.orders import ORDERS_PATH
from app.modules.pos import import_service
from tests.unit.toast_fakes import RECORDED_WEEK_DIR, FakeToast

IMPORTS = "/api/pos/toast/imports"
NOV_9_TO_10 = {"start_date": "2026-11-09", "end_date": "2026-11-10"}
ClientFactory = Callable[[], TestClient]
SignUp = Callable[[TestClient, str], dict[str, Any]]


def recorded(name: str) -> httpx2.Response:
    return httpx2.Response(200, text=(RECORDED_WEEK_DIR / name).read_text())


@pytest.fixture
def toast(monkeypatch: pytest.MonkeyPatch) -> FakeToast:
    """A fake Toast serving the recorded menu and Nov 9 and 10; tests can queue other replies."""
    fake = FakeToast()
    fake.reply(MENUS_PATH, recorded("menus.json"))
    fake.reply(ORDERS_PATH, recorded("orders/2026-11-09.json"), recorded("orders/2026-11-10.json"))

    def make_adapter(_db: Session, restaurant_id: uuid.UUID) -> PosAdapter:
        connection = PosConnection(
            id=uuid.uuid4(), restaurant_id=restaurant_id, provider="TOAST", location_id="guid"
        )
        return fake.adapter(connection=connection)

    monkeypatch.setattr(import_service, "toast_adapter", make_adapter)
    return fake


def connected_owner(
    make_client: ClientFactory, sign_up_owner: SignUp, engine: Engine, email: str
) -> TestClient:
    owner = make_client()
    restaurant_id = sign_up_owner(owner, email)["restaurant_id"]
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO pos_connections (restaurant_id, provider, location_id) "
                "VALUES (:restaurant_id, 'TOAST', 'guid')"
            ),
            {"restaurant_id": restaurant_id},
        )
    return owner


@pytest.fixture
def owner(make_client: ClientFactory, sign_up_owner: SignUp, migrated_engine: Engine) -> TestClient:
    return connected_owner(make_client, sign_up_owner, migrated_engine, "owner@example.com")


@pytest.mark.usefixtures("toast")
def test_owner_imports_sales_and_follows_the_progress(owner: TestClient) -> None:
    assert owner.get(f"{IMPORTS}/latest").json() is None

    started = owner.post(IMPORTS, json=NOV_9_TO_10)
    assert started.status_code == 202, started.text
    assert started.json() | {"id": None, "created_at": None} == {
        "id": None,
        "status": "running",
        "start_date": "2026-11-09",
        "end_date": "2026-11-10",
        "last_completed_date": None,
        "days_completed": 0,
        "total_days": 2,
        "percent": 0,
        "orders_imported": 0,
        "items_imported": 0,
        "error": None,
        "created_at": None,
        "finished_at": None,
    }

    latest = owner.get(f"{IMPORTS}/latest").json()
    assert latest["id"] == started.json()["id"]
    assert latest["status"] == "done"
    assert (latest["days_completed"], latest["percent"]) == (2, 100)
    assert (latest["orders_imported"], latest["items_imported"]) == (56 + 60, 110 + 125)
    assert latest["finished_at"] is not None


def test_a_failed_import_shows_why_and_retry_finishes_it(
    owner: TestClient, toast: FakeToast
) -> None:
    toast.reply(ORDERS_PATH, recorded("orders/2026-11-09.json"), httpx2.Response(503))
    owner.post(IMPORTS, json=NOV_9_TO_10)

    failed = owner.get(f"{IMPORTS}/latest").json()
    assert (failed["status"], failed["percent"], failed["last_completed_date"]) == (
        "failed",
        50,
        "2026-11-09",
    )
    assert "Retry later" in failed["error"]

    toast.reply(ORDERS_PATH, recorded("orders/2026-11-10.json"))
    retried = owner.post(f"{IMPORTS}/{failed['id']}/retry")
    assert retried.status_code == 202, retried.text
    assert retried.json()["status"] == "running"

    done = owner.get(f"{IMPORTS}/latest").json()
    assert (done["id"], done["status"], done["error"]) == (failed["id"], "done", None)
    assert done["orders_imported"] == 56 + 60


@pytest.mark.usefixtures("toast")
def test_only_a_failed_import_of_your_own_restaurant_can_be_retried(
    owner: TestClient,
    make_client: ClientFactory,
    sign_up_owner: SignUp,
    migrated_engine: Engine,
) -> None:
    job_id = owner.post(IMPORTS, json=NOV_9_TO_10).json()["id"]
    other = connected_owner(make_client, sign_up_owner, migrated_engine, "other@example.com")

    assert owner.post(f"{IMPORTS}/{job_id}/retry").status_code == 409  # it is done
    assert other.post(f"{IMPORTS}/{job_id}/retry").status_code == 404
    assert other.get(f"{IMPORTS}/latest").json() is None


def test_a_second_import_waits_for_the_running_one(
    owner: TestClient, migrated_engine: Engine
) -> None:
    with migrated_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO sync_jobs (restaurant_id, provider, start_date, end_date) "
                "SELECT restaurant_id, 'TOAST', '2024-01-01', '2026-11-10' FROM pos_connections"
            )
        )

    response = owner.post(IMPORTS, json=NOV_9_TO_10)

    assert response.status_code == 409
    assert response.json() == {"detail": "An import is already running."}


@pytest.mark.parametrize(
    "payload",
    [
        {"start_date": "2026-11-10", "end_date": "2026-11-09"},
        {"end_date": "2999-01-01"},
        {"start_date": "yesterday"},
        {"restaurant_id": str(uuid.uuid4())},
    ],
    ids=["start after end", "end not finished", "not a date", "unknown field"],
)
def test_a_bad_import_request_is_refused(owner: TestClient, payload: dict[str, str]) -> None:
    response = owner.post(IMPORTS, json=payload)

    assert response.status_code == 422
    assert owner.get(f"{IMPORTS}/latest").json() is None


def test_importing_needs_a_toast_connection(
    make_client: ClientFactory, sign_up_owner: SignUp
) -> None:
    owner = make_client()
    sign_up_owner(owner, "owner@example.com")

    response = owner.post(IMPORTS, json=NOV_9_TO_10)

    assert response.status_code == 404
    assert response.json() == {"detail": "Connect Toast before importing sales."}


def test_imports_are_for_signed_in_owners_only(
    make_client: ClientFactory, sign_up_owner: SignUp, migrated_engine: Engine
) -> None:
    anonymous = make_client()
    assert anonymous.get(f"{IMPORTS}/latest").status_code == 401
    assert anonymous.post(IMPORTS, json={}).status_code == 401

    manager = make_client()
    sign_up_owner(manager, "manager@example.com")
    with migrated_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE restaurant_memberships SET role = 'kitchen_manager' "
                "WHERE user_id = (SELECT id FROM users WHERE email = 'manager@example.com')"
            )
        )
    assert manager.get(f"{IMPORTS}/latest").status_code == 403
    assert manager.post(IMPORTS, json=NOV_9_TO_10).status_code == 403

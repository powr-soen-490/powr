# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Story #52: customer names, emails, card data and addresses are never stored.

Real Toast orders carry customers, servers, payments and delivery addresses. This imports a
recorded day with all of those added back in, then reads every imported table to prove none
of it was saved. Runs in a throwaway database (see ``scratch_engine``).
"""

import copy
import json
import uuid
from datetime import UTC, date, datetime
from typing import Any

import httpx2
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.integrations.pos.interface import PosAdapter
from app.integrations.pos.models import PosConnection
from app.integrations.pos.toast.menus import MENUS_PATH
from app.integrations.pos.toast.orders import ORDERS_PATH
from app.modules.pos import import_service
from app.modules.pos.import_service import start_import
from tests.unit.toast_fakes import RECORDED_WEEK_DIR, FakeToast

PERSONAL_DATA = {
    "firstName": "Eleni",
    "lastName": "Papadopoulos",
    "email": "eleni.papadopoulos@example.com",
    "phone": "561-555-0199",
    "cardNumber": "4111111111111111",
    "address1": "77 Ocean Blvd",
    "city": "Boca Raton",
}
NOV_9 = date(2026, 11, 9)
IMPORTED_TABLES = ("sales_orders", "sales_order_lines", "menu_items", "menu_modifiers", "sync_jobs")


def orders_with_personal_data() -> list[Any]:
    orders: list[Any] = copy.deepcopy(
        json.loads((RECORDED_WEEK_DIR / "orders/2026-11-09.json").read_text())
    )
    person = {key: PERSONAL_DATA[key] for key in ("firstName", "lastName", "email", "phone")}
    for order in orders:
        order["customer"] = person
        order["server"] = {"guid": "employee-1", **person}
        order["deliveryInfo"] = {"address1": PERSONAL_DATA["address1"], "city": "Boca Raton"}
        for check in order["checks"]:
            check["customer"] = person
            check["payments"] = [
                {
                    "cardNumber": PERSONAL_DATA["cardNumber"],
                    # Not searched for below: 4 digits also turn up inside random IDs.
                    "last4Digits": "4242",
                    "cardHolderName": f"{person['firstName']} {person['lastName']}",
                    "amount": 10,
                }
            ]
    return orders


def test_personal_data_in_toast_orders_is_never_stored(migrated_engine: Engine) -> None:
    sessions = sessionmaker(bind=migrated_engine)
    with sessions() as db:
        restaurant_id: uuid.UUID = db.execute(
            text("INSERT INTO restaurants (name) VALUES ('Mykonos Grill') RETURNING id")
        ).scalar_one()
        db.execute(
            text(
                "INSERT INTO pos_connections (restaurant_id, provider, location_id) "
                "VALUES (:restaurant_id, 'TOAST', 'guid')"
            ),
            {"restaurant_id": restaurant_id},
        )
        db.commit()
        job = start_import(
            db,
            restaurant_id=restaurant_id,
            start_date=NOV_9,
            end_date=NOV_9,
            now=datetime(2026, 11, 17, 15, 0, tzinfo=UTC),
        )
    toast = FakeToast()
    toast.reply(
        MENUS_PATH, httpx2.Response(200, text=(RECORDED_WEEK_DIR / "menus.json").read_text())
    )
    toast.reply(ORDERS_PATH, httpx2.Response(200, text=json.dumps(orders_with_personal_data())))

    def make_adapter(_db: Session, restaurant: uuid.UUID) -> PosAdapter:
        connection = PosConnection(
            id=uuid.uuid4(), restaurant_id=restaurant, provider="TOAST", location_id="guid"
        )
        return toast.adapter(connection=connection)

    import_service.run_import(
        sessions, job_id=job.id, restaurant_id=restaurant_id, make_adapter=make_adapter
    )

    with migrated_engine.connect() as connection:
        saved = "\n".join(
            row
            for table in IMPORTED_TABLES
            for row in connection.execute(
                text(f"SELECT row_to_json(t)::text FROM {table} t")
            ).scalars()
        )
    assert '"orders_imported":56' in saved  # the day really was imported
    for value in (*PERSONAL_DATA.values(), "employee-1"):
        assert value not in saved, f"{value!r} was stored"

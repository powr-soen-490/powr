# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Background sales imports end to end: a real database, a fake Toast and the recorded week.

Each test runs in a throwaway database (see ``scratch_engine``).
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta

import httpx2
import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.integrations.pos.interface import PosAdapter
from app.integrations.pos.models import PosConnection
from app.integrations.pos.toast.client import LOGIN_PATH
from app.integrations.pos.toast.menus import MENUS_PATH
from app.integrations.pos.toast.orders import ORDERS_PATH
from app.main import fail_interrupted_imports as fail_interrupted_imports_at_startup
from app.modules.pos import import_service
from app.modules.pos import sync_job_repository as jobs
from app.modules.pos.import_service import (
    DEFAULT_START_DATE,
    RESTARTED_ERROR,
    ImportAlreadyRunningError,
    ImportJobNotFoundError,
    ImportNotRetryableError,
    InvalidImportRangeError,
    PosNotConnectedError,
)
from app.modules.pos.sync_job_repository import SyncJob
from tests.unit.toast_fakes import RECORDED_WEEK_DIR, FakeToast

NOV_9 = date(2026, 11, 9)
NOV_11 = date(2026, 11, 11)
# Late enough that the whole recorded week has finished.
NOW = datetime(2026, 11, 17, 15, 0, tzinfo=UTC)
# Orders and sale lines in the recorded week, Nov 9 to 11.
ORDERS = {date(2026, 11, 9): 56, date(2026, 11, 10): 60, date(2026, 11, 11): 57}
LINES = {date(2026, 11, 9): 110, date(2026, 11, 10): 125, date(2026, 11, 11): 113}


@pytest.fixture
def sessions(migrated_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=migrated_engine)


@pytest.fixture
def db(sessions: sessionmaker[Session]) -> Iterator[Session]:
    with sessions() as session:
        yield session


@pytest.fixture
def restaurant_id(db: Session) -> uuid.UUID:
    return add_restaurant(db)


def add_restaurant(db: Session, *, connected: bool = True) -> uuid.UUID:
    restaurant_id: uuid.UUID = db.execute(
        text("INSERT INTO restaurants (name) VALUES ('Mykonos Grill') RETURNING id")
    ).scalar_one()
    if connected:
        db.execute(
            text(
                "INSERT INTO pos_connections (restaurant_id, provider, location_id) "
                "VALUES (:restaurant_id, 'TOAST', 'guid')"
            ),
            {"restaurant_id": restaurant_id},
        )
    db.commit()
    return restaurant_id


def recorded_day(day: date) -> httpx2.Response:
    return httpx2.Response(200, text=(RECORDED_WEEK_DIR / f"orders/{day}.json").read_text())


def fake_toast(*order_replies: httpx2.Response) -> FakeToast:
    toast = FakeToast()
    toast.reply(
        MENUS_PATH, httpx2.Response(200, text=(RECORDED_WEEK_DIR / "menus.json").read_text())
    )
    toast.reply(ORDERS_PATH, *order_replies)
    return toast


def start(db: Session, restaurant_id: uuid.UUID, end: date = NOV_11) -> SyncJob:
    return import_service.start_import(
        db, restaurant_id=restaurant_id, start_date=NOV_9, end_date=end, now=NOW
    )


def run(sessions: sessionmaker[Session], job: SyncJob, toast: FakeToast) -> SyncJob:
    def make_adapter(_db: Session, restaurant_id: uuid.UUID) -> PosAdapter:
        connection = PosConnection(
            id=uuid.uuid4(), restaurant_id=restaurant_id, provider="TOAST", location_id="guid"
        )
        return toast.adapter(connection=connection)

    import_service.run_import(
        sessions,
        job_id=job.id,
        restaurant_id=job.restaurant_id,
        make_adapter=make_adapter,
        sleep=toast.sleep,
    )
    with sessions() as db:
        saved = jobs.get_job(db, job_id=job.id, restaurant_id=job.restaurant_id)
    assert saved is not None
    return saved


def saved_orders(db: Session, restaurant_id: uuid.UUID) -> int:
    statement = text("SELECT count(*) FROM sales_orders WHERE restaurant_id = :restaurant_id")
    count: int = db.execute(statement, {"restaurant_id": restaurant_id}).scalar_one()
    return count


def test_an_import_saves_every_day_with_one_login(
    db: Session, sessions: sessionmaker[Session], restaurant_id: uuid.UUID
) -> None:
    toast = fake_toast(*(recorded_day(day) for day in ORDERS))

    job = run(sessions, start(db, restaurant_id), toast)

    assert job.status == "done"
    assert job.last_completed_date == NOV_11
    assert (job.days_completed, job.total_days) == (3, 3)
    assert job.orders_imported == sum(ORDERS.values())
    assert job.items_imported == sum(LINES.values())
    assert job.error is None and job.finished_at is not None
    assert len(toast.requests_to(LOGIN_PATH)) == 1
    assert saved_orders(db, restaurant_id) == sum(ORDERS.values())
    menu_sql = "SELECT count(*) FROM menu_items WHERE restaurant_id = :restaurant_id AND is_active"
    assert db.execute(text(menu_sql), {"restaurant_id": restaurant_id}).scalar_one() == 214


def test_a_failed_import_resumes_from_its_bookmark_without_duplicates(
    db: Session, sessions: sessionmaker[Session], restaurant_id: uuid.UUID
) -> None:
    # Day 2 keeps failing, even after the client's own retries.
    job = run(
        sessions, start(db, restaurant_id), fake_toast(recorded_day(NOV_9), httpx2.Response(503))
    )
    assert job.status == "failed"
    assert job.last_completed_date == NOV_9
    assert job.error is not None and "Retry later" in job.error
    assert saved_orders(db, restaurant_id) == ORDERS[NOV_9]

    retried = import_service.retry_import(db, restaurant_id=restaurant_id, job_id=job.id)
    assert retried.status == "running"
    toast = fake_toast(recorded_day(date(2026, 11, 10)), recorded_day(NOV_11))
    job = run(sessions, retried, toast)

    assert job.status == "done"
    asked = [request.url.params["businessDate"] for request in toast.requests_to(ORDERS_PATH)]
    assert asked == ["20261110", "20261111"]  # day 1 was not fetched again
    assert job.orders_imported == sum(ORDERS.values())
    assert saved_orders(db, restaurant_id) == sum(ORDERS.values())


def test_the_import_waits_when_toast_asks_it_to_slow_down(
    db: Session, sessions: sessionmaker[Session], restaurant_id: uuid.UUID
) -> None:
    slow_down = httpx2.Response(429, headers={"Retry-After": "120"})
    toast = fake_toast(slow_down, *(recorded_day(day) for day in ORDERS))

    job = run(sessions, start(db, restaurant_id), toast)

    assert job.status == "done"
    assert 120 in toast.sleeps


def test_the_import_stops_when_toast_asks_for_too_long_a_wait(
    db: Session, sessions: sessionmaker[Session], restaurant_id: uuid.UUID
) -> None:
    toast = fake_toast(httpx2.Response(429, headers={"Retry-After": "3600"}))

    job = run(sessions, start(db, restaurant_id), toast)

    assert job.status == "failed"
    assert job.error is not None and "limiting requests" in job.error
    assert job.last_completed_date is None


def test_disconnecting_toast_stops_the_import_and_keeps_saved_sales(
    db: Session, sessions: sessionmaker[Session], restaurant_id: uuid.UUID
) -> None:
    job = start(db, restaurant_id)
    db.execute(text("DELETE FROM pos_connections WHERE restaurant_id = :id"), {"id": restaurant_id})
    db.commit()

    job = run(sessions, job, fake_toast(recorded_day(NOV_9)))

    assert job.status == "failed"
    assert job.error is not None and "disconnected" in job.error
    with pytest.raises(PosNotConnectedError):
        import_service.retry_import(db, restaurant_id=restaurant_id, job_id=job.id)


def test_a_rejected_toast_login_fails_the_import(
    db: Session, sessions: sessionmaker[Session], restaurant_id: uuid.UUID
) -> None:
    toast = fake_toast(recorded_day(NOV_9))
    toast.reply(LOGIN_PATH, httpx2.Response(401, json={"message": "bad credentials"}))

    job = run(sessions, start(db, restaurant_id), toast)

    assert job.status == "failed"
    assert job.error is not None and "rejected the saved login" in job.error


def test_start_defaults_to_all_history_up_to_the_last_finished_day(
    db: Session, restaurant_id: uuid.UUID
) -> None:
    job = import_service.start_import(
        db, restaurant_id=restaurant_id, start_date=None, end_date=None, now=NOW
    )

    assert job.start_date == DEFAULT_START_DATE
    assert job.end_date == date(2026, 11, 16)
    assert job.status == "running"


@pytest.mark.parametrize(
    ("start_date", "end_date"),
    [(NOV_11, NOV_9), (NOV_9, date(2026, 11, 17))],
    ids=["start after end", "day not finished yet"],
)
def test_start_rejects_a_bad_date_range(
    db: Session, restaurant_id: uuid.UUID, start_date: date, end_date: date
) -> None:
    with pytest.raises(InvalidImportRangeError):
        import_service.start_import(
            db, restaurant_id=restaurant_id, start_date=start_date, end_date=end_date, now=NOW
        )


def test_start_needs_a_toast_connection(db: Session) -> None:
    with pytest.raises(PosNotConnectedError):
        start(db, add_restaurant(db, connected=False))


def test_only_one_import_runs_at_a_time(db: Session, restaurant_id: uuid.UUID) -> None:
    start(db, restaurant_id)

    with pytest.raises(ImportAlreadyRunningError):
        start(db, restaurant_id)
    start(db, add_restaurant(db))  # another restaurant is not blocked


def test_only_this_restaurants_failed_imports_can_be_retried(
    db: Session, sessions: sessionmaker[Session], restaurant_id: uuid.UUID
) -> None:
    done = run(sessions, start(db, restaurant_id, end=NOV_9), fake_toast(recorded_day(NOV_9)))

    with pytest.raises(ImportNotRetryableError):
        import_service.retry_import(db, restaurant_id=restaurant_id, job_id=done.id)
    with pytest.raises(ImportJobNotFoundError):
        import_service.retry_import(db, restaurant_id=add_restaurant(db), job_id=done.id)


def test_startup_fails_imports_cut_off_by_a_restart(
    db: Session, sessions: sessionmaker[Session], restaurant_id: uuid.UUID
) -> None:
    cut_off = start(db, restaurant_id)
    started_at = datetime.now(UTC) + timedelta(seconds=1)
    db.execute(
        text("UPDATE sync_jobs SET updated_at = :before WHERE id = :id"),
        {"before": started_at - timedelta(minutes=5), "id": cut_off.id},
    )
    new = start(db, add_restaurant(db))
    db.execute(
        text("UPDATE sync_jobs SET updated_at = :after WHERE id = :id"),
        {"after": started_at + timedelta(seconds=1), "id": new.id},
    )
    db.commit()

    fail_interrupted_imports_at_startup(sessions, started_at)

    after = jobs.get_job(db, job_id=cut_off.id, restaurant_id=restaurant_id)
    assert after is not None
    assert (after.status, after.error) == ("failed", RESTARTED_ERROR)
    still_running = jobs.get_job(db, job_id=new.id, restaurant_id=new.restaurant_id)
    assert still_running is not None and still_running.status == "running"

# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Background imports of POS sales history, one business day at a time.

The sync_jobs row is the source of truth. Each business day is saved in one transaction
together with the job's bookmark (last_completed_date), so a job that stops for any reason
(an error, a restart, a disconnect) can be retried and continues from the day after the
bookmark, without losing or duplicating anything.
"""

import logging
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.integrations.pos.interface import PosAdapter
from app.integrations.pos.models import SaleLine
from app.integrations.pos.toast.adapter import ToastAdapter
from app.integrations.pos.toast.client import (
    ToastApiError,
    ToastCredentials,
    ToastRateLimitError,
)
from app.modules.pos import import_repository, repository, service
from app.modules.pos import sync_job_repository as jobs
from app.modules.pos.import_mapper import menu_rows, order_rows
from app.modules.pos.sync_job_repository import SyncJob

logger = logging.getLogger(__name__)

TOAST = service.TOAST
# Story #52: Mykonos Grill has sales in Toast since 2024.
DEFAULT_START_DATE = date(2024, 1, 1)
# A business day ends after closing, often around 4am the next morning. Waiting 36 hours
# after midnight UTC means the day has ended in every North American time zone.
BUSINESS_DAY_SETTLE_TIME = timedelta(hours=36)
DEFAULT_CURRENCY = "USD"
# When Toast asks us to slow down, wait as long as it asks if that is at most 10 minutes,
# up to this many times for the same day.
MAX_RATE_LIMIT_WAIT_SECONDS = 600
MAX_RATE_LIMIT_WAITS = 3
RESTARTED_ERROR = "The server restarted during the import. Retry to continue."

type AdapterFactory = Callable[[Session, UUID], PosAdapter]
type SessionFactory = Callable[[], AbstractContextManager[Session]]


class SalesImportError(Exception):
    """An import could not be started or retried. The message is shown to the owner."""


class InvalidImportRangeError(SalesImportError):
    pass


class ImportAlreadyRunningError(SalesImportError):
    pass


class ImportJobNotFoundError(SalesImportError):
    pass


class ImportNotRetryableError(SalesImportError):
    pass


class PosNotConnectedError(SalesImportError):
    pass


class _ImportStoppedError(Exception):
    """Stops a running job; the message is saved on the job for the owner to read."""


def last_finished_business_day(now: datetime) -> date:
    """The newest business day that has surely ended."""
    return (now.astimezone(UTC) - BUSINESS_DAY_SETTLE_TIME).date()


def start_import(
    db: Session,
    *,
    restaurant_id: UUID,
    start_date: date | None,
    end_date: date | None,
    now: datetime,
) -> SyncJob:
    """Create a running Toast import job; the caller then runs it with ``run_import``."""
    latest_day = last_finished_business_day(now)
    start = start_date or DEFAULT_START_DATE
    end = end_date or latest_day
    if start > end:
        raise InvalidImportRangeError("The start date must be on or before the end date.")
    if end > latest_day:
        raise InvalidImportRangeError(
            f"The end date can be {latest_day.isoformat()} at the latest: later days "
            "have not finished yet."
        )
    _require_connection(db, restaurant_id)
    try:
        job = jobs.create_job(
            db, restaurant_id=restaurant_id, provider=TOAST, start_date=start, end_date=end
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ImportAlreadyRunningError("An import is already running.") from exc
    logger.info(
        "Sales import %s created for restaurant %s: %s to %s (%d days)",
        job.id,
        restaurant_id,
        start,
        end,
        job.total_days,
    )
    return job


def retry_import(db: Session, *, restaurant_id: UUID, job_id: UUID) -> SyncJob:
    """Set a failed job running again; it continues from the day after its bookmark."""
    job = jobs.get_job(db, job_id=job_id, restaurant_id=restaurant_id)
    if job is None:
        raise ImportJobNotFoundError("Import not found.")
    if job.status != jobs.FAILED:
        raise ImportNotRetryableError("Only a failed import can be retried.")
    _require_connection(db, restaurant_id)
    try:
        restarted = jobs.restart_job(db, job_id=job_id, restaurant_id=restaurant_id)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ImportAlreadyRunningError("An import is already running.") from exc
    if restarted is None:  # it changed between the two queries
        raise ImportNotRetryableError("Only a failed import can be retried.")
    logger.info("Sales import %s retried from %s", job_id, restarted.last_completed_date)
    return restarted


def get_latest_import(db: Session, *, restaurant_id: UUID) -> SyncJob | None:
    return jobs.get_latest_job(db, restaurant_id=restaurant_id, provider=TOAST)


def run_import(
    session_factory: SessionFactory,
    *,
    job_id: UUID,
    restaurant_id: UUID,
    make_adapter: AdapterFactory | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Run a job until it is done or stops. Runs in the background, after the request that
    started it has answered, so it opens its own database session and never raises."""
    with session_factory() as db:
        try:
            _run(db, job_id, restaurant_id, make_adapter or toast_adapter, sleep)
        except Exception as exc:
            db.rollback()
            message = _error_message(exc)
            if isinstance(exc, _ImportStoppedError):
                logger.warning("Sales import %s stopped: %s", job_id, message)
            else:
                logger.exception("Sales import %s failed", job_id)
            try:
                jobs.fail_job(db, job_id=job_id, restaurant_id=restaurant_id, error=message)
                db.commit()
            except SQLAlchemyError:
                # The database itself is unreachable; the startup check marks the job failed.
                logger.exception("Could not mark sales import %s as failed", job_id)


def fail_interrupted_imports(db: Session, *, started_at: datetime) -> int:
    """Imports run inside the server process, so a job still marked running from before this
    server started was cut off by a restart. Marking it failed lets the owner retry it.
    Jobs started after ``started_at`` are left alone."""
    count = jobs.fail_jobs_running_since(db, before=started_at, error=RESTARTED_ERROR)
    db.commit()
    if count:
        logger.warning("Marked %d interrupted sales import(s) as failed", count)
    return count


def toast_adapter(db: Session, restaurant_id: UUID) -> PosAdapter:
    """A ToastAdapter for the restaurant's saved Toast connection."""
    credentials = service.get_credentials(db, TOAST)
    connection = service.get_connection(db, restaurant_id, TOAST)
    if credentials is None or connection is None:
        raise _ImportStoppedError("Toast is not connected. Connect Toast, then retry the import.")
    return ToastAdapter(
        connection,
        ToastCredentials(
            client_id=credentials["client_id"], client_secret=credentials["client_secret"]
        ),
        currency=DEFAULT_CURRENCY,
        base_url=get_settings().toast_api_base_url,
        transport=service.toast_transport(),
    )


def _run(
    db: Session,
    job_id: UUID,
    restaurant_id: UUID,
    make_adapter: AdapterFactory,
    sleep: Callable[[float], None],
) -> None:
    job = jobs.get_job(db, job_id=job_id, restaurant_id=restaurant_id)
    if job is None or job.status != jobs.RUNNING:
        return
    first_day = (job.last_completed_date or job.start_date - timedelta(days=1)) + timedelta(days=1)
    logger.info("Sales import %s running from %s to %s", job_id, first_day, job.end_date)
    # One adapter, so one Toast login, for the whole job.
    with make_adapter(db, restaurant_id) as adapter:
        if not adapter.authenticate():
            raise _ImportStoppedError("Toast rejected the saved login. Reconnect Toast and retry.")
        currency = _save_menu(db, adapter, restaurant_id)
        day = first_day
        while day <= job.end_date:
            _require_still_connected(db, restaurant_id)
            lines = _fetch_day(adapter, day, sleep)
            saved = import_repository.save_sales_day(
                db,
                restaurant_id=restaurant_id,
                provider=TOAST,
                currency=currency,
                orders=order_rows(lines, restaurant_id),
            )
            jobs.complete_day(
                db,
                job_id=job_id,
                restaurant_id=restaurant_id,
                day=day,
                orders=saved.orders,
                items=saved.lines,
            )
            db.commit()  # the day and the bookmark together, or neither
            day += timedelta(days=1)
    jobs.finish_job(db, job_id=job_id, restaurant_id=restaurant_id)
    db.commit()
    logger.info("Sales import %s finished", job_id)


def _save_menu(db: Session, adapter: PosAdapter, restaurant_id: UUID) -> str:
    """Save the current menu first, so sales of current items find them. Returns the menu's
    currency, used for items that are only seen in old sales."""
    items = adapter.fetch_menu_items()
    import_repository.save_menu(
        db, restaurant_id=restaurant_id, provider=TOAST, menu=menu_rows(items, restaurant_id)
    )
    db.commit()
    return items[0].currency if items else DEFAULT_CURRENCY


def _fetch_day(adapter: PosAdapter, day: date, sleep: Callable[[float], None]) -> list[SaleLine]:
    """One day of sale lines, waiting when Toast asks us to slow down."""
    for attempt in range(MAX_RATE_LIMIT_WAITS + 1):
        try:
            return adapter.fetch_orders_for_business_date(day)
        except ToastRateLimitError as exc:
            wait = exc.retry_after_seconds
            if (
                wait is None
                or wait > MAX_RATE_LIMIT_WAIT_SECONDS
                or attempt == MAX_RATE_LIMIT_WAITS
            ):
                raise _ImportStoppedError(
                    "Toast is limiting requests right now. Retry later: the days already "
                    "imported are kept."
                ) from exc
            logger.warning("Toast rate limit on %s; waiting %.0fs", day, wait)
            sleep(wait)
    raise AssertionError("unreachable")  # pragma: no cover


def _require_connection(db: Session, restaurant_id: UUID) -> None:
    if repository.get_connection(db, restaurant_id, TOAST) is None:
        raise PosNotConnectedError("Connect Toast before importing sales.")


def _require_still_connected(db: Session, restaurant_id: UUID) -> None:
    if repository.get_connection(db, restaurant_id, TOAST) is None:
        raise _ImportStoppedError(
            "Toast was disconnected. Reconnect Toast, then retry to continue the import."
        )


def _error_message(exc: Exception) -> str:
    if isinstance(exc, _ImportStoppedError):
        return str(exc)
    if isinstance(exc, ToastApiError):
        return "Toast could not be reached. Retry later: the days already imported are kept."
    return "Something went wrong during the import. Retry to continue where it stopped."

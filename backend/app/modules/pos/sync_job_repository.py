# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Database queries for sync_jobs, the background POS imports. Nothing here commits."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

RUNNING = "running"
FAILED = "failed"
DONE = "done"


@dataclass(frozen=True)
class SyncJob:
    id: UUID
    restaurant_id: UUID
    provider: str
    status: str
    start_date: date
    end_date: date
    # The bookmark: every business day up to this one is saved. None before the first day.
    last_completed_date: date | None
    orders_imported: int
    items_imported: int
    error: str | None
    created_at: datetime
    finished_at: datetime | None

    @property
    def total_days(self) -> int:
        return (self.end_date - self.start_date).days + 1

    @property
    def days_completed(self) -> int:
        if self.last_completed_date is None:
            return 0
        return (self.last_completed_date - self.start_date).days + 1


_COLUMNS = """
    id, restaurant_id, provider, status, start_date, end_date, last_completed_date,
    orders_imported, items_imported, error, created_at, finished_at
"""


def create_job(
    db: Session, *, restaurant_id: UUID, provider: str, start_date: date, end_date: date
) -> SyncJob:
    """A new running job. Raises IntegrityError (uq_sync_jobs_one_running) when one is
    already running for this restaurant and provider."""
    row = db.execute(
        text(f"""
            INSERT INTO sync_jobs (restaurant_id, provider, start_date, end_date)
            VALUES (:restaurant_id, :provider, :start_date, :end_date)
            RETURNING {_COLUMNS}
        """),
        {
            "restaurant_id": restaurant_id,
            "provider": provider,
            "start_date": start_date,
            "end_date": end_date,
        },
    ).one()
    return _job(row._mapping)


def get_job(db: Session, *, job_id: UUID, restaurant_id: UUID) -> SyncJob | None:
    row = db.execute(
        text(f"""
            SELECT {_COLUMNS} FROM sync_jobs
            WHERE id = :job_id AND restaurant_id = :restaurant_id
        """),
        {"job_id": job_id, "restaurant_id": restaurant_id},
    ).first()
    return _job(row._mapping) if row is not None else None


def get_latest_job(db: Session, *, restaurant_id: UUID, provider: str) -> SyncJob | None:
    row = db.execute(
        text(f"""
            SELECT {_COLUMNS} FROM sync_jobs
            WHERE restaurant_id = :restaurant_id AND provider = :provider
            ORDER BY created_at DESC, id DESC
            LIMIT 1
        """),
        {"restaurant_id": restaurant_id, "provider": provider},
    ).first()
    return _job(row._mapping) if row is not None else None


def complete_day(
    db: Session, *, job_id: UUID, restaurant_id: UUID, day: date, orders: int, items: int
) -> None:
    """Move the bookmark to ``day`` and add its counts. Saved in the same transaction as the
    day's sales, so the bookmark never points past what is really saved."""
    db.execute(
        text("""
            UPDATE sync_jobs
            SET last_completed_date = :day,
                orders_imported = orders_imported + :orders,
                items_imported = items_imported + :items,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :job_id AND restaurant_id = :restaurant_id
        """),
        {
            "job_id": job_id,
            "restaurant_id": restaurant_id,
            "day": day,
            "orders": orders,
            "items": items,
        },
    )


def finish_job(db: Session, *, job_id: UUID, restaurant_id: UUID) -> None:
    _set_status(db, job_id=job_id, restaurant_id=restaurant_id, status=DONE, error=None)


def fail_job(db: Session, *, job_id: UUID, restaurant_id: UUID, error: str) -> None:
    _set_status(db, job_id=job_id, restaurant_id=restaurant_id, status=FAILED, error=error)


def restart_job(db: Session, *, job_id: UUID, restaurant_id: UUID) -> SyncJob | None:
    """Set a failed job running again from its bookmark; None when it is not failed.
    Raises IntegrityError (uq_sync_jobs_one_running) when another job is running."""
    row = db.execute(
        text(f"""
            UPDATE sync_jobs
            SET status = '{RUNNING}', error = NULL, finished_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :job_id AND restaurant_id = :restaurant_id AND status = '{FAILED}'
            RETURNING {_COLUMNS}
        """),
        {"job_id": job_id, "restaurant_id": restaurant_id},
    ).first()
    return _job(row._mapping) if row is not None else None


def fail_jobs_running_since(db: Session, *, before: datetime, error: str) -> int:
    """Mark failed every job, of any restaurant, still running with no progress since
    ``before``. Used once at startup; returns how many were marked."""
    result = db.execute(
        text(f"""
            UPDATE sync_jobs
            SET status = '{FAILED}', error = :error, finished_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE status = '{RUNNING}' AND updated_at < :before
        """),
        {"before": before, "error": error},
    )
    return int(getattr(result, "rowcount", 0))


def _set_status(
    db: Session, *, job_id: UUID, restaurant_id: UUID, status: str, error: str | None
) -> None:
    db.execute(
        text("""
            UPDATE sync_jobs
            SET status = :status, error = :error, finished_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :job_id AND restaurant_id = :restaurant_id
        """),
        {"job_id": job_id, "restaurant_id": restaurant_id, "status": status, "error": error},
    )


def _job(row: Any) -> SyncJob:
    return SyncJob(**{key: row[key] for key in SyncJob.__dataclass_fields__})

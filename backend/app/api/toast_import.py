# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Owner-only endpoints to import Toast sales history in the background and follow it."""

from datetime import UTC, datetime
from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.auth import OwnerDep
from app.core.database import get_db
from app.modules.pos import import_service
from app.modules.pos.sync_job_repository import SyncJob
from app.schemas.pos import SalesImportRequest, SalesImportResponse

router = APIRouter(prefix="/api/pos/toast/imports", tags=["toast"])
DbSession = Annotated[Session, Depends(get_db)]

# The message of each error is written for the owner, so it is sent as the detail.
IMPORT_ERRORS: dict[type[import_service.SalesImportError], int] = {
    import_service.InvalidImportRangeError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    import_service.PosNotConnectedError: status.HTTP_404_NOT_FOUND,
    import_service.ImportJobNotFoundError: status.HTTP_404_NOT_FOUND,
    import_service.ImportAlreadyRunningError: status.HTTP_409_CONFLICT,
    import_service.ImportNotRetryableError: status.HTTP_409_CONFLICT,
}


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=SalesImportResponse)
def start_import(
    payload: SalesImportRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    user: OwnerDep,
    db: DbSession,
) -> SalesImportResponse:
    """Start importing Toast sales in the background, then answer right away (202).

    Without a start date the import begins on 2024-01-01; without an end date it stops at
    the last business day that has surely ended. Poll ``GET /latest`` to follow it.
    """
    try:
        job = import_service.start_import(
            db,
            restaurant_id=user.restaurant_id,
            start_date=payload.start_date,
            end_date=payload.end_date,
            now=datetime.now(UTC),
        )
    except import_service.SalesImportError as exc:
        _import_error(exc)
    except SQLAlchemyError as exc:
        _storage_error(exc)
    _run_in_background(background_tasks, request, job)
    return _response(job)


@router.get("/latest", response_model=SalesImportResponse | None)
def get_latest_import(user: OwnerDep, db: DbSession) -> SalesImportResponse | None:
    """The restaurant's most recent import, or null when it has never imported."""
    try:
        job = import_service.get_latest_import(db, restaurant_id=user.restaurant_id)
    except SQLAlchemyError as exc:
        _storage_error(exc)
    return _response(job) if job is not None else None


@router.post(
    "/{job_id}/retry", status_code=status.HTTP_202_ACCEPTED, response_model=SalesImportResponse
)
def retry_import(
    job_id: UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    user: OwnerDep,
    db: DbSession,
) -> SalesImportResponse:
    """Continue a failed import from the day after the last saved one."""
    try:
        job = import_service.retry_import(db, restaurant_id=user.restaurant_id, job_id=job_id)
    except import_service.SalesImportError as exc:
        _import_error(exc)
    except SQLAlchemyError as exc:
        _storage_error(exc)
    _run_in_background(background_tasks, request, job)
    return _response(job)


def _run_in_background(background_tasks: BackgroundTasks, request: Request, job: SyncJob) -> None:
    # The request's own database session closes once it answers, so the job gets the
    # session factory and opens its own.
    background_tasks.add_task(
        import_service.run_import,
        request.app.state.session_factory,
        job_id=job.id,
        restaurant_id=job.restaurant_id,
    )


def _response(job: SyncJob) -> SalesImportResponse:
    return SalesImportResponse(
        id=job.id,
        status=job.status,  # the database only allows running, failed and done
        start_date=job.start_date,
        end_date=job.end_date,
        last_completed_date=job.last_completed_date,
        days_completed=job.days_completed,
        total_days=job.total_days,
        percent=job.days_completed * 100 // job.total_days,
        orders_imported=job.orders_imported,
        items_imported=job.items_imported,
        error=job.error,
        created_at=job.created_at,
        finished_at=job.finished_at,
    )


def _import_error(exc: import_service.SalesImportError) -> NoReturn:
    raise HTTPException(status_code=IMPORT_ERRORS[type(exc)], detail=str(exc)) from exc


def _storage_error(exc: Exception) -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Could not read or save the import due to a database error.",
    ) from exc

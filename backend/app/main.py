# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
# Human-authored baseline: 50% or more human-written; human-authors: Yassine Hajou
"""FastAPI application entry point. uvicorn serves ``app.main:app``."""

import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.pos import router as pos_router
from app.api.toast import router as toast_router
from app.api.toast_connection import router as toast_connection_router
from app.api.toast_import import router as toast_import_router
from app.core.config import Settings, get_settings
from app.core.database import create_session_factory
from app.core.logging_config import configure_logging
from app.modules.pos import import_service

logger = logging.getLogger(__name__)


async def http_exception_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Ensures all HTTPExceptions return a uniform {"detail": "<string>"} payload."""
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": detail},
        headers=exc.headers,
    )


async def validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Flattens Pydantic 422 validation errors into the same {"detail": "<string>"} shape."""
    messages: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err.get("loc", []) if part != "body")
        msg = err.get("msg", "Invalid input")
        messages.append(f"{loc}: {msg}" if loc else msg)

    detail = "; ".join(messages) if messages else "Invalid request payload."
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": detail},
    )


def fail_interrupted_imports(session_factory: sessionmaker[Session], started_at: datetime) -> None:
    """Mark sales imports cut off by a restart as failed, so the owner can retry them."""
    try:
        with session_factory() as db:
            import_service.fail_interrupted_imports(db, started_at=started_at)
    except SQLAlchemyError:
        logger.warning("Could not check for interrupted sales imports", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # In a background thread, so a sleeping database never delays startup.
    threading.Thread(
        target=fail_interrupted_imports,
        args=(app.state.session_factory, datetime.now(UTC)),
        daemon=True,
    ).start()
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title="powr API", version="0.1.0", lifespan=lifespan)
    app.state.session_factory = create_session_factory(str(settings.database_url))
    app.add_exception_handler(
        StarletteHTTPException,
        http_exception_handler,  # type: ignore[arg-type]
    )
    app.add_exception_handler(
        RequestValidationError,
        validation_exception_handler,  # type: ignore[arg-type]
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(pos_router)
    app.include_router(toast_router)
    app.include_router(toast_connection_router)
    app.include_router(toast_import_router)
    return app


app = create_app()

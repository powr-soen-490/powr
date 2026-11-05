# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
# Human-authored baseline: 50% or more human-written; human-authors: Yassine Hajou
"""FastAPI application entry point. uvicorn serves ``app.main:app``."""

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.pos import router as pos_router
from app.core.config import Settings, get_settings
from app.core.database import create_session_factory
from app.core.logging_config import configure_logging


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


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title="powr API", version="0.1.0")
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
    return app


app = create_app()

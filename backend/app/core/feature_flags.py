# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Shared Flagsmith evaluation and FastAPI route guards."""

from collections.abc import Callable
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, status
from flagsmith import Flagsmith
from flagsmith.exceptions import FlagsmithClientError
from flagsmith.models import DefaultFlag
from requests import RequestException

from app.core.config import Settings, get_settings


class FeatureFlagsUnavailableError(RuntimeError):
    """Raised when the feature flag service cannot provide an evaluation."""


def _disabled_flag(_feature_name: str) -> DefaultFlag:
    return DefaultFlag(enabled=False, value=None)


@lru_cache(maxsize=4)
def _get_flagsmith_client(environment_key: str, api_url: str) -> Flagsmith:
    return Flagsmith(
        environment_key=environment_key,
        api_url=api_url,
        request_timeout_seconds=5,
        default_flag_handler=_disabled_flag,
    )


def is_feature_enabled(feature_name: str, settings: Settings | None = None) -> bool:
    """Evaluate a flag for backend use; unknown flags are disabled."""
    app_settings = settings or get_settings()
    if (
        app_settings.flagsmith_server_side_key is None
        or not app_settings.flagsmith_server_side_key.get_secret_value().strip()
    ):
        raise FeatureFlagsUnavailableError(
            "FLAGSMITH_SERVER_SIDE_KEY must be configured before evaluating feature flags."
        )

    client = _get_flagsmith_client(
        app_settings.flagsmith_server_side_key.get_secret_value(),
        app_settings.flagsmith_api_url,
    )
    try:
        return client.get_environment_flags().is_feature_enabled(feature_name)
    except (FlagsmithClientError, RequestException) as exc:
        raise FeatureFlagsUnavailableError(
            "Flagsmith could not evaluate the requested feature flag."
        ) from exc


def require_feature(feature_name: str) -> Callable[..., None]:
    """Create a route dependency that hides disabled features and fails closed."""

    def check_feature(
        settings: Annotated[Settings, Depends(get_settings)],
    ) -> None:
        try:
            enabled = is_feature_enabled(feature_name, settings)
        except FeatureFlagsUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Feature flag service unavailable.",
            ) from exc
        if not enabled:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Not found.",
            )

    return check_feature

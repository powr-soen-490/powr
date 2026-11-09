# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Application settings, loaded from environment variables and validated at startup."""

from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, PostgresDsn, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The repository-root .env is shared with docker-compose. Inside the container this path
# does not exist, and settings come from the environment variables Compose injects.
ROOT_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


DEV_SESSION_SECRET_KEY = "dev-secret-key"  # Committed Placeholder
DEPLOYED_ENVIRONMENTS = frozenset({"staging", "production"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_ENV_FILE, extra="ignore", hide_input_in_errors=True
    )
    environment: Literal["development", "test", "staging", "production"] = "development"
    database_url: PostgresDsn
    cors_origins: list[str] = ["http://localhost:5173"]
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    flagsmith_server_side_key: SecretStr | None = None
    flagsmith_api_url: str = "https://edge.api.flagsmith.com/api/v1/"

    # Session & Cookie Security Settings
    session_secret_key: str = DEV_SESSION_SECRET_KEY
    session_cookie_name: str = "powr_session"
    session_max_age_seconds: int = 86400  # 24 hours
    # Must be true in staging/prod (which is enforced below)
    # False lets cookies work over localhost in dev
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"

    # Failed login rate-limiting settings (5 failed attempts per 60 seconds)
    login_max_failed_attempts: int = 5
    login_lockout_window_seconds: int = 60

    git_commit: str | None = Field(default=None, validation_alias="RENDER_GIT_COMMIT")

    @model_validator(mode="after")
    def _require_safe_settings_when_deployed(self) -> Self:
        """Refuse to start a deployed environment with the committed development defaults."""
        if self.environment not in DEPLOYED_ENVIRONMENTS:
            return self
        if self.session_secret_key == DEV_SESSION_SECRET_KEY:
            raise ValueError(
                "SESSION_SECRET_KEY must be set to a private value "
                f"when ENVIRONMENT={self.environment}"
            )
        if not self.cookie_secure:
            raise ValueError(f"COOKIE_SECURE must be true when ENVIRONMENT={self.environment}")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

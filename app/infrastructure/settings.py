"""Application settings, sourced exclusively from the environment.

No secret has a production default. ``JWT_SECRET_KEY`` is only auto-generated
when ``DEMO_MODE`` is on; otherwise startup fails fast with a clear message.
"""

from __future__ import annotations

import json
import secrets
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application ---------------------------------------------------
    app_name: str = "Student Engagement Analytics API"
    app_version: str = "2.0.0"
    environment: Literal["local", "ci", "staging", "production"] = "local"
    debug: bool = False

    # --- Demo -----------------------------------------------------------
    demo_mode: bool = Field(
        default=True,
        description="Seed deterministic demo data and create demo users at startup.",
    )
    demo_viewer_username: str = "demo"
    # These are documented, deliberately public demo logins, not secrets. They
    # only exist while DEMO_MODE is on and are overridable from the environment.
    demo_viewer_password: str = "demo-viewer-2026"  # noqa: S105
    demo_analyst_username: str = "analyst"
    demo_analyst_password: str = "analyst-demo-2026"  # noqa: S105
    demo_admin_username: str = "admin"
    demo_admin_password: str = "admin-demo-2026"  # noqa: S105
    demo_seed: int = 42

    # --- Database --------------------------------------------------------
    database_url: str = "sqlite+aiosqlite:///./engagement.db"
    database_echo: bool = False
    database_pool_size: int = 5
    database_max_overflow: int = 10

    # --- Security ---------------------------------------------------------
    jwt_secret_key: str = ""
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    jwt_issuer: str = "student-engagement-api"
    jwt_audience: str = "student-engagement-clients"
    access_token_expire_minutes: Annotated[int, Field(ge=1, le=1440)] = 30

    # --- CORS --------------------------------------------------------------
    cors_allow_origins: list[str] = Field(default_factory=lambda: ["http://localhost:8000"])
    cors_allow_credentials: bool = False
    cors_allow_methods: list[str] = Field(default_factory=lambda: ["GET", "POST", "OPTIONS"])
    cors_allow_headers: list[str] = Field(
        default_factory=lambda: ["Authorization", "Content-Type", "X-Request-ID"]
    )

    # --- Rate limiting ------------------------------------------------------
    rate_limit_enabled: bool = True
    rate_limit_default: str = "120/minute"
    rate_limit_auth: str = "10/minute"

    # --- Logging -------------------------------------------------------------
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "json"

    @field_validator(
        "cors_allow_origins", "cors_allow_methods", "cors_allow_headers", mode="before"
    )
    @classmethod
    def _split_csv(cls, value: object) -> object:
        """Accept a comma-separated string as well as a JSON list."""
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                try:
                    return json.loads(stripped)
                except json.JSONDecodeError:
                    return value
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def _require_secret_outside_demo(self) -> Settings:
        if not self.jwt_secret_key:
            if self.demo_mode or self.environment in ("local", "ci"):
                # Ephemeral per-process secret: tokens do not survive a restart,
                # which is exactly what a throwaway demo should do.
                object.__setattr__(self, "jwt_secret_key", secrets.token_urlsafe(48))
            else:
                msg = (
                    "JWT_SECRET_KEY must be set when DEMO_MODE is off. "
                    'Generate one with: python -c "import secrets; '
                    'print(secrets.token_urlsafe(48))"'
                )
                raise ValueError(msg)
        if len(self.jwt_secret_key) < 32:
            msg = "JWT_SECRET_KEY must be at least 32 characters."
            raise ValueError(msg)
        return self

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()

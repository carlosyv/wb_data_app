"""Application settings loaded from environment variables / .env file."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All config knobs for the WB Data App.

    Values are read from environment variables first, then from the .env file
    located at the project root.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Database ─────────────────────────────────────────────────────────
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "wb_web_app"
    db_user: str = "user"
    db_password: str = "password"

    @property
    def database_url(self) -> str:
        """Async PostgreSQL DSN used by SQLAlchemy."""
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def database_url_sync(self) -> str:
        """Sync PostgreSQL DSN used by Alembic."""
        return (
            f"postgresql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    # ── World Bank API ───────────────────────────────────────────────────
    wb_api_base_url: str = "https://api.worldbank.org/v2"
    wb_max_concurrent_requests: int = 5
    wb_delay_between_requests: float = 0.5  # seconds
    wb_max_retries: int = 5
    wb_backoff_initial: float = 2.0  # seconds
    wb_backoff_max: float = 60.0  # seconds

    # ── App ──────────────────────────────────────────────────────────────
    app_env: str = "development"
    app_port: int = 8000
    app_debug: bool = True


# Singleton — import this everywhere
settings = Settings()

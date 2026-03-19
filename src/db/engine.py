"""Async SQLAlchemy engine and session factory."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config.settings import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.app_debug,
    pool_size=10,
    max_overflow=20,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncSession:  # type: ignore[misc]
    """FastAPI dependency that yields a DB session and closes it after use."""
    async with async_session_factory() as session:
        yield session

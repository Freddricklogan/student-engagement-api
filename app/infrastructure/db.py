"""Async SQLAlchemy 2.0 engine and session-per-request plumbing."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.infrastructure.settings import Settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _enable_sqlite_foreign_keys(engine: AsyncEngine) -> None:
    """SQLite ignores foreign keys unless the pragma is set per connection."""

    @event.listens_for(engine.sync_engine, "connect")
    def _set_pragma(dbapi_connection: Any, _record: Any) -> None:  # pragma: no cover
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def create_engine(settings: Settings) -> AsyncEngine:
    """Build an async engine appropriate for the configured backend."""
    kwargs: dict[str, Any] = {"echo": settings.database_echo, "future": True}
    if settings.is_sqlite:
        # aiosqlite runs each connection on its own thread. Pooling those across
        # event loops (tests, or a reload) leaves threads calling into a closed
        # loop, so SQLite connections are opened and closed per checkout.
        kwargs["poolclass"] = NullPool
    else:
        kwargs["pool_size"] = settings.database_pool_size
        kwargs["max_overflow"] = settings.database_max_overflow
        kwargs["pool_pre_ping"] = True

    engine = create_async_engine(settings.database_url, **kwargs)
    if settings.is_sqlite:
        _enable_sqlite_foreign_keys(engine)
    return engine


def init_engine(settings: Settings) -> AsyncEngine:
    """Initialise (or replace) the process-wide engine and sessionmaker."""
    global _engine, _sessionmaker
    _engine = create_engine(settings)
    _sessionmaker = async_sessionmaker(
        _engine, expire_on_commit=False, autoflush=False, class_=AsyncSession
    )
    return _engine


def get_engine() -> AsyncEngine:
    if _engine is None:  # pragma: no cover - guarded by app lifespan
        msg = "Database engine has not been initialised."
        raise RuntimeError(msg)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:  # pragma: no cover - guarded by app lifespan
        msg = "Database sessionmaker has not been initialised."
        raise RuntimeError(msg)
    return _sessionmaker


async def dispose_engine() -> None:
    """Release pooled connections on shutdown."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


async def session_scope() -> AsyncIterator[AsyncSession]:
    """Yield one session per request, committing on success and rolling back on error."""
    factory = get_sessionmaker()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

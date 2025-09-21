"""Database engine and session factory helpers."""
from __future__ import annotations

from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.config import Settings, get_settings

_engine: Engine | None = None
SessionLocal: sessionmaker[Session] = sessionmaker(
    expire_on_commit=False,
    autoflush=False,
    future=True,
)


def _create_engine(settings: Settings) -> Engine:
    """Construct a new SQLAlchemy engine from the provided settings."""

    return create_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        pool_pre_ping=True,
        future=True,
    )


def init_engine(settings: Settings | None = None) -> Engine:
    """Initialise or rebind the global engine and session factory."""

    global _engine
    settings = settings or get_settings()
    if _engine is not None:
        _engine.dispose()
    _engine = _create_engine(settings)
    SessionLocal.configure(bind=_engine)
    return _engine


def get_engine() -> Engine:
    """Return the active SQLAlchemy engine, initialising it if necessary."""

    if _engine is None:
        return init_engine()
    return _engine


def get_db_session() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session for FastAPI dependency injection."""

    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# Initialise engine on import so application startup has a ready session factory.
init_engine()


__all__ = ["SessionLocal", "get_db_session", "get_engine", "init_engine"]

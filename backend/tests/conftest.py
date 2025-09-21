"""Shared pytest fixtures for backend tests."""
from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from backend.app.config import Settings, get_settings, settings_dependency
from backend.app.main import create_app
from backend.db.session import SessionLocal, init_engine

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def reset_settings_cache() -> Iterator[None]:
    """Ensure settings cache is clear before and after each test."""

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """Return a database URL suitable for integration tests."""

    url = os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@localhost:5432/postgres",
    )

    engine = create_engine(url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - skip when postgres unavailable
        pytest.skip(f"Postgres unavailable for tests: {exc}")
    finally:
        engine.dispose()

    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    os.environ.setdefault("DB_POOL_SIZE", "5")

    try:
        yield url
    finally:
        if previous is not None:
            os.environ["DATABASE_URL"] = previous
        else:
            os.environ.pop("DATABASE_URL", None)


@pytest.fixture(scope="session")
def alembic_config(database_url: str) -> Config:
    """Return Alembic configuration pointed at the test database."""

    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


@pytest.fixture(scope="session")
def migrated_database(alembic_config: Config) -> Iterator[str]:
    """Apply Alembic migrations for the test database."""

    command.upgrade(alembic_config, "head")
    try:
        yield alembic_config.get_main_option("sqlalchemy.url")
    finally:
        command.downgrade(alembic_config, "base")


@pytest.fixture(scope="session")
def settings_override(database_url: str) -> Settings:
    """Session-scoped settings pointing at the isolated database."""

    return Settings(
        app_env="test",
        log_level="INFO",
        postgres_url=database_url,
        qdrant_url="http://localhost:6333",
        app_version="test-version",
        database_url=database_url,
        db_pool_size=5,
        embedding_model="test-embed",
        embedding_fallback_models=[],
        local_ingest_root=Path(PROJECT_ROOT / "tests" / "fixtures" / "docs"),
        chunk_size=200,
        chunk_overlap=20,
        ingest_default_tenant="default",
    )


@pytest.fixture(scope="session")
def db_engine(settings_override: Settings, migrated_database: str):
    """Initialise the global engine against the test database."""

    engine = init_engine(settings_override)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session(db_engine):
    """Yield a transactional SQLAlchemy session for ORM tests."""

    session = SessionLocal()
    try:
        yield session
        session.rollback()
    finally:
        session.close()


@pytest.fixture
def test_settings(settings_override: Settings) -> Settings:
    """Return deterministic settings for FastAPI tests."""

    return settings_override


@pytest.fixture
def app(test_settings: Settings):
    """Create a FastAPI app with overridden settings."""

    application = create_app()
    application.dependency_overrides[settings_dependency] = lambda: test_settings
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
async def async_client(app) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        yield client


@pytest.fixture
def log_capture() -> Iterator[list[dict[str, object]]]:
    """Capture structlog events for assertions."""

    from structlog.testing import capture_logs

    with capture_logs() as logs:
        yield logs

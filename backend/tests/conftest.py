"""Shared pytest fixtures for backend tests."""
from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
from httpx import AsyncClient

from backend.app.config import Settings, get_settings, settings_dependency
from backend.app.main import create_app


@pytest.fixture(autouse=True)
def reset_settings_cache() -> Iterator[None]:
    """Ensure settings cache is clear before and after each test."""

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def test_settings() -> Settings:
    """Return deterministic settings for tests."""

    return Settings(
        app_env="test",
        log_level="INFO",
        postgres_url="postgresql://postgres:postgres@localhost:5432/postgres",
        qdrant_url="http://localhost:6333",
        app_version="test-version",
    )


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

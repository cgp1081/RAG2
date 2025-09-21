"""Shared fixtures for ingestion pipeline tests."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, Sequence

import pytest
from sqlalchemy import text

from backend.app.config import Settings
from backend.db.session import SessionLocal
from backend.ingestion.dedup import cosine_similarity
from backend.ingestion.pipeline import IngestionPipeline
from backend.services.vector_store import VectorPayload


class VectorStoreFake:
    def __init__(self) -> None:
        self.collections: set[str] = set()
        self.storage: Dict[str, Dict[str, dict[str, Any]]] = defaultdict(dict)

    async def ensure_collection(self, tenant_id: str) -> str:
        name = f"tenant_{tenant_id}"
        self.collections.add(name)
        return name

    async def healthcheck(self) -> None:  # pragma: no cover - simple stub
        return None

    async def upsert_batch(
        self,
        tenant_id: str,
        vectors: Iterable[VectorPayload],
        *,
        wait: bool = True,
    ) -> list[str]:
        ids: list[str] = []
        for payload in vectors:
            vector_id = str(payload["id"])
            self.storage[tenant_id][vector_id] = {
                "embedding": list(payload["embedding"]),
                "payload": payload.get("metadata", {}),
            }
            ids.append(vector_id)
        return ids

    async def has_similar_embedding(
        self,
        tenant_id: str,
        embedding: Sequence[float],
        *,
        threshold: float = 0.995,
        filters: dict[str, Any] | None = None,
        limit: int = 5,
    ) -> bool:
        stored = list(self.storage.get(tenant_id, {}).values())
        return any(
            cosine_similarity(entry["embedding"], embedding) >= threshold
            for entry in stored
        )

    async def delete_points(
        self, tenant_id: str, ids: Sequence[str]
    ) -> None:  # pragma: no cover - unused
        for point_id in ids:
            self.storage.get(tenant_id, {}).pop(point_id, None)

    async def close(self) -> None:  # pragma: no cover - nothing to close
        return None


class EmbeddingServiceFake:
    def __init__(self, dim: int = 3) -> None:
        self.dim = dim
        self.fail = False

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if self.fail:
            raise RuntimeError("embedding failure")
        embeddings: list[list[float]] = []
        for value in texts:
            length = float(len(value))
            checksum = float(sum(ord(ch) for ch in value) % 1000)
            embeddings.append([length, checksum, length + checksum][: self.dim])
        return embeddings

    async def healthcheck(self) -> None:  # pragma: no cover - simple stub
        return None


@pytest.fixture
def vector_store_fake() -> VectorStoreFake:
    return VectorStoreFake()


@pytest.fixture
def embedding_service_fake() -> EmbeddingServiceFake:
    return EmbeddingServiceFake()


@pytest.fixture
def ingestion_settings(tmp_path: Path, settings_override: Settings) -> Settings:
    return Settings(
        **{
            **settings_override.model_dump(),
            "local_ingest_root": tmp_path,
            "chunk_size": 40,
            "chunk_overlap": 10,
            "vector_dim": 3,
            "embedding_fallback_models": [],
        }
    )


@pytest.fixture
def ingestion_db_session(request):
    try:
        request.getfixturevalue("db_engine")
    except pytest.FixtureLookupError:
        pytest.skip("database fixture unavailable")
    session = SessionLocal()
    try:
        yield session
        session.rollback()
    finally:
        session.close()


@pytest.fixture
def ingestion_pipeline(
    ingestion_db_session,
    vector_store_fake: VectorStoreFake,
    embedding_service_fake: EmbeddingServiceFake,
    ingestion_settings: Settings,
):
    return IngestionPipeline(
        session=ingestion_db_session,
        vector_store=vector_store_fake,
        embedding_service=embedding_service_fake,
        settings=ingestion_settings,
    )


@pytest.fixture(autouse=True)
def _cleanup_ingestion_tables(ingestion_db_session):
    yield
    ingestion_db_session.execute(
        text(
            "TRUNCATE TABLE ingestion_events, "
            "ingestion_runs, document_chunks, documents "
            "RESTART IDENTITY CASCADE"
        )
    )
    ingestion_db_session.commit()


def pytest_configure(config: pytest.Config) -> None:  # pragma: no cover - pytest hook
    plugin_name = "backend.tests.conftest"
    if not config.pluginmanager.has_plugin(plugin_name):
        try:
            config.pluginmanager.import_plugin(plugin_name)
        except ValueError:
            pass

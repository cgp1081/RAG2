"""Runtime hook for executing the ingestion pipeline from the CLI."""
from __future__ import annotations

from pathlib import Path

import httpx

from backend.app.config import get_settings
from backend.app.logging import get_logger
from backend.db import SessionLocal
from backend.db.models import IngestionRun
from backend.ingestion.pipeline import IngestionPipeline
from backend.services.embedding_service import build_embedding_service
from backend.services.vector_store import build_vector_store

logger = get_logger(__name__)


async def run_ingest(
    *,
    path: Path,
    tenant_id: str,
    infer_metadata: bool,
    batch_size: int,
) -> None:
    settings = get_settings()
    session = SessionLocal()
    run = IngestionRun(
        tenant_id=tenant_id,
        source_id=None,
        status="pending",
        total_documents=0,
        processed_documents=0,
        path=str(path.resolve()),
    )
    session.add(run)
    session.commit()

    vector_store = build_vector_store(settings)
    async with httpx.AsyncClient(timeout=settings.vector_timeout_seconds) as http_client:
        embedding_service = build_embedding_service(settings, http_client)
        pipeline = IngestionPipeline(
            session=session,
            vector_store=vector_store,
            embedding_service=embedding_service,
            settings=settings,
        )
        try:
            await pipeline.ingest_directory(
                run,
                path=path,
                tenant_id=tenant_id,
                infer_metadata=infer_metadata,
                batch_size=batch_size,
            )
        finally:
            await vector_store.close()
            session.close()

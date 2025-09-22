from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from backend.db.models import (
    Document,
    DocumentChunk,
    IngestionEvent,
    IngestionEventType,
    IngestionRun,
)

FIXTURE_DOCS = Path(__file__).resolve().parents[1] / "fixtures" / "docs"


def copy_fixture_docs(source: Path, destination: Path) -> None:
    for item in source.iterdir():
        if item.is_file():
            shutil.copy(item, destination / item.name)


@pytest.mark.asyncio
async def test_ingest_new_documents_creates_chunks_and_embeddings(
    db_session,
    ingestion_pipeline,
    vector_store_fake,
    ingestion_settings,
):
    workspace = ingestion_settings.local_ingest_root
    workspace.mkdir(parents=True, exist_ok=True)
    copy_fixture_docs(FIXTURE_DOCS, workspace)

    run = IngestionRun(
        tenant_id="default",
        source_id=None,
        status="pending",
        total_documents=0,
        processed_documents=0,
    )
    db_session.add(run)
    db_session.commit()

    result = await ingestion_pipeline.ingest_directory(
        run,
        path=workspace,
        tenant_id="default",
        infer_metadata=False,
        batch_size=10,
    )

    db_session.refresh(run)
    docs = db_session.query(Document).all()
    chunks = db_session.query(DocumentChunk).all()
    assert run.status == "completed"
    assert result.processed_documents == 2
    assert len(docs) == 2
    assert len(chunks) >= 2
    stored_vectors = list(vector_store_fake.storage["default"].values())
    assert stored_vectors
    metadata = stored_vectors[0]["payload"]
    assert metadata.get("chunk_id")
    assert metadata.get("content")
    assert len(metadata["content"]) <= 500


@pytest.mark.asyncio
async def test_reingest_skips_duplicates(
    db_session,
    ingestion_pipeline,
    vector_store_fake,
    ingestion_settings,
):
    workspace = ingestion_settings.local_ingest_root
    workspace.mkdir(parents=True, exist_ok=True)
    copy_fixture_docs(FIXTURE_DOCS, workspace)

    async def run_once() -> IngestionRun:
        run = IngestionRun(
            tenant_id="default",
            source_id=None,
            status="pending",
            total_documents=0,
            processed_documents=0,
        )
        db_session.add(run)
        db_session.commit()
        await ingestion_pipeline.ingest_directory(
            run,
            path=workspace,
            tenant_id="default",
            infer_metadata=False,
            batch_size=10,
        )
        db_session.refresh(run)
        return run

    first_run = await run_once()
    initial_chunks = db_session.query(DocumentChunk).count()
    second_run = await run_once()
    second_chunks = db_session.query(DocumentChunk).count()

    assert first_run.status == "completed"
    assert second_run.status == "completed"
    assert second_chunks == initial_chunks


@pytest.mark.asyncio
async def test_unsupported_mime_logs_skip(
    db_session,
    ingestion_pipeline,
    ingestion_settings,
):
    workspace = ingestion_settings.local_ingest_root
    workspace.mkdir(parents=True, exist_ok=True)
    binary_path = workspace / "binary.bin"
    binary_path.write_bytes(b"\x00\xFF\x00\xFF")

    run = IngestionRun(
        tenant_id="default",
        source_id=None,
        status="pending",
        total_documents=0,
        processed_documents=0,
    )
    db_session.add(run)
    db_session.commit()

    result = await ingestion_pipeline.ingest_directory(
        run,
        path=workspace,
        tenant_id="default",
        infer_metadata=False,
        batch_size=10,
    )

    event_types = {event.event_type for event in db_session.query(IngestionEvent).all()}
    assert IngestionEventType.DOCUMENT_SKIPPED in event_types
    assert result.skipped_documents == 1


@pytest.mark.asyncio
async def test_embedding_failure_marks_run_failed(
    db_session,
    ingestion_pipeline,
    embedding_service_fake,
    ingestion_settings,
):
    workspace = ingestion_settings.local_ingest_root
    workspace.mkdir(parents=True, exist_ok=True)
    copy_fixture_docs(FIXTURE_DOCS, workspace)

    run = IngestionRun(
        tenant_id="default",
        source_id=None,
        status="pending",
        total_documents=0,
        processed_documents=0,
    )
    db_session.add(run)
    db_session.commit()

    embedding_service_fake.fail = True

    with pytest.raises(Exception):
        await ingestion_pipeline.ingest_directory(
            run,
            path=workspace,
            tenant_id="default",
            infer_metadata=False,
            batch_size=10,
        )

    db_session.refresh(run)
    assert run.status == "failed"

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.db.models import Document, DocumentChunk, IngestionRun, Source, Tenant


@pytest.mark.asyncio
async def test_list_ingestion_runs_returns_paginated_results(
    async_client,
    db_session,
    test_settings,
):
    tenant = Tenant(name="Acme Corp", slug="acme")
    db_session.add(tenant)
    db_session.flush()

    source = Source(
        tenant_id=tenant.id,
        name="Uploads",
        source_type="local",
    )
    db_session.add(source)
    db_session.flush()

    started_recent = datetime.now(timezone.utc) - timedelta(minutes=1)
    finished_recent = started_recent + timedelta(seconds=90)
    recent_run = IngestionRun(
        tenant_id=tenant.id,
        source_id=source.id,
        status="completed",
        path="/data/acme/latest",
        total_documents=5,
        processed_documents=5,
        started_at=started_recent,
        finished_at=finished_recent,
        error=None,
    )

    started_older = started_recent - timedelta(hours=1)
    finished_older = started_older + timedelta(seconds=30)
    older_run = IngestionRun(
        tenant_id=tenant.id,
        source_id=source.id,
        status="failed",
        path="/data/acme/older",
        total_documents=3,
        processed_documents=1,
        started_at=started_older,
        finished_at=finished_older,
        error="ingestion aborted",
    )

    db_session.add_all([recent_run, older_run])
    db_session.commit()
    db_session.refresh(recent_run)
    db_session.refresh(older_run)

    response = await async_client.get(
        "/admin/ingestion-runs",
        params={"tenant": tenant.slug},
        headers={"X-Admin-API-Key": test_settings.admin_api_key},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert payload["page"] == 1
    assert payload["page_size"] == 50
    first_item = payload["items"][0]
    assert first_item["id"] == str(recent_run.id)
    assert first_item["status"] == "completed"
    assert first_item["source_name"] == "Uploads"
    assert first_item["duration_seconds"] == pytest.approx(90.0, rel=1e-3)
    assert payload["items"][1]["id"] == str(older_run.id)


@pytest.mark.asyncio
async def test_list_documents_filters_by_status(async_client, db_session, test_settings):
    tenant = Tenant(name="Acme Corp", slug="acme")
    db_session.add(tenant)
    db_session.flush()

    source = Source(
        tenant_id=tenant.id,
        name="Knowledge Base",
        source_type="filesystem",
    )
    db_session.add(source)
    db_session.flush()

    ready_doc = Document(
        tenant_id=tenant.id,
        source_id=source.id,
        title="Ready Document",
        status="ready",
        metadata_json=None,
        sha256="abc123",
        content_size=2048,
        mime_type="text/plain",
    )
    pending_doc = Document(
        tenant_id=tenant.id,
        source_id=source.id,
        title="Pending Document",
        status="pending",
        metadata_json=None,
        sha256="def456",
        content_size=1024,
        mime_type="text/plain",
    )
    db_session.add_all([ready_doc, pending_doc])
    db_session.flush()

    chunks = [
        DocumentChunk(
            document_id=ready_doc.id,
            chunk_order=0,
            content="chunk-one",
            embedding=None,
            sha256="chunk1",
            token_count=10,
        ),
        DocumentChunk(
            document_id=ready_doc.id,
            chunk_order=1,
            content="chunk-two",
            embedding=None,
            sha256="chunk2",
            token_count=12,
        ),
    ]
    db_session.add_all(chunks)
    db_session.commit()
    db_session.refresh(ready_doc)

    response = await async_client.get(
        "/admin/documents",
        params={"tenant": tenant.slug, "status": "ready"},
        headers={"X-Admin-API-Key": test_settings.admin_api_key},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert len(payload["items"]) == 1
    doc = payload["items"][0]
    assert doc["id"] == str(ready_doc.id)
    assert doc["chunk_count"] == 2
    assert doc["status"] == "ready"
    assert doc["source_name"] == "Knowledge Base"
    assert doc["sha256"] == "abc123"


@pytest.mark.asyncio
async def test_admin_auth_rejects_missing_key(async_client):
    response = await async_client.get(
        "/admin/ingestion-runs",
        params={"tenant": "any"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "X-Admin-API-Key header required"


@pytest.mark.asyncio
async def test_admin_auth_rejects_wrong_key(async_client):
    response = await async_client.get(
        "/admin/ingestion-runs",
        params={"tenant": "any"},
        headers={"X-Admin-API-Key": "wrong"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid admin API key"

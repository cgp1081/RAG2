from __future__ import annotations

from backend.db import (
    Document,
    DocumentChunk,
    IngestionEvent,
    IngestionRun,
    Source,
    Tenant,
)


def test_model_relationships(db_session):
    tenant = Tenant(name="Acme Corp", slug="acme")
    source = Source(name="Drive", source_type="gdrive", config={"folder": "root"})
    document = Document(
        external_id="doc-1",
        title="Employee Handbook",
        status="ready",
        metadata_json={"category": "hr"},
    )
    chunk = DocumentChunk(chunk_index=0, content="Welcome", embedding={"vector": [0.1, 0.2]})
    run = IngestionRun(status="completed")
    event = IngestionEvent(event_type="chunk_processed", payload={"index": 0})

    tenant.sources.append(source)
    tenant.documents.append(document)
    tenant.ingestion_runs.append(run)
    document.chunks.append(chunk)
    run.events.append(event)
    source.documents.append(document)
    source.ingestion_runs.append(run)

    db_session.add(tenant)
    db_session.flush()

    fetched_tenant = db_session.get(Tenant, tenant.id)
    assert fetched_tenant is not None
    assert fetched_tenant.sources[0].tenant_id == tenant.id
    assert fetched_tenant.documents[0].source_id == source.id
    assert fetched_tenant.documents[0].chunks[0].document_id == document.id

    fetched_run = db_session.get(IngestionRun, run.id)
    assert fetched_run is not None
    assert fetched_run.events[0].run_id == run.id
    assert fetched_run.tenant_id == tenant.id

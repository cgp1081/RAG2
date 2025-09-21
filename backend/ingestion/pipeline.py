"""High-level ingestion pipeline orchestrating document processing."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:  # pragma: no cover - optional dependency handled at runtime
    import magic
except ImportError:  # pragma: no cover - fallback when libmagic unavailable
    magic = None

from pypdf import PdfReader
from sqlalchemy.orm import Session

from backend.app.config import Settings
from backend.app.logging import get_logger
from backend.db.models import (
    Document,
    DocumentChunk,
    IngestionEvent,
    IngestionEventType,
    IngestionRun,
)
from backend.ingestion.chunker import Chunk, chunk_text
from backend.ingestion.dedup import filter_existing_documents, sha256_digest
from backend.services.embedding_service import EmbeddingService
from backend.services.exceptions import EmbeddingRetryableError, EmbeddingServiceError
from backend.services.vector_store import VectorPayload, VectorStoreClient

_logger = get_logger(__name__)
_magic = magic.Magic(mime=True) if magic else None


@dataclass(slots=True)
class IngestionResult:
    processed_documents: int = 0
    skipped_documents: int = 0
    failed_documents: int = 0
    processed_chunks: int = 0
    skipped_chunks: int = 0


class IngestionPipeline:
    """Coordinate filesystem ingestion with persistence and vector indexing."""

    def __init__(
        self,
        session: Session,
        vector_store: VectorStoreClient,
        embedding_service: EmbeddingService,
        settings: Settings,
    ) -> None:
        self.session = session
        self.vector_store = vector_store
        self.embedding_service = embedding_service
        self.settings = settings
        self.config = settings.ingestion_config()
        self.logger = get_logger(__name__)

    async def ingest_directory(
        self,
        run: IngestionRun,
        path: Path,
        *,
        tenant_id: str,
        infer_metadata: bool,
        batch_size: int,
    ) -> IngestionResult:
        result = IngestionResult()
        resolved_path = path.resolve()
        self._validate_path(resolved_path)

        await self._ensure_services(tenant_id)

        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        run.path = str(resolved_path)
        self._record_event(run, IngestionEventType.RUN_STARTED, {"path": str(resolved_path)})
        self.session.commit()

        files = [p for p in sorted(resolved_path.rglob("*")) if p.is_file()]
        run.total_documents = len(files)
        self.session.commit()

        try:
            for file_path in files:
                try:
                    processed = await self._process_file(
                        run,
                        file_path,
                        tenant_id=tenant_id,
                        infer_metadata=infer_metadata,
                        batch_size=batch_size,
                        result=result,
                    )
                    if processed:
                        result.processed_documents += 1
                    else:
                        result.skipped_documents += 1
                except EmbeddingRetryableError as exc:
                    self._record_event(
                        run,
                        IngestionEventType.ERROR,
                        {
                            "path": str(file_path),
                            "message": str(exc),
                        },
                    )
                    raise
                except EmbeddingServiceError as exc:
                    self._record_event(
                        run,
                        IngestionEventType.ERROR,
                        {
                            "path": str(file_path),
                            "message": str(exc),
                        },
                    )
                    raise
                except Exception as exc:  # pragma: no cover - unexpected error
                    result.failed_documents += 1
                    self._record_event(
                        run,
                        IngestionEventType.ERROR,
                        {
                            "path": str(file_path),
                            "message": str(exc),
                        },
                    )
            run.status = "completed"
            run.finished_at = datetime.now(timezone.utc)
            self._record_event(
                run,
                IngestionEventType.RUN_COMPLETED,
                {"processed": result.processed_documents},
            )
            self.session.commit()
            return result
        except Exception:
            run.status = "failed"
            run.finished_at = datetime.now(timezone.utc)
            self.session.commit()
            self._record_event(run, IngestionEventType.RUN_FAILED, {})
            self.session.commit()
            raise

    def _validate_path(self, target: Path) -> None:
        root = self.config.local_root
        if not target.is_dir():
            raise ValueError(f"Ingestion path must be a directory: {target}")
        if root not in target.parents and target != root:
            raise ValueError(f"Path {target} must be within {root}")

    async def _ensure_services(self, tenant_id: str) -> None:
        await self.vector_store.healthcheck()
        await self.embedding_service.healthcheck()
        await self.vector_store.ensure_collection(tenant_id)

    async def _process_file(
        self,
        run: IngestionRun,
        file_path: Path,
        *,
        tenant_id: str,
        infer_metadata: bool,
        batch_size: int,
        result: IngestionResult,
    ) -> bool:
        mime_type = self._detect_mime(file_path)
        content_bytes = file_path.read_bytes()
        text = self._extract_text(file_path, content_bytes, mime_type)
        if text is None:
            self._record_event(
                run,
                IngestionEventType.DOCUMENT_SKIPPED,
                {"path": str(file_path), "reason": "unsupported_mime", "mime": mime_type},
            )
            return False

        doc_sha = sha256_digest(content_bytes)
        existing_shas = filter_existing_documents(self.session, tenant_id, [doc_sha])
        if doc_sha in existing_shas:
            self._record_event(
                run,
                IngestionEventType.DOCUMENT_SKIPPED,
                {"path": str(file_path), "reason": "duplicate", "sha": doc_sha},
            )
            return False

        metadata = {"path": str(file_path)}
        if infer_metadata and text:
            first_line = text.strip().splitlines()[0] if text.strip() else ""
            if first_line:
                metadata["preview"] = first_line[:120]

        document = Document(
            tenant_id=tenant_id,
            source_id=None,
            external_id=str(file_path.name),
            title=file_path.stem,
            status="processing",
            metadata_json=metadata,
            sha256=doc_sha,
            content_size=len(content_bytes),
            mime_type=mime_type,
        )
        self.session.add(document)
        self.session.flush()

        self._record_event(
            run,
            IngestionEventType.DOCUMENT_STARTED,
            {"path": str(file_path), "document_id": str(document.id)},
        )

        chunks = chunk_text(text, self.config.chunk_size, self.config.chunk_overlap)
        seen_chunk_hashes: set[str] = set()
        vector_payloads: list[VectorPayload] = []
        chunk_models: list[DocumentChunk] = []
        chunk_batch: list[Chunk] = []

        async def flush_batch() -> None:
            nonlocal chunk_batch
            if not chunk_batch:
                return
            await self._process_batch(
                tenant_id,
                document,
                chunk_batch,
                vector_payloads,
                chunk_models,
                result,
            )
            chunk_batch = []

        for chunk in chunks:
            if chunk.sha256 in seen_chunk_hashes:
                result.skipped_chunks += 1
                self._record_event(
                    run,
                    IngestionEventType.CHUNK_SKIPPED_DUPLICATE,
                    {
                        "document_id": str(document.id),
                        "chunk_order": chunk.index,
                        "reason": "hash_duplicate",
                    },
                )
                continue
            seen_chunk_hashes.add(chunk.sha256)
            chunk_batch.append(chunk)
            if len(chunk_batch) >= batch_size:
                await flush_batch()

        await flush_batch()

        self.session.add_all(chunk_models)
        document.status = "ready"
        self.session.commit()

        if vector_payloads:
            await self.vector_store.upsert_batch(tenant_id, vector_payloads)

        run.processed_documents += 1
        result.processed_chunks += len(vector_payloads)
        self._record_event(
            run,
            IngestionEventType.DOCUMENT_COMPLETED,
            {
                "path": str(file_path),
                "document_id": str(document.id),
                "chunks": len(vector_payloads),
            },
        )
        self.session.commit()
        return True

    async def _process_batch(
        self,
        tenant_id: str,
        document: Document,
        batch: list[Chunk],
        vector_payloads: list[VectorPayload],
        chunk_models: list[DocumentChunk],
        result: IngestionResult,
    ) -> None:
        texts = [chunk.text for chunk in batch]
        embeddings = await self.embedding_service.embed(texts)
        for chunk, embedding in zip(batch, embeddings, strict=True):
            is_duplicate = await self.vector_store.has_similar_embedding(
                tenant_id,
                embedding,
                filters={
                    "must": [
                        {"key": "tenant_id", "match": {"value": tenant_id}}
                    ]
                },
            )
            if is_duplicate:
                result.skipped_chunks += 1
                continue

            vector_payloads.append(
                VectorPayload(
                    id=chunk.sha256,
                    embedding=embedding,
                    metadata={
                        "tenant_id": tenant_id,
                        "document_id": str(document.id),
                        "chunk_order": chunk.index,
                        "sha256": chunk.sha256,
                    },
                )
            )
            chunk_models.append(
                DocumentChunk(
                    document_id=document.id,
                    chunk_order=chunk.index,
                    content=chunk.text,
                    embedding=None,
                    sha256=chunk.sha256,
                    token_count=chunk.token_count,
                )
            )

    def _record_event(self, run: IngestionRun, event_type: str, payload: dict) -> None:
        event = IngestionEvent(
            run_id=run.id,
            event_type=event_type,
            payload=payload,
        )
        self.session.add(event)

    def _detect_mime(self, path: Path) -> str:
        if _magic:
            return _magic.from_file(str(path)) or "application/octet-stream"
        if path.suffix.lower() in {".txt", ".md", ".log"}:
            return "text/plain"
        if path.suffix.lower() == ".pdf":
            return "application/pdf"
        return "application/octet-stream"

    def _extract_text(self, path: Path, content: bytes, mime_type: str) -> Optional[str]:
        if path.suffix.lower() == ".pdf" or mime_type == "application/pdf":
            reader = PdfReader(path)
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        if mime_type.startswith("text"):
            return content.decode("utf-8", errors="ignore")
        if path.suffix.lower() in {".md", ".txt", ".log"}:
            return content.decode("utf-8", errors="ignore")
        return None

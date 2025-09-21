"""Deduplication helpers for ingestion pipeline."""
from __future__ import annotations

import hashlib
import math
from typing import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Document


def sha256_digest(content: bytes | str) -> str:
    """Return SHA256 hex digest for bytes or string."""

    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def filter_existing_documents(
    session: Session,
    tenant_id: str,
    shas: Iterable[str],
) -> set[str]:
    """Return set of hashes already present for the tenant."""

    sha_list = list(shas)
    if not sha_list:
        return set()
    stmt = select(Document.sha256).where(
        Document.tenant_id == tenant_id,
        Document.sha256.in_(sha_list),
    )
    return {row[0] for row in session.execute(stmt)}


def cosine_similarity(vec1: Sequence[float], vec2: Sequence[float]) -> float:
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


def is_duplicate_embedding(
    existing_embeddings: Iterable[Sequence[float]],
    candidate: Sequence[float],
    *,
    threshold: float = 0.995,
) -> bool:
    """Return True if candidate embedding is sufficiently similar to existing ones."""

    return any(
        cosine_similarity(embedding, candidate) >= threshold
        for embedding in existing_embeddings
    )

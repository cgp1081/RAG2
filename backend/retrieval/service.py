"""Deterministic retrieval engine built on the vector store."""
from __future__ import annotations

from collections.abc import Callable, Sequence
from time import perf_counter
from typing import Any

import numpy as np

from backend.app.config import Settings
from backend.app.logging import get_logger
from backend.retrieval.models import (
    RetrievalFilters,
    RetrievalRequest,
    RetrievalResponse,
    RetrievedChunk,
)
from backend.services.embedding_service import EmbeddingService
from backend.services.vector_store import VectorStoreClient

# TODO: incorporate hybrid keyword/MMR strategies alongside vector search.


class RetrievalService:
    """High-level retrieval orchestrator coordinating embeddings and vector search."""

    def __init__(
        self,
        *,
        embedding_service: EmbeddingService,
        vector_store: VectorStoreClient,
        settings: Settings,
        logger=None,
        diagnostics_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._embedding_service = embedding_service
        self._vector_store = vector_store
        self._settings = settings
        self._logger = logger or get_logger(__name__)
        self._diagnostics_callback = diagnostics_callback

    async def retrieve(
        self,
        query: str,
        tenant_id: str,
        *,
        filters: RetrievalFilters | None = None,
        top_k: int | None = None,
    ) -> RetrievalResponse:
        """Return ranked chunks for the supplied query and tenant."""

        resolved_filters = filters
        if filters is None:
            resolved_filters = RetrievalFilters()
        start_time = perf_counter()

        request = RetrievalRequest(
            query=query,
            tenant_id=tenant_id,
            filters=(
                resolved_filters
                if resolved_filters and not resolved_filters.is_empty()
                else None
            ),
            top_k=max(top_k or self._settings.retrieval_top_k_default, 1),
            score_floor=self._settings.retrieval_score_floor,
        )

        embeddings = await self._embedding_service.embed([request.query])
        if not embeddings:
            diagnostics = self._emit_diagnostics(
                {
                    "reason": "empty_embedding",
                    "requested_top_k": request.top_k,
                    "latency_ms": (perf_counter() - start_time) * 1000,
                }
            )
            return RetrievalResponse(
                chunks=[],
                applied_filters=request.filters,
                diagnostics=diagnostics,
            )

        vector_filters = request.filters.as_dict() if request.filters else None
        results = await self._vector_store.search_with_filters(
            tenant_id=request.tenant_id,
            embedding=embeddings[0],
            top_k=request.top_k,
            filters=vector_filters,
        )

        if not results:
            diagnostics = self._emit_diagnostics(
                {
                    "reason": "no_results",
                    "requested_top_k": request.top_k,
                    "latency_ms": (perf_counter() - start_time) * 1000,
                }
            )
            self._logger.info(
                "retrieval.completed",
                tenant_id=tenant_id,
                requested_top_k=request.top_k,
                kept=0,
                dropped=0,
                raw_results=0,
            )
            return RetrievalResponse(
                chunks=[],
                applied_filters=request.filters,
                diagnostics=diagnostics,
            )

        normalized_scores = self._normalize_scores([result.score for result in results])

        kept: list[RetrievedChunk] = []
        dropped = 0
        kept_scores: list[float] = []
        for result, norm_score in sorted(
            zip(results, normalized_scores, strict=True),
            key=lambda pair: pair[1],
            reverse=True,
        ):
            if norm_score < request.score_floor:
                dropped += 1
                continue
            payload = dict(result.payload or {})
            chunk = RetrievedChunk(
                chunk_id=str(payload.get("chunk_id") or result.id),
                document_id=str(payload.get("document_id", "")),
                tenant_id=str(payload.get("tenant_id", tenant_id)),
                score=float(result.score),
                normalized_score=float(norm_score),
                content=str(
                    payload.get("content")
                    or payload.get("text")
                    or ""
                ),
                metadata=payload,
            )
            kept.append(chunk)
            kept_scores.append(float(norm_score))

        diagnostics = self._emit_diagnostics(
            {
                "requested_top_k": request.top_k,
                "raw_results": len(results),
                "kept": len(kept),
                "dropped_below_floor": dropped,
                "score_stats": _score_stats(kept_scores),
                "floor": request.score_floor,
                "latency_ms": (perf_counter() - start_time) * 1000,
            }
        )

        self._logger.info(
            "retrieval.completed",
            tenant_id=tenant_id,
            requested_top_k=request.top_k,
            raw_results=len(results),
            kept=len(kept),
            dropped=dropped,
        )

        return RetrievalResponse(
            chunks=kept,
            applied_filters=request.filters,
            diagnostics=diagnostics,
        )

    def _normalize_scores(self, scores: Sequence[float]) -> np.ndarray:
        """Normalise raw similarity scores to the range [0, 1]."""

        if not scores:
            return np.array([], dtype=float)

        arr = np.asarray(scores, dtype=float)
        ceiling = self._settings.retrieval_score_ceiling
        if ceiling is not None:
            arr = np.clip(arr, a_min=None, a_max=float(ceiling))

        min_score = float(arr.min())
        max_score = float(arr.max())
        if np.isclose(max_score, min_score):
            return np.ones_like(arr, dtype=float)
        normalized = (arr - min_score) / (max_score - min_score)
        return normalized

    def set_diagnostics_callback(
        self, callback: Callable[[dict[str, Any]], None] | None
    ) -> None:
        """Register a callback for retrieval diagnostics payloads."""

        self._diagnostics_callback = callback

    def _emit_diagnostics(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._settings.retrieval_diagnostics:
            return {}
        diagnostics = dict(payload)
        if self._diagnostics_callback is not None:
            try:
                self._diagnostics_callback(dict(diagnostics))
            except Exception:  # pragma: no cover - defensive
                self._logger.warning("retrieval.diagnostics_hook_failed")
        return diagnostics


def _score_stats(scores: list[float]) -> dict[str, float | int]:
    if not scores:
        return {}
    scores_array = np.array(scores, dtype=float)
    return {
        "count": len(scores),
        "min": float(scores_array.min()),
        "max": float(scores_array.max()),
        "mean": float(scores_array.mean()),
        "std": float(scores_array.std(ddof=0)),
    }

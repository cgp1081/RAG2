"""End-to-end orchestration for retrieval-augmented generation."""
from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Sequence
from uuid import uuid4

from structlog.stdlib import BoundLogger

from backend.app.config import Settings
from backend.app.observability import record_rag_duration
from backend.app.logging import get_logger
from backend.rag.llm_client import LLMClient
from backend.rag.prompts import (
    MAX_SNIPPET_LENGTH,
    PromptBuilder,
    PromptChunk,
    PromptTable,
    truncate_snippet,
)
from backend.retrieval.models import RetrievalFilters, RetrievedChunk
from backend.retrieval.service import RetrievalService
from backend.structured.query_service import QueryResult


@dataclass(slots=True)
class Citation:
    """Describes a chunk used to support a generated answer."""

    document_id: str
    chunk_id: str
    source_type: str | None
    title: str | None
    snippet: str
    score: float
    normalized_score: float


@dataclass(slots=True)
class TokenUsage:
    """Tracks prompt/completion token counts."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(slots=True)
class RAGResult:
    """Result payload returned by the RAG pipeline."""

    answer: str
    model: str
    prompt: str
    prompt_id: str
    citations: list[Citation]
    token_usage: TokenUsage
    latency_ms: float
    table: QueryResult | None = None


class RAGPipeline:
    """Coordinates retrieval, prompt rendering, and LLM completion."""

    def __init__(
        self,
        *,
        retrieval_service: RetrievalService,
        llm_client: LLMClient,
        prompt_builder: PromptBuilder,
        settings: Settings,
        logger: BoundLogger | None = None,
    ) -> None:
        self._retrieval_service = retrieval_service
        self._llm_client = llm_client
        self._prompt_builder = prompt_builder
        self._settings = settings
        self._logger = logger or get_logger(__name__)

    async def generate_answer(
        self,
        query: str,
        tenant_id: str,
        filters: RetrievalFilters | None = None,
        structured_result: QueryResult | None = None,
    ) -> RAGResult:
        """Run the full retrieval → generation pipeline."""

        prompt_id = str(uuid4())
        start = perf_counter()

        retrieval_response = await self._retrieval_service.retrieve(
            query,
            tenant_id,
            filters=filters,
        )

        retrieved_chunks: Sequence[RetrievedChunk] = retrieval_response.chunks
        tabular_intent = detect_tabular_intent(query, retrieved_chunks)
        prompt_chunks: list[PromptChunk] = []
        citations: list[Citation] = []

        for chunk in retrieved_chunks:
            metadata = dict(chunk.metadata or {})
            title = metadata.get("title") or metadata.get("document_title") or metadata.get("path")
            source_type = metadata.get("source_type")
            snippet_source = chunk.content or metadata.get("content") or ""
            snippet = truncate_snippet(snippet_source, MAX_SNIPPET_LENGTH)
            prompt_chunks.append(
                PromptChunk(
                    document_id=chunk.document_id,
                    chunk_id=chunk.chunk_id,
                    source_type=source_type,
                    title=title,
                    snippet=snippet,
                )
            )
            citations.append(
                Citation(
                    document_id=chunk.document_id,
                    chunk_id=chunk.chunk_id,
                    source_type=source_type,
                    title=title,
                    snippet=snippet,
                    score=chunk.score,
                    normalized_score=chunk.normalized_score,
                )
            )

        prompt_table = None
        if structured_result is not None:
            prompt_table = _format_prompt_table(structured_result)
            citations.append(
                Citation(
                    document_id=f"Table:{structured_result.table_name}",
                    chunk_id="table",
                    source_type="table",
                    title=structured_result.table_name,
                    snippet=_table_citation_snippet(structured_result),
                    score=1.0,
                    normalized_score=1.0,
                )
            )

        prompt = self._prompt_builder.build_prompt(query, prompt_chunks, table=prompt_table)

        if not prompt_chunks and structured_result is None:
            latency_ms = (perf_counter() - start) * 1000
            usage = TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0)
            record_rag_duration(
                tenant_id=tenant_id,
                outcome="no_context",
                duration_seconds=latency_ms / 1000,
            )
            self._logger.info(
                "rag.pipeline.no_context",
                tenant_id=tenant_id,
                prompt_id=prompt_id,
                latency_ms=latency_ms,
            )
            return RAGResult(
                answer="I don't know",
                model=self._settings.llm_model,
                prompt=prompt,
                prompt_id=prompt_id,
                citations=[],
                token_usage=usage,
                latency_ms=latency_ms,
                table=structured_result,
            )
        if tabular_intent and structured_result is None:
            self._logger.info(
                "rag.pipeline.tabular_intent_without_table",
                tenant_id=tenant_id,
                prompt_id=prompt_id,
            )

        llm_result = await self._llm_client.generate(prompt)
        answer_text = llm_result.text.strip() if llm_result.text else ""
        if not answer_text:
            answer_text = "I don't know"

        usage = llm_result.token_usage or {}
        token_usage = TokenUsage(
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            total_tokens=int(usage.get("total_tokens", 0)),
        )

        latency_ms = (perf_counter() - start) * 1000
        record_rag_duration(
            tenant_id=tenant_id,
            outcome="success",
            duration_seconds=latency_ms / 1000,
        )
        self._logger.info(
            "rag.pipeline.completed",
            tenant_id=tenant_id,
            prompt_id=prompt_id,
            chunk_count=len(retrieved_chunks),
            citation_count=len(citations),
            latency_ms=latency_ms,
        )
        if structured_result is not None and prompt_chunks:
            self._logger.info(
                "rag.pipeline.hybrid",
                tenant_id=tenant_id,
                prompt_id=prompt_id,
                table=structured_result.table_name,
                table_rows=structured_result.row_count,
                chunk_count=len(prompt_chunks),
            )

        return RAGResult(
            answer=answer_text,
            model=llm_result.model or self._settings.llm_model,
            prompt=prompt,
            prompt_id=prompt_id,
            citations=citations,
            token_usage=token_usage,
            latency_ms=latency_ms,
            table=structured_result,
        )


def detect_tabular_intent(query: str, retrieved_chunks: Sequence[RetrievedChunk]) -> bool:
    lowered = query.lower()
    for keyword in ("table", "row", "column", "dataset", "csv"):
        if keyword in lowered:
            return True
    return False


def _format_prompt_table(result: QueryResult) -> PromptTable:
    column_names = [column.name for column in result.columns]
    preview_rows: list[str] = []
    for row in result.rows[:5]:
        ordered = [str(row.values.get(name, "")) for name in column_names]
        preview_rows.append(" | ".join(ordered))
    if not preview_rows:
        preview_rows.append("(no rows returned)")
    return PromptTable(
        table_name=result.table_name,
        columns=column_names,
        sample_rows=preview_rows,
    )


def _table_citation_snippet(result: QueryResult) -> str:
    if not result.rows:
        return "No rows returned"
    first_row = result.rows[0].values
    snippet_parts = [f"{key}={value}" for key, value in list(first_row.items())[:5]]
    return ", ".join(snippet_parts)


__all__ = [
    "RAGPipeline",
    "RAGResult",
    "Citation",
    "TokenUsage",
    "detect_tabular_intent",
]

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import pytest

from backend.app.config import Settings
from backend.rag.llm_client import LLMResult
from backend.rag.pipeline import RAGPipeline
from backend.rag.prompts import PromptBuilder
from backend.retrieval.models import RetrievedChunk, RetrievalResponse
from backend.structured.query_service import ColumnMeta, QueryResult, TableRow


@dataclass
class FakeRetrievalService:
    chunks: list[RetrievedChunk]

    async def retrieve(self, query: str, tenant_id: str, filters=None):
        return RetrievalResponse(chunks=list(self.chunks), applied_filters=filters, diagnostics={})


class FakeLLMClient:
    def __init__(self, text: str, usage: dict[str, int] | None = None, model: str = "fake-model") -> None:
        self._text = text
        self._usage = usage or {}
        self._model = model
        self.calls: list[str] = []

    async def generate(self, prompt: str) -> LLMResult:
        self.calls.append(prompt)
        return LLMResult(text=self._text, model=self._model, token_usage=self._usage)


@pytest.mark.asyncio
async def test_generate_answer_returns_citations() -> None:
    chunk_one_text = "Overview\n" + ("A" * 410)
    chunk_two_text = "Details about policies."
    chunks = [
        RetrievedChunk(
            chunk_id="chunk-1",
            document_id="doc-1",
            tenant_id="tenant-1",
            score=0.82,
            normalized_score=0.91,
            content=chunk_one_text,
            metadata={"title": "Employee Handbook", "source_type": "manual"},
        ),
        RetrievedChunk(
            chunk_id="chunk-2",
            document_id="doc-2",
            tenant_id="tenant-1",
            score=0.71,
            normalized_score=0.83,
            content=chunk_two_text,
            metadata={"title": "Support Guide", "source_type": "faq"},
        ),
    ]

    retrieval_service = FakeRetrievalService(chunks)
    llm_client = FakeLLMClient(
        text="Here is an answer referencing [1] and [2].",
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        model="stub-llm",
    )
    settings = Settings(llm_model="stub-llm")
    pipeline = RAGPipeline(
        retrieval_service=retrieval_service,
        llm_client=llm_client,
        prompt_builder=PromptBuilder(),
        settings=settings,
    )

    result = await pipeline.generate_answer("What policies apply?", "tenant-1")

    assert result.answer == "Here is an answer referencing [1] and [2]."
    assert [c.document_id for c in result.citations] == ["doc-1", "doc-2"]
    assert len(result.citations) == 2
    assert all(len(c.snippet) <= 400 for c in result.citations)
    assert "[1] Title: Employee Handbook" in result.prompt
    assert "User Question:\nWhat policies apply?" in result.prompt
    assert llm_client.calls, "LLM client should be invoked when context is available"
    assert result.model == "stub-llm"
    assert result.token_usage.prompt_tokens == 10
    assert result.token_usage.completion_tokens == 5
    assert result.token_usage.total_tokens == 15
    assert result.table is None
    UUID(result.prompt_id)


@pytest.mark.asyncio
async def test_generate_answer_no_context_returns_i_dont_know() -> None:
    retrieval_service = FakeRetrievalService([])

    class GuardingLLMClient:
        def __init__(self) -> None:
            self.called = False

        async def generate(self, prompt: str) -> LLMResult:  # pragma: no cover - defensive
            self.called = True
            return LLMResult(text="should not happen", model="", token_usage={})

    llm_client = GuardingLLMClient()
    settings = Settings(llm_model="stub-llm")
    pipeline = RAGPipeline(
        retrieval_service=retrieval_service,
        llm_client=llm_client,
        prompt_builder=PromptBuilder(),
        settings=settings,
    )

    result = await pipeline.generate_answer("Missing context?", "tenant-1")

    assert result.answer == "I don't know"
    assert not result.citations
    assert result.token_usage.prompt_tokens == 0
    assert result.token_usage.completion_tokens == 0
    assert result.token_usage.total_tokens == 0
    assert result.table is None
    assert not getattr(llm_client, "called", False)


@pytest.mark.asyncio
async def test_generate_answer_blank_completion_falls_back() -> None:
    chunks = [
        RetrievedChunk(
            chunk_id="chunk-1",
            document_id="doc-1",
            tenant_id="tenant-1",
            score=0.5,
            normalized_score=0.6,
            content="Some detail.",
            metadata={"title": "Doc", "source_type": "note"},
        )
    ]
    retrieval_service = FakeRetrievalService(chunks)
    llm_client = FakeLLMClient(text="   ")
    settings = Settings(llm_model="fallback-model")
    pipeline = RAGPipeline(
        retrieval_service=retrieval_service,
        llm_client=llm_client,
        prompt_builder=PromptBuilder(),
        settings=settings,
    )

    result = await pipeline.generate_answer("Provide details", "tenant-1")

    assert result.answer == "I don't know"
    assert result.citations
    assert llm_client.calls, "LLM client should be called even if it returns whitespace"


@pytest.mark.asyncio
async def test_generate_answer_with_structured_table() -> None:
    chunks: list[RetrievedChunk] = []
    retrieval_service = FakeRetrievalService(chunks)
    llm_client = FakeLLMClient(text="Table response", model="stub")
    settings = Settings(llm_model="stub")
    pipeline = RAGPipeline(
        retrieval_service=retrieval_service,
        llm_client=llm_client,
        prompt_builder=PromptBuilder(),
        settings=settings,
    )

    table_result = QueryResult(
        table_id=UUID("00000000-0000-0000-0000-000000000001"),
        table_name="employees",
        columns=[ColumnMeta(name="id", data_type="integer"), ColumnMeta(name="name", data_type="string")],
        rows=[TableRow(values={"id": 1, "name": "Alice"})],
        row_count=1,
        execution_ms=4.2,
        log_id=UUID("00000000-0000-0000-0000-000000000002"),
    )

    result = await pipeline.generate_answer(
        "Show employee table",
        "tenant-1",
        structured_result=table_result,
    )

    assert result.table is table_result
    assert any(c.document_id.startswith("Table:") for c in result.citations)
    assert "[Table] employees" in result.prompt

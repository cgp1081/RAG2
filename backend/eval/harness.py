"""Retrieval evaluation harness for precision/recall benchmarking."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import yaml

from backend.app.config import Settings
from backend.app.logging import get_logger
from backend.retrieval.models import RetrievalFilters
from backend.retrieval.service import RetrievalResponse, RetrievalService


@dataclass(slots=True)
class EvalExample:
    question: str
    expected_documents: list[str] = field(default_factory=list)
    expected_snippets: list[str] = field(default_factory=list)
    metadata_filters: dict[str, Any] = field(default_factory=dict)
    weight: float = 1.0
    notes: str | None = None


@dataclass(slots=True)
class EvalResult:
    question: str
    expected_documents: list[str]
    retrieved_documents: list[str]
    hit_documents: list[str]
    missed_documents: list[str]
    precision: float
    recall: float
    requested_k: int
    snippet_hits: int
    snippet_total: int
    snippet_coverage: float
    diagnostics: dict[str, Any]
    weight: float
    notes: str | None

    @property
    def success(self) -> bool:
        return math.isclose(self.precision, 1.0) and math.isclose(self.recall, 1.0)


@dataclass(slots=True)
class PrecisionRecallSummary:
    macro_precision: float
    macro_recall: float
    weighted_precision: float
    weighted_recall: float
    average_snippet_coverage: float
    total_examples: int
    perfect_examples: int
    failing_examples: int
    generated_at: datetime

    @property
    def all_passed(self) -> bool:
        return self.failing_examples == 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "macro_precision": self.macro_precision,
            "macro_recall": self.macro_recall,
            "weighted_precision": self.weighted_precision,
            "weighted_recall": self.weighted_recall,
            "average_snippet_coverage": self.average_snippet_coverage,
            "total_examples": self.total_examples,
            "perfect_examples": self.perfect_examples,
            "failing_examples": self.failing_examples,
            "generated_at": self.generated_at.isoformat(),
        }


@dataclass(slots=True)
class EvalMetrics:
    results: list[EvalResult]
    summary: PrecisionRecallSummary
    dataset_path: Path | None
    top_k: int

    def to_report_dict(self) -> dict[str, Any]:
        examples_payload = []
        for result in self.results:
            examples_payload.append(
                {
                    "question": result.question,
                    "precision": result.precision,
                    "recall": result.recall,
                    "requested_k": result.requested_k,
                    "expected_documents": list(result.expected_documents),
                    "hit_documents": list(result.hit_documents),
                    "missed_documents": list(result.missed_documents),
                    "retrieved_documents": list(result.retrieved_documents),
                    "snippet_coverage": result.snippet_coverage,
                    "snippet_hits": result.snippet_hits,
                    "snippet_total": result.snippet_total,
                    "weight": result.weight,
                    "notes": result.notes,
                    "diagnostics": dict(sorted(result.diagnostics.items())) if result.diagnostics else {},
                }
            )
        return {
            "summary": self.summary.as_dict(),
            "configuration": {
                "top_k": self.top_k,
                "dataset_path": str(self.dataset_path) if self.dataset_path else None,
            },
            "examples": examples_payload,
        }


def load_dataset(path: Path) -> list[EvalExample]:
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")

    raw_content = path.read_text(encoding="utf-8")
    data: Any
    if path.suffix.lower() in {".yaml", ".yml"}:
        data = yaml.safe_load(raw_content)
    elif path.suffix.lower() == ".json":
        data = json.loads(raw_content)
    else:
        raise ValueError("Unsupported dataset format. Use .yaml, .yml, or .json")

    if not isinstance(data, list):
        raise ValueError("Dataset must be a list of examples")

    examples: list[EvalExample] = []
    for idx, entry in enumerate(data, start=1):
        if not isinstance(entry, dict):
            raise ValueError(f"Example #{idx} must be an object")
        question = entry.get("question")
        if not question or not isinstance(question, str):
            raise ValueError(f"Example #{idx} missing 'question' string")

        expected_documents = _to_list(entry.get("expected_documents"))
        expected_snippets = _to_list(entry.get("expected_snippets"))
        metadata_filters = entry.get("metadata_filters") or {}
        if not isinstance(metadata_filters, dict):
            raise ValueError(f"Example #{idx} metadata_filters must be an object")
        weight = entry.get("weight", 1.0)
        try:
            weight_value = float(weight)
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive guard
            raise ValueError(f"Example #{idx} weight must be numeric") from exc
        notes = entry.get("notes")
        if notes is not None and not isinstance(notes, str):
            raise ValueError(f"Example #{idx} notes must be a string if provided")

        examples.append(
            EvalExample(
                question=question,
                expected_documents=expected_documents,
                expected_snippets=expected_snippets,
                metadata_filters=metadata_filters,
                weight=weight_value,
                notes=notes,
            )
        )
    return examples


class RetrievalEvaluator:
    """Coordinate evaluation runs against the retrieval service."""

    def __init__(
        self,
        *,
        retrieval_service: RetrievalService,
        settings: Settings,
        logger=None,
    ) -> None:
        self._retrieval_service = retrieval_service
        self._settings = settings
        self._logger = logger or get_logger(__name__)
        self._last_diagnostics: dict[str, Any] | None = None
        self._retrieval_service.set_diagnostics_callback(self._capture_diagnostics)

    async def run(
        self,
        dataset: Sequence[EvalExample],
        tenant_id: str,
        *,
        top_k: int | None = None,
        dataset_path: Path | None = None,
    ) -> EvalMetrics:
        if not dataset:
            raise ValueError("Dataset is empty")

        eval_config = self._settings.eval_config()
        resolved_top_k = max(top_k or eval_config.top_k, 1)
        original_diagnostics = self._settings.retrieval_diagnostics
        self._settings.retrieval_diagnostics = True

        results: list[EvalResult] = []
        precision_sum = 0.0
        recall_sum = 0.0
        snippet_coverage_sum = 0.0
        weighted_precision_sum = 0.0
        weighted_recall_sum = 0.0
        total_weight = 0.0
        perfect_examples = 0

        try:
            for example in dataset:
                filters = _build_filters(example.metadata_filters)
                self._last_diagnostics = None
                response: RetrievalResponse = await self._retrieval_service.retrieve(
                    query=example.question,
                    tenant_id=tenant_id,
                    filters=filters,
                    top_k=resolved_top_k,
                )
                result = _evaluate_example(
                    example=example,
                    response=response,
                    fallback_diagnostics=self._last_diagnostics or {},
                    requested_k=resolved_top_k,
                )
                results.append(result)
                precision_sum += result.precision
                recall_sum += result.recall
                snippet_coverage_sum += result.snippet_coverage
                weight = max(example.weight, 0.0)
                weighted_precision_sum += result.precision * weight
                weighted_recall_sum += result.recall * weight
                total_weight += weight
                if result.success:
                    perfect_examples += 1
        finally:
            self._settings.retrieval_diagnostics = original_diagnostics

        count = len(results)
        macro_precision = precision_sum / count
        macro_recall = recall_sum / count
        average_snippet_coverage = snippet_coverage_sum / count
        if total_weight > 0:
            weighted_precision = weighted_precision_sum / total_weight
            weighted_recall = weighted_recall_sum / total_weight
        else:
            weighted_precision = macro_precision
            weighted_recall = macro_recall

        summary = PrecisionRecallSummary(
            macro_precision=macro_precision,
            macro_recall=macro_recall,
            weighted_precision=weighted_precision,
            weighted_recall=weighted_recall,
            average_snippet_coverage=average_snippet_coverage,
            total_examples=count,
            perfect_examples=perfect_examples,
            failing_examples=count - perfect_examples,
            generated_at=datetime.now(timezone.utc),
        )

        return EvalMetrics(
            results=results,
            summary=summary,
            dataset_path=dataset_path,
            top_k=resolved_top_k,
        )

    def _capture_diagnostics(self, payload: dict[str, Any]) -> None:
        self._last_diagnostics = dict(payload)


def _build_filters(payload: dict[str, Any]) -> RetrievalFilters | None:
    if not payload:
        return None
    source_type = payload.get("source_type")
    if isinstance(source_type, str):
        source_type = [source_type]
    tags = payload.get("tags")
    if isinstance(tags, str):
        tags = [tags]
    filters = RetrievalFilters(
        source_type=source_type or None,
        tags=tags or None,
        visibility_scope=payload.get("visibility_scope"),
    )
    return None if filters.is_empty() else filters


def _evaluate_example(
    *,
    example: EvalExample,
    response: RetrievalResponse,
    fallback_diagnostics: dict[str, Any],
    requested_k: int,
) -> EvalResult:
    expected_docs = list(dict.fromkeys(example.expected_documents))
    expected_set = set(expected_docs)
    retrieved_documents = [chunk.document_id for chunk in response.chunks]
    retrieved_unique = list(dict.fromkeys(retrieved_documents))

    hit_set = {doc for doc in retrieved_unique if doc in expected_set}
    hit_documents = sorted(hit_set)
    missed_documents = sorted(expected_set - hit_set)

    retrieved_count = len(retrieved_unique)
    if retrieved_count == 0:
        precision = 1.0 if not expected_set else 0.0
    else:
        precision = len(hit_set) / retrieved_count

    if not expected_set:
        recall = 1.0
    else:
        recall = len(hit_set) / len(expected_set)

    expected_snippets = example.expected_snippets
    snippet_hits = 0
    if expected_snippets:
        lowered_chunks = [chunk.content.lower() for chunk in response.chunks]
        for snippet in expected_snippets:
            target = snippet.lower()
            if any(target in content for content in lowered_chunks):
                snippet_hits += 1
    snippet_total = len(expected_snippets)
    snippet_coverage = (
        snippet_hits / snippet_total if snippet_total else 1.0
    )

    diagnostics = response.diagnostics or fallback_diagnostics
    if diagnostics and "requested_top_k" not in diagnostics:
        diagnostics = dict(diagnostics)
        diagnostics.setdefault("requested_top_k", requested_k)

    return EvalResult(
        question=example.question,
        expected_documents=expected_docs,
        retrieved_documents=retrieved_unique,
        hit_documents=hit_documents,
        missed_documents=missed_documents,
        precision=precision,
        recall=recall,
        requested_k=diagnostics.get("requested_top_k", requested_k) if diagnostics else requested_k,
        snippet_hits=snippet_hits,
        snippet_total=snippet_total,
        snippet_coverage=snippet_coverage,
        diagnostics=diagnostics,
        weight=example.weight,
        notes=example.notes,
    )


def _to_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        result = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError("Expected list entries to be strings")
            result.append(item)
        return result
    raise ValueError("Expected a string or list of strings")

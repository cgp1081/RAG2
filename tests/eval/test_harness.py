from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from backend.app.config import Settings
from backend.cli import app as cli_app
from backend.cli import eval as cli_eval
from backend.eval.harness import (
    EvalExample,
    RetrievalEvaluator,
    load_dataset,
)
from backend.eval.report import write_report
from backend.retrieval.models import RetrievalResponse, RetrievedChunk


class FakeRetrievalService:
    def __init__(self, responses: dict[str, RetrievalResponse]):
        self._responses = responses
        self._callback = None

    def set_diagnostics_callback(self, callback):
        self._callback = callback

    async def retrieve(self, query: str, tenant_id: str, *, filters=None, top_k=None):
        response = self._responses[query]
        diagnostics = dict(response.diagnostics)
        if self._callback is not None:
            self._callback(dict(diagnostics))
        return response


def _make_response(document_ids: list[str], *, content: str = "", requested_top_k: int = 5) -> RetrievalResponse:
    chunks = [
        RetrievedChunk(
            chunk_id=f"chunk-{idx}",
            document_id=doc_id,
            tenant_id="tenant",
            score=1.0,
            normalized_score=1.0,
            content=content or f"content for {doc_id}",
            metadata={},
        )
        for idx, doc_id in enumerate(document_ids, start=1)
    ]
    diagnostics = {
        "requested_top_k": requested_top_k,
        "latency_ms": 12.5,
    }
    return RetrievalResponse(chunks=chunks, applied_filters=None, diagnostics=diagnostics)


@pytest.mark.asyncio
async def test_harness_computes_perfect_scores(test_settings: Settings, tmp_path: Path) -> None:
    response = _make_response(["doc-employee-handbook"], content="Paid Time Off benefits")
    service = FakeRetrievalService({"What is the PTO policy?": response})
    evaluator = RetrievalEvaluator(retrieval_service=service, settings=test_settings)

    dataset = [
        EvalExample(
            question="What is the PTO policy?",
            expected_documents=["doc-employee-handbook"],
            expected_snippets=["Paid Time Off"],
        )
    ]

    metrics = await evaluator.run(dataset, tenant_id="tenant", top_k=1, dataset_path=tmp_path / "dataset.yaml")
    assert metrics.summary.all_passed
    assert metrics.summary.macro_precision == 1.0
    assert metrics.summary.macro_recall == 1.0
    report_path = write_report(metrics, tmp_path)
    assert report_path.exists()
    data = report_path.read_text(encoding="utf-8")
    assert "doc-employee-handbook" in data


@pytest.mark.asyncio
async def test_harness_detects_missing_document(test_settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    response = _make_response(["doc-unrelated"], content="Other info")
    service = FakeRetrievalService({"What is the PTO policy?": response})
    evaluator = RetrievalEvaluator(retrieval_service=service, settings=test_settings)
    dataset = [
        EvalExample(
            question="What is the PTO policy?",
            expected_documents=["doc-employee-handbook"],
        )
    ]

    metrics = await evaluator.run(dataset, tenant_id="tenant", top_k=1, dataset_path=None)
    assert not metrics.summary.all_passed
    assert metrics.summary.failing_examples == 1

    dataset_file = tmp_path / "dataset.yaml"
    with dataset_file.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(
            [
                {
                    "question": "What is the PTO policy?",
                    "expected_documents": ["doc-employee-handbook"],
                }
            ],
            handle,
        )

    async def fake_execute_eval(**_: Any) -> int:
        return 1

    monkeypatch.setattr(cli_eval, "_execute_eval", fake_execute_eval)
    runner = CliRunner()
    result = runner.invoke(cli_app, ["eval", "--dataset", str(dataset_file)])
    assert result.exit_code == 1


def test_dataset_loader_validates_schema(tmp_path: Path) -> None:
    malformed = tmp_path / "bad.yaml"
    malformed.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        load_dataset(malformed)

    not_found = tmp_path / "missing.yaml"
    with pytest.raises(FileNotFoundError):
        load_dataset(not_found)

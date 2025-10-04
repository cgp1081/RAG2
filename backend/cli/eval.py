"""CLI command for running retrieval evaluation harness."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import httpx
import typer

from backend.app.config import get_settings
from backend.eval import (
    RetrievalEvaluator,
    load_dataset,
    render_console_report,
    write_report,
)
from backend.retrieval.service import RetrievalService
from backend.services import build_embedding_service, build_vector_store


async def _execute_eval(
    *,
    dataset_path: Path,
    tenant: str,
    top_k: Optional[int],
    output_dir: Path,
) -> int:
    settings = get_settings()
    dataset = load_dataset(dataset_path)
    vector_store = build_vector_store(settings)

    try:
        async with httpx.AsyncClient(timeout=settings.vector_timeout_seconds) as embedding_client:
            embedding_service = build_embedding_service(settings, embedding_client)
            retrieval_service = RetrievalService(
                embedding_service=embedding_service,
                vector_store=vector_store,
                settings=settings,
            )
            evaluator = RetrievalEvaluator(
                retrieval_service=retrieval_service,
                settings=settings,
            )
            metrics = await evaluator.run(
                dataset=dataset,
                tenant_id=tenant,
                top_k=top_k,
                dataset_path=dataset_path,
            )
    finally:
        await vector_store.close()

    report_path = write_report(metrics, output_dir)
    render_console_report(metrics)
    typer.echo(f"Report saved to {report_path}")
    return 0 if metrics.summary.all_passed else 1


def eval_command(  # pragma: no cover - Typer entry point wrapper
    dataset: Path = typer.Option(..., "--dataset", exists=True, file_okay=True, dir_okay=False),
    tenant: Optional[str] = typer.Option(
        None,
        "--tenant",
        help="Tenant identifier (defaults to settings.ingest_default_tenant).",
    ),
    top_k: Optional[int] = typer.Option(
        None,
        "--top-k",
        min=1,
        help="Override retrieval top-k (defaults to settings.eval_top_k).",
    ),
    output_dir: Optional[Path] = typer.Option(
        None,
        "--output-dir",
        file_okay=False,
        dir_okay=True,
        help="Directory where evaluation reports are written.",
    ),
) -> None:
    """Run the retrieval evaluation harness against a golden dataset."""

    settings = get_settings()
    eval_config = settings.eval_config()
    resolved_tenant = tenant or settings.ingest_default_tenant
    resolved_output = (output_dir or eval_config.output_dir).resolve()

    exit_code = asyncio.run(
        _execute_eval(
            dataset_path=dataset,
            tenant=resolved_tenant,
            top_k=top_k,
            output_dir=resolved_output,
        )
    )
    raise typer.Exit(code=exit_code)


__all__ = ["eval_command"]

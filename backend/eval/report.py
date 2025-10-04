"""Utilities for writing and rendering evaluation reports."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.table import Table

from backend.eval.harness import EvalMetrics


def write_report(metrics: EvalMetrics, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    data = metrics.to_report_dict()
    payload = json.dumps(data, indent=2, sort_keys=True)

    latest_path = output_dir / "last_eval.json"
    latest_path.write_text(payload + "\n", encoding="utf-8")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    timestamped_path = output_dir / f"eval-{timestamp}.json"
    timestamped_path.write_text(payload + "\n", encoding="utf-8")
    return timestamped_path


def render_console_report(metrics: EvalMetrics) -> None:
    console = Console()
    summary = metrics.summary

    console.print(
        f"[bold]Evaluation Summary:[/bold] precision={summary.macro_precision:.3f} "
        f"recall={summary.macro_recall:.3f} weighted_precision={summary.weighted_precision:.3f} "
        f"weighted_recall={summary.weighted_recall:.3f} snippet_coverage={summary.average_snippet_coverage:.3f}"
    )

    table = Table(title="Per-question results", show_lines=False)
    table.add_column("Question", overflow="fold")
    table.add_column("Precision", justify="right")
    table.add_column("Recall", justify="right")
    table.add_column("Snippet", justify="right")
    table.add_column("Hits", justify="left")
    table.add_column("Missed", justify="left")

    for result in metrics.results:
        style = "green" if result.success else "red"
        table.add_row(
            result.question,
            f"{result.precision:.2f}",
            f"{result.recall:.2f}",
            f"{result.snippet_coverage:.2f}",
            ", ".join(result.hit_documents) or "—",
            ", ".join(result.missed_documents) or "—",
            style=style,
        )

    console.print(table)
    if not summary.all_passed:
        console.print(
            f"[red]{summary.failing_examples} example(s) failed precision/recall targets.[/red]",
            highlight=False,
        )
    console.print("Report written to", metrics.dataset_path or "(path unknown)")

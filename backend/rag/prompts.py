"""Prompt assembly for RAG answer generation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from jinja2 import Template

MAX_SNIPPET_LENGTH = 400


def truncate_snippet(text: str, limit: int = MAX_SNIPPET_LENGTH) -> str:
    """Return a snippet constrained to ``limit`` while preserving line breaks."""

    snippet = text.strip()
    if len(snippet) <= limit:
        return snippet
    if limit <= 3:
        return snippet[:limit]
    trimmed = snippet[: limit - 3].rstrip()
    return f"{trimmed}..."


_PROMPT_TEMPLATE = Template(
    """
System Instructions:
You are a retrieval-augmented assistant. Base every answer strictly on the supplied context snippets.
Cite sources using bracket notation that references the context numbers (e.g., [1]).
If the context does not contain the answer, reply exactly with "I don't know".

Context:
{% if chunks %}
{% for chunk in chunks -%}
[{{ loop.index }}] Title: {{ chunk.title }} | Source: {{ chunk.source_type }}
Document ID: {{ chunk.document_id }} | Chunk ID: {{ chunk.chunk_id }}
{{ chunk.snippet }}

{%- endfor %}
{% else %}
[No context provided]
{% endif %}

User Question:
{{ question }}

Answer Instructions:
- Respond with clear, complete sentences unless the user requests another format.
- Include citations referencing the context numbers like [1].
- If you lack sufficient context or are uncertain, respond with "I don't know".
""".strip(),
    trim_blocks=True,
    lstrip_blocks=True,
)


@dataclass(slots=True)
class PromptChunk:
    """Input representation of retrieval context for prompt rendering."""

    document_id: str
    chunk_id: str
    source_type: str | None
    title: str | None
    snippet: str


class PromptBuilder:
    """Render deterministic prompts for the RAG pipeline."""

    template: Template

    def __init__(self, template: Template | None = None) -> None:
        self.template = template or _PROMPT_TEMPLATE

    def build_prompt(self, question: str, chunks: Sequence[PromptChunk]) -> str:
        """Render the prompt for the supplied question and context chunks."""

        rendered_chunks: list[dict[str, str]] = []
        for chunk in chunks:
            title = chunk.title or f"Document {chunk.document_id or 'Unknown'}"
            source_type = chunk.source_type or "unknown"
            rendered_chunks.append(
                {
                    "document_id": chunk.document_id,
                    "chunk_id": chunk.chunk_id,
                    "title": title,
                    "source_type": source_type,
                    "snippet": truncate_snippet(chunk.snippet, MAX_SNIPPET_LENGTH),
                }
            )
        return self.template.render(question=question, chunks=rendered_chunks)


__all__ = ["PromptBuilder", "PromptChunk", "truncate_snippet", "MAX_SNIPPET_LENGTH"]

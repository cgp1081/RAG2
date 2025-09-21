"""Utilities for splitting text into token-aware chunks."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable, List

import tiktoken

_encoder = tiktoken.get_encoding("cl100k_base")


@dataclass(slots=True)
class Chunk:
    """Represents a chunk of text with metadata."""

    text: str
    token_count: int
    sha256: str
    index: int


def _chunk_tokens(tokens: List[int], chunk_size: int, chunk_overlap: int) -> Iterable[List[int]]:
    step = max(1, chunk_size - chunk_overlap)
    for start in range(0, len(tokens), step):
        yield tokens[start : start + chunk_size]


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> list[Chunk]:
    """Split text into overlapping token chunks.

    Args:
        text: Source text to split.
        chunk_size: Maximum tokens per chunk.
        chunk_overlap: Overlap in tokens between consecutive chunks.
    """

    if not text:
        return []

    tokens = _encoder.encode(text)
    if not tokens:
        return []

    chunks: list[Chunk] = []
    for idx, token_slice in enumerate(_chunk_tokens(tokens, chunk_size, chunk_overlap)):
        if not token_slice:
            continue
        chunk_text_value = _encoder.decode(token_slice)
        chunks.append(
            Chunk(
                text=chunk_text_value,
                token_count=len(token_slice),
                sha256=_sha256_text(chunk_text_value),
                index=idx,
            )
        )
    return chunks

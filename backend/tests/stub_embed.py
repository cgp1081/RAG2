"""Manual helper for exercising the embedding service."""
from __future__ import annotations

import asyncio

import httpx

from backend.app.config import get_settings
from backend.app.logging import configure_logging
from backend.services.embedding_service import build_embedding_service
from backend.services.exceptions import EmbeddingServiceError


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    async with httpx.AsyncClient() as client:
        service = build_embedding_service(settings, client)
        try:
            embeddings = await service.embed(["stub embedding test"])
        except EmbeddingServiceError as exc:  # pragma: no cover - manual helper
            print(f"Embedding service error: {exc}")
            return

        if not embeddings:
            print("No embeddings returned.")
            return

        print(
            f"Received {len(embeddings)} embeddings; dimension={len(embeddings[0])}"
        )


if __name__ == "__main__":
    asyncio.run(main())

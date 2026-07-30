"""Enqueue generation work (inline for tests, ARQ for production)."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID


class GenerationQueue(Protocol):
    async def enqueue(self, generation_id: UUID, *, modality: str) -> None: ...


class InlineGenerationQueue:
    """Records enqueued jobs for tests / sync processing."""

    def __init__(self) -> None:
        self.items: list[tuple[UUID, str]] = []

    async def enqueue(self, generation_id: UUID, *, modality: str) -> None:
        self.items.append((generation_id, modality))

    def pop_all(self) -> list[tuple[UUID, str]]:
        items = list(self.items)
        self.items.clear()
        return items


class ArqGenerationQueue:
    def __init__(self, arq_pool: object) -> None:
        self._pool = arq_pool

    async def enqueue(self, generation_id: UUID, *, modality: str) -> None:
        queue_name = {
            "text": "kelbet:text",
            "image": "kelbet:image",
            "image_edit": "kelbet:image",
            "upscale": "kelbet:image",
            "video": "kelbet:video",
        }.get(modality, "kelbet:image")
        await self._pool.enqueue_job(  # type: ignore[attr-defined]
            "process_generation",
            str(generation_id),
            _queue_name=queue_name,
        )

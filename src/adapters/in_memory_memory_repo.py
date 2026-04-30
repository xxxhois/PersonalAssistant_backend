from typing import Any, Dict, List, Optional

from src.core.ports.memory_port import MemoryChunk, MemoryPort


class InMemoryMemoryRepository(MemoryPort):
    """Lightweight memory repository for local development and tests."""

    def __init__(self) -> None:
        self._chunks: List[MemoryChunk] = []

    async def query_context(
        self,
        query: str,
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[MemoryChunk]:
        del query, filters
        return self._chunks[:limit]

    async def store(self, chunk: MemoryChunk) -> None:
        self._chunks.append(chunk)

    async def batch_store(self, chunks: List[MemoryChunk]) -> None:
        self._chunks.extend(chunks)

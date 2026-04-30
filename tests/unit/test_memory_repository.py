from src.adapters.pg_repo import PGBackedMemoryRepository
from src.core.ports.memory_port import MemoryChunk
import pytest


class FakePGMemoryRepository:
    def __init__(self) -> None:
        self.stored: list[MemoryChunk] = []

    async def query_context(self, query, limit=5, filters=None):
        del query, filters
        return self.stored[:limit]

    async def batch_store(self, chunks):
        self.stored.extend(chunks)

    async def get_by_ids(self, ids, filters=None):
        del filters
        by_id = {chunk.metadata["id"]: chunk for chunk in self.stored}
        return [by_id[memory_id] for memory_id in ids if memory_id in by_id]


class FakeVectorIndex:
    def __init__(self) -> None:
        self.indexed: list[MemoryChunk] = []

    async def query_context(self, query, limit=5, filters=None):
        del query, filters
        return [
            MemoryChunk(
                content=chunk.content,
                metadata={"id": chunk.metadata["id"]},
                score=0.82,
            )
            for chunk in self.indexed[:limit]
        ]

    async def batch_store(self, chunks):
        self.indexed.extend(chunks)


@pytest.mark.asyncio
async def test_pg_backed_memory_stores_pg_first_and_uses_chroma_only_as_index():
    pg_repo = FakePGMemoryRepository()
    vector_index = FakeVectorIndex()
    repo = PGBackedMemoryRepository(pg_repo=pg_repo, vector_index=vector_index)  # type: ignore[arg-type]

    await repo.store(
        MemoryChunk(
            content="User likes concise responses.",
            metadata={"user_id": "user-1", "scope": "companion"},
            score=0.0,
        )
    )

    assert len(pg_repo.stored) == 1
    assert len(vector_index.indexed) == 1
    assert pg_repo.stored[0].metadata["id"] == vector_index.indexed[0].metadata["id"]

    results = await repo.query_context(
        "concise",
        filters={"user_id": "user-1", "scope": "companion"},
    )

    assert results == pg_repo.stored
    assert results[0].score == 0.82

from datetime import datetime, timedelta, timezone

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
                score=chunk.score,
            )
            for chunk in self.indexed[:limit]
        ]

    async def batch_store(self, chunks):
        self.indexed.extend(chunks)


class FailingVectorIndex:
    async def query_context(self, query, limit=5, filters=None):
        del query, limit, filters
        raise RuntimeError("index unavailable")

    async def batch_store(self, chunks):
        del chunks


@pytest.mark.asyncio
async def test_pg_backed_memory_stores_pg_first_and_uses_chroma_only_as_index():
    pg_repo = FakePGMemoryRepository()
    vector_index = FakeVectorIndex()
    repo = PGBackedMemoryRepository(pg_repo=pg_repo, vector_index=vector_index)  # type: ignore[arg-type]

    await repo.store(
        MemoryChunk(
            content="User likes concise responses.",
            metadata={"user_id": "user-1", "scope": "companion"},
            score=0.82,
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
    assert results[0].metadata["semantic_score"] == 0.82
    assert results[0].score > 0.0


@pytest.mark.asyncio
async def test_pg_backed_memory_hydrates_and_reranks_candidates():
    now = datetime.now(timezone.utc)
    pg_repo = FakePGMemoryRepository()
    vector_index = FakeVectorIndex()
    repo = PGBackedMemoryRepository(pg_repo=pg_repo, vector_index=vector_index)  # type: ignore[arg-type]

    await repo.batch_store(
        [
            MemoryChunk(
                content="Recent important graduation project context.",
                metadata={
                    "id": "recent-important",
                    "user_id": "user-1",
                    "scope": "companion",
                    "importance": 0.9,
                    "updated_at": now.isoformat(),
                },
                score=0.7,
            ),
            MemoryChunk(
                content="Old low importance context.",
                metadata={
                    "id": "old-low",
                    "user_id": "user-1",
                    "scope": "companion",
                    "importance": 0.2,
                    "updated_at": (now - timedelta(days=365)).isoformat(),
                },
                score=0.72,
            ),
        ]
    )

    results = await repo.query_context(
        "graduation project context",
        limit=2,
        filters={"user_id": "user-1", "scope": "companion"},
    )

    assert [chunk.metadata["id"] for chunk in results] == ["recent-important", "old-low"]
    assert results[0].score > results[1].score


@pytest.mark.asyncio
async def test_pg_backed_memory_falls_back_to_pg_when_chroma_query_fails():
    pg_repo = FakePGMemoryRepository()
    pg_repo.stored.append(
        MemoryChunk(
            content="Durable PG fallback memory.",
            metadata={"id": "pg-only", "user_id": "user-1", "scope": "companion"},
            score=0.0,
        )
    )
    repo = PGBackedMemoryRepository(pg_repo=pg_repo, vector_index=FailingVectorIndex())  # type: ignore[arg-type]

    results = await repo.query_context(
        "fallback",
        limit=1,
        filters={"user_id": "user-1", "scope": "companion"},
    )

    assert len(results) == 1
    assert results[0].metadata["id"] == "pg-only"

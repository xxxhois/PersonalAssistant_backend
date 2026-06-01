from unittest.mock import AsyncMock

import pytest

from src.core.ports.memory_port import MemoryChunk, MemoryPort
from src.services.memory_service import MemoryService
from src.services.mental_state import MentalState, MentalStateSnapshot


@pytest.mark.asyncio
async def test_memory_service_skips_low_signal_turns() -> None:
    memory_port = AsyncMock(spec=MemoryPort)
    service = MemoryService(memory_port)

    await service.store_turn_summary(
        user_id="user-1",
        user_input="ok",
        assistant_output="Sure.",
        mental_state=MentalStateSnapshot(state=MentalState.NEUTRAL, confidence=0.5),
    )

    memory_port.store.assert_not_called()


@pytest.mark.asyncio
async def test_memory_service_stores_selected_preference_memory() -> None:
    memory_port = AsyncMock(spec=MemoryPort)
    memory_port.query_context.return_value = []
    service = MemoryService(memory_port)

    await service.store_turn_summary(
        user_id="user-1",
        user_input="I prefer concise answers; please do not be verbose.",
        assistant_output="Understood. I will keep it concise.",
        mental_state=MentalStateSnapshot(state=MentalState.NEUTRAL, confidence=0.5),
    )

    memory_port.store.assert_awaited_once()
    chunk = memory_port.store.await_args.args[0]
    assert chunk.metadata["memory_type"] == "preference"
    assert chunk.metadata["user_id"] == "user-1"
    assert chunk.content.startswith("User memory (preference")
    assert "Understood" not in chunk.content
    assert chunk.metadata["write_policy"] == "insert"


@pytest.mark.asyncio
async def test_memory_service_stores_graduation_project_topic() -> None:
    memory_port = AsyncMock(spec=MemoryPort)
    memory_port.query_context.return_value = []
    service = MemoryService(memory_port)

    await service.store_turn_summary(
        user_id="user-1",
        user_input="我的毕设题目是基于大模型的人格化自主规划系统设计与实现。",
        assistant_output="记下了。",
        mental_state=MentalStateSnapshot(state=MentalState.NEUTRAL, confidence=0.5),
    )

    memory_port.store.assert_awaited_once()
    chunk = memory_port.store.await_args.args[0]
    assert chunk.metadata["memory_type"] == "project_context"
    assert "毕设题目" in chunk.content


@pytest.mark.asyncio
async def test_memory_service_retrieves_for_thesis_topic_query() -> None:
    memory_port = AsyncMock(spec=MemoryPort)
    memory_port.query_context.return_value = [
        MemoryChunk(
            content="User memory (project_context): 我的毕设题目是基于大模型的人格化自主规划系统设计与实现。",
            metadata={"id": "topic-memory"},
            score=0.9,
        )
    ]
    service = MemoryService(memory_port)

    result = await service.retrieve_for_companion(
        user_id="user-1",
        query="我的毕设题目是什么？",
    )

    assert result
    assert result[0].metadata["id"] == "topic-memory"
    memory_port.query_context.assert_awaited_once()


@pytest.mark.asyncio
async def test_memory_service_updates_similar_existing_memory() -> None:
    memory_port = AsyncMock(spec=MemoryPort)
    memory_port.query_context.return_value = [
        MemoryChunk(
            content="User memory (preference, user_preference): I prefer concise answers.",
            metadata={
                "id": "existing-memory",
                "user_id": "user-1",
                "scope": "companion",
                "memory_type": "preference",
                "importance": 0.6,
                "created_at": "2026-01-01T00:00:00+00:00",
                "semantic_score": 0.74,
            },
            score=0.7,
        )
    ]
    service = MemoryService(memory_port)

    await service.store_turn_summary(
        user_id="user-1",
        user_input="I prefer concise answers; keep them short.",
        assistant_output="Understood.",
        mental_state=MentalStateSnapshot(state=MentalState.NEUTRAL, confidence=0.5),
    )

    memory_port.store.assert_awaited_once()
    chunk = memory_port.store.await_args.args[0]
    assert chunk.metadata["id"] == "existing-memory"
    assert chunk.metadata["write_policy"] == "update"
    assert chunk.metadata["created_at"] == "2026-01-01T00:00:00+00:00"
    assert chunk.metadata["importance"] == 0.75


@pytest.mark.asyncio
async def test_memory_service_skips_retrieval_for_low_signal_query() -> None:
    memory_port = AsyncMock(spec=MemoryPort)
    service = MemoryService(memory_port)

    result = await service.retrieve_for_companion(
        user_id="user-1",
        query="ok",
    )

    assert result == []
    memory_port.query_context.assert_not_called()


@pytest.mark.asyncio
async def test_memory_service_retrieves_and_applies_context_budget() -> None:
    memory_port = AsyncMock(spec=MemoryPort)
    memory_port.query_context.return_value = [
        MemoryChunk(content="A" * 700, metadata={"id": "1"}, score=0.9),
        MemoryChunk(content="B" * 600, metadata={"id": "2"}, score=0.8),
    ]
    service = MemoryService(memory_port)

    result = await service.retrieve_for_companion(
        user_id="user-1",
        query="What did I say before about my graduation project?",
    )

    assert len(result) == 1
    assert result[0].metadata["id"] == "1"
    memory_port.query_context.assert_awaited_once_with(
        query="What did I say before about my graduation project?",
        limit=5,
        filters={"user_id": "user-1", "scope": "companion"},
    )

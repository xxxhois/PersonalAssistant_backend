from unittest.mock import AsyncMock

import pytest

from src.core.ports.memory_port import MemoryPort
from src.services.memory_service import MemoryService
from src.services.mental_state import MentalState, MentalStateSnapshot


@pytest.mark.asyncio
async def test_memory_service_skips_low_signal_turns() -> None:
    memory_port = AsyncMock(spec=MemoryPort)
    service = MemoryService(memory_port)

    await service.store_turn_summary(
        user_id="user-1",
        user_input="好的",
        assistant_output="行。",
        mental_state=MentalStateSnapshot(state=MentalState.NEUTRAL, confidence=0.5),
    )

    memory_port.store.assert_not_called()


@pytest.mark.asyncio
async def test_memory_service_stores_selected_preference_memory() -> None:
    memory_port = AsyncMock(spec=MemoryPort)
    service = MemoryService(memory_port)

    await service.store_turn_summary(
        user_id="user-1",
        user_input="我喜欢回答短一点，别太啰嗦",
        assistant_output="明白，我会短一点。",
        mental_state=MentalStateSnapshot(state=MentalState.NEUTRAL, confidence=0.5),
    )

    memory_port.store.assert_awaited_once()
    chunk = memory_port.store.await_args.args[0]
    assert chunk.metadata["memory_type"] == "preference"
    assert chunk.metadata["user_id"] == "user-1"
    assert chunk.content.startswith("User memory (preference")
    assert "明白，我会短一点" not in chunk.content

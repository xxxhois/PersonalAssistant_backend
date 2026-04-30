from src.core.ports.memory_port import MemoryChunk
from src.services.companion import CompanionService
import pytest


class FakeLLMClient:
    def __init__(self) -> None:
        self.calls = []

    async def chat_stream(self, **kwargs):
        self.calls.append(kwargs)
        yield "Not much noise tonight. "
        yield "Start with one small step."


class FakeMemoryPort:
    def __init__(self) -> None:
        self.stored: list[MemoryChunk] = []

    async def query_context(self, query, limit=5, filters=None):
        del query, limit, filters
        return [
            MemoryChunk(
                content="User memory (preference): user likes concise replies.",
                metadata={
                    "id": "mem-1",
                    "user_id": "user-1",
                    "scope": "companion",
                    "memory_type": "preference",
                    "mental_state": "low_energy",
                },
                score=0.9,
            )
        ]

    async def store(self, chunk):
        self.stored.append(chunk)

    async def batch_store(self, chunks):
        self.stored.extend(chunks)


@pytest.mark.asyncio
async def test_companion_chat_injects_persona_memory_and_mental_state():
    llm_client = FakeLLMClient()
    memory_port = FakeMemoryPort()
    service = CompanionService(llm_client=llm_client, memory_port=memory_port)  # type: ignore[arg-type]

    tokens = []
    async for token in service.chat_stream(
        user_id="user-1",
        user_input="我喜欢短一点的回答，今天真的好累",
    ):
        tokens.append(token)

    assert "".join(tokens).startswith("Not much noise")
    call = llm_client.calls[0]
    assert "hard-boiled noir detective" in call["custom_system_prompt"]
    assert "Detected state: low_energy" in call["custom_system_prompt"]
    assert call["memory_chunks"] == [
        "User memory (preference): user likes concise replies."
    ]
    assert memory_port.stored
    assert memory_port.stored[0].metadata["memory_type"] == "preference"

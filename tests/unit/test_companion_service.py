from src.core.ports.memory_port import MemoryChunk
from src.schemas.htn import HTNPlan, HTNTask, PlanStatus, TaskStatus
from src.services.companion import CompanionService
import pytest
from uuid import uuid4


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


class FakeTaskPort:
    async def get_active_plan(self, user_id):
        del user_id
        return HTNPlan(
            plan_id=uuid4(),
            goal="Finish the graduation project backend memory system",
            status=PlanStatus.ACTIVE,
            tasks=[
                HTNTask(
                    id=uuid4(),
                    title="Verify PG and Chroma memory retrieval",
                    status=TaskStatus.IN_PROGRESS,
                    metadata={"scheduled_date": "2026-06-01"},
                ),
                HTNTask(
                    id=uuid4(),
                    title="Write thesis implementation chapter",
                    status=TaskStatus.PENDING,
                    metadata={},
                ),
            ],
        )


@pytest.mark.asyncio
async def test_companion_chat_injects_persona_memory_and_mental_state():
    llm_client = FakeLLMClient()
    memory_port = FakeMemoryPort()
    service = CompanionService(
        llm_client=llm_client,
        memory_port=memory_port,
        task_port=FakeTaskPort(),  # type: ignore[arg-type]
    )  # type: ignore[arg-type]

    tokens = []
    async for token in service.chat_stream(
        user_id="user-1",
        user_input="我喜欢短一点的回答，今天真的好累",
    ):
        tokens.append(token)

    assert "".join(tokens).startswith("Not much noise")
    call = llm_client.calls[0]
    assert "PERSONA STATE MACHINE PROMPT" in call["custom_system_prompt"]
    assert "STABLE PERSONA LAYER:" in call["custom_system_prompt"]
    assert "DYNAMIC STATE LAYER:" in call["custom_system_prompt"]
    assert "SCENE BOUNDARY LAYER:" in call["custom_system_prompt"]
    assert "hard-boiled noir detective" in call["custom_system_prompt"]
    assert "Detected state: low_energy" in call["custom_system_prompt"]
    assert "Response strategy: low_friction_action" in call["custom_system_prompt"]
    assert "MARLOWE RESPONSE CONTRACT" in call["custom_system_prompt"]
    assert "Sound like 马洛 speaking" in call["custom_system_prompt"]
    assert "Do not say you are an AI assistant" in call["custom_system_prompt"]
    assert "Do not use bullet points" in call["custom_system_prompt"]
    assert call["user_context"].preferences["preferred_length"] == "short"
    assert call["memory_chunks"] == [
        "Current active plan context:\n"
        "Goal: Finish the graduation project backend memory system\n"
        "Status: active\n"
        "Open tasks:\n"
        "1. Verify PG and Chroma memory retrieval (2026-06-01)\n"
        "2. Write thesis implementation chapter",
        "User memory (preference): user likes concise replies."
    ]
    assert "current user state" in call["custom_system_prompt"]
    assert memory_port.stored
    assert memory_port.stored[0].metadata["memory_type"] == "preference"

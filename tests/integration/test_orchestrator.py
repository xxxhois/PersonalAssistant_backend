import pytest
from unittest.mock import AsyncMock, MagicMock

from src.core.ports.llm_client_port import LLMRequest
from src.core.ports.memory_port import MemoryChunk, MemoryPort
from src.core.ports.task_port import TaskPort
from src.schemas.sse import SSEEventType
from src.services.orchestrator import Orchestrator


@pytest.mark.asyncio
async def test_orchestrator_chat_stream_flow():
    """Test the full Orchestrator chat stream flow."""

    class MockLLMPort:
        def __init__(self):
            self.requests: list[LLMRequest] = []

        async def stream(self, request: LLMRequest):
            self.requests.append(request)

            if request.max_tokens == 500 and "Analyze the user's intent" in request.prompt:
                yield '{"intent": "general", "confidence": 1.0}'
                return

            yield "Hello, "
            yield "world!"
            yield "<!--TASK_START-->"
            yield '{"type": "TASK_CREATED", "id": "task_1"}'
            yield "<!--TASK_END-->"

    llm_port = MockLLMPort()
    task_port = MagicMock(spec=TaskPort)

    memory_port = MagicMock(spec=MemoryPort)
    memory_port.query_context = AsyncMock(
        return_value=[
            MemoryChunk(content="Previous context", metadata={}, score=0.9),
        ]
    )

    orchestrator = Orchestrator(
        llm_port=llm_port,
        task_port=task_port,
        memory_port=memory_port,
    )

    request_id = "test_req_123"
    frames = []
    async for frame in orchestrator.chat_stream("user_1", "Hello!", request_id):
        frames.append(frame)

    event_types = [f.event for f in frames]

    assert SSEEventType.TOKEN in event_types
    assert SSEEventType.TASK_EVENT in event_types
    assert SSEEventType.DONE in event_types

    assert event_types[-1] == SSEEventType.DONE
    assert frames[-1].data["request_id"] == request_id

    seqs = [f.seq for f in frames]
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == len(seqs)

    memory_port.query_context.assert_called_once()

    chat_requests = [
        request
        for request in llm_port.requests
        if request.stop == ["<!--TASK_END-->"]
    ]
    assert len(chat_requests) == 1

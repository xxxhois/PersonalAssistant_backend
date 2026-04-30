import pytest
from unittest.mock import AsyncMock, MagicMock
from src.services.orchestrator import Orchestrator
from src.core.ports.llm_client_port import LLMStreamPort, LLMRequest
from src.core.ports.task_port import TaskPort
from src.core.ports.memory_port import MemoryPort, MemoryChunk
from src.schemas.sse import SSEEventType, SSEFrame

@pytest.mark.asyncio
async def test_orchestrator_chat_stream_flow():
    """测试 Orchestrator 对话流完整流程"""
    
    # 1. 模拟 LLM Stream Port
    llm_port = MagicMock(spec=LLMStreamPort)
    async def mock_stream(request: LLMRequest):
        yield "Hello, "
        yield "world!"
        yield "<!--TASK_START-->"
        yield '{"type": "TASK_CREATED", "id": "task_1"}'
        yield "<!--TASK_END-->"
    llm_port.stream.side_effect = mock_stream

    # 2. 模拟 Task Port
    task_port = MagicMock(spec=TaskPort)
    
    # 3. 模拟 Memory Port
    memory_port = MagicMock(spec=MemoryPort)
    memory_port.query_context = AsyncMock(return_value=[
        MemoryChunk(content="Previous context", metadata={}, score=0.9)
    ])

    # 4. 初始化 Orchestrator
    orchestrator = Orchestrator(
        llm_port=llm_port,
        task_port=task_port,
        memory_port=memory_port
    )

    # 5. 执行测试
    request_id = "test_req_123"
    frames = []
    async for frame in orchestrator.chat_stream("user_1", "Hello!", request_id):
        frames.append(frame)

    # 6. 验证结果
    # 验证事件类型序列
    event_types = [f.event for f in frames]
    
    # 至少应包含 TOKEN, TASK_EVENT, DONE
    assert SSEEventType.TOKEN in event_types
    assert SSEEventType.TASK_EVENT in event_types
    assert SSEEventType.DONE in event_types

    # 验证最后一个事件是 DONE
    assert event_types[-1] == SSEEventType.DONE
    assert frames[-1].data["request_id"] == request_id

    # 验证序列号递增
    seqs = [f.seq for f in frames]
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == len(seqs)

    # 验证 Memory Port 被调用
    memory_port.query_context.assert_called_once()
    
    # 验证 LLM Port 被调用
    llm_port.stream.assert_called_once()

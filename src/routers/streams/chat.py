import uuid
from typing import AsyncIterator
from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse
from src.services.orchestrator import Orchestrator
from src.infra.llm_router import llm_router
from src.adapters.pg_repo import PGTaskRepository
from src.adapters.chroma_adapter import ChromaAdapter
from sqlalchemy.ext.asyncio import AsyncSession
# 假设有一个全局获取 DB Session 的依赖
# from src.infra.db.session import get_db

router = APIRouter(prefix="/streams")

def get_orchestrator(
    # db: AsyncSession = Depends(get_db)
) -> Orchestrator:
    """
    Orchestrator 依赖注入组装
    """
    # 实际项目中应从依赖注入容器或 get_db 中获取适配器
    # 这里为了演示进行手动组装
    llm_port = llm_router.get_provider("openai")
    
    # 占位实现适配器
    task_port = PGTaskRepository(session=None)  # type: ignore
    memory_port = ChromaAdapter(host="localhost", port=8000)
    
    return Orchestrator(
        llm_port=llm_port,
        task_port=task_port,
        memory_port=memory_port
    )

@router.get("/chat")
async def chat(
    user_input: str,
    request: Request,
    orchestrator: Orchestrator = Depends(get_orchestrator)
) -> EventSourceResponse:
    """
    SSE 流式对话路由
    """
    request_id = str(uuid.uuid4())
    user_id = "default_user"  # 实际应从 Auth Middleware 获取

    async def event_generator() -> AsyncIterator[dict]:
        async for frame in orchestrator.chat_stream(user_id, user_input, request_id):
            yield {
                "id": frame.id,
                "event": frame.event.value,
                "data": frame.model_dump_json(include={"data", "request_id", "seq", "recoverable"})
            }

    return EventSourceResponse(event_generator())

import uuid
import json
from typing import AsyncIterator
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from src.services.orchestrator import Orchestrator
from sqlalchemy.ext.asyncio import AsyncSession
from src.routers.api_v1.dependencies import build_companion_orchestrator
from src.infra.db.session import get_db_session

router = APIRouter(prefix="/streams")

def get_orchestrator(
    session: AsyncSession = Depends(get_db_session),
) -> Orchestrator:
    """Build the companion orchestrator through the shared dependency path."""
    return build_companion_orchestrator(session=session)

@router.get("/chat")
async def chat(
    user_input: str,
    request: Request,
    orchestrator: Orchestrator = Depends(get_orchestrator)
) -> StreamingResponse:
    """
    SSE 流式对话路由
    """
    request_id = str(uuid.uuid4())
    user_id = "default_user"  # 实际应从 Auth Middleware 获取

    async def event_generator() -> AsyncIterator[str]:
        async for frame in orchestrator.chat_stream(user_id, user_input, request_id):
            if await request.is_disconnected():
                break
            yield f"data: {json.dumps(frame.model_dump(mode='json'))}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

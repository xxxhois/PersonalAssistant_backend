import json
import uuid
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions.app_exception import AppException, ErrorCode
from src.infra.db.session import get_db_session
from src.routers.api_v1.dependencies import build_companion_orchestrator
from src.schemas.chat import ChatMode, ChatStreamRequest
from src.schemas.sse import SSEEventType, SSEFrame

router = APIRouter(prefix="/api/v1", tags=["chat"])


def sse_frame_to_json(frame: SSEFrame) -> str:
    return f"data: {json.dumps(frame.model_dump(mode='json'))}\n\n"


@router.post("/chat/stream")
async def chat_stream(
    request: ChatStreamRequest,
    session: AsyncSession = Depends(get_db_session),
) -> StreamingResponse:
    if request.mode == ChatMode.PLANNING:
        raise HTTPException(
            status_code=400,
            detail=(
                "planning mode is handled by /api/v1/planning endpoints; "
                "companion chat intentionally stays decoupled from goal decomposition"
            ),
        )

    request_id = str(uuid.uuid4())
    orchestrator = build_companion_orchestrator(session=session)

    async def event_generator() -> AsyncIterator[str]:
        try:
            async for frame in orchestrator.chat_stream(
                user_id=request.user_id,
                user_input=request.user_message,
                request_id=request_id,
            ):
                yield sse_frame_to_json(frame)
        except AppException as exc:
            yield sse_frame_to_json(
                SSEFrame(
                    id="error_0",
                    request_id=request_id,
                    seq=0,
                    event=SSEEventType.ERROR,
                    data={"code": exc.code.value, "message": exc.message},
                    recoverable=exc.recoverable,
                )
            )
        except Exception as exc:
            yield sse_frame_to_json(
                SSEFrame(
                    id="error_0",
                    request_id=request_id,
                    seq=0,
                    event=SSEEventType.ERROR,
                    data={
                        "code": ErrorCode.INTERNAL_ERROR.value,
                        "message": str(exc),
                    },
                    recoverable=False,
                )
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Request-ID": request_id,
        },
    )

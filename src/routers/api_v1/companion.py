import json
import uuid
from typing import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from src.core.exceptions.app_exception import AppException, ErrorCode
from src.routers.api_v1.dependencies import get_proactive_companion_service
from src.schemas.companion import ProactiveOutreachRequest
from src.schemas.sse import SSEEventType, SSEFrame
from src.services.proactive import ProactiveCompanionService

router = APIRouter(prefix="/api/v1/companion", tags=["companion"])


def _frame_to_sse(frame: SSEFrame) -> str:
    return f"data: {json.dumps(frame.model_dump(mode='json'), ensure_ascii=False)}\n\n"


@router.post("/proactive/stream")
async def proactive_outreach_stream(
    request: ProactiveOutreachRequest,
    service: ProactiveCompanionService = Depends(get_proactive_companion_service),
) -> StreamingResponse:
    request_id = str(uuid.uuid4())

    async def event_generator() -> AsyncIterator[str]:
        seq = 0
        try:
            async for token in service.outreach_stream(
                user_id=request.user_id,
                trigger_reason=request.trigger_reason,
            ):
                seq += 1
                yield _frame_to_sse(
                    SSEFrame(
                        id=f"token_{seq}",
                        event=SSEEventType.TOKEN,
                        data={"token": token},
                        request_id=request_id,
                        seq=seq,
                    )
                )

            seq += 1
            yield _frame_to_sse(
                SSEFrame(
                    id=f"done_{seq}",
                    event=SSEEventType.DONE,
                    data={"request_id": request_id},
                    request_id=request_id,
                    seq=seq,
                )
            )
        except AppException as exc:
            seq += 1
            yield _frame_to_sse(
                SSEFrame(
                    id=f"error_{seq}",
                    event=SSEEventType.ERROR,
                    data={"code": exc.code.value, "message": exc.message},
                    request_id=request_id,
                    seq=seq,
                    recoverable=exc.recoverable,
                )
            )
        except Exception as exc:
            seq += 1
            yield _frame_to_sse(
                SSEFrame(
                    id=f"error_{seq}",
                    event=SSEEventType.ERROR,
                    data={
                        "code": ErrorCode.INTERNAL_ERROR.value,
                        "message": str(exc),
                    },
                    request_id=request_id,
                    seq=seq,
                    recoverable=False,
                )
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )

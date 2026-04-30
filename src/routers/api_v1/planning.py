import json
import uuid
from typing import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from src.core.exceptions.app_exception import AppException, ErrorCode
from src.routers.api_v1.dependencies import get_planning_service
from src.schemas.planning import (
    DecomposeProgressEvent,
    GoalInitRequest,
    PlanConfirmRequest,
    PlanStartRequest,
    TaskUpdateRequest,
)
from src.schemas.sse import SSEEventType, SSEFrame
from src.services.planning import PlanningService

router = APIRouter(prefix="/api/v1/planning", tags=["planning"])


def _frame_to_sse(frame: SSEFrame) -> str:
    return f"data: {json.dumps(frame.model_dump(mode='json'), ensure_ascii=False)}\n\n"


@router.post("/initialize")
async def initialize_planning(
    request: GoalInitRequest,
    planning_service: PlanningService = Depends(get_planning_service),
):
    return await planning_service.initialize_goal(request)


@router.post("/stream")
async def stream_planning(
    request: PlanStartRequest,
    planning_service: PlanningService = Depends(get_planning_service),
):
    request_id = str(uuid.uuid4())

    async def event_generator() -> AsyncIterator[str]:
        seq = 0
        try:
            async for item in planning_service.stream_plan(request):
                seq += 1
                if isinstance(item, DecomposeProgressEvent):
                    frame = SSEFrame(
                        id=f"progress_{seq}",
                        event=SSEEventType.PROGRESS,
                        data=item.model_dump(),
                        request_id=request_id,
                        seq=seq,
                    )
                else:
                    frame = SSEFrame(
                        id=f"done_{seq}",
                        event=SSEEventType.DONE,
                        data={"plan": item.model_dump(mode="json")},
                        request_id=request_id,
                        seq=seq,
                    )
                yield _frame_to_sse(frame)
        except AppException as exc:
            seq += 1
            yield _frame_to_sse(
                SSEFrame(
                    id=f"error_{seq}",
                    event=SSEEventType.ERROR,
                    data={
                        "code": exc.code.value,
                        "message": exc.message,
                        "details": exc.details,
                    },
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


@router.post("/confirm")
async def confirm_planning(
    request: PlanConfirmRequest,
    planning_service: PlanningService = Depends(get_planning_service),
):
    try:
        return await planning_service.confirm_plan(request)
    except AppException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/plans/{plan_id}")
async def get_plan(
    plan_id: UUID,
    planning_service: PlanningService = Depends(get_planning_service),
):
    try:
        return await planning_service.get_plan(plan_id)
    except AppException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/plans/{plan_id}")
async def delete_plan(
    plan_id: UUID,
    planning_service: PlanningService = Depends(get_planning_service),
):
    try:
        return await planning_service.delete_plan(plan_id)
    except AppException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/users/{user_id}/active-plan")
async def get_active_plan(
    user_id: str,
    planning_service: PlanningService = Depends(get_planning_service),
):
    try:
        return await planning_service.get_active_plan(user_id)
    except AppException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/users/{user_id}/plans")
async def list_plans(
    user_id: str,
    limit: int = 20,
    offset: int = 0,
    planning_service: PlanningService = Depends(get_planning_service),
):
    try:
        return await planning_service.list_plans(
            user_id=user_id,
            limit=limit,
            offset=offset,
        )
    except AppException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.patch("/tasks/{task_id}")
async def update_task(
    task_id: UUID,
    request: TaskUpdateRequest,
    planning_service: PlanningService = Depends(get_planning_service),
):
    try:
        return await planning_service.update_task(task_id=task_id, request=request)
    except AppException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

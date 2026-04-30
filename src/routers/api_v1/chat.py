"""
聊天 API 端点（v1）
接收 HTTP 请求，调用 Orchestrator，返回 SSE 流
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
import uuid
import json
from typing import AsyncIterator

from src.routers.api_v1.dependencies import get_orchestrator
from src.services.orchestrator import Orchestrator
from src.schemas.sse import SSEFrame
from src.core.exceptions.app_exception import AppException, ErrorCode

# 创建路由器
router = APIRouter(prefix="/api/v1", tags=["chat"])


async def sse_frame_to_json(frame: SSEFrame) -> str:
    """
    将 SSEFrame 转换为 JSON 字符串（SSE 格式）
    SSE 格式：data: {json}\n\n
    """
    return f"data: {json.dumps(frame.to_dict())}\n\n"


@router.post("/chat/stream")
async def chat_stream(
    user_message: str,
    user_id: str = "default_user",
    orchestrator: Orchestrator = Depends(get_orchestrator)
):
    """
    流式聊天端点
    
    Args:
        user_message: 用户消息
        user_id: 用户 ID（用于上下文管理）
    
    Returns:
        SSE 流
    
    Example:
        POST /api/v1/chat/stream
        {
            "user_message": "请帮我计划今天的工作",
            "user_id": "user_123"
        }
        
        Response (SSE):
        data: {"seq": 1, "type": "text_chunk", "data": {"text": "好"}}
        data: {"seq": 2, "type": "text_chunk", "data": {"text": "的"}}
        ...
        data: {"seq": 100, "type": "done", "data": {...}}
    """
    try:
        # 生成请求 ID（用于追踪）
        request_id = str(uuid.uuid4())
        
        async def event_generator() -> AsyncIterator[str]:
            """
            生成 SSE 事件流
            """
            try:
                # 调用 Orchestrator 获取事件流
                async for frame in orchestrator.chat_stream(
                    user_id=user_id,
                    user_input=user_message,
                    request_id=request_id
                ):
                    # 将 SSEFrame 转换为 JSON 并发送
                    yield await sse_frame_to_json(frame)
            except AppException as e:
                # 发送错误帧
                error_frame = SSEFrame(
                    request_id=request_id,
                    seq=0,
                    event_type="error",
                    data={
                        "code": e.code.value,
                        "message": e.message,
                        "recoverable": e.recoverable
                    }
                )
                yield await sse_frame_to_json(error_frame)
            except Exception as e:
                # 未知错误
                error_frame = SSEFrame(
                    request_id=request_id,
                    seq=0,
                    event_type="error",
                    data={
                        "code": ErrorCode.INTERNAL_ERROR.value,
                        "message": str(e),
                        "recoverable": False
                    }
                )
                yield await sse_frame_to_json(error_frame)
        
        # 返回 SSE 流
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Request-ID": request_id,
            }
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start chat stream: {str(e)}"
        )


@router.post("/chat/analyze-emotion")
async def analyze_emotion(
    text: str,
    orchestrator: Orchestrator = Depends(get_orchestrator)
):
    """
    分析文本情感
    
    Args:
        text: 要分析的文本
    
    Returns:
        {
            "emotion": "happy|sad|...",
            "intensity": 0-10,
            "reasoning": "..."
        }
    """
    try:
        # 这里应该调用 LLMClient.analyze_emotion()
        # result = orchestrator.llm_client.analyze_emotion(text)
        # return result
        raise NotImplementedError("Emotion analysis endpoint not implemented")
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# === 注册路由 ===
# 在主应用中使用：
# app.include_router(router)

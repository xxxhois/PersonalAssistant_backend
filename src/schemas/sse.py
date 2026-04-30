from enum import Enum
from pydantic import BaseModel, Field, model_validator
from typing import Any, Optional, Dict, Union, List
from src.schemas.htn import JsonValue

class SSEEventType(str, Enum):
    """
    SSE 帧事件类型
    遵循架构铁律：token / task_event / progress / error / done / heartbeat
    禁止使用 event: message 或纯文本 data
    """
    TOKEN = "token"
    TASK_EVENT = "task_event"
    PROGRESS = "progress"
    ERROR = "error"
    DONE = "done"
    HEARTBEAT = "heartbeat"

class SSEFrame(BaseModel):
    """
    符合铁律的 SSE 帧定义 (SSEFrame)
    """
    id: str = Field(..., description="格式：{type}_{seq}，用于断线重连与幂等去重")
    event: SSEEventType = Field(..., description="多事件类型枚举")
    data: JsonValue = Field(..., description="所有 data 字段必须为合法 JSON")
    request_id: str = Field(..., description="请求全局 ID，由 SSE 层透传")
    seq: int = Field(..., description="单调递增序列号")
    recoverable: Optional[bool] = Field(None, description="error 事件必须包含此值")

    @model_validator(mode="after")
    def validate_error_event(self) -> "SSEFrame":
        """
        遵循架构铁律：error 事件必须包含 recoverable 布尔值
        true 触发自动重试，false 终止流并推送 done
        """
        if self.event == SSEEventType.ERROR and self.recoverable is None:
            raise ValueError("error event MUST contain 'recoverable' boolean")
        return self

from pydantic import BaseModel, Field
from typing import Any, Optional
from src.core.exceptions.app_exception import ErrorCode

class ErrorResponse(BaseModel):
    """
    统一错误响应结构 (ErrorResponse)
    遵循架构铁律：外部捕获器（FastAPI exception_handler / SSE finally）必须统一包装为此结构
    """
    code: ErrorCode = Field(..., description="业务错误代码")
    message: str = Field(..., description="错误简述")
    details: Optional[Any] = Field(None, description="错误详情，开发环境可含 traceback，生产环境脱敏")
    request_id: str = Field(..., description="全局请求唯一 ID")
    recoverable: bool = Field(..., description="是否可自动重试：网络/限流为 True；校验/权限/逻辑为 False")

from enum import Enum
from typing import Any, Optional

class ErrorCode(str, Enum):
    """
    业务错误代码枚举 (ErrorCode)
    遵循架构铁律：所有业务/领域异常必须继承 AppException，使用此枚举定义 code
    """
    # 系统级
    INTERNAL_ERROR = "SYS_INTERNAL_ERROR"
    # 业务逻辑级
    VALIDATION_ERROR = "BIZ_VALIDATION_ERROR"
    UNAUTHORIZED = "BIZ_UNAUTHORIZED"
    FORBIDDEN = "BIZ_FORBIDDEN"
    NOT_FOUND = "BIZ_NOT_FOUND"
    # 编排与 HTN 级
    HTN_PLAN_FAILED = "BIZ_HTN_PLAN_FAILED"
    TASK_EXECUTION_ERROR = "BIZ_TASK_EXECUTION_ERROR"
    # 基础设施级
    LLM_PROVIDER_ERROR = "INF_LLM_PROVIDER_ERROR"
    LLM_TIMEOUT = "INF_LLM_TIMEOUT"
    MEMORY_RETRIEVAL_FAILED = "INF_MEMORY_RETRIEVAL_FAILED"
    TOOL_EXECUTION_FAILED = "INF_TOOL_EXECUTION_FAILED"

class AppException(Exception):
    """
    业务/领域异常基类 (AppException)
    遵循架构铁律：外部捕获器必须包装为 ErrorResponse 结构
    """
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        details: Optional[Any] = None,
        recoverable: bool = False
    ) -> None:
        self.code = code
        self.message = message
        self.details = details
        self.recoverable = recoverable
        super().__init__(message)

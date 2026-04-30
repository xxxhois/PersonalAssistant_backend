from typing import Protocol, Optional, Any, Dict
from pydantic import BaseModel, Field
from src.schemas.htn import JsonValue

class ToolExecutionResult(BaseModel):
    """
    工具执行结果标准化 (ToolExecutionResult)
    遵循架构铁律：ToolExecutionResult(data=None, error=None, retryable=False)
    """
    data: Optional[JsonValue] = Field(None, description="成功时的返回数据")
    error: Optional[str] = Field(None, description="错误消息")
    retryable: bool = Field(default=False, description="是否建议重试")

class ToolPort(Protocol):
    """
    MCP 工具调用接口 (ToolPort)
    遵循架构铁律：工具调用必须封装在 adapters/mcp_client.py 中
    """
    async def call_tool(
        self, 
        name: str, 
        arguments: Dict[str, JsonValue]
    ) -> ToolExecutionResult:
        """
        统一调用接口
        name: 工具名，arguments: 参数字典
        """
        ...

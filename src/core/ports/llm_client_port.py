from typing import Protocol, AsyncIterator, Optional, Dict, Any
from pydantic import BaseModel, Field
from src.schemas.htn import JsonValue

class LLMRequest(BaseModel):
    """
    LLM 请求模型 (LLMRequest)
    """
    prompt: str = Field(..., description="LLM 提示词")
    system_prompt: Optional[str] = Field(None, description="系统级指令")
    temperature: float = Field(default=0.7)
    max_tokens: Optional[int] = Field(default=None)
    stop: Optional[list[str]] = Field(default=None)
    tools: Optional[list[dict[str, Any]]] = Field(default=None, description="可选工具定义")

class LLMStreamPort(Protocol):
    """
    LLM 流式调用接口 (LLMStreamPort)
    遵循架构铁律：业务层严禁直接 import openai 等 SDK
    所有调用必须通过此接口
    """
    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """
        流式返回 Token 序列
        Adapter 必须处理重试、超时、错误降级
        """
        ...

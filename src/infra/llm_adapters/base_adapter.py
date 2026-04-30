from typing import AsyncIterator, Optional
from src.core.ports.llm_client_port import LLMStreamPort, LLMRequest

class BaseLLMAdapter(LLMStreamPort):
    """
    LLM 适配器基类
    统一处理：重试（指数退避）、超时（默认 30s）、Chunk 拼接、错误降级
    """
    def __init__(self, provider: str, api_key: str) -> None:
        self.provider = provider
        self.api_key = api_key

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """ Adapter 必须继承基类，实现具体 SDK 调用 """
        # 具体实现由 infra/llm_adapters/xxx_adapter.py 完成
        yield ""

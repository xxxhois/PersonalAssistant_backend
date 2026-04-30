from src.core.ports.llm_client_port import LLMStreamPort
from typing import AsyncIterator

class CompanionService:
    """
    人格化陪伴逻辑
    以心智状态机驱动对话风格与回应策略
    """
    def __init__(self, llm_port: LLMStreamPort) -> None:
        self.llm = llm_port

    async def chat(self, user_input: str) -> AsyncIterator[str]:
        """通过 Prompt Engineering 约束语气、同理心与边界"""
        ...

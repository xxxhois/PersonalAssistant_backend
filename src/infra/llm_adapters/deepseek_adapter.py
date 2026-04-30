from typing import Optional

from src.infra.llm_adapters.openai_compatible_adapter import OpenAICompatibleAdapter


class DeepSeekAdapter(OpenAICompatibleAdapter):
    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        model: str = "deepseek-chat",
    ) -> None:
        super().__init__(
            provider="deepseek",
            api_key=api_key,
            model=model,
            base_url=base_url or "https://api.deepseek.com",
        )

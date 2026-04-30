from typing import Optional

from src.infra.llm_adapters.openai_compatible_adapter import OpenAICompatibleAdapter


class OpenAIAdapter(OpenAICompatibleAdapter):
    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        model: str = "gpt-4o",
    ) -> None:
        super().__init__(
            provider="openai",
            api_key=api_key,
            model=model,
            base_url=base_url,
        )

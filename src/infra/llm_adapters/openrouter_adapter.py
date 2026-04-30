from typing import Optional

from src.infra.llm_adapters.openai_compatible_adapter import OpenAICompatibleAdapter


class OpenRouterAdapter(OpenAICompatibleAdapter):
    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        model: str = "openai/gpt-4o",
        site_url: Optional[str] = None,
        app_name: Optional[str] = None,
    ) -> None:
        headers: dict[str, str] = {}
        if site_url:
            headers["HTTP-Referer"] = site_url
        if app_name:
            headers["X-OpenRouter-Title"] = app_name

        super().__init__(
            provider="openrouter",
            api_key=api_key,
            model=model,
            base_url=base_url or "https://openrouter.ai/api/v1",
            default_headers=headers or None,
        )

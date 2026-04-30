import os
from typing import Dict, Optional

from dotenv import load_dotenv

from src.core.exceptions.app_exception import AppException, ErrorCode
from src.core.ports.llm_client_port import LLMStreamPort
from src.infra.llm_adapters.deepseek_adapter import DeepSeekAdapter
from src.infra.llm_adapters.openai_adapter import OpenAIAdapter
from src.infra.llm_adapters.openrouter_adapter import OpenRouterAdapter

load_dotenv()


class LLMRouter:
    def __init__(self) -> None:
        self._providers: Dict[str, LLMStreamPort] = {}
        self._default_provider_name: Optional[str] = os.getenv("LLM_PROVIDER", "openai")
        self._initialize_from_env()

    def _initialize_from_env(self) -> None:
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            self._providers["openai"] = OpenAIAdapter(
                api_key=openai_key,
                base_url=os.getenv("OPENAI_BASE_URL"),
                model=os.getenv("LLM_MODEL", "gpt-4o"),
            )

        deepseek_key = os.getenv("DEEPSEEK_API_KEY")
        if deepseek_key:
            self._providers["deepseek"] = DeepSeekAdapter(
                api_key=deepseek_key,
                base_url=os.getenv("DEEPSEEK_BASE_URL"),
                model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            )

        openrouter_key = os.getenv("OPENROUTER_API_KEY")
        if openrouter_key:
            self._providers["openrouter"] = OpenRouterAdapter(
                api_key=openrouter_key,
                base_url=os.getenv("OPENROUTER_BASE_URL"),
                model=os.getenv("OPENROUTER_MODEL", "openai/gpt-4o"),
                site_url=os.getenv("OPENROUTER_SITE_URL"),
                app_name=os.getenv("OPENROUTER_APP_NAME"),
            )

    def get_provider(self, name: Optional[str] = None) -> LLMStreamPort:
        provider_name = name or self._default_provider_name
        if not provider_name:
            raise AppException(
                code=ErrorCode.LLM_PROVIDER_ERROR,
                message="No LLM provider name specified or configured in env.",
                recoverable=False,
            )

        provider = self._providers.get(provider_name)
        if not provider:
            raise AppException(
                code=ErrorCode.LLM_PROVIDER_ERROR,
                message=f"LLM provider '{provider_name}' is not configured or missing API key.",
                recoverable=False,
            )

        return provider


llm_router = LLMRouter()

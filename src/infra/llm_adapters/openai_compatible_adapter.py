import asyncio
from typing import AsyncIterator, Optional

from openai import APIError, APITimeoutError, AsyncOpenAI, RateLimitError

from src.core.exceptions.app_exception import AppException, ErrorCode
from src.core.ports.llm_client_port import LLMRequest
from src.infra.llm_adapters.base_adapter import BaseLLMAdapter


class OpenAICompatibleAdapter(BaseLLMAdapter):
    """Reusable adapter for providers exposing an OpenAI-compatible chat API."""

    def __init__(
        self,
        provider: str,
        api_key: str,
        model: str,
        base_url: Optional[str] = None,
        timeout_seconds: float = 30.0,
        default_headers: Optional[dict[str, str]] = None,
    ) -> None:
        super().__init__(provider=provider, api_key=api_key)
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers=default_headers,
        )
        self.model = model
        self.timeout_seconds = timeout_seconds

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        max_retries = 3
        retry_delay = 1.0

        for attempt in range(max_retries):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": request.system_prompt
                            or "You are a helpful assistant.",
                        },
                        {"role": "user", "content": request.prompt},
                    ],
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    stop=request.stop,
                    tools=request.tools,
                    stream=True,
                    timeout=self.timeout_seconds,
                )

                async for chunk in response:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
                return
            except (APITimeoutError, RateLimitError) as exc:
                if attempt == max_retries - 1:
                    raise AppException(
                        code=(
                            ErrorCode.LLM_TIMEOUT
                            if isinstance(exc, APITimeoutError)
                            else ErrorCode.LLM_PROVIDER_ERROR
                        ),
                        message=(
                            f"{self.provider} API error after {max_retries} retries: {exc}"
                        ),
                        recoverable=True,
                    ) from exc
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
            except APIError as exc:
                raise AppException(
                    code=ErrorCode.LLM_PROVIDER_ERROR,
                    message=f"{self.provider} API returned an error: {exc}",
                    recoverable=False,
                ) from exc
            except Exception as exc:
                raise AppException(
                    code=ErrorCode.INTERNAL_ERROR,
                    message=f"Unexpected error in {self.provider} adapter: {exc}",
                    recoverable=False,
                ) from exc

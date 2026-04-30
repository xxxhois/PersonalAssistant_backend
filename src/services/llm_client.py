"""
LLM 客户端包装层
在 OpenAIAdapter 之上再加一层包装，处理 Prompt 构建和请求编排
遵循架构铁律：业务逻辑层不直接导入 openai SDK
"""
import json
from typing import Any, AsyncIterator, Optional

from src.core.exceptions.app_exception import AppException, ErrorCode
from src.core.ports.llm_client_port import LLMRequest, LLMStreamPort
from src.core.prompts.dynamic_prompts import UserContext
from src.core.prompts.prompt_builder import PromptBuilder


class LLMClient:
    """
    LLM 客户端包装类
    负责：
    1. Prompt 构建（通过 PromptBuilder）
    2. 参数验证和转换
    3. 流式调用编排
    """

    def __init__(
        self,
        llm_adapter: LLMStreamPort,
        prompt_builder: PromptBuilder,
    ):
        self.llm_adapter = llm_adapter
        self.prompt_builder = prompt_builder

    async def chat_stream(
        self,
        user_message: str,
        user_context: UserContext,
        memory_chunks: Optional[list[str]] = None,
        task_type: str = "general",
    ) -> AsyncIterator[str]:
        try:
            llm_request = self.prompt_builder.build_chat_request(
                user_message=user_message,
                user_context=user_context,
                memory_chunks=memory_chunks,
                task_type=task_type,
            )

            async for token in self.llm_adapter.stream(llm_request):
                yield token

        except AppException:
            raise
        except Exception as e:
            raise AppException(
                code=ErrorCode.INTERNAL_ERROR,
                message=f"LLMClient error: {str(e)}",
                recoverable=False,
            ) from e

    async def analyze_emotion(self, text: str) -> dict[str, Any]:
        try:
            llm_request = self.prompt_builder.build_system_analysis_request(
                analysis_target=text,
                analysis_type="emotion",
            )
            response = await self._collect_response(llm_request)
            return json.loads(response)
        except json.JSONDecodeError:
            return {
                "emotion": "neutral",
                "intensity": 5,
                "reasoning": "Failed to parse response",
            }
        except Exception as e:
            raise AppException(
                code=ErrorCode.LLM_PROVIDER_ERROR,
                message=f"Emotion analysis failed: {str(e)}",
                recoverable=True,
            ) from e

    async def analyze_intent(self, text: str) -> dict[str, Any]:
        try:
            llm_request = self.prompt_builder.build_system_analysis_request(
                analysis_target=text,
                analysis_type="intent",
            )
            response = await self._collect_response(llm_request)
            return json.loads(response)
        except Exception as e:
            raise AppException(
                code=ErrorCode.LLM_PROVIDER_ERROR,
                message=f"Intent analysis failed: {str(e)}",
                recoverable=True,
            ) from e

    async def summarize(self, text: str, style: str = "concise") -> str:
        try:
            llm_request = self.prompt_builder.build_summarization_request(
                text=text,
                summary_style=style,
            )
            return await self._collect_response(llm_request)
        except Exception as e:
            raise AppException(
                code=ErrorCode.LLM_PROVIDER_ERROR,
                message=f"Summarization failed: {str(e)}",
                recoverable=True,
            ) from e

    async def generate_json(
        self,
        prompt: str,
        system_prompt: str,
        temperature: float = 0.4,
        max_tokens: int = 1200,
    ) -> dict[str, Any]:
        request = self.prompt_builder.build_raw_request(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        response = await self._collect_response(request)
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            parsed = self._extract_json_object(response)
            if parsed is None:
                raise AppException(
                    code=ErrorCode.LLM_PROVIDER_ERROR,
                    message="LLM did not return valid JSON",
                    details=response,
                    recoverable=True,
                )
            return parsed

    async def _collect_response(self, request: LLMRequest) -> str:
        response = ""
        async for chunk in self.llm_adapter.stream(request):
            response += chunk
        return response

    def _extract_json_object(self, response: str) -> Optional[dict[str, Any]]:
        start = response.find("{")
        end = response.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            parsed = json.loads(response[start : end + 1])
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

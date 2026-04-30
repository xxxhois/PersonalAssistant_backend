import asyncio
import uuid
from typing import AsyncIterator, Optional, List
from src.core.ports.llm_client_port import LLMStreamPort, LLMRequest
from src.core.ports.task_port import TaskPort
from src.core.ports.memory_port import MemoryPort
from src.core.prompts.prompt_builder import PromptBuilder
from src.core.prompts.dynamic_prompts import UserContext
from src.services.llm_client import LLMClient
from src.services.companion import CompanionService
from src.parsers.shadow_parser import ShadowParser
from src.schemas.sse import SSEFrame, SSEEventType
from src.schemas.htn import JsonValue
from src.core.exceptions.app_exception import AppException, ErrorCode

class Orchestrator:
    """
    编排层实现 (Orchestrator)
    职责：
    1. 检索记忆上下文
    2. 分析用户意图
    3. 通过 LLMClient 构建和调用 LLM
    4. 解析响应并生成 SSE 事件
    5. 任务提取和持久化
    
    遵循架构约束：仅通过 Ports 交互，实现状态机流转与 SSE 事件生成
    """
    def __init__(
        self,
        llm_port: LLMStreamPort,
        task_port: TaskPort,
        memory_port: MemoryPort
    ) -> None:
        self.llm_adapter = llm_port
        self.task_port = task_port
        self.memory_port = memory_port
        
        # 初始化 Prompt 构建器和 LLM 客户端
        self.prompt_builder = PromptBuilder()
        self.llm_client = LLMClient(
            llm_adapter=llm_port,
            prompt_builder=self.prompt_builder
        )
        self.companion_service = CompanionService(
            llm_client=self.llm_client,
            memory_port=memory_port,
        )

    async def chat_stream(
        self, 
        user_id: str, 
        user_input: str,
        request_id: str
    ) -> AsyncIterator[SSEFrame]:
        """
        处理对话流，产生 SSEFrame 序列
        
        流程：
        1. 构建用户上下文 -> 2. 检索记忆 -> 3. 分析意图 
        4. LLMClient 自动构建 Prompt -> 5. 流式调用 LLM 
        6. 解析 Chunk -> 7. 生成 SSE 事件
        """
        parser = ShadowParser()
        seq = 0

        try:
            # CompanionService owns persona, memory, and mental-state prompt shaping.
            async for chunk in self.companion_service.chat_stream(
                user_id=user_id,
                user_input=user_input,
            ):
                # 步骤 6：解析 Chunk（提取任务、标记等）
                events = parser.feed(chunk)
                
                # 步骤 7：发送解析出的事件
                for event_type, data in events:
                    seq += 1
                    yield self._create_frame(request_id, seq, event_type, data)

            # 4. 刷新 Parser Buffer
            for event_type, data in parser.flush():
                seq += 1
                yield self._create_frame(request_id, seq, event_type, data)

            # 5. 发送完成标志
            seq += 1
            yield self._create_frame(request_id, seq, SSEEventType.DONE, {"request_id": request_id})

        except AppException as e:
            # 捕获业务异常并转为 SSE Error
            seq += 1
            yield self._create_frame(
                request_id, 
                seq, 
                SSEEventType.ERROR, 
                {"code": e.code.value, "message": e.message},
                recoverable=e.recoverable
            )
        except Exception as e:
            # 捕获未知异常
            seq += 1
            yield self._create_frame(
                request_id, 
                seq, 
                SSEEventType.ERROR, 
                {"code": ErrorCode.INTERNAL_ERROR.value, "message": str(e)},
                recoverable=False
            )
    
    # === 私有辅助方法 ===
    
    async def _build_user_context(self, user_id: str) -> UserContext:
        """
        构建用户上下文
        从数据库检索用户信息、历史对话数、偏好等
        
        TODO: 从真实数据源加载用户信息
        """
        return UserContext(
            user_id=user_id,
            user_name=f"User_{user_id}",
            emotional_state=None,
            conversation_history_count=0,
            goals=None,
            preferences={"preferred_length": "medium"}
        )
    
    async def _retrieve_memory_context(self, query: str) -> List[str]:
        """
        从记忆中检索相关上下文
        检索失败不中断流程
        """
        try:
            context = await self.memory_port.query_context(query, limit=3)
            return [c.content for c in context]
        except Exception as e:
            # 记忆检索失败不中断流，但应记录日志
            print(f"[WARNING] Memory retrieval failed: {e}")
            return []
    
    async def _analyze_intent(self, text: str) -> str:
        """
        分析用户意图以优化 Prompt
        意图类型：planning, advice, brainstorming, problem_solving, reflection, general
        
        失败时返回 "general" 作为默认值
        """
        try:
            result = await self.llm_client.analyze_intent(text)
            return result.get("intent", "general")
        except Exception as e:
            print(f"[WARNING] Intent analysis failed: {e}")
            return "general"

    def _create_frame(
        self, 
        request_id: str, 
        seq: int, 
        event: SSEEventType, 
        data: JsonValue,
        recoverable: Optional[bool] = None
    ) -> SSEFrame:
        """创建统一格式的 SSEFrame"""
        return SSEFrame(
            id=f"{event.value}_{seq}",
            event=event,
            data=data,
            request_id=request_id,
            seq=seq,
            recoverable=recoverable
        )

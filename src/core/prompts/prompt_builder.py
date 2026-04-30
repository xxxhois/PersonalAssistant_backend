"""
Prompt 构建器（高级编排）
负责组装最终的 LLMRequest，将系统提示、动态上下文、用户消息整合
"""
from typing import Optional, List
from src.core.ports.llm_client_port import LLMRequest
from src.core.prompts.system_prompts import SystemPrompts, PersonalityType, SYSTEM_PROMPT_TEMPLATES
from src.core.prompts.dynamic_prompts import DynamicPromptBuilder, UserContext


class PromptBuilder:
    """
    核心 Prompt 构建器
    遵循架构铁律：所有 LLMRequest 必须通过此类创建
    """
    
    def __init__(
        self,
        personality: PersonalityType = PersonalityType.BALANCED,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ):
        """
        初始化 Prompt 构建器
        
        Args:
            personality: 人格类型
            temperature: 温度参数
            max_tokens: 最大 Token 数
        """
        self.personality = personality
        self.temperature = temperature
        self.max_tokens = max_tokens
    
    def build_chat_request(
        self,
        user_message: str,
        user_context: UserContext,
        memory_chunks: Optional[List[str]] = None,
        task_type: str = "general",
        custom_system_prompt: Optional[str] = None,
    ) -> LLMRequest:
        """
        构建聊天请求（标准调用）
        
        Args:
            user_message: 用户消息
            user_context: 用户上下文
            memory_chunks: 从记忆中检索的相关信息
            task_type: 任务类型，用于调整 Prompt 风格
            custom_system_prompt: 自定义系统提示（覆盖默认值）
        
        Returns:
            LLMRequest 对象
        """
        # 步骤 1：获取或自定义系统提示
        system_prompt = custom_system_prompt or SYSTEM_PROMPT_TEMPLATES.get(
            self.personality.value,
            SYSTEM_PROMPT_TEMPLATES["balanced"]
        )
        
        # 步骤 2：构建用户上下文摘要
        context_summary = DynamicPromptBuilder.build_user_context_summary(
            user_context,
            memory_chunks or []
        )
        
        # 步骤 3：构建最终的用户 Prompt
        if context_summary:
            user_prompt = f"{context_summary}\n\n---\n\n{user_message}"
        else:
            user_prompt = user_message
        
        # 步骤 4：根据情感状态动态调整
        system_prompt = DynamicPromptBuilder.inject_constraints_based_on_context(
            system_prompt,
            user_context
        )
        
        # 步骤 5：创建 LLMRequest
        return LLMRequest(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stop=["<!--TASK_END-->"],  # 任务标记结束符
        )
    
    def build_system_analysis_request(
        self,
        analysis_target: str,
        analysis_type: str,  # "emotion", "intent", "priority", "feasibility"
        custom_instructions: Optional[str] = None,
    ) -> LLMRequest:
        """
        构建系统分析请求
        用于对用户输入进行特殊分析
        
        Args:
            analysis_target: 分析对象（通常是用户消息）
            analysis_type: 分析类型
            custom_instructions: 自定义分析指令
        
        Returns:
            LLMRequest 对象
        """
        analysis_instructions = {
            "emotion": (
                "Analyze the emotional tone and sentiment of the following text. "
                "Return a JSON object with: {\"emotion\": \"happy|sad|angry|neutral|anxious|...\", \"intensity\": 0-10, \"reasoning\": \"...\"}"
            ),
            "intent": (
                "Analyze the user's intent. "
                "Return a JSON object with: {\"intent\": \"planning|advice|brainstorming|problem_solving|reflection|other\", \"confidence\": 0-1}"
            ),
            "priority": (
                "Assess the priority/urgency of the user's request. "
                "Return a JSON object with: {\"priority\": \"high|medium|low\", \"reasoning\": \"...\"}"
            ),
            "feasibility": (
                "Assess the feasibility of what the user is asking for. "
                "Return a JSON object with: {\"feasibility\": \"easy|moderate|difficult|impossible\", \"obstacles\": [...], \"suggestions\": [...]}"
            ),
        }
        
        instruction = custom_instructions or analysis_instructions.get(
            analysis_type,
            "Analyze the following and provide structured output as JSON."
        )
        
        return LLMRequest(
            prompt=f"{instruction}\n\nText to analyze:\n{analysis_target}",
            system_prompt=(
                "You are an analytical assistant. "
                "Always respond with valid JSON output only, no additional text."
            ),
            temperature=0.3,  # 低温度，确保一致的分析结果
            max_tokens=500,
        )
    
    def build_summarization_request(
        self,
        text: str,
        summary_style: str = "concise",  # "concise", "detailed", "bullet_points"
    ) -> LLMRequest:
        """
        构建摘要请求
        
        Args:
            text: 要摘要的文本
            summary_style: 摘要风格
        
        Returns:
            LLMRequest 对象
        """
        style_instructions = {
            "concise": "Provide a brief, one-paragraph summary.",
            "detailed": "Provide a comprehensive summary with key points and context.",
            "bullet_points": "Provide a bullet-point summary with the main ideas.",
        }
        
        instruction = style_instructions.get(summary_style, style_instructions["concise"])
        
        return LLMRequest(
            prompt=f"{instruction}\n\nText to summarize:\n{text}",
            system_prompt="You are a summarization expert.",
            temperature=0.3,
            max_tokens=500,
        )

    def build_raw_request(
        self,
        prompt: str,
        system_prompt: str,
        temperature: float = 0.4,
        max_tokens: int = 1200,
    ) -> LLMRequest:
        """Build a direct structured request for specialized workflows."""
        return LLMRequest(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

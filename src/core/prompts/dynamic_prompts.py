"""
动态 Prompt 生成器
根据运行时上下文（用户历史、情感状态、任务类型等）动态生成用户 Prompt
"""
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime


@dataclass
class UserContext:
    """用户上下文信息"""
    user_id: str
    user_name: Optional[str] = None
    emotional_state: Optional[str] = None  # "happy", "sad", "stressed", etc.
    conversation_history_count: int = 0
    last_interaction: Optional[datetime] = None
    goals: Optional[List[str]] = None
    preferences: Optional[Dict[str, Any]] = None


class DynamicPromptBuilder:
    """
    动态 Prompt 构建器
    根据用户信息和上下文实时生成或调整 Prompt
    """
    
    @staticmethod
    def build_user_context_summary(context: UserContext, memory_chunks: List[str]) -> str:
        """
        构建用户上下文摘要
        用于插入到 Prompt 中提供背景信息
        
        Args:
            context: 用户上下文
            memory_chunks: 从记忆中检索的相关信息
        
        Returns:
            格式化的上下文摘要
        """
        summary_parts = []
        
        # 添加用户识别信息
        if context.user_name:
            summary_parts.append(f"User: {context.user_name}")
        
        # 添加情感状态（如可用）
        if context.emotional_state:
            summary_parts.append(f"Current mood/context: {context.emotional_state}")
        
        # 添加用户目标（如可用）
        if context.goals:
            goals_str = ", ".join(context.goals)
            summary_parts.append(f"User's goals: {goals_str}")
        
        # 添加记忆上下文
        if memory_chunks:
            memory_text = "\n".join([f"- {chunk}" for chunk in memory_chunks])
            summary_parts.append(f"Relevant context from past:\n{memory_text}")
        
        return "\n".join(summary_parts) if summary_parts else ""
    
    @staticmethod
    def build_task_specific_prompt(
        task_type: str,
        user_message: str,
        memory_context: str
    ) -> str:
        """
        构建特定任务类型的 Prompt
        
        Args:
            task_type: 任务类型，如 "planning", "advice", "brainstorming", "problem-solving"
            user_message: 用户消息
            memory_context: 记忆上下文摘要
        
        Returns:
            完整的用户 Prompt
        """
        task_instructions = {
            "planning": (
                "The user is asking for help with planning or organizing. "
                "Please provide a structured plan with clear steps and timeline."
            ),
            "advice": (
                "The user is seeking advice or guidance. "
                "Provide thoughtful, balanced advice considering multiple perspectives."
            ),
            "brainstorming": (
                "The user wants to brainstorm ideas. "
                "Generate creative, diverse ideas and encourage exploration."
            ),
            "problem_solving": (
                "The user is facing a problem. "
                "Help them analyze the problem and develop practical solutions."
            ),
            "reflection": (
                "The user wants to reflect on something. "
                "Ask insightful questions and help them gain clarity."
            ),
        }
        
        task_instruction = task_instructions.get(task_type, "")
        
        prompt_parts = []
        
        if memory_context:
            prompt_parts.append(f"CONTEXT:\n{memory_context}\n")
        
        if task_instruction:
            prompt_parts.append(f"TASK GUIDANCE:\n{task_instruction}\n")
        
        prompt_parts.append(f"USER MESSAGE:\n{user_message}")
        
        return "\n".join(prompt_parts)
    
    @staticmethod
    def inject_constraints_based_on_context(
        base_prompt: str,
        user_context: UserContext
    ) -> str:
        """
        根据用户状态动态注入约束条件
        
        Args:
            base_prompt: 基础 Prompt
            user_context: 用户上下文
        
        Returns:
            增强的 Prompt
        """
        injections = []
        
        # 如果用户处于压力状态，提醒要更温和
        if user_context.emotional_state and "stress" in user_context.emotional_state.lower():
            injections.append("\nNOTE: User may be stressed. Be extra supportive and validate their feelings.")
        
        # 如果是新用户，提供更多上下文
        if user_context.conversation_history_count == 0:
            injections.append("\nNOTE: This is the user's first message. Introduce yourself briefly.")
        
        return base_prompt + "".join(injections)

from typing import AsyncIterator, Optional

from src.core.ports.memory_port import MemoryPort
from src.core.ports.task_port import TaskPort
from src.core.prompts.dynamic_prompts import UserContext
from src.core.prompts.persona_profiles import PersonaId, get_persona_profile
from src.core.prompts.system_prompts import SystemPrompts
from src.schemas.htn import HTNPlan
from src.services.llm_client import LLMClient
from src.services.memory_service import MemoryService
from src.services.mental_state import MentalStateMachine


class ProactiveCompanionService:
    """
    Persona-aware proactive outreach.

    Unlike normal companion chat, proactive outreach may read the user's active goal
    and decomposed tasks. It still does not create or mutate plans.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        memory_port: MemoryPort,
        task_port: TaskPort,
        persona_id: PersonaId = PersonaId.MARLOWE_NOIR,
        mental_state_machine: Optional[MentalStateMachine] = None,
    ) -> None:
        self.llm_client = llm_client
        self.memory_service = MemoryService(memory_port)
        self.task_port = task_port
        self.persona_id = persona_id
        self.mental_state_machine = mental_state_machine or MentalStateMachine()

    async def outreach_stream(
        self,
        user_id: str,
        trigger_reason: str,
    ) -> AsyncIterator[str]:
        active_plan = await self.task_port.get_active_plan(user_id)
        memories = await self.memory_service.retrieve_for_companion(
            user_id=user_id,
            query=trigger_reason,
            limit=3,
        )
        mental_state = self.mental_state_machine.evaluate(trigger_reason, memories)
        plan_context = self._format_plan_context(active_plan)

        user_message = (
            f"Trigger reason: {trigger_reason}\n\n"
            f"Active goal and tasks:\n{plan_context}\n\n"
            "Write a short proactive companion message. It should feel useful, not noisy."
        )

        persona = get_persona_profile(self.persona_id)
        async for token in self.llm_client.chat_stream(
            user_message=user_message,
            user_context=UserContext(
                user_id=user_id,
                user_name=f"User_{user_id}",
                emotional_state=mental_state.state.value,
                conversation_history_count=1,
                preferences={"persona": self.persona_id.value},
            ),
            memory_chunks=[chunk.content for chunk in memories],
            task_type="proactive_companion",
            custom_system_prompt=(
                f"{persona.system_instruction}\n\n"
                f"{SystemPrompts.get_behavior_constraints()}\n\n"
                "PROACTIVE OUTREACH RULES:\n"
                "Use the active goal and decomposed tasks as grounding. Do not create new "
                "plans, change task status, or pretend the user asked a new question. Keep "
                "the message brief and easy to ignore."
            ),
        ):
            yield token

    def _format_plan_context(self, plan: Optional[HTNPlan]) -> str:
        if plan is None:
            return "No active plan is available."

        task_lines = []
        for task in plan.tasks[:8]:
            schedule = (
                f"{task.metadata.get('scheduled_date') or ''} "
                f"{task.metadata.get('scheduled_time') or ''}"
            ).strip()
            task_lines.append(f"- {task.title} [{task.status.value}] {schedule}".strip())
        tasks = "\n".join(task_lines) if task_lines else "- No tasks in active plan."
        extra = plan.model_extra or {}
        return f"Goal: {plan.goal}\nSummary: {extra.get('goal_summary', '')}\n{tasks}"

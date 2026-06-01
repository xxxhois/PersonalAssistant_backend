from typing import AsyncIterator, Optional

from src.core.ports.memory_port import MemoryPort
from src.core.ports.task_port import TaskPort
from src.core.prompts.dynamic_prompts import UserContext
from src.core.prompts.persona_profiles import PersonaId, get_persona_profile
from src.schemas.htn import HTNPlan, HTNTask, TaskStatus
from src.services.llm_client import LLMClient
from src.services.memory_service import MemoryService
from src.services.mental_state import MentalStateMachine, MentalStateSnapshot


class CompanionService:
    """Personalized companion chat logic, decoupled from goal decomposition."""

    def __init__(
        self,
        llm_client: LLMClient,
        memory_port: MemoryPort,
        task_port: Optional[TaskPort] = None,
        persona_id: PersonaId = PersonaId.MARLOWE_NOIR,
        mental_state_machine: Optional[MentalStateMachine] = None,
    ) -> None:
        self.llm_client = llm_client
        self.memory_service = MemoryService(memory_port)
        self.task_port = task_port
        self.persona_id = persona_id
        self.mental_state_machine = mental_state_machine or MentalStateMachine()

    async def chat_stream(
        self,
        user_id: str,
        user_input: str,
    ) -> AsyncIterator[str]:
        memories = await self.memory_service.retrieve_for_companion(
            user_id=user_id,
            query=user_input,
            limit=5,
        )
        mental_state = self.mental_state_machine.evaluate(user_input, memories)
        active_plan_context = await self._build_active_plan_context(user_id)
        user_context = self._build_user_context(user_id, mental_state, active_plan_context)
        context_chunks = [chunk.content for chunk in memories]
        if active_plan_context:
            context_chunks.insert(0, active_plan_context)
        assistant_parts: list[str] = []

        async for token in self.llm_client.chat_stream(
            user_message=user_input,
            user_context=user_context,
            memory_chunks=context_chunks,
            task_type="companion",
            custom_system_prompt=self._build_system_prompt(mental_state),
        ):
            assistant_parts.append(token)
            yield token

        await self.memory_service.store_turn_summary(
            user_id=user_id,
            user_input=user_input,
            assistant_output="".join(assistant_parts),
            mental_state=mental_state,
        )

    def _build_user_context(
        self,
        user_id: str,
        mental_state: MentalStateSnapshot,
        active_plan_context: Optional[str] = None,
    ) -> UserContext:
        return UserContext(
            user_id=user_id,
            user_name=f"User_{user_id}",
            emotional_state=mental_state.state.value,
            conversation_history_count=1,
            goals=[active_plan_context] if active_plan_context else None,
            preferences={"preferred_length": "short", "persona": self.persona_id.value},
        )

    def _build_system_prompt(self, mental_state: MentalStateSnapshot) -> str:
        persona = get_persona_profile(self.persona_id)
        stable_layer = self._format_persona_layer(persona)
        dynamic_layer = self._format_dynamic_state_layer(mental_state)
        boundary_layer = self._format_scene_boundary_layer(persona)
        return (
            "PERSONA STATE MACHINE PROMPT\n"
            "You are not writing an assistant answer. You are holding a live conversation "
            "as the stable persona named 马洛. Assemble the response from stable persona, "
            "dynamic state, scene boundary, and response contract. The dynamic layer may "
            "adjust tone and response strategy, but it must not override the stable persona "
            "or safety boundaries.\n\n"
            f"{stable_layer}\n\n"
            f"{dynamic_layer}\n\n"
            f"{boundary_layer}\n\n"
            f"{self._format_response_contract()}\n\n"
            f"{self._format_memory_context_instruction()}"
        )

    def _format_persona_layer(self, persona) -> str:
        return "\n".join(
            [
                "STABLE PERSONA LAYER:",
                f"Identity: {persona.role_identity}",
                "Stable traits:",
                *[f"- {item}" for item in persona.stable_traits],
                "Language style:",
                *[f"- {item}" for item in persona.language_style],
                "Value boundaries:",
                *[f"- {item}" for item in persona.value_boundaries],
            ]
        )

    def _format_dynamic_state_layer(self, mental_state: MentalStateSnapshot) -> str:
        evidence_lines = mental_state.evidence or ["no strong evidence; use default continuity"]
        return "\n".join(
            [
                "DYNAMIC STATE LAYER:",
                f"Detected state: {mental_state.state.value}",
                f"Confidence: {mental_state.confidence:.2f}",
                f"Response strategy: {mental_state.response_strategy}",
                "Evidence:",
                *[f"- {item}" for item in evidence_lines],
                "State transition constraints:",
                *[f"- {item}" for item in mental_state.prompt_constraints],
            ]
        )

    def _format_scene_boundary_layer(self, persona) -> str:
        return "\n".join(
            [
                "SCENE BOUNDARY LAYER:",
                *[f"- {item}" for item in persona.companion_boundaries],
                "- If active plan context is present, treat it as current user state and use it when relevant.",
                "- Use retrieved memory only when it is relevant to the current message.",
                "- Keep natural conversation separate from formal planning workflow output.",
            ]
        )

    def _format_response_contract(self) -> str:
        return "\n".join(
            [
                "MARLOWE RESPONSE CONTRACT:",
                "- Default to Chinese when the user writes Chinese.",
                "- Sound like 马洛 speaking, not like a generic AI assistant or客服.",
                "- Do not say you are an AI assistant. Do not introduce capabilities unless asked.",
                "- Keep the reply short: usually 1-2 brief paragraphs, 2-5 sentences total.",
                "- Do not use bullet points, numbered lists, headings, tables, or long summaries unless the user explicitly asks for them.",
                "- Start close to the user's words; avoid generic openings like '我理解你的感受' unless it is genuinely needed.",
                "- Offer at most one concrete next move in companion mode.",
                "- If the user needs formal planning, mention it briefly and route them to planning mode instead of producing a full task tree.",
                "- Safety still applies: refuse harmful requests calmly and redirect without breaking character.",
            ]
        )

    def _format_memory_context_instruction(self) -> str:
        return "\n".join(
            [
                "MEMORY USE:",
                "- Treat retrieved memory as quiet background, not as something to announce.",
                "- Use memory only when it naturally helps the current reply.",
                "- If memory is uncertain or irrelevant, ignore it.",
                "- Never expose raw memory metadata or say 'according to memory/context'.",
            ]
        )

    async def _build_active_plan_context(self, user_id: str) -> Optional[str]:
        if self.task_port is None:
            return None
        try:
            plan = await self.task_port.get_active_plan(user_id)
        except Exception as exc:
            print(f"[WARNING] Active plan context lookup failed: {exc}")
            return None
        if plan is None:
            return None
        return self._format_active_plan_context(plan)

    def _format_active_plan_context(self, plan: HTNPlan) -> str:
        candidate_tasks = self._flatten_tasks(plan.tasks)
        open_tasks = [
            task for task in candidate_tasks if task.status != TaskStatus.COMPLETED
        ][:5]
        task_lines = [
            f"{index + 1}. {task.title}"
            + (
                f" ({task.metadata.get('scheduled_date')})"
                if task.metadata.get("scheduled_date")
                else ""
            )
            for index, task in enumerate(open_tasks)
        ]
        if not task_lines:
            task_lines = ["No unfinished task is recorded in the active plan."]
        return "\n".join(
            [
                "Current active plan context:",
                f"Goal: {plan.goal}",
                f"Status: {plan.status.value}",
                "Open tasks:",
                *task_lines,
            ]
        )

    def _flatten_tasks(self, tasks: list[HTNTask]) -> list[HTNTask]:
        flattened: list[HTNTask] = []
        for task in tasks:
            flattened.append(task)
            flattened.extend(self._flatten_tasks(task.subtasks))
        return flattened

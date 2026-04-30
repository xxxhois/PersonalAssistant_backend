from typing import AsyncIterator, Optional

from src.core.ports.memory_port import MemoryPort
from src.core.prompts.dynamic_prompts import UserContext
from src.core.prompts.persona_profiles import PersonaId, get_persona_profile
from src.core.prompts.system_prompts import SystemPrompts
from src.services.llm_client import LLMClient
from src.services.memory_service import MemoryService
from src.services.mental_state import MentalStateMachine, MentalStateSnapshot


class CompanionService:
    """Personalized companion chat logic, decoupled from goal decomposition."""

    def __init__(
        self,
        llm_client: LLMClient,
        memory_port: MemoryPort,
        persona_id: PersonaId = PersonaId.MARLOWE_NOIR,
        mental_state_machine: Optional[MentalStateMachine] = None,
    ) -> None:
        self.llm_client = llm_client
        self.memory_service = MemoryService(memory_port)
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
        user_context = self._build_user_context(user_id, mental_state)
        assistant_parts: list[str] = []

        async for token in self.llm_client.chat_stream(
            user_message=user_input,
            user_context=user_context,
            memory_chunks=[chunk.content for chunk in memories],
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
    ) -> UserContext:
        return UserContext(
            user_id=user_id,
            user_name=f"User_{user_id}",
            emotional_state=mental_state.state.value,
            conversation_history_count=1,
            goals=None,
            preferences={"preferred_length": "medium", "persona": self.persona_id.value},
        )

    def _build_system_prompt(self, mental_state: MentalStateSnapshot) -> str:
        persona = get_persona_profile(self.persona_id)
        state_lines = "\n".join(
            f"- {constraint}" for constraint in mental_state.prompt_constraints
        )
        return (
            f"{persona.system_instruction}\n\n"
            f"{SystemPrompts.get_behavior_constraints()}\n\n"
            f"{SystemPrompts.get_memory_context_instruction()}\n\n"
            "COMPANION MODE BOUNDARY:\n"
            "This route is for conversation, emotional support, reflection, and proactive "
            "companion messaging. Do not decompose big goals into formal task trees here. "
            "If the user asks for formal goal decomposition, briefly tell them this should "
            "go through planning mode.\n\n"
            "MENTAL STATE GUIDANCE:\n"
            f"Detected state: {mental_state.state.value} "
            f"(confidence {mental_state.confidence:.2f}).\n"
            f"{state_lines}"
        )

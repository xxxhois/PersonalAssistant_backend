from datetime import datetime, timezone
from uuid import uuid4

from src.core.ports.memory_port import MemoryChunk, MemoryPort
from src.services.mental_state import MentalStateSnapshot


class MemoryService:
    """Companion memory policy over a MemoryPort."""

    def __init__(self, memory_port: MemoryPort) -> None:
        self.memory_port = memory_port

    async def retrieve_for_companion(
        self,
        user_id: str,
        query: str,
        limit: int = 5,
    ) -> list[MemoryChunk]:
        return await self.memory_port.query_context(
            query=query,
            limit=limit,
            filters={"user_id": user_id, "scope": "companion"},
        )

    async def store_turn_summary(
        self,
        user_id: str,
        user_input: str,
        assistant_output: str,
        mental_state: MentalStateSnapshot,
    ) -> None:
        candidate = self._classify_memory_candidate(user_input, mental_state)
        if candidate is None:
            return

        content = self._build_turn_memory(user_input, assistant_output, candidate)
        if not content:
            return

        now = datetime.now(timezone.utc).isoformat()
        await self.memory_port.store(
            MemoryChunk(
                content=content,
                metadata={
                    "id": str(uuid4()),
                    "user_id": user_id,
                    "scope": "companion",
                    "memory_type": candidate["memory_type"],
                    "mental_state": mental_state.state.value,
                    "importance": candidate["importance"],
                    "created_at": now,
                    "source": "chat",
                    "selection_reason": candidate["reason"],
                },
                score=0.0,
            )
        )

    def _classify_memory_candidate(
        self,
        user_input: str,
        mental_state: MentalStateSnapshot,
    ) -> dict[str, object] | None:
        text = user_input.strip()
        lowered = text.lower()
        if len(text) < 8:
            return None

        explicit_memory_words = ("记住", "remember", "以后", "别忘", "提醒我")
        preference_words = ("喜欢", "讨厌", "偏好", "prefer", "hate", "like")
        goal_words = ("目标", "计划", "毕业", "项目", "答辩", "goal", "project")

        if any(word in lowered for word in explicit_memory_words):
            return {
                "memory_type": "fact",
                "importance": 0.85,
                "reason": "explicit_memory_request",
            }
        if any(word in lowered for word in preference_words):
            return {
                "memory_type": "preference",
                "importance": 0.75,
                "reason": "user_preference",
            }
        if any(word in lowered for word in goal_words):
            return {
                "memory_type": "project_context",
                "importance": 0.7,
                "reason": "goal_or_project_context",
            }
        if mental_state.state.value != "neutral" and mental_state.confidence >= 0.65:
            return {
                "memory_type": "emotion",
                "importance": 0.65,
                "reason": "salient_mental_state",
            }
        return None

    def _build_turn_memory(
        self,
        user_input: str,
        assistant_output: str,
        candidate: dict[str, object],
    ) -> str:
        user_text = user_input.strip()
        if len(user_text) < 8:
            return ""
        memory_type = str(candidate["memory_type"])
        reason = str(candidate["reason"])
        if memory_type in {"preference", "fact", "project_context"}:
            return f"User memory ({memory_type}, {reason}): {user_text}"

        assistant_text = assistant_output.strip().replace("\n", " ")
        if len(assistant_text) > 240:
            assistant_text = assistant_text[:237] + "..."
        return f"Emotional episode ({reason}): user said: {user_text}\nAssistant replied: {assistant_text}"

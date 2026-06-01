from datetime import datetime, timezone
from difflib import SequenceMatcher
from uuid import uuid4

from src.core.ports.memory_port import MemoryChunk, MemoryPort
from src.services.mental_state import MentalStateSnapshot


class MemoryService:
    """Companion memory policy over a MemoryPort."""

    MAX_CONTEXT_CHARS = 1200
    DUPLICATE_SIMILARITY_THRESHOLD = 0.72
    SEMANTIC_DUPLICATE_THRESHOLD = 0.66

    def __init__(self, memory_port: MemoryPort) -> None:
        self.memory_port = memory_port

    async def retrieve_for_companion(
        self,
        user_id: str,
        query: str,
        limit: int = 5,
    ) -> list[MemoryChunk]:
        if not self._should_retrieve(query):
            return []

        chunks = await self.memory_port.query_context(
            query=query,
            limit=limit,
            filters={"user_id": user_id, "scope": "companion"},
        )
        return self._fit_context_budget(chunks, max_chars=self.MAX_CONTEXT_CHARS)

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
        existing = await self._find_existing_memory(
            user_id=user_id,
            content=content,
            memory_type=str(candidate["memory_type"]),
        )
        metadata = {
            "id": str(uuid4()),
            "user_id": user_id,
            "scope": "companion",
            "memory_type": candidate["memory_type"],
            "mental_state": mental_state.state.value,
            "importance": candidate["importance"],
            "created_at": now,
            "updated_at": now,
            "source": "chat",
            "selection_reason": candidate["reason"],
            "write_policy": "insert",
        }
        if existing is not None:
            metadata.update(existing.metadata)
            metadata.update(
                {
                    "id": str(existing.metadata.get("id") or existing.metadata.get("memory_id")),
                    "user_id": user_id,
                    "scope": "companion",
                    "memory_type": candidate["memory_type"],
                    "mental_state": mental_state.state.value,
                    "importance": max(
                        self._as_float(existing.metadata.get("importance"), 0.5),
                        self._as_float(candidate["importance"], 0.5),
                    ),
                    "updated_at": now,
                    "source": "chat",
                    "selection_reason": candidate["reason"],
                    "write_policy": "update",
                    "previous_content": existing.content[:500],
                }
            )

        await self.memory_port.store(
            MemoryChunk(
                content=content,
                metadata=metadata,
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
        goal_words = (
            "目标",
            "计划",
            "毕业",
            "毕设",
            "论文",
            "题目",
            "项目",
            "答辩",
            "goal",
            "project",
            "thesis",
            "topic",
            "title",
        )

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

    async def _find_existing_memory(
        self,
        user_id: str,
        content: str,
        memory_type: str,
    ) -> MemoryChunk | None:
        try:
            candidates = await self.memory_port.query_context(
                query=content,
                limit=3,
                filters={
                    "user_id": user_id,
                    "scope": "companion",
                    "memory_type": memory_type,
                },
            )
        except Exception as exc:
            print(f"[WARNING] Memory duplicate check failed; inserting new memory: {exc}")
            return None

        best_candidate: MemoryChunk | None = None
        best_score = 0.0
        normalized_content = self._normalize_text(content)
        for candidate in candidates:
            semantic_score = self._as_float(
                candidate.metadata.get("semantic_score"),
                candidate.score,
            )
            text_score = SequenceMatcher(
                None,
                normalized_content,
                self._normalize_text(candidate.content),
            ).ratio()
            duplicate_score = max(semantic_score, text_score)
            if duplicate_score > best_score:
                best_score = duplicate_score
                best_candidate = candidate

        if best_candidate is None:
            return None
        if best_score >= self.DUPLICATE_SIMILARITY_THRESHOLD:
            return best_candidate
        if self._as_float(best_candidate.metadata.get("semantic_score"), 0.0) >= (
            self.SEMANTIC_DUPLICATE_THRESHOLD
        ):
            return best_candidate
        return None

    def _normalize_text(self, value: str) -> str:
        return " ".join(value.lower().strip().split())

    def _as_float(self, value: object, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _should_retrieve(self, query: str) -> bool:
        text = query.strip()
        lowered = text.lower()
        if len(text) < 8:
            return False

        low_signal_inputs = {
            "ok",
            "okay",
            "yes",
            "no",
            "thanks",
            "thank you",
            "hello",
            "hi",
            "好的",
            "好",
            "嗯",
            "谢谢",
            "你好",
        }
        if lowered in low_signal_inputs:
            return False

        retrieval_keywords = (
            "remember",
            "memory",
            "preference",
            "prefer",
            "goal",
            "plan",
            "project",
            "history",
            "before",
            "last time",
            "记住",
            "记得",
            "上次",
            "以前",
            "之前",
            "偏好",
            "喜欢",
            "讨厌",
            "目标",
            "计划",
            "项目",
            "毕业",
            "毕设",
            "论文",
            "题目",
            "课题",
            "选题",
            "压力",
            "焦虑",
            "难过",
            "累",
        )
        if any(keyword in lowered for keyword in retrieval_keywords):
            return True

        return len(text) >= 20

    def _fit_context_budget(
        self,
        chunks: list[MemoryChunk],
        max_chars: int,
    ) -> list[MemoryChunk]:
        selected: list[MemoryChunk] = []
        used = 0
        for chunk in chunks:
            content_length = len(chunk.content)
            if used + content_length > max_chars:
                break
            selected.append(chunk)
            used += content_length
        return selected

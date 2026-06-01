from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

from src.core.ports.memory_port import MemoryChunk


class MentalState(str, Enum):
    NEUTRAL = "neutral"
    STRESSED = "stressed"
    LOW_ENERGY = "low_energy"
    CONFUSED = "confused"
    MOTIVATED = "motivated"
    VULNERABLE = "vulnerable"


@dataclass(frozen=True)
class MentalStateSnapshot:
    state: MentalState
    confidence: float
    evidence: list[str] = field(default_factory=list)
    response_strategy: str = "balanced_continuity"
    prompt_constraints: list[str] = field(default_factory=list)


class MentalStateMachine:
    """Small deterministic state machine for companion tone control."""

    _KEYWORDS: dict[MentalState, tuple[str, ...]] = {
        MentalState.STRESSED: (
            "stress",
            "stressed",
            "pressure",
            "overwhelmed",
            "焦虑",
            "压力",
            "崩",
            "赶不完",
        ),
        MentalState.LOW_ENERGY: (
            "tired",
            "exhausted",
            "burned out",
            "累",
            "疲惫",
            "没劲",
            "不想动",
        ),
        MentalState.CONFUSED: (
            "confused",
            "lost",
            "unclear",
            "不知道",
            "迷茫",
            "混乱",
            "不清楚",
        ),
        MentalState.MOTIVATED: (
            "ready",
            "excited",
            "motivated",
            "开始",
            "冲",
            "有动力",
            "想做",
        ),
        MentalState.VULNERABLE: (
            "sad",
            "lonely",
            "afraid",
            "难过",
            "孤独",
            "害怕",
            "撑不住",
        ),
    }

    def evaluate(
        self,
        user_input: str,
        memory_chunks: Iterable[MemoryChunk] = (),
    ) -> MentalStateSnapshot:
        text = user_input.lower()
        scores: dict[MentalState, int] = {state: 0 for state in self._KEYWORDS}
        evidence: dict[MentalState, list[str]] = {state: [] for state in self._KEYWORDS}

        for state, keywords in self._KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in text:
                    scores[state] += 2
                    evidence[state].append(f"current message contains '{keyword}'")

        for chunk in memory_chunks:
            memory_state = str(chunk.metadata.get("mental_state", "")).lower()
            for state in self._KEYWORDS:
                if memory_state == state.value:
                    scores[state] += 1
                    evidence[state].append("related memory carries this state")

        selected = max(scores, key=lambda state: scores[state])
        if scores[selected] == 0:
            return MentalStateSnapshot(
                state=MentalState.NEUTRAL,
                confidence=0.5,
                evidence=[],
                response_strategy="balanced_continuity",
                prompt_constraints=[
                    "Use the persona naturally without forcing emotional interpretation.",
                    "Keep the response grounded in the current user message.",
                ],
            )

        confidence = min(0.95, 0.55 + scores[selected] * 0.12)
        return MentalStateSnapshot(
            state=selected,
            confidence=confidence,
            evidence=evidence[selected],
            response_strategy=self._strategy_for(selected),
            prompt_constraints=self._constraints_for(selected),
        )

    def _strategy_for(self, state: MentalState) -> str:
        strategies = {
            MentalState.STRESSED: "pressure_reduction",
            MentalState.LOW_ENERGY: "low_friction_action",
            MentalState.CONFUSED: "clarify_and_structure",
            MentalState.MOTIVATED: "momentum_to_action",
            MentalState.VULNERABLE: "emotional_safety",
        }
        return strategies[state]

    def _constraints_for(self, state: MentalState) -> list[str]:
        constraints = {
            MentalState.STRESSED: [
                "Keep the stable persona, but soften intensity.",
                "Lower the pressure; avoid piling on many options.",
                "Validate the strain briefly, then offer one concrete next step.",
            ],
            MentalState.LOW_ENERGY: [
                "Keep the stable persona, but reduce cognitive load.",
                "Keep the reply short and low-friction.",
                "Suggest the smallest useful action.",
            ],
            MentalState.CONFUSED: [
                "Keep the stable persona, but prioritize clarity over style.",
                "Clarify the situation with one or two precise questions.",
                "Use simple structure and avoid jargon.",
            ],
            MentalState.MOTIVATED: [
                "Keep the stable persona, but let the pace become more direct.",
                "Match the user's momentum with crisp, practical encouragement.",
                "Offer a next action that can start immediately.",
            ],
            MentalState.VULNERABLE: [
                "Keep the stable persona, but make emotional safety the first constraint.",
                "Be gentle and grounded.",
                "Do not over-dramatize; prioritize emotional safety and support.",
            ],
        }
        return constraints[state]

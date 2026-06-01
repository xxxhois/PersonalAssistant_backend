from contextlib import asynccontextmanager
from typing import Any

import pytest

from src.schemas.htn import HTNPlan
from src.schemas.planning import (
    GoalInitRequest,
    PlanConfirmRequest,
    PlanStartRequest,
    PlanTaskDecomposeRequest,
    QuestionAnswer,
)
from src.services.planning import PlanningService, PlanningSessionStore


class FakeLLMClient:
    async def generate_json(
        self,
        prompt: str,
        system_prompt: str,
        temperature: float = 0.4,
        max_tokens: int = 1200,
    ) -> dict[str, Any]:
        del system_prompt, temperature, max_tokens
        if "questions" in prompt and "goal_summary" in prompt:
            return {
                "session_id": "session-1",
                "goal_summary": "Finish thesis project",
                "questions": [
                    {
                        "question_id": "q1",
                        "question_text": "How much time?",
                        "options": [
                            {"key": "A", "label": "1 hour"},
                            {"key": "B", "label": "2 hours"},
                        ],
                    },
                    {
                        "question_id": "q2",
                        "question_text": "Current level?",
                        "options": [
                            {"key": "A", "label": "Intermediate"},
                            {"key": "B", "label": "Advanced"},
                        ],
                    },
                    {
                        "question_id": "q3",
                        "question_text": "Deadline?",
                        "options": [
                            {"key": "A", "label": "This month"},
                            {"key": "B", "label": "Next month"},
                        ],
                    },
                ],
            }
        if "milestones" in prompt:
            return {
                "progress_message": "Split into coarse phases.",
                "milestones": [
                    {
                        "title": "Memory subsystem",
                        "description": "Implement long-term memory.",
                        "estimated_days": 3,
                        "order": 1,
                    },
                    {
                        "title": "Persona subsystem",
                        "description": "Implement persona state machine.",
                        "estimated_days": 2,
                        "order": 2,
                    },
                ],
            }
        return {
            "progress_message": "Refined selected phase.",
            "tasks": [
                {
                    "title": "Write memory retrieval test",
                    "description": "Cover PG and Chroma retrieval.",
                    "estimated_hours": 1,
                    "order": 1,
                },
                {
                    "title": "Improve memory update policy",
                    "description": "Needs follow-up decomposition.",
                    "estimated_hours": 5,
                    "order": 2,
                },
            ],
        }


class LongRangeLLMClient(FakeLLMClient):
    async def generate_json(
        self,
        prompt: str,
        system_prompt: str,
        temperature: float = 0.4,
        max_tokens: int = 1200,
    ) -> dict[str, Any]:
        payload = await super().generate_json(prompt, system_prompt, temperature, max_tokens)
        if "milestones" in prompt:
            payload["milestones"] = [
                {
                    "title": "Overlong milestone",
                    "description": "Should be capped to schema max.",
                    "estimated_days": 14,
                    "order": 1,
                }
            ]
        return payload


class FakeTaskPort:
    @asynccontextmanager
    async def within_transaction(self):
        yield self

    async def save_plan(self, plan: HTNPlan) -> None:
        self.plan = plan

    async def get_plan(self, plan_id):
        if getattr(self, "plan", None) is None or self.plan.plan_id != plan_id:
            raise AssertionError("plan not saved")
        return self.plan

    async def replace_task_subtree(self, plan_id, task_id, subtasks):
        if getattr(self, "plan", None) is None or self.plan.plan_id != plan_id:
            raise AssertionError("plan not saved")

        def replace(tasks):
            updated = []
            found = False
            for task in tasks:
                if task.id == task_id:
                    found = True
                    updated.append(task.model_copy(update={"subtasks": subtasks}))
                    continue
                child_result = replace(task.subtasks)
                if child_result is not None:
                    found = True
                    updated.append(task.model_copy(update={"subtasks": child_result}))
                else:
                    updated.append(task)
            return updated if found else None

        updated_tasks = replace(self.plan.tasks)
        if updated_tasks is None:
            raise AssertionError("task not found")
        self.plan = self.plan.model_copy(update={"tasks": updated_tasks})


@pytest.mark.asyncio
async def test_planning_stream_returns_first_layer_containers_only() -> None:
    service = PlanningService(
        llm_client=FakeLLMClient(),  # type: ignore[arg-type]
        task_port=FakeTaskPort(),  # type: ignore[arg-type]
        session_store=PlanningSessionStore(),
    )
    await service.initialize_goal(
        GoalInitRequest(user_id="user-1", goal_description="Finish thesis project")
    )

    items = [
        item
        async for item in service.stream_plan(
            PlanStartRequest(
                session_id="session-1",
                user_id="user-1",
                answers=[QuestionAnswer(question_id="q1", selected_keys=["A"])],
            )
        )
    ]

    result = items[-1]
    assert result.total_tasks == 2
    assert all(task.task_type == "container" for task in result.tasks)
    assert all(task.can_decompose for task in result.tasks)
    assert all(task.scheduled_date is None for task in result.tasks)


@pytest.mark.asyncio
async def test_planning_can_decompose_selected_container_task() -> None:
    service = PlanningService(
        llm_client=FakeLLMClient(),  # type: ignore[arg-type]
        task_port=FakeTaskPort(),  # type: ignore[arg-type]
        session_store=PlanningSessionStore(),
    )
    await service.initialize_goal(
        GoalInitRequest(user_id="user-1", goal_description="Finish thesis project")
    )
    initial_items = [
        item
        async for item in service.stream_plan(
            PlanStartRequest(
                session_id="session-1",
                user_id="user-1",
                answers=[QuestionAnswer(question_id="q1", selected_keys=["A"])],
            )
        )
    ]
    first_task_id = initial_items[-1].tasks[0].task_id

    expanded_items = [
        item
        async for item in service.stream_task_decomposition(
            PlanTaskDecomposeRequest(
                session_id="session-1",
                user_id="user-1",
                task_id=first_task_id,
            )
        )
    ]

    expanded_result = expanded_items[-1]
    assert [task.task_type for task in expanded_result.tasks] == ["atomic", "container"]
    assert expanded_result.tasks[0].can_decompose is False
    assert expanded_result.tasks[1].can_decompose is True
    assert len(service.session_store.get("session-1").plan_result.tasks) == 4


@pytest.mark.asyncio
async def test_planning_confirm_persists_container_and_children() -> None:
    task_port = FakeTaskPort()
    service = PlanningService(
        llm_client=FakeLLMClient(),  # type: ignore[arg-type]
        task_port=task_port,  # type: ignore[arg-type]
        session_store=PlanningSessionStore(),
    )
    await service.initialize_goal(
        GoalInitRequest(user_id="user-1", goal_description="Finish thesis project")
    )
    initial_items = [
        item
        async for item in service.stream_plan(
            PlanStartRequest(
                session_id="session-1",
                user_id="user-1",
                answers=[QuestionAnswer(question_id="q1", selected_keys=["A"])],
            )
        )
    ]
    root_task_id = initial_items[-1].tasks[0].task_id
    expanded_items = [
        item
        async for item in service.stream_task_decomposition(
            PlanTaskDecomposeRequest(
                session_id="session-1",
                user_id="user-1",
                task_id=root_task_id,
            )
        )
    ]
    child_task_id = expanded_items[-1].tasks[0].task_id

    confirm_result = await service.confirm_plan(
        PlanConfirmRequest(
            session_id="session-1",
            user_id="user-1",
            confirmed_task_ids=[root_task_id, child_task_id],
        )
    )

    assert confirm_result.confirmed_count == 2
    assert task_port.plan is not None
    assert len(task_port.plan.tasks) == 1
    assert task_port.plan.tasks[0].subtasks


@pytest.mark.asyncio
async def test_persisted_active_plan_can_continue_decomposition() -> None:
    task_port = FakeTaskPort()
    service = PlanningService(
        llm_client=FakeLLMClient(),  # type: ignore[arg-type]
        task_port=task_port,  # type: ignore[arg-type]
        session_store=PlanningSessionStore(),
    )
    await service.initialize_goal(
        GoalInitRequest(user_id="user-1", goal_description="Finish thesis project")
    )
    initial_items = [
        item
        async for item in service.stream_plan(
            PlanStartRequest(
                session_id="session-1",
                user_id="user-1",
                answers=[QuestionAnswer(question_id="q1", selected_keys=["A"])],
            )
        )
    ]
    root_task_id = initial_items[-1].tasks[0].task_id
    confirm_result = await service.confirm_plan(
        PlanConfirmRequest(
            session_id="session-1",
            user_id="user-1",
            confirmed_task_ids=[root_task_id],
        )
    )

    items = [
        item
        async for item in service.stream_task_decomposition(
            PlanTaskDecomposeRequest(
                session_id="session-1",
                user_id="user-1",
                task_id=root_task_id,
                plan_id=confirm_result.plan_id,
            )
        )
    ]

    assert items[-1].tasks[0].task_type == "atomic"
    assert task_port.plan is not None
    assert task_port.plan.tasks[0].subtasks


@pytest.mark.asyncio
async def test_planning_caps_overlong_task_duration() -> None:
    service = PlanningService(
        llm_client=LongRangeLLMClient(),  # type: ignore[arg-type]
        task_port=FakeTaskPort(),  # type: ignore[arg-type]
        session_store=PlanningSessionStore(),
    )
    await service.initialize_goal(
        GoalInitRequest(user_id="user-1", goal_description="Finish thesis project")
    )
    items = [
        item
        async for item in service.stream_plan(
            PlanStartRequest(
                session_id="session-1",
                user_id="user-1",
                answers=[QuestionAnswer(question_id="q1", selected_keys=["A"])],
            )
        )
    ]

    assert items[-1].tasks[0].estimated_duration_minutes == 10080

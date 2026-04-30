import json
from typing import Any

from fastapi.testclient import TestClient

from src.main import app
from src.routers.api_v1.dependencies import get_planning_service
from src.schemas.planning import (
    ClarifyQuestion,
    DecomposeProgressEvent,
    GoalInitResponse,
    PersistedPlanResponse,
    PersistedTaskResponse,
    PlanConfirmResponse,
    PlanListResponse,
    PlanResult,
    QuestionOption,
    TaskUpdateResponse,
)


class FakePlanningService:
    plan_uuid = "33333333-3333-3333-3333-333333333333"

    async def initialize_goal(self, request: Any) -> GoalInitResponse:
        del request
        return GoalInitResponse(
            session_id="session-1",
            goal_summary="Learn Python basics in three months.",
            questions=[
                ClarifyQuestion(
                    question_id="q1",
                    question_text="How much time can you spend each day?",
                    options=[
                        QuestionOption(key="A", label="30 minutes"),
                        QuestionOption(key="B", label="1 hour"),
                        QuestionOption(key="C", label="2 hours"),
                    ],
                ),
                ClarifyQuestion(
                    question_id="q2",
                    question_text="What is your current level?",
                    options=[
                        QuestionOption(key="A", label="Beginner"),
                        QuestionOption(key="B", label="Know some syntax"),
                        QuestionOption(key="C", label="Built small projects"),
                    ],
                ),
                ClarifyQuestion(
                    question_id="q3",
                    question_text="What pace do you prefer?",
                    options=[
                        QuestionOption(key="A", label="Steady"),
                        QuestionOption(key="B", label="Fast"),
                    ],
                ),
            ],
        )

    async def stream_plan(self, request: Any):
        del request
        yield DecomposeProgressEvent(
            depth=1,
            message="Split the goal into milestones.",
            subtask_count=3,
        )
        yield DecomposeProgressEvent(
            depth=2,
            message="Refine the first milestone into daily tasks.",
            subtask_count=4,
        )
        yield PlanResult(
            session_id="session-1",
            goal_summary="Learn Python basics in three months.",
            total_tasks=2,
            total_estimated_hours=3.0,
            tasks=[
                {
                    "task_id": "11111111-1111-1111-1111-111111111111",
                    "title": "Install Python and editor",
                    "description": "Prepare the local environment.",
                    "estimated_duration_minutes": 60,
                    "scheduled_date": "2026-04-29",
                    "scheduled_time": "09:00-10:00",
                    "order": 1,
                    "parent_goal": "Phase 1",
                    "checked": False,
                },
                {
                    "task_id": "22222222-2222-2222-2222-222222222222",
                    "title": "Practice variables and data types",
                    "description": "Finish 5 small exercises.",
                    "estimated_duration_minutes": 120,
                    "scheduled_date": "2026-04-30",
                    "scheduled_time": "09:00-11:00",
                    "order": 2,
                    "parent_goal": "Phase 1",
                    "checked": False,
                },
            ],
        )

    async def confirm_plan(self, request: Any) -> PlanConfirmResponse:
        del request
        task = PersistedTaskResponse(
            task_id="11111111-1111-1111-1111-111111111111",
            plan_id=self.plan_uuid,
            title="Install Python and editor",
            description="Prepare the local environment.",
            status="pending",
            estimated_duration_minutes=60,
            scheduled_date="2026-04-29",
            scheduled_time="09:00-10:00",
            order=1,
            parent_goal="Phase 1",
            checked=True,
            created_at="2026-04-29T10:00:00",
            updated_at="2026-04-29T10:00:00",
        )
        plan = PersistedPlanResponse(
            plan_id=self.plan_uuid,
            user_id="user-1",
            goal="Learn Python and build a small project",
            goal_summary="Learn Python basics in three months.",
            status="active",
            total_tasks=1,
            total_estimated_hours=1.0,
            source_session_id="session-1",
            created_at="2026-04-29T10:00:00",
            updated_at="2026-04-29T10:00:00",
            tasks=[task],
        )
        return PlanConfirmResponse(
            plan_id=self.plan_uuid,
            confirmed_count=1,
            message="Plan saved",
            plan=plan,
        )

    async def get_plan(self, plan_id: Any) -> PersistedPlanResponse:
        del plan_id
        return (await self.confirm_plan(None)).plan

    async def get_active_plan(self, user_id: str) -> PersistedPlanResponse:
        del user_id
        return (await self.confirm_plan(None)).plan

    async def list_plans(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> PlanListResponse:
        del user_id
        return PlanListResponse(
            items=[
                {
                    "plan_id": self.plan_uuid,
                    "user_id": "user-1",
                    "goal": "Learn Python and build a small project",
                    "goal_summary": "Learn Python basics in three months.",
                    "status": "active",
                    "total_tasks": 1,
                    "total_estimated_hours": 1.0,
                    "source_session_id": "session-1",
                    "created_at": "2026-04-29T10:00:00",
                    "updated_at": "2026-04-29T10:00:00",
                }
            ],
            total=1,
            limit=limit,
            offset=offset,
        )

    async def update_task(self, task_id: Any, request: Any) -> TaskUpdateResponse:
        del task_id, request
        task = (await self.confirm_plan(None)).plan.tasks[0]
        return TaskUpdateResponse(message="Task updated", task=task)


def test_planning_api_flow() -> None:
    app.dependency_overrides[get_planning_service] = lambda: FakePlanningService()

    with TestClient(app) as client:
        init_response = client.post(
            "/api/v1/planning/initialize",
            json={
                "user_id": "user-1",
                "goal_description": "Learn Python and build a small project",
            },
        )
        assert init_response.status_code == 200
        init_payload = init_response.json()
        assert init_payload["session_id"] == "session-1"
        assert len(init_payload["questions"]) == 3

        with client.stream(
            "POST",
            "/api/v1/planning/stream",
            json={
                "session_id": "session-1",
                "user_id": "user-1",
                "answers": [
                    {"question_id": "q1", "selected_keys": ["B"]},
                    {"question_id": "q2", "selected_keys": ["A"]},
                ],
            },
        ) as stream_response:
            assert stream_response.status_code == 200
            frames = [
                json.loads(line.removeprefix("data: "))
                for line in stream_response.iter_lines()
                if line.startswith("data: ")
            ]

        assert frames[0]["event"] == "progress"
        assert frames[-1]["event"] == "done"
        assert frames[-1]["data"]["plan"]["total_tasks"] == 2

        confirm_response = client.post(
            "/api/v1/planning/confirm",
            json={
                "session_id": "session-1",
                "user_id": "user-1",
                "confirmed_task_ids": [
                    "11111111-1111-1111-1111-111111111111",
                ],
            },
        )
        assert confirm_response.status_code == 200
        confirm_payload = confirm_response.json()
        assert confirm_payload["plan_id"] == FakePlanningService.plan_uuid
        assert confirm_payload["confirmed_count"] == 1

        list_response = client.get("/api/v1/planning/users/user-1/plans")
        assert list_response.status_code == 200
        assert list_response.json()["total"] == 1

        active_response = client.get("/api/v1/planning/users/user-1/active-plan")
        assert active_response.status_code == 200
        assert active_response.json()["plan_id"] == FakePlanningService.plan_uuid

        detail_response = client.get(
            f"/api/v1/planning/plans/{FakePlanningService.plan_uuid}"
        )
        assert detail_response.status_code == 200

        task_response = client.patch(
            "/api/v1/planning/tasks/11111111-1111-1111-1111-111111111111",
            json={"checked": True},
        )
        assert task_response.status_code == 200
        assert task_response.json()["task"]["checked"] is True

    app.dependency_overrides.clear()

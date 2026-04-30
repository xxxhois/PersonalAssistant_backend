from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncIterator, Dict, Optional
from uuid import UUID

from src.core.exceptions.app_exception import AppException, ErrorCode
from src.core.ports.task_port import TaskPort
from src.schemas.htn import HTNPlan, HTNTask, PlanStatus, TaskStatus


class InMemoryTaskRepository(TaskPort):
    """In-memory task storage used in tests and local fallback mode."""

    def __init__(self) -> None:
        self._tasks: Dict[UUID, HTNTask] = {}
        self._plans: Dict[str, HTNPlan] = {}

    @asynccontextmanager
    async def within_transaction(self) -> AsyncIterator["InMemoryTaskRepository"]:
        yield self

    async def get_task(self, task_id: UUID) -> HTNTask:
        task = self._tasks.get(task_id)
        if task is None:
            raise AppException(
                code=ErrorCode.NOT_FOUND,
                message=f"Task {task_id} not found",
                recoverable=False,
            )
        return task

    async def update_task_status(
        self,
        task_id: UUID,
        status: TaskStatus,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        task = await self.get_task(task_id)
        updated_metadata = dict(task.metadata)
        if metadata:
            updated_metadata.update(metadata)
        self._tasks[task_id] = task.model_copy(
            update={"status": status, "metadata": updated_metadata}
        )

    async def save_plan(self, plan: HTNPlan) -> None:
        now = datetime.utcnow()
        stored_plan = plan.model_copy(
            update={
                "created_at": plan.created_at or now,
                "updated_at": now,
            }
        )
        self._plans[str(plan.plan_id)] = stored_plan
        for task in stored_plan.tasks:
            self._store_task_tree(task, str(stored_plan.plan_id))

    async def get_plan(self, plan_id: UUID) -> HTNPlan:
        plan = self._plans.get(str(plan_id))
        if plan is None:
            raise AppException(
                code=ErrorCode.NOT_FOUND,
                message=f"Plan {plan_id} not found",
                recoverable=False,
            )
        return plan

    async def list_plans(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[HTNPlan]:
        plans = [
            plan
            for plan in self._plans.values()
            if plan.model_extra and plan.model_extra.get("user_id") == user_id
        ]
        plans.sort(key=lambda item: item.updated_at, reverse=True)
        return plans[offset : offset + limit]

    async def count_plans(self, user_id: str) -> int:
        return sum(
            1
            for plan in self._plans.values()
            if plan.model_extra and plan.model_extra.get("user_id") == user_id
        )

    async def delete_plan(self, plan_id: UUID) -> None:
        plan = self._plans.pop(str(plan_id), None)
        if plan is None:
            raise AppException(
                code=ErrorCode.NOT_FOUND,
                message=f"Plan {plan_id} not found",
                recoverable=False,
            )
        for task in plan.tasks:
            self._delete_task_tree(task)

    async def get_active_plan(self, user_id: str) -> Optional[HTNPlan]:
        for plan in self._plans.values():
            if (
                plan.status == PlanStatus.ACTIVE
                and plan.model_extra
                and plan.model_extra.get("user_id") == user_id
            ):
                return plan
        return None

    def _store_task_tree(self, task: HTNTask, plan_id: str) -> None:
        task.metadata.setdefault("plan_id", plan_id)
        self._tasks[task.id] = task
        for subtask in task.subtasks:
            self._store_task_tree(subtask, plan_id)

    def _delete_task_tree(self, task: HTNTask) -> None:
        self._tasks.pop(task.id, None)
        for subtask in task.subtasks:
            self._delete_task_tree(subtask)

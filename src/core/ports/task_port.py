from typing import Any, AsyncContextManager, Optional, Protocol
from uuid import UUID

from src.schemas.htn import HTNPlan, HTNTask, TaskStatus


class TaskPort(Protocol):
    """Task and plan persistence boundary."""

    def within_transaction(self) -> AsyncContextManager[Any]:
        ...

    async def get_task(self, task_id: UUID) -> HTNTask:
        ...

    async def update_task_status(
        self,
        task_id: UUID,
        status: TaskStatus,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        ...

    async def save_plan(self, plan: HTNPlan) -> None:
        ...

    async def get_plan(self, plan_id: UUID) -> HTNPlan:
        ...

    async def list_plans(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[HTNPlan]:
        ...

    async def count_plans(self, user_id: str) -> int:
        ...

    async def delete_plan(self, plan_id: UUID) -> None:
        ...

    async def get_active_plan(self, user_id: str) -> Optional[HTNPlan]:
        ...

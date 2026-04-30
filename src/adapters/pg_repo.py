from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Any, AsyncIterator, Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    delete,
    func,
    insert,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import declarative_base

from src.core.exceptions.app_exception import AppException, ErrorCode
from src.core.ports.task_port import TaskPort
from src.schemas.htn import HTNPlan, HTNTask, PlanStatus, TaskStatus

Base = declarative_base()


class PlanModel(Base):
    __tablename__ = "plans"

    id = Column(PGUUID(as_uuid=True), primary_key=True)
    user_id = Column(String(255), nullable=False, index=True)
    goal = Column(String(2000), nullable=False)
    goal_summary = Column(String(500), nullable=False)
    status = Column(String(20), nullable=False, default=PlanStatus.ACTIVE.value, index=True)
    source_session_id = Column(String(64), nullable=True, index=True)
    total_tasks = Column(Integer, nullable=False, default=0)
    total_estimated_minutes = Column(Integer, nullable=False, default=0)
    metadata_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class TaskModel(Base):
    __tablename__ = "tasks"

    id = Column(PGUUID(as_uuid=True), primary_key=True)
    plan_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title = Column(String(255), nullable=False)
    description = Column(String(2000), nullable=False, default="")
    status = Column(String(20), nullable=False, default=TaskStatus.PENDING.value, index=True)
    task_order = Column(Integer, nullable=False, default=1)
    estimated_duration_minutes = Column(Integer, nullable=False, default=60)
    scheduled_date = Column(Date, nullable=True)
    scheduled_time = Column(String(32), nullable=True)
    parent_goal = Column(String(255), nullable=False, default="")
    checked = Column(Boolean, nullable=False, default=False)
    metadata_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class OutboxModel(Base):
    __tablename__ = "outbox"

    id = Column(PGUUID(as_uuid=True), primary_key=True)
    event_type = Column(String(50), nullable=False)
    payload = Column(JSON, nullable=False)
    processed = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PGTaskRepository(TaskPort):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @asynccontextmanager
    async def within_transaction(self) -> AsyncIterator[AsyncSession]:
        if not self.session.in_transaction():
            async with self.session.begin():
                yield self.session
        else:
            yield self.session

    async def get_task(self, task_id: UUID) -> HTNTask:
        stmt = select(TaskModel).where(TaskModel.id == task_id)
        result = await self.session.execute(stmt)
        task_model = result.scalar_one_or_none()
        if task_model is None:
            raise AppException(
                code=ErrorCode.NOT_FOUND,
                message=f"Task {task_id} not found",
                recoverable=False,
            )
        return self._map_task_model(task_model, subtasks=[])

    async def update_task_status(
        self,
        task_id: UUID,
        status: TaskStatus,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        task = await self.get_task(task_id)
        merged_metadata = dict(task.metadata)
        if metadata:
            merged_metadata.update(metadata)

        stmt = (
            update(TaskModel)
            .where(TaskModel.id == task_id)
            .values(
                status=status.value,
                checked=bool(merged_metadata.get("checked", False)),
                metadata_json=merged_metadata,
                updated_at=datetime.utcnow(),
            )
        )
        await self.session.execute(stmt)

        if status == TaskStatus.COMPLETED:
            outbox_stmt = insert(OutboxModel).values(
                id=uuid4(),
                event_type="task.completed",
                payload={"task_id": str(task_id), "status": status.value},
                processed=False,
            )
            await self.session.execute(outbox_stmt)

    async def save_plan(self, plan: HTNPlan) -> None:
        plan_metadata = dict(plan.model_extra or {})
        total_minutes = sum(
            int(task.metadata.get("estimated_duration_minutes", 0)) for task in plan.tasks
        )
        plan_row = {
            "id": plan.plan_id,
            "user_id": str(plan_metadata.get("user_id", "")),
            "goal": plan.goal,
            "goal_summary": str(plan_metadata.get("goal_summary", "")),
            "status": plan.status.value,
            "source_session_id": str(plan_metadata.get("source_session_id", "")) or None,
            "total_tasks": len(plan.tasks),
            "total_estimated_minutes": total_minutes,
            "metadata_json": plan_metadata,
            "created_at": plan.created_at,
            "updated_at": datetime.utcnow(),
        }
        await self.session.execute(insert(PlanModel).values(**plan_row))

        for task in plan.tasks:
            await self._insert_task_tree(task=task, plan_id=plan.plan_id, parent_id=None)

    async def get_plan(self, plan_id: UUID) -> HTNPlan:
        plan_stmt = select(PlanModel).where(PlanModel.id == plan_id)
        plan_result = await self.session.execute(plan_stmt)
        plan_model = plan_result.scalar_one_or_none()
        if plan_model is None:
            raise AppException(
                code=ErrorCode.NOT_FOUND,
                message=f"Plan {plan_id} not found",
                recoverable=False,
            )

        tasks_stmt = (
            select(TaskModel)
            .where(TaskModel.plan_id == plan_id)
            .order_by(TaskModel.task_order.asc(), TaskModel.created_at.asc())
        )
        task_result = await self.session.execute(tasks_stmt)
        task_models = list(task_result.scalars().all())
        tasks = self._build_task_tree(task_models)

        return HTNPlan(
            plan_id=plan_model.id,
            goal=plan_model.goal,
            tasks=tasks,
            status=PlanStatus(plan_model.status),
            created_at=plan_model.created_at,
            updated_at=plan_model.updated_at,
            user_id=plan_model.user_id,
            goal_summary=plan_model.goal_summary,
            source_session_id=plan_model.source_session_id,
        )

    async def list_plans(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[HTNPlan]:
        stmt = (
            select(PlanModel)
            .where(PlanModel.user_id == user_id)
            .order_by(PlanModel.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        plan_models = list(result.scalars().all())
        plans: list[HTNPlan] = []
        for plan_model in plan_models:
            plans.append(await self.get_plan(plan_model.id))
        return plans

    async def count_plans(self, user_id: str) -> int:
        stmt = select(func.count()).select_from(PlanModel).where(PlanModel.user_id == user_id)
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def delete_plan(self, plan_id: UUID) -> None:
        stmt = delete(PlanModel).where(PlanModel.id == plan_id)
        result = await self.session.execute(stmt)
        if result.rowcount == 0:
            raise AppException(
                code=ErrorCode.NOT_FOUND,
                message=f"Plan {plan_id} not found",
                recoverable=False,
            )

    async def get_active_plan(self, user_id: str) -> Optional[HTNPlan]:
        stmt = (
            select(PlanModel)
            .where(
                PlanModel.user_id == user_id,
                PlanModel.status == PlanStatus.ACTIVE.value,
            )
            .order_by(PlanModel.updated_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        plan_model = result.scalar_one_or_none()
        if plan_model is None:
            return None
        return await self.get_plan(plan_model.id)

    async def _insert_task_tree(
        self,
        task: HTNTask,
        plan_id: UUID,
        parent_id: Optional[UUID],
    ) -> None:
        metadata = dict(task.metadata)
        scheduled_date = self._parse_date(metadata.get("scheduled_date"))
        row = {
            "id": task.id,
            "plan_id": plan_id,
            "parent_id": parent_id,
            "title": task.title,
            "description": task.description or "",
            "status": task.status.value,
            "task_order": int(metadata.get("order", 1)),
            "estimated_duration_minutes": int(
                metadata.get("estimated_duration_minutes", 60)
            ),
            "scheduled_date": scheduled_date,
            "scheduled_time": metadata.get("scheduled_time"),
            "parent_goal": str(metadata.get("parent_goal", "")),
            "checked": bool(metadata.get("checked", False)),
            "metadata_json": metadata,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        await self.session.execute(insert(TaskModel).values(**row))
        for subtask in task.subtasks:
            await self._insert_task_tree(subtask, plan_id=plan_id, parent_id=task.id)

    def _build_task_tree(self, task_models: list[TaskModel]) -> list[HTNTask]:
        by_parent: dict[Optional[UUID], list[TaskModel]] = {}
        for task_model in task_models:
            by_parent.setdefault(task_model.parent_id, []).append(task_model)

        def build(parent_id: Optional[UUID]) -> list[HTNTask]:
            children = by_parent.get(parent_id, [])
            built: list[HTNTask] = []
            for child in children:
                built.append(self._map_task_model(child, build(child.id)))
            return built

        return build(None)

    def _map_task_model(self, task_model: TaskModel, subtasks: list[HTNTask]) -> HTNTask:
        metadata = dict(task_model.metadata_json or {})
        metadata.setdefault("estimated_duration_minutes", task_model.estimated_duration_minutes)
        metadata.setdefault(
            "scheduled_date",
            task_model.scheduled_date.isoformat() if task_model.scheduled_date else None,
        )
        metadata.setdefault("scheduled_time", task_model.scheduled_time)
        metadata.setdefault("order", task_model.task_order)
        metadata.setdefault("parent_goal", task_model.parent_goal)
        metadata.setdefault("checked", task_model.checked)
        metadata.setdefault("plan_id", str(task_model.plan_id))
        metadata.setdefault(
            "created_at",
            task_model.created_at.isoformat() if task_model.created_at else None,
        )
        metadata.setdefault(
            "updated_at",
            task_model.updated_at.isoformat() if task_model.updated_at else None,
        )

        return HTNTask(
            id=task_model.id,
            title=task_model.title,
            description=task_model.description,
            status=TaskStatus(task_model.status),
            subtasks=subtasks,
            metadata=metadata,
        )

    def _parse_date(self, value: Any) -> Optional[date]:
        if value in (None, ""):
            return None
        if isinstance(value, date):
            return value
        return date.fromisoformat(str(value))

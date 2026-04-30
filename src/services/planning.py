from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from math import ceil
from typing import AsyncIterator, Dict, List, Optional
from uuid import UUID, uuid4

from src.core.exceptions.app_exception import AppException, ErrorCode
from src.core.ports.task_port import TaskPort
from src.core.prompts.planning_prompts import PlanningPrompts
from src.schemas.htn import HTNPlan, HTNTask, PlanStatus, TaskStatus
from src.schemas.planning import (
    AtomicTaskItem,
    DecomposeProgressEvent,
    GoalInitRequest,
    GoalInitResponse,
    PersistedPlanResponse,
    PersistedTaskResponse,
    PlanConfirmRequest,
    PlanConfirmResponse,
    PlanDeleteResponse,
    PlanListItemResponse,
    PlanListResponse,
    PlanResult,
    PlanStartRequest,
    QuestionAnswer,
    TaskUpdateRequest,
    TaskUpdateResponse,
)
from src.services.llm_client import LLMClient


@dataclass
class PlanningSession:
    session_id: str
    user_id: str
    goal_description: str
    goal_summary: str
    questions_by_id: Dict[str, Dict[str, object]]
    answer_map: Dict[str, List[str]] = field(default_factory=dict)
    plan_result: Optional[PlanResult] = None


class PlanningSessionStore:
    def __init__(self) -> None:
        self._sessions: Dict[str, PlanningSession] = {}

    def save(self, session: PlanningSession) -> None:
        self._sessions[session.session_id] = session

    def get(self, session_id: str) -> PlanningSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise AppException(
                code=ErrorCode.NOT_FOUND,
                message=f"Planning session {session_id} not found",
                recoverable=False,
            )
        return session


class PlanningService:
    def __init__(
        self,
        llm_client: LLMClient,
        task_port: TaskPort,
        session_store: PlanningSessionStore,
    ) -> None:
        self.llm_client = llm_client
        self.task_port = task_port
        self.session_store = session_store

    async def initialize_goal(self, request: GoalInitRequest) -> GoalInitResponse:
        payload = await self.llm_client.generate_json(
            prompt=PlanningPrompts.build_clarify_questions_prompt(
                request.goal_description
            ),
            system_prompt=PlanningPrompts.get_planning_system_prompt(),
            temperature=0.4,
            max_tokens=1200,
        )

        try:
            response = GoalInitResponse.model_validate(payload)
        except Exception as exc:
            raise AppException(
                code=ErrorCode.LLM_PROVIDER_ERROR,
                message=f"Invalid clarify-question response: {exc}",
                details=payload,
                recoverable=True,
            ) from exc

        session = PlanningSession(
            session_id=response.session_id,
            user_id=request.user_id,
            goal_description=request.goal_description,
            goal_summary=response.goal_summary,
            questions_by_id={
                question.question_id: {
                    "question_text": question.question_text,
                    "options": {option.key: option.label for option in question.options},
                }
                for question in response.questions
            },
        )
        self.session_store.save(session)
        return response

    async def stream_plan(
        self,
        request: PlanStartRequest,
    ) -> AsyncIterator[DecomposeProgressEvent | PlanResult]:
        session = self.session_store.get(request.session_id)
        if session.user_id != request.user_id:
            raise AppException(
                code=ErrorCode.FORBIDDEN,
                message="Planning session does not belong to this user",
                recoverable=False,
            )

        clarify_context = self._build_clarify_context(session, request.answers)
        session.answer_map = {
            answer.question_id: answer.selected_keys for answer in request.answers
        }

        high_level_payload = await self.llm_client.generate_json(
            prompt=PlanningPrompts.build_high_level_decompose_prompt(
                goal_description=session.goal_description,
                clarify_context=clarify_context,
            ),
            system_prompt=PlanningPrompts.get_planning_system_prompt(),
            temperature=0.4,
            max_tokens=1400,
        )

        milestones = high_level_payload.get("milestones", [])
        yield DecomposeProgressEvent(
            depth=1,
            message=str(
                high_level_payload.get("progress_message", "已完成目标的阶段拆分。")
            ),
            subtask_count=len(milestones),
        )

        day_cursor = date.today()
        budget_minutes = self._infer_daily_budget_minutes(session)
        atomic_items: List[AtomicTaskItem] = []
        global_order = 1

        for milestone_index, milestone in enumerate(milestones, start=1):
            mid_level_payload = await self.llm_client.generate_json(
                prompt=PlanningPrompts.build_mid_level_decompose_prompt(
                    goal_description=session.goal_description,
                    milestone_title=str(milestone.get("title", f"阶段 {milestone_index}")),
                    milestone_description=str(milestone.get("description", "")),
                    clarify_context=clarify_context,
                ),
                system_prompt=PlanningPrompts.get_planning_system_prompt(),
                temperature=0.4,
                max_tokens=1400,
            )
            tasks = mid_level_payload.get("tasks", [])
            yield DecomposeProgressEvent(
                depth=2,
                message=str(
                    mid_level_payload.get(
                        "progress_message",
                        f"已细化阶段 {milestone_index} 的具体任务。",
                    )
                ),
                subtask_count=len(tasks),
            )

            for task in tasks:
                estimated_hours = float(task.get("estimated_hours", 2))
                if estimated_hours <= 2:
                    schedule = self._schedule_atomic_task(
                        day_cursor=day_cursor,
                        duration_minutes=max(30, int(estimated_hours * 60)),
                        daily_budget_minutes=budget_minutes,
                    )
                    day_cursor = schedule["day_cursor"]
                    atomic_items.append(
                        AtomicTaskItem(
                            title=str(task.get("title", "未命名任务")),
                            description=str(task.get("description", "")),
                            estimated_duration_minutes=int(schedule["duration_minutes"]),
                            scheduled_date=str(schedule["scheduled_date"]),
                            scheduled_time=str(schedule["scheduled_time"]),
                            order=global_order,
                            parent_goal=str(milestone.get("title", "")),
                        )
                    )
                    global_order += 1
                    continue

                atomic_payload = await self.llm_client.generate_json(
                    prompt=PlanningPrompts.build_atomic_decompose_prompt(
                        goal_description=session.goal_description,
                        task_title=str(task.get("title", "未命名任务")),
                        task_description=str(task.get("description", "")),
                        estimated_hours=estimated_hours,
                        clarify_context=clarify_context,
                    ),
                    system_prompt=PlanningPrompts.get_planning_system_prompt(),
                    temperature=0.4,
                    max_tokens=1600,
                )
                generated_atomic_tasks = atomic_payload.get("atomic_tasks", [])
                yield DecomposeProgressEvent(
                    depth=3,
                    message=str(
                        atomic_payload.get(
                            "progress_message",
                            f"已将任务 {task.get('title', '未命名任务')} 细化为原子步骤。",
                        )
                    ),
                    subtask_count=len(generated_atomic_tasks),
                )

                for atomic_task in generated_atomic_tasks:
                    duration_minutes = int(
                        atomic_task.get("estimated_duration_minutes", 60)
                    )
                    schedule = self._schedule_atomic_task(
                        day_cursor=day_cursor,
                        duration_minutes=duration_minutes,
                        daily_budget_minutes=budget_minutes,
                        preferred_slot=atomic_task.get("suggested_time_slot"),
                    )
                    day_cursor = schedule["day_cursor"]
                    atomic_items.append(
                        AtomicTaskItem(
                            title=str(atomic_task.get("title", "未命名原子任务")),
                            description=str(atomic_task.get("description", "")),
                            estimated_duration_minutes=int(schedule["duration_minutes"]),
                            scheduled_date=str(schedule["scheduled_date"]),
                            scheduled_time=str(schedule["scheduled_time"]),
                            order=global_order,
                            parent_goal=str(milestone.get("title", "")),
                        )
                    )
                    global_order += 1

        total_minutes = sum(item.estimated_duration_minutes for item in atomic_items)
        result = PlanResult(
            session_id=session.session_id,
            goal_summary=session.goal_summary,
            total_tasks=len(atomic_items),
            total_estimated_hours=round(total_minutes / 60, 1),
            tasks=atomic_items,
        )
        session.plan_result = result
        self.session_store.save(session)
        yield result

    async def confirm_plan(self, request: PlanConfirmRequest) -> PlanConfirmResponse:
        session = self.session_store.get(request.session_id)
        if session.user_id != request.user_id:
            raise AppException(
                code=ErrorCode.FORBIDDEN,
                message="Planning session does not belong to this user",
                recoverable=False,
            )
        if session.plan_result is None:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                message="Plan has not been generated yet",
                recoverable=False,
            )

        confirmed_set = set(request.confirmed_task_ids)
        confirmed_tasks = [
            task for task in session.plan_result.tasks if task.task_id in confirmed_set
        ]
        if not confirmed_tasks:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                message="No valid confirmed tasks were provided",
                recoverable=False,
            )

        plan_id = uuid4()
        now = datetime.utcnow()
        htn_tasks = [
            HTNTask(
                id=UUID(task.task_id),
                title=task.title,
                description=task.description,
                status=TaskStatus.PENDING,
                metadata={
                    "estimated_duration_minutes": task.estimated_duration_minutes,
                    "scheduled_date": task.scheduled_date,
                    "scheduled_time": task.scheduled_time,
                    "order": task.order,
                    "parent_goal": task.parent_goal,
                    "checked": True,
                    "created_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                },
            )
            for task in confirmed_tasks
        ]
        plan = HTNPlan(
            plan_id=plan_id,
            goal=session.goal_description,
            tasks=htn_tasks,
            status=PlanStatus.ACTIVE,
            created_at=now,
            updated_at=now,
            user_id=request.user_id,
            goal_summary=session.goal_summary,
            source_session_id=session.session_id,
        )

        async with self.task_port.within_transaction():
            await self.task_port.save_plan(plan)

        saved_plan = await self.task_port.get_plan(plan_id)
        persisted_plan = self._to_persisted_plan_response(saved_plan)
        return PlanConfirmResponse(
            plan_id=str(plan_id),
            confirmed_count=len(confirmed_tasks),
            message="任务计划已保存",
            plan=persisted_plan,
        )

    async def get_plan(self, plan_id: UUID) -> PersistedPlanResponse:
        plan = await self.task_port.get_plan(plan_id)
        return self._to_persisted_plan_response(plan)

    async def get_active_plan(self, user_id: str) -> Optional[PersistedPlanResponse]:
        plan = await self.task_port.get_active_plan(user_id)
        if plan is None:
            return None
        return self._to_persisted_plan_response(plan)

    async def list_plans(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> PlanListResponse:
        plans = await self.task_port.list_plans(user_id=user_id, limit=limit, offset=offset)
        total = await self.task_port.count_plans(user_id=user_id)
        items = [self._to_plan_list_item(plan) for plan in plans]
        return PlanListResponse(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
        )

    async def update_task(
        self,
        task_id: UUID,
        request: TaskUpdateRequest,
    ) -> TaskUpdateResponse:
        task = await self.task_port.get_task(task_id)
        metadata = dict(task.metadata)

        checked = request.checked
        if checked is None:
            checked = bool(metadata.get("checked", False))

        if request.status is not None:
            try:
                status = TaskStatus(request.status)
            except ValueError as exc:
                raise AppException(
                    code=ErrorCode.VALIDATION_ERROR,
                    message=f"Unsupported task status: {request.status}",
                    recoverable=False,
                ) from exc
        else:
            status = TaskStatus.COMPLETED if checked else TaskStatus.PENDING

        metadata["checked"] = checked
        metadata["updated_at"] = datetime.utcnow().isoformat()

        async with self.task_port.within_transaction():
            await self.task_port.update_task_status(task_id, status=status, metadata=metadata)

        updated_task = await self.task_port.get_task(task_id)
        persisted_task = self._to_persisted_task_response_from_task(updated_task)
        return TaskUpdateResponse(task=persisted_task)

    async def delete_plan(self, plan_id: UUID) -> PlanDeleteResponse:
        async with self.task_port.within_transaction():
            await self.task_port.delete_plan(plan_id)
        return PlanDeleteResponse(plan_id=str(plan_id))

    def _build_clarify_context(
        self,
        session: PlanningSession,
        answers: List[QuestionAnswer],
    ) -> str:
        parts: List[str] = []
        for answer in answers:
            question_info = session.questions_by_id.get(answer.question_id)
            if question_info is None:
                continue
            options = question_info["options"]
            option_labels = [
                str(options[key]) for key in answer.selected_keys if key in options
            ]
            if option_labels:
                parts.append(
                    f"{question_info['question_text']}：{'、'.join(option_labels)}"
                )
        if not parts:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                message="No valid planning answers were provided",
                recoverable=False,
            )
        return "\n".join(parts)

    def _infer_daily_budget_minutes(self, session: PlanningSession) -> int:
        for question_id, question_info in session.questions_by_id.items():
            question_text = str(question_info.get("question_text", ""))
            if "时间" not in question_text and "投入" not in question_text:
                continue
            options = question_info["options"]
            for selected_key in session.answer_map.get(question_id, []):
                label = str(options.get(selected_key, ""))
                if "30" in label:
                    return 60
                if "1 小时" in label or "1小时" in label:
                    return 120
                if "2 小时" in label or "2小时" in label:
                    return 180
                if "4 小时" in label or "4小时" in label:
                    return 300
        return 180

    def _schedule_atomic_task(
        self,
        day_cursor: date,
        duration_minutes: int,
        daily_budget_minutes: int,
        preferred_slot: Optional[object] = None,
    ) -> Dict[str, object]:
        bounded_minutes = min(max(duration_minutes, 30), 240)
        days_required = max(1, ceil(bounded_minutes / max(daily_budget_minutes, 60)))
        scheduled_date = day_cursor.isoformat()
        scheduled_time = (
            str(preferred_slot)
            if preferred_slot
            else self._default_time_slot(bounded_minutes)
        )
        next_day_cursor = day_cursor + timedelta(days=days_required)
        return {
            "day_cursor": next_day_cursor,
            "duration_minutes": bounded_minutes,
            "scheduled_date": scheduled_date,
            "scheduled_time": scheduled_time,
        }

    def _default_time_slot(self, duration_minutes: int) -> str:
        if duration_minutes <= 60:
            return "09:00-10:00"
        if duration_minutes <= 120:
            return "09:00-11:00"
        if duration_minutes <= 180:
            return "14:00-17:00"
        return "09:00-13:00"

    def _to_persisted_plan_response(self, plan: HTNPlan) -> PersistedPlanResponse:
        tasks = [self._to_persisted_task_response(plan.plan_id, task) for task in plan.tasks]
        total_minutes = sum(task.estimated_duration_minutes for task in tasks)
        return PersistedPlanResponse(
            plan_id=str(plan.plan_id),
            user_id=str((plan.model_extra or {}).get("user_id", "")),
            goal=plan.goal,
            goal_summary=str((plan.model_extra or {}).get("goal_summary", "")),
            status=plan.status.value,
            total_tasks=len(tasks),
            total_estimated_hours=round(total_minutes / 60, 1),
            source_session_id=(plan.model_extra or {}).get("source_session_id"),
            created_at=plan.created_at,
            updated_at=plan.updated_at,
            tasks=tasks,
        )

    def _to_plan_list_item(self, plan: HTNPlan) -> PlanListItemResponse:
        tasks = [self._to_persisted_task_response(plan.plan_id, task) for task in plan.tasks]
        total_minutes = sum(task.estimated_duration_minutes for task in tasks)
        return PlanListItemResponse(
            plan_id=str(plan.plan_id),
            user_id=str((plan.model_extra or {}).get("user_id", "")),
            goal=plan.goal,
            goal_summary=str((plan.model_extra or {}).get("goal_summary", "")),
            status=plan.status.value,
            total_tasks=len(tasks),
            total_estimated_hours=round(total_minutes / 60, 1),
            source_session_id=(plan.model_extra or {}).get("source_session_id"),
            created_at=plan.created_at,
            updated_at=plan.updated_at,
        )

    def _to_persisted_task_response(
        self,
        plan_id: UUID,
        task: HTNTask,
    ) -> PersistedTaskResponse:
        metadata = dict(task.metadata)
        created_at = self._parse_datetime(metadata.get("created_at")) or datetime.utcnow()
        updated_at = self._parse_datetime(metadata.get("updated_at")) or created_at
        return PersistedTaskResponse(
            task_id=str(task.id),
            plan_id=str(plan_id),
            title=task.title,
            description=task.description or "",
            status=task.status.value,
            estimated_duration_minutes=int(
                metadata.get("estimated_duration_minutes", 60)
            ),
            scheduled_date=metadata.get("scheduled_date"),
            scheduled_time=metadata.get("scheduled_time"),
            order=int(metadata.get("order", 1)),
            parent_goal=str(metadata.get("parent_goal", "")),
            checked=bool(metadata.get("checked", False)),
            created_at=created_at,
            updated_at=updated_at,
        )

    def _to_persisted_task_response_from_task(
        self,
        task: HTNTask,
    ) -> PersistedTaskResponse:
        metadata = dict(task.metadata)
        plan_id = metadata.get("plan_id")
        if not plan_id:
            raise AppException(
                code=ErrorCode.INTERNAL_ERROR,
                message=f"Persisted task {task.id} is missing plan_id metadata",
                recoverable=False,
            )
        return self._to_persisted_task_response(UUID(str(plan_id)), task)

    def _parse_datetime(self, value: object) -> Optional[datetime]:
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value))

"""Schemas for the autonomous planning workflow."""

from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class GoalInitRequest(BaseModel):
    user_id: str = Field(..., description="User ID")
    goal_description: str = Field(
        ...,
        min_length=2,
        max_length=2000,
        description="User goal description",
    )


class QuestionOption(BaseModel):
    key: str = Field(..., description="Option key, such as A/B/C")
    label: str = Field(..., description="Option display text")


class ClarifyQuestion(BaseModel):
    question_id: str = Field(default_factory=lambda: str(uuid4())[:8])
    question_text: str = Field(..., description="Question text")
    options: List[QuestionOption] = Field(..., min_length=2, max_length=6)
    allow_multiple: bool = Field(default=False)


class GoalInitResponse(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    goal_summary: str = Field(..., description="One-line goal summary")
    questions: List[ClarifyQuestion] = Field(..., min_length=3, max_length=5)


class QuestionAnswer(BaseModel):
    question_id: str
    selected_keys: List[str] = Field(..., min_length=1)


class PlanStartRequest(BaseModel):
    session_id: str
    user_id: str
    answers: List[QuestionAnswer] = Field(..., min_length=1)


class DecomposeProgressEvent(BaseModel):
    depth: int = Field(..., description="Current decomposition depth")
    message: str = Field(..., description="One-line progress update")
    subtask_count: int = Field(default=0)


class AtomicTaskItem(BaseModel):
    task_id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    description: str = ""
    estimated_duration_minutes: int = Field(..., ge=5, le=480)
    scheduled_date: Optional[str] = Field(default=None, description="YYYY-MM-DD")
    scheduled_time: Optional[str] = Field(default=None, description="09:00-10:30")
    order: int
    parent_goal: str = ""
    checked: bool = False


class PlanResult(BaseModel):
    session_id: str
    goal_summary: str
    total_tasks: int
    total_estimated_hours: float
    tasks: List[AtomicTaskItem]


class PlanConfirmRequest(BaseModel):
    session_id: str
    user_id: str
    confirmed_task_ids: List[str] = Field(..., min_length=1)


class PersistedTaskResponse(BaseModel):
    task_id: str
    plan_id: str
    title: str
    description: str = ""
    status: str
    estimated_duration_minutes: int
    scheduled_date: Optional[str] = None
    scheduled_time: Optional[str] = None
    order: int
    parent_goal: str = ""
    checked: bool = False
    created_at: datetime
    updated_at: datetime


class PersistedPlanResponse(BaseModel):
    plan_id: str
    user_id: str
    goal: str
    goal_summary: str
    status: str
    total_tasks: int
    total_estimated_hours: float
    source_session_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    tasks: List[PersistedTaskResponse]


class PlanListItemResponse(BaseModel):
    plan_id: str
    user_id: str
    goal: str
    goal_summary: str
    status: str
    total_tasks: int
    total_estimated_hours: float
    source_session_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class PlanListResponse(BaseModel):
    items: List[PlanListItemResponse]
    total: int
    limit: int
    offset: int


class PlanConfirmResponse(BaseModel):
    plan_id: str = Field(default_factory=lambda: str(uuid4()))
    confirmed_count: int
    message: str = Field(default="任务计划已保存")
    plan: PersistedPlanResponse


class TaskUpdateRequest(BaseModel):
    checked: Optional[bool] = None
    status: Optional[str] = None


class TaskUpdateResponse(BaseModel):
    message: str = Field(default="任务已更新")
    task: PersistedTaskResponse


class PlanDeleteResponse(BaseModel):
    message: str = Field(default="计划已删除")
    plan_id: str

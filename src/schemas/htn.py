from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field
from uuid import UUID
from datetime import datetime

# Keep this permissive to avoid recursive schema expansion issues in Pydantic v2.
JsonValue = Any

class TaskStatus(str, Enum):
    """HTN 任务状态枚举"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class PlanStatus(str, Enum):
    """HTN 计划状态枚举"""
    ACTIVE = "active"
    FINISHED = "finished"
    ABORTED = "aborted"

class HTNTask(BaseModel):
    """
    原子任务/子任务树模型 (HTNTask)
    遵循架构铁律：严禁使用裸 dict/list/Any 作为 HTN 状态
    """
    id: UUID
    title: str = Field(..., description="任务标题")
    description: Optional[str] = Field(None, description="任务详细描述")
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    subtasks: List["HTNTask"] = Field(default_factory=list)
    metadata: Dict[str, JsonValue] = Field(default_factory=dict, description="任务扩展属性，强校验 JsonValue")
    
    # 支持递归定义
    model_config = ConfigDict(arbitrary_types_allowed=True)

class HTNPlan(BaseModel):
    """
    HTN 计划模型 (HTNPlan)
    遵循架构铁律：混合契约模式 (extra="allow")
    核心字段强校验，扩展字段通过 extra 允许
    """
    model_config = ConfigDict(extra="allow")

    plan_id: UUID = Field(..., description="计划唯一 ID")
    goal: str = Field(..., description="宏大目标原始描述")
    tasks: List[HTNTask] = Field(..., description="分解后的原子任务树")
    status: PlanStatus = Field(default=PlanStatus.ACTIVE)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any, Optional


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PlanStatus(Enum):
    PENDING = "pending"
    VALIDATING = "validating"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DependencyCondition(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    ANY = "any"


@dataclass
class TaskDependency:
    task_id: str
    condition: DependencyCondition = DependencyCondition.SUCCESS

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "condition": self.condition.value,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TaskDependency":
        return cls(
            task_id=data["task_id"],
            condition=DependencyCondition(data.get("condition", "success")),
        )


@dataclass
class TaskResult:
    task_id: str
    success: bool
    output: Optional[Any] = None
    error: Optional[str] = None
    traceback: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TaskResult":
        return cls(
            task_id=data["task_id"],
            success=data["success"],
            output=data.get("output"),
            error=data.get("error"),
            traceback=data.get("traceback"),
        )


@dataclass
class PlanContext:
    plan_id: str
    task_outputs: dict[str, Any]
    logger: Any
    config: Any

    def to_dict(self) -> dict:
        # Logger and config might not be serializable
        # We only serialize the parts that can be persisted
        return {
            "plan_id": self.plan_id,
            "task_outputs": self.task_outputs,
        }

    @classmethod
    def from_dict(cls, data: dict, logger: Any, config: Any) -> "PlanContext":
        return cls(
            plan_id=data["plan_id"],
            task_outputs=data.get("task_outputs", {}),
            logger=logger,
            config=config,
        )

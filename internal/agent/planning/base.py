from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, List, Optional


@dataclass
class TaskResult:
    task_id: str
    success: bool
    result: Any
    error: str | None = None


@dataclass
class PlanContext:
    goal: str
    context: dict[str, Any]
    metadata: dict[str, Any] | None = None


class Task(ABC):
    @property
    @abstractmethod
    def task_id(self) -> str: ...

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    @abstractmethod
    def dependencies(self) -> List[str]: ...

    @property
    @abstractmethod
    def status(self) -> str: ...

    @abstractmethod
    async def execute(self, context: PlanContext) -> TaskResult: ...


class Plan(ABC):
    @property
    @abstractmethod
    def plan_id(self) -> str: ...

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    @abstractmethod
    def tasks(self) -> List[Task]: ...

    @abstractmethod
    def add_task(self, task: Task) -> None: ...

    @abstractmethod
    def remove_task(self, task_id: str) -> None: ...

    @abstractmethod
    def get_task(self, task_id: str) -> Optional[Task]: ...

    @abstractmethod
    async def execute(self, context: PlanContext) -> List[TaskResult]: ...

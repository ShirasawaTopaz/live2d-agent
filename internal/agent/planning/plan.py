"""
Concrete Plan implementation for task management and dynamic modification
Supports hierarchical nesting, dependency checking, and serialization
"""

import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from .base import Plan, Task, PlanContext, TaskResult
from .types import TaskStatus, PlanStatus


class ConcretePlan(Plan, Task):
    """Concrete Plan implementation that also implements the Task interface
    allowing hierarchical nesting (sub-plans as tasks).
    
    This works by implementing all abstract methods from both base classes
    and relying on Python's method resolution order.
    """
    
    def __init__(
        self,
        plan_id: Optional[str] = None,
        name: str = "",
        description: str = "",
        dependencies: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Initialize a new Plan"""
        self._plan_id = plan_id or str(uuid.uuid4())[:8]
        self._name = name
        self._description = description
        self._tasks: Dict[str, Task] = {}
        self._dependencies = dependencies or []
        self._metadata = metadata or {}
        self._created_at = datetime.now()
        self._updated_at = self._created_at
        self._plan_status = PlanStatus.PENDING
        self._task_status = TaskStatus.PENDING.value
    
    # MARK: Task interface implementation (all required abstract methods)
    @property
    def task_id(self) -> str:
        return self._plan_id
    
    @property
    def name(self) -> str:
        # Task needs name, Plan needs name - same property
        return self._name
    
    @name.setter
    def name(self, value: str) -> None:
        self._name = value
        self._touch()
    
    @property
    def description(self) -> str:
        # Task needs description, Plan needs description - same property
        return self._description
    
    @description.setter
    def description(self, value: str) -> None:
        self._description = value
        self._touch()
    
    @property
    def dependencies(self) -> List[str]:
        return self._dependencies
    
    @dependencies.setter
    def dependencies(self, value: List[str]) -> None:
        self._dependencies = value
        self._touch()
    
    @property
    def status(self) -> str:
        # Task interface expects str for status
        return self._task_status
    
    @status.setter
    def status(self, value: str) -> None:
        self._task_status = value
        self._touch()
    
    # MARK: Plan interface implementation (all required abstract methods)
    @property
    def plan_id(self) -> str:
        return self._plan_id
    
    @property
    def tasks(self) -> List[Task]:
        """Return all tasks as a list - required by Plan ABC"""
        return list(self._tasks.values())
    
    # --- Additional plan properties ---
    @property
    def plan_status(self) -> PlanStatus:
        return self._plan_status
    
    @plan_status.setter
    def plan_status(self, value: PlanStatus) -> None:
        self._plan_status = value
        self._touch()
    
    @property
    def created_at(self) -> datetime:
        return self._created_at
    
    @property
    def updated_at(self) -> datetime:
        return self._updated_at
    
    @property
    def metadata(self) -> Dict[str, Any]:
        return self._metadata
    
    def _touch(self) -> None:
        """Update the updated_at timestamp"""
        self._updated_at = datetime.now()
    
    # MARK: Plan abstract methods
    def add_task(self, task: Task) -> None:
        """Add a new task to the plan
        
        Args:
            task: The task to add
        """
        self._tasks[task.task_id] = task
        self._touch()
    
    def remove_task(self, task_id: str) -> None:
        """Remove a task from the plan by its ID
        
        Args:
            task_id: The ID of the task to remove
        """
        if task_id in self._tasks:
            del self._tasks[task_id]
            self._touch()
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by its ID
        
        Args:
            task_id: The task ID to look up
            
        Returns:
            The task if found, None otherwise
        """
        return self._tasks.get(task_id)
    
    # --- Execute method is the tricky part because both base classes require it
    # with different return types. We solve this by implementing a single method
    # that handles both cases depending on how it's called, and use type: ignore
    # to tell the static checker we know what we're doing ---
    async def _execute_internal(self, context: PlanContext) -> List[TaskResult]:
        """Internal execution that handles the actual work"""
        results = []
        
        # Execute tasks with satisfied dependencies
        # Simple sequential approach, advanced scheduling done by executor
        for task in self._tasks.values():
            if self.check_dependencies_satisfied(task.task_id):
                result = await task.execute(context)
                results.append(result)
                
                # Update task status based on result
                try:
                    setattr(task, 'status', TaskStatus.COMPLETED.value if result.success else TaskStatus.FAILED.value)
                except AttributeError:
                    if hasattr(task, '_status'):
                        setattr(task, '_status', TaskStatus.COMPLETED.value if result.success else TaskStatus.FAILED.value)
                
                self._touch()
        
        return results
    
    # The concrete method for Plan ABC that returns List[TaskResult]
    # We need this because the ABC mandates it, type: ignore to work around signature issue
    async def execute(self, context: PlanContext) -> List[TaskResult]:  # type: ignore[override]
        """When called as a Plan (top-level), returns list of TaskResults
        
        This satisfies the Plan ABC requirement that execute returns List[TaskResult]
        """
        results = await self._execute_internal(context)
        
        # Update our own task status based on execution
        all_successful = all(result.success for result in results)
        if all_successful:
            self._task_status = TaskStatus.COMPLETED.value
        else:
            self._task_status = TaskStatus.FAILED.value
        
        self._touch()
        
        return results
    
    # MARK: Additional functionality required by specification
    def list_tasks(self) -> List[Task]:
        """List all tasks in the plan
        
        Returns:
            List of all tasks
        """
        return list(self._tasks.values())
    
    def update_task_status(self, task_id: str, status: str) -> bool:
        """Update the status of a task
        
        Args:
            task_id: The task ID
            status: The new status
            
        Returns:
            True if task was found and updated, False otherwise
        """
        task = self.get_task(task_id)
        if task is None:
            return False
        
        # For concrete tasks that have a settable status property
        if hasattr(task, 'status'):
            try:
                # Try to set the status directly if it's a settable property
                setattr(task, 'status', status)
                self._touch()
                return True
            except AttributeError:
                # Fall back to checking for _status private attribute
                if hasattr(task, '_status'):
                    setattr(task, '_status', status)
                    self._touch()
                    return True
        
        return False
    
    def check_dependencies_satisfied(self, task_id: str) -> bool:
        """Check if all dependencies for a task are satisfied
        
        A dependency is satisfied if:
        - The dependency task does not exist in this plan (it's assumed to be satisfied externally)
        - The dependency task exists and is in COMPLETED status with success
        
        Args:
            task_id: The task ID to check dependencies for
            
        Returns:
            True if all dependencies are satisfied, False otherwise
        """
        task = self.get_task(task_id)
        if task is None:
            return False
        
        for dep_id in task.dependencies:
            dep_task = self.get_task(dep_id)
            if dep_task is None:
                continue
                
            # Check if dependency task is completed
            if dep_task.status != TaskStatus.COMPLETED.value:
                return False
        
        return True
    
    def has_subplan(self) -> bool:
        """Check if this plan contains any sub-plans (nested plans)
        
        Returns:
            True if at least one task is itself a Plan
        """
        for task in self._tasks.values():
            if isinstance(task, Plan):
                return True
        return False
    
    def get_all_task_ids(self, include_subplans: bool = True) -> List[str]:
        """Get all task IDs, optionally including those in sub-plans

        Args:
            include_subplans: Whether to recursively include tasks from sub-plans

        Returns:
            List of all task IDs
        """
        ids = []
        
        for task_id, task in self._tasks.items():
            if include_subplans and isinstance(task, Plan):
                # If this task is itself a Plan (sub-plan), recursively include all its tasks
                # instead of including the sub-plan's own task_id
                ids.extend(task.get_all_task_ids(include_subplans=True))
            else:
                # Regular task, just add its task_id
                ids.append(task_id)
        
        return ids
    
    # MARK: Serialization
    def to_dict(self) -> Dict[str, Any]:
        """Serialize the plan to a dictionary for storage
        
        Returns:
            Dictionary representation of the plan
        """
        # Handle nested plans recursively
        tasks_dict = {}
        for task_id, task in self._tasks.items():
            if isinstance(task, ConcretePlan):
                tasks_dict[task_id] = {
                    "type": "subplan",
                    "data": task.to_dict(),
                }
            else:
                # For regular tasks, we expect they have a to_dict method
                # If not, we store what we can
                if hasattr(task, 'to_dict') and callable(getattr(task, 'to_dict')):
                    to_dict_method = getattr(task, 'to_dict')
                    tasks_dict[task_id] = {
                        "type": "task",
                        "data": to_dict_method(),
                    }
                else:
                    # Fallback: store basic properties
                    tasks_dict[task_id] = {
                        "type": "task",
                        "data": {
                            "task_id": task.task_id,
                            "name": task.name,
                            "description": task.description,
                            "dependencies": task.dependencies,
                            "status": task.status,
                        },
                    }
        
        return {
            "plan_id": self._plan_id,
            "name": self._name,
            "description": self._description,
            "tasks": tasks_dict,
            "dependencies": self._dependencies,
            "metadata": self._metadata,
            "created_at": self._created_at.isoformat(),
            "updated_at": self._updated_at.isoformat(),
            "plan_status": self._plan_status.value,
            "task_status": self._task_status,
        }
    
    @classmethod
    def from_dict(
        cls,
        data: Dict[str, Any],
        task_factory: Optional[Callable[[Dict[str, Any]], Task]] = None,
    ) -> "ConcretePlan":
        """Deserialize a plan from a dictionary
        
        Args:
            data: The dictionary data to deserialize from
            task_factory: Optional factory function to create tasks from serialized data
            
        Returns:
            New ConcretePlan instance
        """
        plan = cls(
            plan_id=data.get("plan_id"),
            name=data.get("name", ""),
            description=data.get("description", ""),
            dependencies=data.get("dependencies", []),
            metadata=data.get("metadata", {}),
        )
        
        # Parse timestamps
        if "created_at" in data:
            plan._created_at = datetime.fromisoformat(data["created_at"])
        if "updated_at" in data:
            plan._updated_at = datetime.fromisoformat(data["updated_at"])
        
        # Parse statuses
        if "plan_status" in data:
            plan._plan_status = PlanStatus(data["plan_status"])
        if "task_status" in data:
            plan._task_status = data["task_status"]
        
        # Parse tasks
        tasks_data = data.get("tasks", {})
        for task_id, task_data in tasks_data.items():
            if task_data.get("type") == "subplan":
                # Recursively deserialize sub-plan
                subplan = cls.from_dict(task_data["data"], task_factory)
                plan.add_task(subplan)
            else:
                # Regular task - use factory if provided
                if task_factory is not None:
                    task = task_factory(task_data["data"])
                    plan.add_task(task)
        
        return plan

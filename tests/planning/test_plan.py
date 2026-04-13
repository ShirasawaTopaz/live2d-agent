"""Unit tests for ConcretePlan implementation."""

from datetime import datetime
from internal.agent.planning.plan import ConcretePlan
from internal.agent.planning.base import Task
from internal.agent.planning.types import TaskStatus, PlanStatus


class SimpleTask(Task):
    """Simple concrete Task implementation for testing."""
    
    def __init__(self, task_id: str, name: str, description: str = "", 
                 dependencies: list[str] = None, status: str = TaskStatus.PENDING.value):
        self._task_id = task_id
        self._name = name
        self._description = description
        self._dependencies = dependencies or []
        self._status = status
    
    @property
    def task_id(self) -> str:
        return self._task_id
    
    @property
    def name(self) -> str:
        return self._name
    
    @name.setter
    def name(self, value: str) -> None:
        self._name = value
    
    @property
    def description(self) -> str:
        return self._description
    
    @description.setter
    def description(self, value: str) -> None:
        self._description = value
    
    @property
    def dependencies(self) -> list[str]:
        return self._dependencies
    
    @dependencies.setter
    def dependencies(self, value: list[str]) -> None:
        self._dependencies = value
    
    @property
    def status(self) -> str:
        return self._status
    
    @status.setter
    def status(self, value: str) -> None:
        self._status = value
    
    async def execute(self, context):
        from internal.agent.planning.base import TaskResult
        return TaskResult(
            task_id=self._task_id,
            success=True,
            result="Executed",
            error=None
        )
    
    def to_dict(self):
        """Serialize to dictionary for testing."""
        return {
            "task_id": self._task_id,
            "name": self._name,
            "description": self._description,
            "dependencies": self._dependencies,
            "status": self._status,
        }


class TestConcretePlan:
    """Test cases for the ConcretePlan class."""
    
    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.plan = ConcretePlan(
            plan_id="test-plan-1",
            name="Test Plan",
            description="A test plan for unit testing"
        )
    
    def test_initial_state(self):
        """Test that a new plan has correct initial state."""
        assert self.plan.plan_id == "test-plan-1"
        assert self.plan.name == "Test Plan"
        assert self.plan.description == "A test plan for unit testing"
        assert self.plan.plan_status == PlanStatus.PENDING
        assert self.plan.status == TaskStatus.PENDING.value
        assert len(self.plan.tasks) == 0
        assert self.plan.dependencies == []
        assert isinstance(self.plan.created_at, datetime)
        assert isinstance(self.plan.updated_at, datetime)
    
    def test_add_task(self):
        """Test adding tasks to the plan."""
        task = SimpleTask("task-1", "First Task")
        self.plan.add_task(task)
        
        assert len(self.plan.tasks) == 1
        assert self.plan.get_task("task-1") == task
    
    def test_add_multiple_tasks(self):
        """Test adding multiple tasks to the plan."""
        task1 = SimpleTask("task-1", "First Task")
        task2 = SimpleTask("task-2", "Second Task")
        task3 = SimpleTask("task-3", "Third Task")
        
        self.plan.add_task(task1)
        self.plan.add_task(task2)
        self.plan.add_task(task3)
        
        assert len(self.plan.tasks) == 3
        assert self.plan.get_task("task-1") == task1
        assert self.plan.get_task("task-2") == task2
        assert self.plan.get_task("task-3") == task3
    
    def test_remove_task(self):
        """Test removing tasks from the plan."""
        task = SimpleTask("task-1", "First Task")
        self.plan.add_task(task)
        assert len(self.plan.tasks) == 1
        
        self.plan.remove_task("task-1")
        assert len(self.plan.tasks) == 0
        assert self.plan.get_task("task-1") is None
    
    def test_remove_nonexistent_task(self):
        """Test removing a task that doesn't exist (should not raise)."""
        self.plan.remove_task("nonexistent")
        assert len(self.plan.tasks) == 0
    
    def test_get_task_returns_none_for_nonexistent(self):
        """Test that get_task returns None for non-existent task IDs."""
        assert self.plan.get_task("nonexistent") is None
    
    def test_get_task_by_id_success(self):
        """Test getting a task by its ID when it exists."""
        task = SimpleTask("task-123", "Test Task")
        self.plan.add_task(task)
        
        found = self.plan.get_task("task-123")
        assert found is not None
        assert found.task_id == "task-123"
        assert found.name == "Test Task"

    def test_dynamic_modification_add_after_start(self):
        """Test that tasks can be added after execution has started."""
        # Start the plan by changing status
        self.plan.plan_status = PlanStatus.RUNNING
        self.plan.status = TaskStatus.RUNNING.value
        
        # Add a task after execution started
        task = SimpleTask("late-task", "Added Late", dependencies=["early-task"])
        self.plan.add_task(task)
        
        # Verify it was added
        found = self.plan.get_task("late-task")
        assert found is not None
        assert found.dependencies == ["early-task"]

    def test_dynamic_modification_remove_after_start(self):
        """Test that tasks can be removed after execution has started."""
        # Add a task
        task = SimpleTask("task-to-remove", "Will Be Removed")
        self.plan.add_task(task)
        
        # Start execution
        self.plan.plan_status = PlanStatus.RUNNING
        
        # Remove the task
        self.plan.remove_task("task-to-remove")
        
        # Verify it was removed
        assert self.plan.get_task("task-to-remove") is None

    def test_check_dependencies_satisfied_no_dependencies(self):
        """Test that a task with no dependencies is always satisfied."""
        task = SimpleTask("task-1", "No Dependencies")
        self.plan.add_task(task)
        
        assert self.plan.check_dependencies_satisfied("task-1") is True

    def test_check_dependencies_satisfied_all_completed(self):
        """Test that dependencies are satisfied when all are completed."""
        task1 = SimpleTask("dep-1", "Dependency 1", status=TaskStatus.COMPLETED.value)
        task2 = SimpleTask("dep-2", "Dependency 2", status=TaskStatus.COMPLETED.value)
        task3 = SimpleTask("main", "Main Task", dependencies=["dep-1", "dep-2"])
        
        self.plan.add_task(task1)
        self.plan.add_task(task2)
        self.plan.add_task(task3)
        
        assert self.plan.check_dependencies_satisfied("main") is True

    def test_check_dependencies_satisfied_not_all_completed(self):
        """Test that dependencies are not satisfied if any dependency is not completed."""
        task1 = SimpleTask("dep-1", "Dependency 1", status=TaskStatus.COMPLETED.value)
        task2 = SimpleTask("dep-2", "Dependency 2", status=TaskStatus.PENDING.value)
        task3 = SimpleTask("main", "Main Task", dependencies=["dep-1", "dep-2"])
        
        self.plan.add_task(task1)
        self.plan.add_task(task2)
        self.plan.add_task(task3)
        
        assert self.plan.check_dependencies_satisfied("main") is False

    def test_check_dependencies_satisfied_external_dependency(self):
        """Test that non-existent (external) dependencies are considered satisfied."""
        # Task depends on a task not in this plan
        task = SimpleTask("main", "Main Task", dependencies=["external-task"])
        self.plan.add_task(task)
        
        # External dependency should be considered satisfied
        assert self.plan.check_dependencies_satisfied("main") is True

    def test_check_dependencies_satisfied_nonexistent_task(self):
        """Test that checking dependencies for a non-existent task returns False."""
        assert self.plan.check_dependencies_satisfied("nonexistent") is False

    def test_update_task_status_success(self):
        """Test successful update of task status."""
        task = SimpleTask("task-1", "Test Task")
        self.plan.add_task(task)
        
        result = self.plan.update_task_status("task-1", TaskStatus.COMPLETED.value)
        assert result is True
        assert task.status == TaskStatus.COMPLETED.value

    def test_update_task_status_nonexistent_task(self):
        """Test that update on non-existent task returns False."""
        result = self.plan.update_task_status("nonexistent", TaskStatus.COMPLETED.value)
        assert result is False

    def test_has_subplan_true(self):
        """Test has_subplan returns True when plan contains a sub-plan."""
        subplan = ConcretePlan(plan_id="sub-1", name="Sub Plan")
        self.plan.add_task(subplan)
        
        assert self.plan.has_subplan() is True

    def test_has_subplan_false(self):
        """Test has_subplan returns False when no sub-plans."""
        task = SimpleTask("task-1", "Regular Task")
        self.plan.add_task(task)
        
        assert self.plan.has_subplan() is False

    def test_has_subplan_empty_plan(self):
        """Test has_subplan returns False for empty plan."""
        assert self.plan.has_subplan() is False

    def test_get_all_task_ids_no_subplans(self):
        """Test getting all task IDs when there are no sub-plans."""
        task1 = SimpleTask("t1", "Task 1")
        task2 = SimpleTask("t2", "Task 2")
        self.plan.add_task(task1)
        self.plan.add_task(task2)
        
        ids = self.plan.get_all_task_ids(include_subplans=True)
        assert sorted(ids) == sorted(["t1", "t2"])

    def test_get_all_task_ids_with_subplans(self):
        """Test getting all task IDs including from nested sub-plans."""
        task1 = SimpleTask("t1", "Task 1")
        subplan = ConcretePlan(plan_id="sub1", name="Sub Plan 1")
        subtask1 = SimpleTask("st1", "Sub Task 1")
        subtask2 = SimpleTask("st2", "Sub Task 2")
        subplan.add_task(subtask1)
        subplan.add_task(subtask2)
        
        self.plan.add_task(task1)
        self.plan.add_task(subplan)
        
        ids = self.plan.get_all_task_ids(include_subplans=True)
        assert sorted(ids) == sorted(["t1", "st1", "st2"])

    def test_get_all_task_ids_no_subplan_include(self):
        """Test when include_subplans is False, sub-plan tasks are not included."""
        task1 = SimpleTask("t1", "Task 1")
        subplan = ConcretePlan(plan_id="sub1", name="Sub Plan 1")
        subplan.add_task(SimpleTask("st1", "Sub Task"))
        self.plan.add_task(task1)
        self.plan.add_task(subplan)
        
        ids = self.plan.get_all_task_ids(include_subplans=False)
        assert sorted(ids) == sorted(["t1", "sub1"])

    def test_to_dict_from_dict_round_trip(self):
        """Test serialization round-trip preserves all data."""
        # Add some tasks
        task1 = SimpleTask("t1", "Task One", "First task description", [], TaskStatus.PENDING.value)
        task2 = SimpleTask("t2", "Task Two", "", ["t1"], TaskStatus.COMPLETED.value)
        self.plan.add_task(task1)
        self.plan.add_task(task2)
        
        # Add some metadata
        self.plan.metadata["key"] = "value"
        self.plan.metadata["number"] = 42
        self.plan.plan_status = PlanStatus.RUNNING
        
        # Serialize
        data = self.plan.to_dict()
        
        # Verify data structure
        assert data["plan_id"] == "test-plan-1"
        assert data["name"] == "Test Plan"
        assert data["description"] == "A test plan for unit testing"
        assert len(data["tasks"]) == 2
        assert data["metadata"] == {"key": "value", "number": 42}
        assert data["plan_status"] == PlanStatus.RUNNING.value
        
        # Deserialize
        def task_factory(task_data):
            return SimpleTask(
                task_data["task_id"],
                task_data["name"],
                task_data.get("description", ""),
                task_data.get("dependencies", []),
                task_data.get("status", TaskStatus.PENDING.value)
            )
        
        restored = ConcretePlan.from_dict(data, task_factory)
        
        # Verify restored state
        assert restored.plan_id == self.plan.plan_id
        assert restored.name == self.plan.name
        assert restored.description == self.plan.description
        assert restored.plan_status == self.plan.plan_status
        assert restored.status == self.plan.status
        assert restored.metadata == self.plan.metadata
        assert len(restored.tasks) == 2
        
        # Check tasks were restored
        restored_t1 = restored.get_task("t1")
        assert restored_t1 is not None
        assert restored_t1.name == "Task One"
        assert restored_t1.dependencies == []
        
        restored_t2 = restored.get_task("t2")
        assert restored_t2 is not None
        assert restored_t2.name == "Task Two"
        assert restored_t2.dependencies == ["t1"]

    def test_nested_subplan_serialization(self):
        """Test that nested sub-plans serialize and deserialize correctly."""
        # Create a deeply nested structure
        level3 = ConcretePlan(plan_id="l3", name="Level 3 Plan")
        level3.add_task(SimpleTask("l3-t1", "L3 Task"))
        
        level2 = ConcretePlan(plan_id="l2", name="Level 2 Plan")
        level2.add_task(level3)
        
        level1 = ConcretePlan(plan_id="l1", name="Level 1 Plan")
        level1.add_task(SimpleTask("l1-t1", "L1 Task"))
        level1.add_task(level2)
        
        self.plan.add_task(level1)
        self.plan.add_task(SimpleTask("root-t1", "Root Task"))
        
        # Serialize
        data = self.plan.to_dict()
        
        # Verify the nested structure in serialized data
        assert "l1" in data["tasks"]
        assert data["tasks"]["l1"]["type"] == "subplan"
        
        l1_data = data["tasks"]["l1"]["data"]
        assert "l2" in l1_data["tasks"]
        assert l1_data["tasks"]["l2"]["type"] == "subplan"
        
        l2_data = l1_data["tasks"]["l2"]["data"]
        assert "l3" in l2_data["tasks"]
        assert l2_data["tasks"]["l3"]["type"] == "subplan"
        
        # Deserialize back
        def task_factory(task_data):
            return SimpleTask(
                task_data["task_id"],
                task_data["name"],
                task_data.get("description", ""),
                task_data.get("dependencies", []),
                task_data.get("status", TaskStatus.PENDING.value)
            )
        
        restored = ConcretePlan.from_dict(data, task_factory)
        
        # Verify nesting was preserved
        restored_l1 = restored.get_task("l1")
        assert isinstance(restored_l1, ConcretePlan)
        
        restored_l2 = restored_l1.get_task("l2")
        assert isinstance(restored_l2, ConcretePlan)
        
        restored_l3 = restored_l2.get_task("l3")
        assert isinstance(restored_l3, ConcretePlan)
        
        restored_l3_t1 = restored_l3.get_task("l3-t1")
        assert restored_l3_t1 is not None
        assert restored_l3_t1.name == "L3 Task"

    def test_updated_at_changes_on_modification(self):
        """Test that updated_at timestamp changes when plan is modified."""
        original_updated = self.plan.updated_at
        original_created = self.plan.created_at
        
        # Modify the plan
        self.plan.name = "Updated Name"
        
        assert self.plan.updated_at > original_updated
        assert self.plan.created_at == original_created

    def test_list_tasks_returns_all_tasks(self):
        """Test that list_tasks returns all tasks in the plan."""
        task1 = SimpleTask("t1", "Task 1")
        task2 = SimpleTask("t2", "Task 2")
        self.plan.add_task(task1)
        self.plan.add_task(task2)
        
        tasks = self.plan.list_tasks()
        assert len(tasks) == 2
        assert any(t.task_id == "t1" for t in tasks)
        assert any(t.task_id == "t2" for t in tasks)
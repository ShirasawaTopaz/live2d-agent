"""Tests for PlanValidator: dependency validation, cycle detection, depth checking."""

from typing import List, Optional
from dataclasses import dataclass


from internal.agent.planning.validator import PlanValidator, ValidationResult
from internal.agent.planning.base import Plan, Task


# Create concrete implementations for testing
@dataclass
class TestTask(Task):
    """Concrete Task implementation for testing."""
    _task_id: str
    _name: str
    _description: str
    _dependencies: List[str]
    _status: str = "pending"
    
    @property
    def task_id(self) -> str:
        return self._task_id
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def description(self) -> str:
        return self._description
    
    @property
    def dependencies(self) -> List[str]:
        return self._dependencies
    
    @property
    def status(self) -> str:
        return self._status
    
    async def execute(self, context):
        from internal.agent.planning.base import TaskResult
        return TaskResult(
            task_id=self._task_id,
            success=True,
            result=None
        )


@dataclass
class TestPlan(Plan):
    """Concrete Plan implementation for testing."""
    _plan_id: str
    _name: str
    _description: str
    _tasks: List[TestTask]
    
    @property
    def plan_id(self) -> str:
        return self._plan_id
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def description(self) -> str:
        return self._description
    
    @property
    def tasks(self) -> List[TestTask]:
        return self._tasks
    
    def add_task(self, task: Task) -> None:
        self._tasks.append(task)
    
    def remove_task(self, task_id: str) -> None:
        self._tasks = [t for t in self._tasks if t.task_id != task_id]
    
    def get_task(self, task_id: str) -> Optional[Task]:
        for task in self._tasks:
            if task.task_id == task_id:
                return task
        return None
    
    async def execute(self, context):
        results = []
        for task in self._tasks:
            result = await task.execute(context)
            results.append(result)
        return results


class TestValidationResult:
    """Tests for ValidationResult class."""

    def test_bool_returns_is_valid(self):
        """Test that __bool__ returns is_valid value."""
        result_valid = ValidationResult(is_valid=True, errors=[])
        assert bool(result_valid) is True
        assert result_valid

        result_invalid = ValidationResult(is_valid=False, errors=["error"])
        assert bool(result_invalid) is False
        assert not result_invalid

    def test_stores_errors_correctly(self):
        """Test that errors are stored correctly."""
        errors = ["error1", "error2"]
        result = ValidationResult(is_valid=False, errors=errors)
        assert result.errors == errors


class TestPlanValidatorValidation:
    """Tests for PlanValidator.validate() with various scenarios."""

    def test_empty_plan_passes_validation(self):
        """Test that an empty plan is valid."""
        validator = PlanValidator()
        plan = TestPlan(
            _plan_id="test",
            _name="Test Plan",
            _description="Empty plan",
            _tasks=[]
        )
        result = validator.validate(plan)
        assert result.is_valid is True
        assert len(result.errors) == 0
        assert bool(result) is True  # Test __bool__ magic method

    def test_valid_plan_with_dependencies_passes(self):
        """Test a valid plan with proper dependencies passes validation."""
        validator = PlanValidator()
        tasks = [
            TestTask("task1", "Task 1", "First task", []),
            TestTask("task2", "Task 2", "Second task", ["task1"]),
            TestTask("task3", "Task 3", "Third task", ["task1", "task2"]),
        ]
        plan = TestPlan(
            _plan_id="test",
            _name="Test Plan",
            _description="Valid plan with dependencies",
            _tasks=tasks
        )
        result = validator.validate(plan)
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_duplicate_task_id_fails(self):
        """Test that duplicate task_ids causes validation failure."""
        validator = PlanValidator()
        tasks = [
            TestTask("task1", "Task 1", "First task", []),
            TestTask("task1", "Task 1 Duplicate", "Duplicate", []),
        ]
        plan = TestPlan(
            _plan_id="test",
            _name="Test Plan",
            _description="Plan with duplicate task_ids",
            _tasks=tasks
        )
        result = validator.validate(plan)
        assert result.is_valid is False
        assert any("Duplicate task_id: task1" in err for err in result.errors)

    def test_dependency_on_non_existent_task_fails(self):
        """Test that dependency on non-existent task fails validation."""
        validator = PlanValidator()
        tasks = [
            TestTask("task1", "Task 1", "Task", ["missing_task"]),
        ]
        plan = TestPlan(
            _plan_id="test",
            _name="Test Plan",
            _description="Plan with missing dependency",
            _tasks=tasks
        )
        result = validator.validate(plan)
        assert result.is_valid is False
        assert any("depends on non-existent task: missing_task" in err for err in result.errors)

    def test_cyclic_detection_direct_cycle(self):
        """Test direct cycle A -> B -> A is detected."""
        validator = PlanValidator()
        tasks = [
            TestTask("A", "Task A", "A depends on B", ["B"]),
            TestTask("B", "Task B", "B depends on A", ["A"]),
        ]
        plan = TestPlan(
            _plan_id="test",
            _name="Test Plan",
            _description="Plan with cyclic dependency",
            _tasks=tasks
        )
        result = validator.validate(plan)
        assert result.is_valid is False
        assert any("Cyclic dependency detected" in err for err in result.errors)

    def test_cyclic_detection_indirect_cycle(self):
        """Test indirect cycle A -> B -> C -> A is detected."""
        validator = PlanValidator()
        tasks = [
            TestTask("A", "Task A", "A", ["B"]),
            TestTask("B", "Task B", "B", ["C"]),
            TestTask("C", "Task C", "C", ["A"]),
        ]
        plan = TestPlan(
            _plan_id="test",
            _name="Test Plan",
            _description="Indirect cycle",
            _tasks=tasks
        )
        result = validator.validate(plan)
        assert result.is_valid is False
        assert any("Cyclic dependency detected" in err for err in result.errors)

    def test_cyclic_detection_self_dependency(self):
        """Test that a task depending on itself is detected as a cycle."""
        validator = PlanValidator()
        tasks = [
            TestTask("A", "Task A", "A depends on itself", ["A"]),
        ]
        plan = TestPlan(
            _plan_id="test",
            _name="Test Plan",
            _description="Self dependency",
            _tasks=tasks
        )
        result = validator.validate(plan)
        assert result.is_valid is False
        assert any("Cyclic dependency detected" in err for err in result.errors)

    def test_max_depth_not_exceeded_passes(self):
        """Test that when depth is under max_depth it passes."""
        validator = PlanValidator(max_depth=5)
        # Depth chain: 1 -> 2 -> 3 -> 4 (depth 4 < 5)
        tasks = [
            TestTask("1", "Task 1", "", []),
            TestTask("2", "Task 2", "", ["1"]),
            TestTask("3", "Task 3", "", ["2"]),
            TestTask("4", "Task 4", "", ["3"]),
        ]
        plan = TestPlan(
            _plan_id="test",
            _name="Test Plan",
            _description="Depth under limit",
            _tasks=tasks
        )
        result = validator.validate(plan)
        assert result.is_valid is True

    def test_max_depth_exceeded_fails(self):
        """Test that when max depth is exceeded, validation fails."""
        validator = PlanValidator(max_depth=3)
        # Depth chain: 1 -> 2 -> 3 -> 4 (depth 4 > 3)
        tasks = [
            TestTask("1", "Task 1", "", []),
            TestTask("2", "Task 2", "", ["1"]),
            TestTask("3", "Task 3", "", ["2"]),
            TestTask("4", "Task 4", "", ["3"]),
        ]
        plan = TestPlan(
            _plan_id="test",
            _name="Test Plan",
            _description="Depth over limit",
            _tasks=tasks
        )
        result = validator.validate(plan)
        assert result.is_valid is False
        assert any("Maximum hierarchy depth exceeded" in err for err in result.errors)

    def test_max_depth_multiple_branches(self):
        """Test max depth calculation with multiple branches."""
        validator = PlanValidator(max_depth=4)
        tasks = [
            TestTask("root1", "Root 1", "", []),
            TestTask("root2", "Root 2", "", []),
            TestTask("child1a", "Child 1A", "", ["root1"]),
            TestTask("child1b", "Child 1B", "", ["root2"]),
            TestTask("grandchild1a", "Grandchild 1A", "", ["child1a"]),
            TestTask("greatgrand", "Great Grandchild", "", ["grandchild1a"]),
            # That's depth 4: root1 -> child1a -> grandchild1a -> greatgrand (4)
        ]
        plan = TestPlan(
            _plan_id="test",
            _name="Test Plan",
            _description="Multiple branches",
            _tasks=tasks
        )
        result = validator.validate(plan)
        assert result.is_valid is True

    def test_max_depth_multiple_branches_exceeded(self):
        """Test max depth catches the deepest branch when it exceeds."""
        validator = PlanValidator(max_depth=3)
        tasks = [
            TestTask("root1", "Root 1", "", []),
            TestTask("root2", "Root 2", "", []),
            TestTask("child1a", "Child 1A", "", ["root1"]),
            TestTask("child1b", "Child 1B", "", ["root2"]),
            TestTask("grandchild1a", "Grandchild 1A", "", ["child1a"]),
            TestTask("greatgrand", "Great Grandchild", "", ["grandchild1a"]),
            # That's depth 4 > 3
        ]
        plan = TestPlan(
            _plan_id="test",
            _name="Test Plan",
            _description="Deepest branch exceeds",
            _tasks=tasks
        )
        result = validator.validate(plan)
        assert result.is_valid is False

    def test_multiple_errors_reported(self):
        """Test that multiple validation errors are all reported."""
        validator = PlanValidator()
        tasks = [
            TestTask("A", "A", "", ["missing"]),  # Missing dependency
            TestTask("A", "A duplicate", "", []),  # Duplicate ID
            TestTask("B", "B", "", ["C"]),
            TestTask("C", "C", "", ["B"]),  # Cycle B -> C -> B
        ]
        plan = TestPlan(
            _plan_id="test",
            _name="Test Plan",
            _description="Multiple errors",
            _tasks=tasks
        )
        result = validator.validate(plan)
        assert result.is_valid is False
        assert len(result.errors) >= 3  # At least: duplicate + missing + cycle
        assert any("Duplicate task_id: A" in err for err in result.errors)
        assert any("depends on non-existent task: missing" in err for err in result.errors)
        assert any("Cyclic dependency detected" in err for err in result.errors)


class TestPlanValidatorFindReadyTasks:
    """Tests for find_ready_tasks method."""

    def test_empty_plan_returns_empty(self):
        """Test empty plan returns empty ready list."""
        validator = PlanValidator()
        plan = TestPlan(
            _plan_id="test",
            _name="Test",
            _description="Empty",
            _tasks=[]
        )
        ready = validator.find_ready_tasks(plan, [])
        assert ready == []

    def test_root_tasks_are_ready_when_no_completed(self):
        """Test tasks without dependencies are immediately ready."""
        validator = PlanValidator()
        tasks = [
            TestTask("task1", "Task 1", "", []),
            TestTask("task2", "Task 2", "", []),
        ]
        plan = TestPlan(
            _plan_id="test",
            _name="Test",
            _description="Two root tasks",
            _tasks=tasks
        )
        ready = validator.find_ready_tasks(plan, [])
        assert len(ready) == 2
        assert {t.task_id for t in ready} == {"task1", "task2"}

    def test_only_tasks_with_all_deps_completed_are_ready(self):
        """Test that only tasks with all dependencies completed are ready."""
        validator = PlanValidator()
        tasks = [
            TestTask("task1", "Task 1", "", []),
            TestTask("task2", "Task 2", "", ["task1"]),
            TestTask("task3", "Task 3", "", ["task2"]),
        ]
        plan = TestPlan(
            _plan_id="test",
            _name="Test",
            _description="Chain",
            _tasks=tasks
        )
        
        # After 0 completed: only task1 is ready
        ready = validator.find_ready_tasks(plan, [])
        assert len(ready) == 1
        assert ready[0].task_id == "task1"
        
        # After task1 completed: task2 is ready
        ready = validator.find_ready_tasks(plan, ["task1"])
        assert len(ready) == 1
        assert ready[0].task_id == "task2"
        
        # After task1 and task2 completed: task3 is ready
        ready = validator.find_ready_tasks(plan, ["task1", "task2"])
        assert len(ready) == 1
        assert ready[0].task_id == "task3"
        
        # After all completed: none ready
        ready = validator.find_ready_tasks(plan, ["task1", "task2", "task3"])
        assert len(ready) == 0

    def test_task_with_multiple_dependencies_only_ready_when_all_done(self):
        """Test a task that depends on multiple tasks is only ready when all are done."""
        validator = PlanValidator()
        tasks = [
            TestTask("A", "A", "", []),
            TestTask("B", "B", "", []),
            TestTask("C", "C", "", ["A", "B"]),
        ]
        plan = TestPlan(
            _plan_id="test",
            _name="Test",
            _description="Join",
            _tasks=tasks
        )
        
        # Only A completed: C not ready
        ready = validator.find_ready_tasks(plan, ["A"])
        assert len(ready) == 1  # Still B is ready
        assert {t.task_id for t in ready} == {"B"}
        
        # Only B completed: C not ready
        ready = validator.find_ready_tasks(plan, ["B"])
        assert len(ready) == 1  # Still A is ready
        assert {t.task_id for t in ready} == {"A"}
        
        # Both A and B completed: C is ready
        ready = validator.find_ready_tasks(plan, ["A", "B"])
        assert len(ready) == 1
        assert ready[0].task_id == "C"

    def test_completed_tasks_are_not_included(self):
        """Test that already completed tasks are not included in ready."""
        validator = PlanValidator()
        tasks = [
            TestTask("A", "A", "", []),
            TestTask("B", "B", "", ["A"]),
        ]
        plan = TestPlan(
            _plan_id="test",
            _name="Test",
            _description="Two tasks",
            _tasks=tasks
        )
        
        # A is already completed, so only B is ready
        ready = validator.find_ready_tasks(plan, ["A"])
        assert len(ready) == 1
        assert ready[0].task_id == "B"
        
        # Neither completed: A is ready
        ready = validator.find_ready_tasks(plan, [])
        assert len(ready) == 1
        assert ready[0].task_id == "A"

    def test_parallel_tasks_multiple_ready(self):
        """Test that multiple independent tasks can be ready at the same time."""
        validator = PlanValidator()
        tasks = [
            TestTask("A", "A", "", []),
            TestTask("B", "B", "", []),
            TestTask("C", "C", "", []),
            TestTask("D", "D", "", ["A", "B"]),
        ]
        plan = TestPlan(
            _plan_id="test",
            _name="Test",
            _description="Parallel tasks",
            _tasks=tasks
        )
        
        ready = validator.find_ready_tasks(plan, [])
        assert len(ready) == 3
        assert {t.task_id for t in ready} == {"A", "B", "C"}
        
        # After A and B completed, D becomes ready
        ready = validator.find_ready_tasks(plan, ["A", "B"])
        assert len(ready) == 2  # C is still not completed
        assert {t.task_id for t in ready} == {"C", "D"}

    def test_disconnected_graph_all_roots_are_ready(self):
        """Test that in a disconnected graph, all root tasks are ready."""
        validator = PlanValidator()
        tasks = [
            TestTask("A", "A", "", []),
            TestTask("B", "B", "", ["A"]),
            TestTask("C", "C", "", []),
            TestTask("D", "D", "", ["C"]),
        ]
        plan = TestPlan(
            _plan_id="test",
            _name="Test",
            _description="Disconnected graph",
            _tasks=tasks
        )
        
        ready = validator.find_ready_tasks(plan, [])
        assert len(ready) == 2
        assert {t.task_id for t in ready} == {"A", "C"}

    def test_diamond_dependency_pattern(self):
        """Test find_ready_tasks works with diamond dependency pattern."""
        # Diamond pattern: A -> B, A -> C, B -> D, C -> D
        validator = PlanValidator()
        tasks = [
            TestTask("A", "A", "", []),
            TestTask("B", "B", "", ["A"]),
            TestTask("C", "C", "", ["A"]),
            TestTask("D", "D", "", ["B", "C"]),
        ]
        plan = TestPlan(
            _plan_id="test",
            _name="Test",
            _description="Diamond pattern",
            _tasks=tasks
        )
        
        # Start: only A ready
        ready = validator.find_ready_tasks(plan, [])
        assert len(ready) == 1
        assert ready[0].task_id == "A"
        
        # A done: B and C ready
        ready = validator.find_ready_tasks(plan, ["A"])
        assert len(ready) == 2
        assert {t.task_id for t in ready} == {"B", "C"}
        
        # A + B done: C still ready, D not ready (needs C too)
        ready = validator.find_ready_tasks(plan, ["A", "B"])
        assert len(ready) == 1
        assert ready[0].task_id == "C"
        
        # A + B + C done: D now ready
        ready = validator.find_ready_tasks(plan, ["A", "B", "C"])
        assert len(ready) == 1
        assert ready[0].task_id == "D"

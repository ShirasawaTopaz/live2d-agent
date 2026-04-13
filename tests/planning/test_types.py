"""Tests for all planning types: enums, TaskDependency, TaskResult, PlanContext."""

from internal.agent.planning.types import (
    TaskStatus,
    PlanStatus,
    DependencyCondition,
    TaskDependency,
    TaskResult,
    PlanContext,
)


class TestTaskStatusEnum:
    """Tests for TaskStatus enum."""

    def test_enum_values(self):
        """Test all TaskStatus enum values are correctly defined."""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.CANCELLED.value == "cancelled"

    def test_enum_serialization(self):
        """Test that TaskStatus can be serialized/deserialized by value."""
        for status in TaskStatus:
            # Deserialize from value
            deserialized = TaskStatus(status.value)
            assert deserialized == status

    def test_enum_comparison(self):
        """Test enum comparison works correctly."""
        assert TaskStatus.PENDING != TaskStatus.COMPLETED
        assert TaskStatus.PENDING == TaskStatus.PENDING


class TestPlanStatusEnum:
    """Tests for PlanStatus enum."""

    def test_enum_values(self):
        """Test all PlanStatus enum values are correctly defined."""
        assert PlanStatus.PENDING.value == "pending"
        assert PlanStatus.VALIDATING.value == "validating"
        assert PlanStatus.RUNNING.value == "running"
        assert PlanStatus.COMPLETED.value == "completed"
        assert PlanStatus.FAILED.value == "failed"
        assert PlanStatus.CANCELLED.value == "cancelled"

    def test_enum_serialization(self):
        """Test that PlanStatus can be serialized/deserialized by value."""
        for status in PlanStatus:
            # Deserialize from value
            deserialized = PlanStatus(status.value)
            assert deserialized == status


class TestDependencyConditionEnum:
    """Tests for DependencyCondition enum."""

    def test_enum_values(self):
        """Test all DependencyCondition enum values are correctly defined."""
        assert DependencyCondition.SUCCESS.value == "success"
        assert DependencyCondition.FAILURE.value == "failure"
        assert DependencyCondition.ANY.value == "any"

    def test_enum_serialization(self):
        """Test that DependencyCondition can be serialized/deserialized by value."""
        for condition in DependencyCondition:
            deserialized = DependencyCondition(condition.value)
            assert deserialized == condition


class TestTaskDependency:
    """Tests for TaskDependency dataclass."""

    def test_instantiate_with_default_condition(self):
        """Test instantiation with default condition (SUCCESS)."""
        dep = TaskDependency(task_id="task1")
        assert dep.task_id == "task1"
        assert dep.condition == DependencyCondition.SUCCESS

    def test_instantiate_with_custom_condition(self):
        """Test instantiation with custom condition."""
        dep = TaskDependency(task_id="task1", condition=DependencyCondition.ANY)
        assert dep.task_id == "task1"
        assert dep.condition == DependencyCondition.ANY

    def test_to_dict(self):
        """Test to_dict serialization."""
        dep = TaskDependency(task_id="task1", condition=DependencyCondition.FAILURE)
        data = dep.to_dict()
        assert data["task_id"] == "task1"
        assert data["condition"] == "failure"

    def test_from_dict_default_condition(self):
        """Test from_dict deserialization when condition is missing (uses default)."""
        data = {"task_id": "task1"}
        dep = TaskDependency.from_dict(data)
        assert dep.task_id == "task1"
        assert dep.condition == DependencyCondition.SUCCESS

    def test_from_dict_with_condition(self):
        """Test from_dict deserialization with explicit condition."""
        data = {"task_id": "task1", "condition": "any"}
        dep = TaskDependency.from_dict(data)
        assert dep.task_id == "task1"
        assert dep.condition == DependencyCondition.ANY

    def test_round_trip_serialization(self):
        """Test serialization -> deserialization round trip preserves data."""
        original = TaskDependency(task_id="dep1", condition=DependencyCondition.ANY)
        data = original.to_dict()
        restored = TaskDependency.from_dict(data)
        assert original.task_id == restored.task_id
        assert original.condition == restored.condition


class TestTaskResult:
    """Tests for TaskResult dataclass."""

    def test_instantiate_success_with_output(self):
        """Test instantiation for successful task with output."""
        result = TaskResult(
            task_id="task1",
            success=True,
            output={"key": "value"},
            error=None
        )
        assert result.task_id == "task1"
        assert result.success is True
        assert result.output == {"key": "value"}
        assert result.error is None

    def test_instantiate_failure_with_error(self):
        """Test instantiation for failed task with error message."""
        result = TaskResult(
            task_id="task1",
            success=False,
            output=None,
            error="Something went wrong",
            traceback="Traceback..."
        )
        assert result.task_id == "task1"
        assert result.success is False
        assert result.output is None
        assert result.error == "Something went wrong"
        assert result.traceback == "Traceback..."

    def test_instantiate_with_minimal_args(self):
        """Test instantiation with only required arguments."""
        result = TaskResult(task_id="task1", success=True)
        assert result.task_id == "task1"
        assert result.success is True
        assert result.output is None
        assert result.error is None
        assert result.traceback is None

    def test_to_dict(self):
        """Test to_dict serialization using dataclasses.asdict."""
        result = TaskResult(
            task_id="task1",
            success=True,
            output=42,
            error=None
        )
        data = result.to_dict()
        assert data["task_id"] == "task1"
        assert data["success"] is True
        assert data["output"] == 42
        assert data["error"] is None

    def test_from_dict(self):
        """Test from_dict deserialization."""
        data = {
            "task_id": "task1",
            "success": True,
            "output": {"result": 42},
            "error": None
        }
        result = TaskResult.from_dict(data)
        assert result.task_id == "task1"
        assert result.success is True
        assert result.output == {"result": 42}
        assert result.error is None
        assert result.success is True
        assert result.output == {"result": 42}
        assert result.error is None

    def test_from_dict_with_optional_fields_missing(self):
        """Test from_dict when optional fields are missing."""
        data = {
            "task_id": "task1",
            "success": False
        }
        result = TaskResult.from_dict(data)
        assert result.task_id == "task1"
        assert result.success is False
        assert result.output is None
        assert result.error is None

    def test_round_trip_serialization(self):
        """Test serialization -> deserialization round trip preserves data."""
        original = TaskResult(
            task_id="result1",
            success=True,
            output={"data": [1, 2, 3]},
            error=None,
            traceback=None
        )
        data = original.to_dict()
        restored = TaskResult.from_dict(data)
        assert original.task_id == restored.task_id
        assert original.success == restored.success
        assert original.output == restored.output
        assert original.error == restored.error
        assert original.traceback == restored.traceback


class TestPlanContext:
    """Tests for PlanContext dataclass."""

    def test_instantiate(self):
        """Test basic instantiation."""
        mock_logger = object()
        mock_config = object()
        context = PlanContext(
            plan_id="plan1",
            task_outputs={"task1": "output1"},
            logger=mock_logger,
            config=mock_config
        )
        assert context.plan_id == "plan1"
        assert context.task_outputs == {"task1": "output1"}
        assert context.logger is mock_logger
        assert context.config is mock_config

    def test_instantiate_empty_task_outputs(self):
        """Test instantiation with empty task outputs."""
        mock_logger = object()
        mock_config = object()
        context = PlanContext(
            plan_id="plan1",
            task_outputs={},
            logger=mock_logger,
            config=mock_config
        )
        assert context.task_outputs == {}

    def test_to_dict_only_serializes_serializable_fields(self):
        """Test to_dict only serializes plan_id and task_outputs (skips logger/config)."""
        mock_logger = object()
        mock_config = object()
        context = PlanContext(
            plan_id="plan1",
            task_outputs={"task1": "output1"},
            logger=mock_logger,
            config=mock_config
        )
        data = context.to_dict()
        assert data["plan_id"] == "plan1"
        assert data["task_outputs"] == {"task1": "output1"}
        assert "logger" not in data
        assert "config" not in data

    def test_from_dict(self):
        """Test from_dict reconstruction with logger/config injection."""
        mock_logger = object()
        mock_config = {"key": "value"}
        data = {
            "plan_id": "plan1",
            "task_outputs": {"task1": "result1"}
        }
        context = PlanContext.from_dict(data, mock_logger, mock_config)
        assert context.plan_id == "plan1"
        assert context.task_outputs == {"task1": "result1"}
        assert context.logger is mock_logger
        assert context.config == mock_config

    def test_from_dict_defaults_empty_task_outputs(self):
        """Test from_dict defaults to empty dict when task_outputs is missing."""
        mock_logger = object()
        mock_config = object()
        data = {
            "plan_id": "plan1"
        }
        context = PlanContext.from_dict(data, mock_logger, mock_config)
        assert context.plan_id == "plan1"
        assert context.task_outputs == {}
        assert context.logger is mock_logger
        assert context.config is mock_config

    def test_round_trip_serialization(self):
        """Test serialization -> deserialization round trip."""
        mock_logger = object()
        mock_config = object()
        original = PlanContext(
            plan_id="plan123",
            task_outputs={"a": 1, "b": 2},
            logger=mock_logger,
            config=mock_config
        )
        data = original.to_dict()
        restored = PlanContext.from_dict(data, mock_logger, mock_config)
        assert original.plan_id == restored.plan_id
        assert original.task_outputs == restored.task_outputs
        # logger and config are injected externally, so check identity preserved
        assert original.logger is restored.logger
        assert original.config is restored.config

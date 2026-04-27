"""Integration tests for the full Agent with planning support."""

import tempfile
import pytest
import asyncio
from typing import Any, MutableMapping, AsyncIterator

from internal.agent.agent import Agent
from internal.agent.agent_support.trait import ModelTrait
from internal.agent.planning.base import Task, TaskResult as PlanTaskResult
from internal.agent.planning.plan import ConcretePlan
from internal.agent.planning.types import PlanStatus, TaskStatus
from internal.agent.planning.storage.base import PlanStorage
from internal.agent.planning.storage.json import JSONPlanStorage
from internal.config.config import AIModelConfig, AIModelType, PlanningConfig, MemoryConfig


class MockModel(ModelTrait):
    """Mock model implementation for testing."""
    
    def __init__(self, config: AIModelConfig):
        self.config = config
        self.history: list[MutableMapping[str, Any]] = []
        self._tools_supported = False
    
    async def chat(self, message: Any, tools: list[dict] | None = None) -> dict:
        """Simple mock chat that returns a fixed response."""
        if message is None and self.history:
            # Continue from previous turn, just return a continuation
            last_msg = self.history[-1] if self.history else None
            return {
                "role": "assistant",
                "content": f"Mock response to: {last_msg.get('content', '') if last_msg else ''}"
            }
        return {
            "role": "assistant",
            "content": f"Mock response to: {str(message)}"
        }
    
    def stream_chat(self, message: Any, tools: list[dict] | None = None) -> AsyncIterator[dict]:
        """Mock stream chat that just returns a single chunk."""
        async def mock_stream():
            yield {"content": "Mock streaming response", "done": True}
        return mock_stream()


def create_mock_model_config() -> AIModelConfig:
    """Create a mock model config for testing."""
    return AIModelConfig(
        name="mock-model",
        model="mock",
        system_prompt="You are a helpful assistant.",
        type=AIModelType.OllamaModel,
        default=True,
        config={},
        temperature=0.7
    )


class SimpleTaskForTest(Task):
    """Simple concrete Task implementation that just records execution."""
    
    def __init__(self, task_id: str, name: str, description: str = "",
                 dependencies: list[str] | None = None, should_fail: bool = False):
        self._task_id = task_id
        self._name = name
        self._description = description
        self._dependencies = dependencies or []
        self._status = TaskStatus.PENDING.value
        self.should_fail = should_fail
        self.executed = False
        self.output = None
    
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
    
    @status.setter
    def status(self, value: str) -> None:
        self._status = value
    
    async def execute(self, context):
        self.executed = True
        if self.should_fail:
            return PlanTaskResult(
                task_id=self._task_id,
                success=False,
                result=None,
                error="Task failed as expected"
            )
        return PlanTaskResult(
            task_id=self._task_id,
            success=True,
            result=f"Task {self._task_id} executed successfully",
            error=None
        )


class TestAgentIntegrationWithPlanner:
    """Integration tests for Agent with planner integration."""
    
    def setup_method(self):
        """Set up test fixtures with temporary storage."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.mock_model_config = create_mock_model_config()
    
    def teardown_method(self):
        """Clean up temporary directory."""
        self.temp_dir.cleanup()
    
    def create_planning_config(self, enabled: bool):
        """Create a planning config with temporary storage."""
        if not enabled:
            return PlanningConfig(enabled=False)
        
        return PlanningConfig(
            enabled=True,
            storage_type="json",
            storage_path=f"{self.temp_dir.name}/plans.json",
            max_concurrency=2,
            max_plan_depth=10,
            auto_save=True
        )
    
    def test_agent_has_planner_initialized(self):
        """Test that Agent has planner properly initialized when planning enabled."""
        planning_config = self.create_planning_config(enabled=True)
        agent = Agent(MockModel(self.mock_model_config), None, None, planning_config)
        
        assert agent.planner is not None
        assert agent.planner.storage is not None
        assert agent.planner.agent is agent
    
    def test_agent_no_planner_when_disabled(self):
        """Test that planner is None when planning not enabled."""
        planning_config = self.create_planning_config(enabled=False)
        agent = Agent(MockModel(self.mock_model_config), None, None, planning_config)
        
        assert agent.planner is None
    
    @pytest.mark.asyncio
    async def test_simple_plan_execution_through_agent(self):
        """Test a simple two-task plan with dependency executes correctly through agent.execute_plan."""
        planning_config = self.create_planning_config(enabled=True)
        agent = Agent(MockModel(self.mock_model_config), None, None, planning_config)
        
        assert agent.planner is not None
        # Initialize planner storage
        await agent.planner.storage.init()
        
        # Create a concrete plan
        plan = ConcretePlan(
            plan_id="test-simple-plan",
            name="Simple Test Plan",
            description="A simple two-task plan with dependency"
        )
        
        # Create tasks with dependency: task2 depends on task1
        task1 = SimpleTaskForTest("task1", "First Task", "First task to execute")
        task2 = SimpleTaskForTest("task2", "Second Task", "Second task that depends on first", ["task1"])
        
        plan.add_task(task1)
        plan.add_task(task2)
        
        # Execute through agent
        final_status = await agent.execute_plan(plan)
        
        # Verify execution completed successfully
        assert final_status == PlanStatus.COMPLETED
        assert plan.plan_status == PlanStatus.COMPLETED
        
        # Both tasks should have been executed by our test task
        assert task1.executed is True
        assert task2.executed is True
    
    @pytest.mark.asyncio
    async def test_plan_persisted_after_execution(self):
        """Test that after execution completes, plan is persisted to storage."""
        planning_config = self.create_planning_config(enabled=True)
        agent = Agent(MockModel(self.mock_model_config), None, None, planning_config)
        
        assert agent.planner is not None
        # Initialize planner storage
        await agent.planner.storage.init()
        
        # Create and execute a simple plan
        plan = ConcretePlan(
            plan_id="test-persist-plan",
            name="Persisted Plan",
            description="Plan to test persistence"
        )
        task1 = SimpleTaskForTest("task1", "Task 1")
        task2 = SimpleTaskForTest("task2", "Task 2", dependencies=["task1"])
        plan.add_task(task1)
        plan.add_task(task2)
        
        # Execute and verify completion
        final_status = await agent.execute_plan(plan)
        assert final_status == PlanStatus.COMPLETED
        assert task1.executed is True
        assert task2.executed is True
        
        # Check that the plan ID exists in storage
        if hasattr(agent.planner.storage, '_plans'):
            # JSON storage keeps plans in memory
            assert "test-persist-plan" in agent.planner.storage._plans
            stored_data = agent.planner.storage._plans["test-persist-plan"]
            assert stored_data is not None
            assert stored_data["plan_id"] == "test-persist-plan"
            assert stored_data["name"] == "Persisted Plan"
            assert len(stored_data["tasks"]) == 2
        else:
            # For SQLite check that count increases and plan is in list
            plan_ids = await agent.planner.storage.list_plans()
            assert "test-persist-plan" in plan_ids
            count = await agent.planner.storage.count()
            assert count >= 1
    
    @pytest.mark.asyncio
    async def test_existing_chat_functionality_unchanged(self):
        """Test that existing chat functionality still works when planner is enabled."""
        # Create agent with planner enabled but we're just testing chat still works
        planning_config = self.create_planning_config(enabled=True)
        
        # Enable memory for this test - MemoryConfig doesn't take constructor arguments
        memory_config = MemoryConfig()
        memory_config.enabled = False
        
        agent = Agent(MockModel(self.mock_model_config), memory_config, None, planning_config)
        
        # Create a mock websocket that just records messages
        class MockWS:
            called = False
            last_message = None
            
            async def send(self, data):
                self.called = True
                self.last_message = data
                return None
        
        mock_ws = MockWS()
        
         # Execute chat - mock_ws is compatible due to duck typing
         response = await agent.chat("Hello, how are you?", mock_ws)  # type: ignore
        
        # Verify chat completed successfully
        assert response is not None
        assert "role" in response
        assert "content" in response
        assert response["role"] == "assistant"
        assert "Mock" in response["content"]
        
        # Planner is still initialized even though we used chat
        assert agent.planner is not None
        assert agent.planner.agent is agent
        
        # Tool registry still works
        assert len(agent.tool_registry.tools) > 0

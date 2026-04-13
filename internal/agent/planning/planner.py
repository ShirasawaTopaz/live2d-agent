"""
Planner - Main orchestrator interface for task planning and execution.
Coordinates validation, execution, and persistence of execution plans.
"""

import asyncio
import logging
from typing import Any, Optional, Callable, Dict, TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    from internal.agent.agent import Agent
from internal.agent.planning.base import Plan, PlanContext
from internal.agent.planning.plan import ConcretePlan
from internal.agent.planning.validator import PlanValidator, ValidationResult
from internal.agent.planning.executor import PlanExecutor
from internal.agent.planning.registry import PlanRegistry
from internal.agent.planning.storage.base import PlanStorage
from internal.agent.planning.types import PlanStatus

logger = logging.getLogger(__name__)


@dataclass
class PlannerConfig:
    """Configuration for the Planner."""
    max_concurrency: int = 4
    max_plan_depth: int = 10
    auto_save: bool = True
    """Auto-save after each step completion."""
    

class StatusCallback:
    """Callback type for plan status updates."""
    def __call__(self, plan: Plan, status: PlanStatus, step: Optional[str] = None) -> None:
        ...


class Planner:
    """Main Planner orchestrator that coordinates plan execution.
    
    Responsibilities:
    - Holds references to all components: storage, registry, executor, validator
    - Creates new plans from templates
    - Validates plans before execution
    - Executes plans through the executor
    - Saves plan state after each step
    - Supports dynamic modification during execution
    - Integrates with agent to provide tool access
    - Provides status updates via callbacks
    """
    
    def __init__(
        self,
        storage: PlanStorage,
        registry: Optional[PlanRegistry] = None,
        config: Optional[PlannerConfig] = None,
        agent: Optional[Agent] = None,
    ):
        """Initialize the Planner.
        
        Args:
            storage: Plan storage backend for persistence
            registry: Optional plan registry for template lookup
            config: Optional planner configuration
            agent: Optional agent instance for tool integration
        """
        self.storage = storage
        self.registry = registry or PlanRegistry()
        self.config = config or PlannerConfig()
        self.agent = agent
        
        # Create validator with configured max depth
        self.validator = PlanValidator(max_depth=self.config.max_plan_depth)
        
        # Create executor with configured max concurrency
        self.executor = PlanExecutor(
            max_concurrency=self.config.max_concurrency,
            validator=self.validator
        )
        
        # Status callback
        self._status_callback: Optional[StatusCallback] = None
        
        # Track currently executing plan
        self._current_plan: Optional[Plan] = None
        self._execution_lock = asyncio.Lock()
        
        logger.debug(
            f"Planner initialized: max_concurrency={self.config.max_concurrency}, "
            f"max_depth={self.config.max_plan_depth}, auto_save={self.config.auto_save}"
        )
    
    def set_status_callback(self, callback: Optional[StatusCallback]) -> None:
        """Set callback for status updates during execution.
        
        Args:
            callback: The callback function to invoke on status changes
        """
        self._status_callback = callback
    
    def set_agent(self, agent: Agent) -> None:
        """Set or update the agent instance for tool integration.
        
        Args:
            agent: The agent instance to use
        """
        self.agent = agent
    
    def create_plan(
        self,
        name: str,
        description: str = "",
        plan_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ConcretePlan:
        """Create a new empty plan.
        
        Args:
            name: Name of the plan
            description: Description of what the plan does
            plan_id: Optional custom plan ID (generated if not provided)
            metadata: Optional metadata to attach to the plan
        
        Returns:
            A new ConcretePlan instance
        """
        plan = ConcretePlan(
            plan_id=plan_id,
            name=name,
            description=description,
            metadata=metadata,
        )
        
        logger.debug(f"Created new plan: {plan.plan_id} - {name}")
        return plan
    
    def get_plan_from_registry(self, plan_id: str) -> Optional[Plan]:
        """Get a plan template from the registry.
        
        Args:
            plan_id: The ID of the plan template
        
        Returns:
            The plan template if found, None otherwise
        """
        return self.registry.get(plan_id)
    
    def validate_plan(self, plan: Plan) -> ValidationResult:
        """Validate a plan before execution.
        
        Args:
            plan: The plan to validate
        
        Returns:
            ValidationResult with is_valid flag and any errors
        """
        return self.validator.validate(plan)
    
    async def save_plan(self, plan: Plan) -> None:
        """Save the current plan state to storage.
        
        Args:
            plan: The plan to save
        """
        await self.storage.save(plan)
        logger.debug(f"Saved plan to storage: {plan.plan_id}")
    
    async def load_plan(self, plan_id: str) -> Optional[Plan]:
        """Load a plan from storage by ID.
        
        Args:
            plan_id: The ID of the plan to load
        
        Returns:
            The loaded plan if found, None otherwise
        """
        return await self.storage.load(plan_id)
    
    async def delete_plan(self, plan_id: str) -> bool:
        """Delete a plan from storage.
        
        Args:
            plan_id: The ID of the plan to delete
        
        Returns:
            True if deleted successfully, False otherwise
        """
        return await self.storage.delete(plan_id)
    
    def modify_plan(
        self,
        plan: Plan,
        modifier: Callable[[Plan], None],
    ) -> None:
        """Modify a plan dynamically during execution and auto-save.
        
        Args:
            plan: The plan to modify
            modifier: A callable that modifies the plan in-place
        """
        modifier(plan)
        
        if self.config.auto_save:
            # Save after modification asynchronously
            asyncio.create_task(self.save_plan(plan))
            logger.debug(f"Plan modified and auto-saved: {plan.plan_id}")
    
    def _update_status(self, plan: Plan, status: PlanStatus, step: Optional[str] = None) -> None:
        """Update plan status and invoke callback if set.
        
        Args:
            plan: The plan whose status changed
            status: The new status
            step: Optional description of the current step
        """
        # Update plan status if it has a plan_status property
        if hasattr(plan, 'plan_status'):
            try:
                setattr(plan, 'plan_status', status)
            except AttributeError:
                pass
        
        # Invoke callback if set
        if self._status_callback:
            try:
                self._status_callback(plan, status, step)
            except Exception as e:
                logger.error(f"Error in status callback: {e}", exc_info=True)
    
    async def execute_plan(self, plan: Plan, context: Optional[PlanContext] = None) -> PlanStatus:
        """Execute a plan from start to finish.
        
        This method:
        1. Validates the plan
        2. Updates status
        3. Saves initial state
        4. Executes through plan executor
        5. Auto-saves after each step (if enabled)
        6. Returns final status
        
        Args:
            plan: The plan to execute
            context: Optional execution context. If not provided, an empty context is created
        
        Returns:
            The final PlanStatus after execution completes
        """
        async with self._execution_lock:
            self._current_plan = plan
            
            # Create default context if none provided
            if context is None:
                from .base import PlanContext
                context = PlanContext(
                    goal=plan.description or plan.name,
                    context={},
                    metadata={"plan_id": plan.plan_id, "agent": self.agent}
                )
            
            # Add agent reference to context for tool integration
            if self.agent is not None:
                context.context["agent"] = self.agent
                context.context["tool_registry"] = self.agent.tool_registry
            
            # Initial status update
            self._update_status(plan, PlanStatus.VALIDATING)
            
            # Validate before starting
            validation = self.validate_plan(plan)
            if not validation.is_valid:
                self._update_status(plan, PlanStatus.FAILED)
                if self.config.auto_save:
                    await self.save_plan(plan)
                logger.error(f"Plan validation failed: {validation.errors}")
                return PlanStatus.FAILED
            
            # Update to running status
            self._update_status(plan, PlanStatus.RUNNING)
            
            # Save initial state
            if self.config.auto_save:
                await self.save_plan(plan)
            
            # Execute the plan
            logger.info(f"Starting execution of plan: {plan.plan_id}")
            summary = await self.executor.execute(plan, context)
            
            # Get final status from summary
            final_status = summary.status
            
            # Update with final status
            self._update_status(plan, final_status)
            
            # Save final state
            if self.config.auto_save:
                await self.save_plan(plan)
            
            # Log result
            if final_status == PlanStatus.COMPLETED:
                logger.info(
                    f"Plan {plan.plan_id} completed successfully: "
                    f"{len(summary.completed_tasks)} tasks completed"
                )
            else:
                if summary.failed_task:
                    logger.error(
                        f"Plan {plan.plan_id} failed at task {summary.failed_task.task_id}: "
                        f"{summary.failed_task.error}"
                    )
                elif summary.validation_errors:
                    logger.error(
                        f"Plan {plan.plan_id} validation failed: {summary.validation_errors}"
                    )
            
            self._current_plan = None
            return final_status
    
    async def cancel_current(self) -> None:
        """Cancel the currently executing plan."""
        if self._current_plan is not None and self.executor.status == PlanStatus.RUNNING:
            await self.executor.cancel()
            self._update_status(self._current_plan, PlanStatus.CANCELLED)
            if self.config.auto_save:
                await self.save_plan(self._current_plan)
            logger.info(f"Cancelled execution of plan: {self._current_plan.plan_id}")
    
    @property
    def current_plan(self) -> Optional[Plan]:
        """Get the currently executing plan if any."""
        return self._current_plan
    
    @property
    def is_executing(self) -> bool:
        """Check if a plan is currently executing."""
        return self._current_plan is not None and self.executor.status == PlanStatus.RUNNING
    
    async def initialize(self) -> None:
        """Initialize the planner and underlying storage.
        
        Should be called once at application startup.
        """
        await self.storage.init()
        logger.info("Planner initialized and storage ready")
    
    async def list_plans(self) -> list[str]:
        """List all stored plan IDs.
        
        Returns:
            List of plan IDs in storage
        """
        return await self.storage.list_plans()
    
    async def count_plans(self) -> int:
        """Count the number of stored plans.
        
        Returns:
            Number of plans in storage
        """
        return await self.storage.count()

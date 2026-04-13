import asyncio
from dataclasses import dataclass
from typing import List, Optional, Set
from internal.agent.planning.base import Plan, Task, PlanContext, TaskResult
from internal.agent.planning.validator import PlanValidator
from internal.agent.planning.types import PlanStatus


@dataclass
class ExecutionSummary:
    """Summary of plan execution."""
    plan_id: str
    status: PlanStatus
    completed_tasks: List[TaskResult]
    failed_task: Optional[TaskResult] = None
    validation_errors: Optional[List[str]] = None
    
    @property
    def is_success(self) -> bool:
        return self.status == PlanStatus.COMPLETED


class PlanExecutor:
    """Executes a plan with dependency-based parallel scheduling.
    
    Features:
    - Validates plan before execution starts
    - Maintains execution state (running, completed, failed tasks)
    - Uses dependency graph to find ready tasks
    - Executes ready tasks in parallel up to max_concurrency
    - On task failure: cancels all running tasks immediately
    - Proper asyncio task cancellation handling
    """
    
    def __init__(
        self,
        max_concurrency: int = 4,
        validator: Optional[PlanValidator] = None
    ):
        """Initialize the plan executor.
        
        Args:
            max_concurrency: Maximum number of tasks to run in parallel (default: 4)
            validator: Optional custom plan validator (default: creates new PlanValidator)
        """
        self.max_concurrency = max_concurrency
        self.validator = validator or PlanValidator()
        
        # Execution state
        self._status: PlanStatus = PlanStatus.PENDING
        self._running_tasks: Set[asyncio.Task] = set()
        self._completed_tasks: List[TaskResult] = []
        self._failed_task: Optional[TaskResult] = None
        self._completed_task_ids: Set[str] = set()
        self._pending_task_ids: Set[str] = set()
        
    @property
    def status(self) -> PlanStatus:
        """Get current execution status."""
        return self._status
    
    @property
    def running_tasks(self) -> Set[asyncio.Task]:
        """Get currently running tasks."""
        return self._running_tasks
    
    @property
    def completed_tasks(self) -> List[TaskResult]:
        """Get completed tasks."""
        return self._completed_tasks
    
    @property
    def failed_task(self) -> Optional[TaskResult]:
        """Get the failed task if any."""
        return self._failed_task
    
    def _reset_state(self, plan: Plan):
        """Reset execution state for a new plan run."""
        self._status = PlanStatus.PENDING
        self._running_tasks.clear()
        self._completed_tasks.clear()
        self._failed_task = None
        self._completed_task_ids.clear()
        self._pending_task_ids = {task.task_id for task in plan.tasks}
    
    def _find_ready_tasks(self, plan: Plan) -> List[Task]:
        """Find tasks that are ready to execute (all dependencies completed successfully).
        
        A task is ready if:
        - It hasn't been completed yet
        - All of its dependencies are in completed_task_ids
        - It hasn't been started yet (still in pending_task_ids)
        
        Args:
            plan: The execution plan
            
        Returns:
            List of tasks ready to execute
        """
        ready_tasks: List[Task] = []
        
        for task in plan.tasks:
            task_id = task.task_id
            if task_id in self._completed_task_ids:
                continue
            if task_id not in self._pending_task_ids:
                continue  # Already running
            
            # Check if all dependencies are completed successfully
            all_deps_completed = all(
                dep in self._completed_task_ids
                for dep in task.dependencies
            )
            
            if all_deps_completed:
                ready_tasks.append(task)
        
        return ready_tasks
    
    async def _execute_task(
        self,
        task: Task,
        context: PlanContext,
    ) -> TaskResult:
        """Execute a single task and handle any exceptions.
        
        Args:
            task: The task to execute
            context: The plan context
            
        Returns:
            TaskResult with execution outcome
        """
        try:
            result = await task.execute(context)
            return result
        except asyncio.CancelledError:
            return TaskResult(
                task_id=task.task_id,
                success=False,
                result=None,
                error="Task was cancelled due to plan failure"
            )
        except Exception as e:
            return TaskResult(
                task_id=task.task_id,
                success=False,
                result=None,
                error=str(e)
            )
    
    def _cancel_all_running(self):
        """Cancel all currently running tasks."""
        for running_task in self._running_tasks:
            if not running_task.done():
                running_task.cancel()
    
    async def execute(self, plan: Plan, context: PlanContext) -> ExecutionSummary:
        """Execute the plan with dependency-based parallel scheduling.
        
        Args:
            plan: The plan to execute
            context: The plan execution context
            
        Returns:
            ExecutionSummary with final status and results
        """
        # Reset state for new execution
        self._reset_state(plan)
        
        # Validate plan before starting
        self._status = PlanStatus.VALIDATING
        validation_result = self.validator.validate(plan)
        
        if not validation_result.is_valid:
            self._status = PlanStatus.FAILED
            return ExecutionSummary(
                plan_id=plan.plan_id,
                status=PlanStatus.FAILED,
                completed_tasks=[],
                validation_errors=validation_result.errors
            )
        
        self._status = PlanStatus.RUNNING
        
        # Main execution loop
        while self._status == PlanStatus.RUNNING:
            # Find all ready tasks
            ready_tasks = self._find_ready_tasks(plan)
            
            # If no ready tasks and no running tasks, we're done
            if not ready_tasks and not self._running_tasks:
                # Check if all tasks completed
                if len(self._completed_tasks) == len(plan.tasks):
                    self._status = PlanStatus.COMPLETED
                break
            
            # How many more tasks can we start?
            available_slots = self.max_concurrency - len(self._running_tasks)
            
            if available_slots > 0 and ready_tasks:
                # Start as many as we can fit
                tasks_to_start = ready_tasks[:available_slots]
                
                for task in tasks_to_start:
                    self._pending_task_ids.remove(task.task_id)
                    # Create asyncio task and add to running set
                    asyncio_task = asyncio.create_task(
                        self._execute_task(task, context)
                    )
                    # Store task reference to prevent garbage collection
                    asyncio_task.add_done_callback(
                        lambda t: self._running_tasks.discard(t)
                    )
                    self._running_tasks.add(asyncio_task)
            
            # Wait for at least one task to complete
            if self._running_tasks:
                done, pending = await asyncio.wait(
                    self._running_tasks,
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # Process completed tasks
                for completed_task in done:
                    try:
                        result = completed_task.result()
                    except asyncio.CancelledError:
                        # Task was cancelled, skip processing
                        continue
                    except Exception as e:
                        # This should not happen since _execute_task catches
                        result = TaskResult(
                            task_id="unknown",
                            success=False,
                            result=None,
                            error=f"Uncaught exception in task: {str(e)}"
                        )
                    
                    # Add to completed results
                    self._completed_tasks.append(result)
                    
                    if result.success:
                        self._completed_task_ids.add(result.task_id)
                    else:
                        # Task failed - cancel everything and stop
                        self._failed_task = result
                        self._status = PlanStatus.FAILED
                        self._cancel_all_running()
                        break
                else:
                    # No failures in this batch, continue
                    continue
                
                # If we broke due to failure, exit loop
                break
        
        # Final cleanup and return summary
        if self._status == PlanStatus.FAILED:
            # Ensure all running tasks are cancelled
            self._cancel_all_running()
            # Wait briefly for cancellation to complete
            if self._running_tasks:
                await asyncio.gather(*self._running_tasks, return_exceptions=True)
        
        return ExecutionSummary(
            plan_id=plan.plan_id,
            status=self._status,
            completed_tasks=self._completed_tasks,
            failed_task=self._failed_task
        )
    
    async def cancel(self):
        """Cancel the current execution."""
        if self._status == PlanStatus.RUNNING:
            self._status = PlanStatus.CANCELLED
            self._cancel_all_running()
            if self._running_tasks:
                await asyncio.gather(*self._running_tasks, return_exceptions=True)
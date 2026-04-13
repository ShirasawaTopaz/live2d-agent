from dataclasses import dataclass
from typing import List, Set

from .base import Plan, Task


@dataclass
class ValidationResult:
    """Result of plan validation."""
    is_valid: bool
    errors: List[str]

    def __bool__(self) -> bool:
        return self.is_valid


class PlanValidator:
    """Validates execution plans for dependency cycles, duplicate tasks, and depth limits."""

    def __init__(self, max_depth: int = 10):
        self.max_depth = max_depth

    def validate(self, plan: Plan) -> ValidationResult:
        """Full validation of the plan combining all checks."""
        errors = []

        # Check dependencies
        dep_errors = self.validate_dependencies(plan)
        errors.extend(dep_errors)

        # Check max depth
        depth_errors = self.validate_max_depth(plan)
        errors.extend(depth_errors)

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors
        )

    def validate_dependencies(self, plan: Plan) -> List[str]:
        """Validate plan dependencies:
        - Check for duplicate task_ids
        - Check that all dependencies reference existing tasks
        - Check for cyclic dependencies
        """
        errors: List[str] = []

        # Check for duplicate task_ids
        task_ids: Set[str] = set()
        for task in plan.tasks:
            if task.task_id in task_ids:
                errors.append(f"Duplicate task_id: {task.task_id}")
            task_ids.add(task.task_id)

        # Check all dependencies reference existing tasks
        for task in plan.tasks:
            for dep in task.dependencies:
                if dep not in task_ids:
                    errors.append(f"Task '{task.task_id}' depends on non-existent task: {dep}")

        # Check for cyclic dependencies using DFS
        visited: Set[str] = set()
        rec_stack: Set[str] = set()

        def has_cycle(task_id: str) -> bool:
            visited.add(task_id)
            rec_stack.add(task_id)

            task = plan.get_task(task_id)
            if task:
                for dep in task.dependencies:
                    if dep not in visited:
                        if has_cycle(dep):
                            return True
                    elif dep in rec_stack:
                        # Found a cycle
                        cycle_path = self._build_cycle_path(task_id, dep, plan)
                        errors.append(f"Cyclic dependency detected: {' -> '.join(cycle_path)} -> {dep}")
                        return True

            rec_stack.remove(task_id)
            return False

        # Check each unvisited node for cycles
        for task in plan.tasks:
            if task.task_id not in visited:
                has_cycle(task.task_id)

        return errors

    def _build_cycle_path(self, current_task_id: str, start_dep_id: str, plan: Plan) -> List[str]:
        """Build the path from the cycle start to current task for error reporting."""
        path = [start_dep_id]
        visited = set([start_dep_id])
        found = False

        def dfs(next_id: str):
            nonlocal found
            if found:
                return
            path.append(next_id)
            visited.add(next_id)
            if next_id == current_task_id:
                found = True
                return
            task = plan.get_task(next_id)
            if task:
                for dep in task.dependencies:
                    if dep == start_dep_id:
                        path.append(next_id)
                        found = True
                        return
                    if dep not in visited:
                        dfs(dep)
                if found:
                    return
            path.pop()

        task = plan.get_task(current_task_id)
        if task:
            for dep in task.dependencies:
                if dep == start_dep_id:
                    path.append(current_task_id)
                    break
                dfs(dep)

        return path

    def validate_max_depth(self, plan: Plan) -> List[str]:
        """Check that the dependency hierarchy depth doesn't exceed max_depth."""
        errors: List[str] = []
        max_depth = 0
        depth_cache: dict[str, int] = {}
        visited: set[str] = set()

        def calculate_depth(task_id: str) -> int:
            """Calculate the depth of a task by finding the longest path from any root."""
            if task_id in depth_cache:
                return depth_cache[task_id]

            # Detect cycles to prevent infinite recursion
            if task_id in visited:
                # If we're already visiting this task, it's part of a cycle
                # Return 1 to avoid infinite recursion, but cycle will be caught by dependency validation
                return 1

            task = plan.get_task(task_id)
            if not task:
                return 0

            visited.add(task_id)

            if not task.dependencies:
                # Root task has depth 1
                depth = 1
            else:
                # Depth is 1 + maximum depth of all dependencies
                dep_depths = []
                for dep in task.dependencies:
                    dep_depth = calculate_depth(dep)
                    dep_depths.append(dep_depth)
                depth = 1 + max(dep_depths) if dep_depths else 1

            visited.remove(task_id)
            depth_cache[task_id] = depth
            return depth

        # Calculate depth for all tasks
        for task in plan.tasks:
            task_depth = calculate_depth(task.task_id)
            if task_depth > max_depth:
                max_depth = task_depth

        if max_depth > self.max_depth:
            errors.append(
                f"Maximum hierarchy depth exceeded: {max_depth} > {self.max_depth}. "
                "This could cause stack overflow during execution."
            )

        return errors

    def find_ready_tasks(self, plan: Plan, completed_results: List[str]) -> List[Task]:
        """Find tasks that have all dependencies completed successfully.

        Args:
            plan: The execution plan
            completed_results: List of task_ids that have completed successfully

        Returns:
            List of tasks that are ready to execute
        """
        ready_tasks: List[Task] = []
        completed_set = set(completed_results)

        for task in plan.tasks:
            # Task is ready if all dependencies are completed successfully
            # And task itself isn't already completed
            if task.task_id not in completed_set:
                all_deps_completed = all(dep in completed_set for dep in task.dependencies)
                if all_deps_completed:
                    ready_tasks.append(task)

        return ready_tasks

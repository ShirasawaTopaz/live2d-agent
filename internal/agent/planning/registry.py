"""Plan registry - manages all registered plan templates."""

from typing import Optional
from .base import Plan


class PlanRegistry:
    """Plan registry - manages all registered plan templates.

    This is a singleton class that maintains a registry of all
    loaded plan templates. It provides methods to register, unregister,
    and query plans.

    Example:
        ```python
        registry = PlanRegistry()
        registry.register(my_plan)

        plan = registry.get("my_plan")
        all_plans = registry.list_plans()
        ```
    """

    _instance: Optional["PlanRegistry"] = None

    def __new__(cls) -> "PlanRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self._plans: dict[str, Plan] = {}

    def register(self, plan: Plan) -> None:
        """Register a plan template.

        Args:
            plan: The plan instance to register

        Raises:
            ValueError: If a plan with the same ID is already registered
        """
        if plan.plan_id in self._plans:
            raise ValueError(f"Plan '{plan.plan_id}' is already registered")

        self._plans[plan.plan_id] = plan

    def unregister(self, plan_id: str) -> None:
        """Unregister a plan template.

        Args:
            plan_id: The ID of the plan to unregister
        """
        if plan_id in self._plans:
            del self._plans[plan_id]

    def get(self, plan_id: str) -> Optional[Plan]:
        """Get a plan template by ID.

        Args:
            plan_id: The plan ID

        Returns:
            The plan instance, or None if not found
        """
        return self._plans.get(plan_id)

    def list_plans(self) -> list[str]:
        """List all registered plan template IDs.

        Returns:
            List of plan IDs
        """
        return list(self._plans.keys())

    def filter_by_tags(self, tags: list[str]) -> list[Plan]:
        """Filter plan templates by tags.

        Args:
            tags: List of tags to filter by

        Returns:
            List of plans that have all the specified tags
        """
        # Plans don't have tags by default, so this is a placeholder
        # for future extension when we add metadata with tags
        # For now just return all plans
        return list(self._plans.values())

    def filter_by_category(self, category: str) -> list[Plan]:
        """Filter plan templates by category.

        Args:
            category: The category to filter by

        Returns:
            List of plans in the specified category
        """
        # Placeholder for future extension when we add metadata
        return list(self._plans.values())

    def clear(self) -> None:
        """Clear all registered plan templates."""
        self._plans.clear()
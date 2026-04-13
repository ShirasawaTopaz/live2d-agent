"""Skill registry - manages all registered Skills."""

from typing import Optional
from .base import Skill, SkillMetadata


class SkillRegistry:
    """Skill registry - manages all registered Skills.

    This is a singleton class that maintains a registry of all
    loaded skills. It provides methods to register, unregister,
    and query skills.

    Example:
        ```python
        registry = SkillRegistry()
        registry.register(my_skill)

        skill = registry.get("file_ops")
        all_skills = registry.list_skills()
        ```
    """

    _instance: Optional["SkillRegistry"] = None

    def __new__(cls) -> "SkillRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self._skills: dict[str, Skill] = {}
        self._metadata: dict[str, SkillMetadata] = {}

    def register(self, skill: Skill) -> None:
        """Register a Skill.

        Args:
            skill: The skill instance to register

        Raises:
            ValueError: If a skill with the same name is already registered
        """
        if skill.name in self._skills:
            raise ValueError(f"Skill '{skill.name}' is already registered")

        self._skills[skill.name] = skill
        self._metadata[skill.name] = skill.metadata

    def unregister(self, name: str) -> None:
        """Unregister a Skill.

        Args:
            name: The name of the skill to unregister
        """
        if name in self._skills:
            del self._skills[name]
            del self._metadata[name]

    def get(self, name: str) -> Optional[Skill]:
        """Get a Skill by name.

        Args:
            name: The skill name

        Returns:
            The skill instance, or None if not found
        """
        return self._skills.get(name)

    def get_metadata(self, name: str) -> Optional[SkillMetadata]:
        """Get Skill metadata.

        Args:
            name: The skill name

        Returns:
            The skill metadata, or None if not found
        """
        return self._metadata.get(name)

    def list_skills(self) -> list[str]:
        """List all registered Skill names.

        Returns:
            List of skill names
        """
        return list(self._skills.keys())

    def list_by_category(self, category: str) -> list[SkillMetadata]:
        """List Skills by category.

        Args:
            category: The category to filter by

        Returns:
            List of skill metadata in the category
        """
        return [meta for meta in self._metadata.values() if meta.category == category]

    def get_all_prompts(self) -> dict[str, list]:
        """Get all prompts provided by all Skills.

        Returns:
            Dictionary mapping skill names to their prompts
        """
        return {name: skill.prompts for name, skill in self._skills.items()}

    def get_all_tools(self) -> dict[str, list]:
        """Get all tools provided by all Skills.

        Returns:
            Dictionary mapping skill names to their tools
        """
        return {name: skill.tools for name, skill in self._skills.items()}

    def clear(self) -> None:
        """Clear all registered Skills."""
        self._skills.clear()
        self._metadata.clear()

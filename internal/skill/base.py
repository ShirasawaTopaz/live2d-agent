"""Skill abstract base class and related data classes."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class SkillMetadata:
    """Skill metadata.

    Attributes:
        name: Unique identifier for the skill
        version: Semantic version string
        description: Human-readable description
        author: Author or organization
        category: Classification category (e.g., "core", "utility", "external")
        tags: List of searchable tags
    """

    name: str
    version: str
    description: str
    author: str
    category: str = "general"
    tags: list[str] = field(default_factory=list)


@dataclass
class SkillPrompt:
    """Prompt module provided by a Skill.

    Attributes:
        name: Unique identifier within the skill
        description: What this prompt provides
        content: The actual prompt content (markdown)
        required: Whether this prompt should always be included
    """

    name: str
    description: str
    content: str
    required: bool = True


@dataclass
class SkillTool:
    """Tool definition provided by a Skill.

    This is a metadata container. The actual Tool instance
    is provided by the skill's get_tool_instances() method.

    Attributes:
        name: Unique tool identifier
        description: What this tool does
    """

    name: str
    description: str


class Skill(ABC):
    """Abstract base class for Skills.

    A Skill is a functional unit that can:
    1. Provide a set of related Tools
    2. Provide Prompt modules to enhance AI capabilities
    3. Declare dependencies
    4. Have its own configuration

    Example:
        ```python
        class FileOpsSkill(Skill):
            def _load_metadata(self) -> SkillMetadata:
                return SkillMetadata(
                    name="file_ops",
                    version="1.0.0",
                    description="File operations",
                    author="Live2oder"
                )

            def _load(self) -> None:
                # Define tools and prompts
                pass

            async def initialize(self) -> bool:
                return True

            async def shutdown(self) -> None:
                pass
        ```
    """

    def __init__(self, config: Optional[dict] = None):
        """Initialize the skill.

        Args:
            config: Optional configuration dictionary
        """
        self.config = config or {}
        self._metadata = self._load_metadata()
        self._prompts: list[SkillPrompt] = []
        self._tools: list[SkillTool] = []
        self._loaded = False

    @abstractmethod
    def _load_metadata(self) -> SkillMetadata:
        """Load skill metadata.

        Returns:
            SkillMetadata instance with skill information
        """
        pass

    @property
    def metadata(self) -> SkillMetadata:
        """Get skill metadata."""
        return self._metadata

    @property
    def name(self) -> str:
        """Get skill name (shortcut for metadata.name)."""
        return self._metadata.name

    @property
    def prompts(self) -> list[SkillPrompt]:
        """Get all prompts provided by this skill.

        Lazy-loads prompts on first access.
        """
        if not self._loaded:
            self._load()
        return self._prompts

    @property
    def tools(self) -> list[SkillTool]:
        """Get all tools provided by this skill.

        Lazy-loads tools on first access.
        """
        if not self._loaded:
            self._load()
        return self._tools

    @abstractmethod
    def _load(self) -> None:
        """Load the skill's prompts and tools definitions.

        This method should populate self._prompts and self._tools.
        Called automatically on first access to prompts or tools.
        """
        self._loaded = True

    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize the skill.

        This is called when the skill is being enabled.
        Use this to set up resources, check dependencies, etc.

        Returns:
            True if initialization successful
        """
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """Shutdown the skill and cleanup resources.

        This is called when the skill is being disabled.
        Use this to release resources, close connections, etc.
        """
        pass

    def get_config(self, key: str, default: Any = None) -> Any:
        """Get a configuration item.

        Args:
            key: Configuration key
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        return self.config.get(key, default)

    def validate_dependencies(self) -> tuple[bool, list[str]]:
        """Validate if dependencies are satisfied.

        Override this method to implement custom dependency checking.

        Returns:
            Tuple of (is_satisfied, list_of_missing_dependencies)
        """
        return True, []

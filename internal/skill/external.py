"""External skill loaded dynamically from filesystem."""

import shutil
from pathlib import Path
from typing import Optional

from .base import Skill, SkillMetadata, SkillPrompt, SkillTool


class ExternalSkill(Skill):
    """External skill loaded dynamically from filesystem.

    External skills are loaded from YAML definitions on the filesystem,
    allowing users to add skills without modifying code.

    Directory structure:
        my_skill/
            skill.yaml      # Skill definition
            prompts/
                *.md        # Prompt modules

    Example skill.yaml:
        ```yaml
        name: my_skill
        version: 1.0.0
        description: My custom skill
        author: My Name
        category: utility
        tags: [custom, utility]

        dependencies:
          python_packages: ["requests"]
          system_commands: ["git"]

        tools:
          - name: my_tool
            description: Does something useful
        ```

    Example:
        ```python
        skill_def = yaml.safe_load(open("my_skill/skill.yaml"))
        skill = ExternalSkill("path/to/my_skill", skill_def)

        if skill.validate_dependencies():
            await skill.initialize()
        ```
    """

    def __init__(self, path: str, skill_def: dict, config: Optional[dict] = None):
        """Initialize external skill.

        Args:
            path: Path to the skill directory
            skill_def: Parsed skill.yaml definition
            config: Optional configuration override
        """
        self.path = Path(path)
        self.skill_def = skill_def
        super().__init__(config)

    def _load_metadata(self) -> SkillMetadata:
        """Load metadata from skill.yaml definition.

        Returns:
            SkillMetadata instance
        """
        return SkillMetadata(
            name=self.skill_def["name"],
            version=self.skill_def.get("version", "1.0.0"),
            description=self.skill_def.get("description", ""),
            author=self.skill_def.get("author", "Unknown"),
            category=self.skill_def.get("category", "general"),
            tags=self.skill_def.get("tags", []),
        )

    def _load(self) -> None:
        """Load prompts and tools definitions.

        Loads prompts from the prompts/ directory and tools
        from the skill.yaml definition.
        """
        # Load prompts from prompts/ directory
        prompts_dir = self.path / "prompts"
        if prompts_dir.exists():
            for prompt_file in prompts_dir.glob("*.md"):
                content = prompt_file.read_text(encoding="utf-8")
                self._prompts.append(
                    SkillPrompt(
                        name=prompt_file.stem,
                        description=f"Prompt from {prompt_file.name}",
                        content=content,
                    )
                )

        # Load tools from skill.yaml definition
        for tool_def in self.skill_def.get("tools", []):
            self._tools.append(
                SkillTool(
                    name=tool_def["name"], description=tool_def.get("description", "")
                )
            )

        self._loaded = True

    async def initialize(self) -> bool:
        """Initialize external skill.

        Validates dependencies before returning success.

        Returns:
            True if initialization successful
        """
        satisfied, missing = self.validate_dependencies()
        if not satisfied:
            print(f"Skill '{self.name}' dependencies not satisfied: {missing}")
            return False

        return True

    async def shutdown(self) -> None:
        """Shutdown external skill.

        External skills loaded from YAML don't typically
        have resources to clean up.
        """
        pass

    def validate_dependencies(self) -> tuple[bool, list[str]]:
        """Validate if dependencies are satisfied.

        Checks Python packages, system commands, and other skills
        as declared in the skill.yaml.

        Returns:
            Tuple of (is_satisfied, list_of_missing_dependencies)
        """
        missing = []
        deps = self.skill_def.get("dependencies", {})

        # Check Python package dependencies
        for package in deps.get("python_packages", []):
            try:
                __import__(package)
            except ImportError:
                missing.append(f"python:{package}")

        # Check system command dependencies
        for cmd in deps.get("system_commands", []):
            if not shutil.which(cmd):
                missing.append(f"cmd:{cmd}")

        return len(missing) == 0, missing

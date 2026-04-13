"""File operations skill - built-in implementation."""

from internal.agent.tool.file import (
    FileGrepTool,
    FileReadTool,
    FileRunTool,
    FileWriteTool,
)

from ..base import Skill, SkillMetadata, SkillPrompt, SkillTool


class FileOpsSkill(Skill):
    """File operations skill - built-in implementation.

    This skill provides file operation capabilities including:
    - Reading files
    - Writing files
    - Searching file contents (grep)
    - Executing files

    It wraps the existing file tool implementations and provides
    a default prompt module that teaches the AI how to use these tools.

    Example:
        ```python
        skill = FileOpsSkill()

        # Get tools
        tools = skill.get_tool_instances()

        # Get prompt
        prompts = skill.prompts
        ```
    """

    def _load_metadata(self) -> SkillMetadata:
        """Load skill metadata.

        Returns:
            SkillMetadata for this skill
        """
        return SkillMetadata(
            name="file_ops",
            version="1.0.0",
            description="文件操作技能，支持读写、搜索、执行文件",
            author="Live2oder Team",
            category="core",
            tags=["file", "io", "system"],
        )

    def _load(self) -> None:
        """Load built-in tools and prompts.

        Defines the tool signatures and loads the default prompt.
        """
        # Built-in skills reference existing Tool classes
        self._tools = [
            SkillTool(name="file_read", description="读取文件内容"),
            SkillTool(name="file_write", description="写入文件内容"),
            SkillTool(name="file_grep", description="搜索文件内容"),
            SkillTool(name="file_run", description="执行文件"),
        ]

        # Load built-in prompt
        self._prompts = [
            SkillPrompt(
                name="file_ops",
                description="文件操作相关规则和能力说明",
                content=self._get_default_prompt(),
                required=True,
            )
        ]

        self._loaded = True

    def _get_default_prompt(self) -> str:
        """Get default file_ops prompt.

        Returns:
            Default prompt content in Chinese
        """
        return """## 文件操作能力

你有以下文件操作工具：

1. **file_read** - 读取文件内容
2. **file_write** - 写入文件内容
3. **file_grep** - 在文件中搜索内容
4. **file_run** - 执行文件（需谨慎使用）

### 使用规则

- 读取文件前先确认路径存在
- 写入文件前确认内容正确
- 执行命令前让用户确认
- 不要读取/写入过大的文件（>10MB）
"""

    async def initialize(self) -> bool:
        """Initialize file operations skill.

        Checks necessary permissions, etc.

        Returns:
            True if initialization successful
        """
        # Check necessary permissions, etc.
        return True

    async def shutdown(self) -> None:
        """Shutdown skill.

        No resources to clean up for built-in skills.
        """
        pass

    def get_tool_instances(self) -> list:
        """Get actual Tool instances for registration.

        Returns:
            List of Tool instances
        """
        return [
            FileReadTool(),
            FileWriteTool(),
            FileGrepTool(),
            FileRunTool(),
        ]

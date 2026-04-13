"""Skill lifecycle manager."""

import os
import sys
import yaml
from pathlib import Path
from typing import Optional

from .base import Skill
from .external import ExternalSkill
from .registry import SkillRegistry


class SkillManager:
    """Skill lifecycle manager.

    Responsibilities:
    1. Load skills from filesystem
    2. Manage skill enable/disable
    3. Handle skill initialization and shutdown
    4. Integrate with PromptManager and ToolRegistry

    Example:
        ```python
        manager = SkillManager(
            skill_dirs=["./skills", "./internal/skill/builtin"],
            prompt_manager=prompt_manager,
            tool_registry=tool_registry
        )

        # Load all skills
        loaded = await manager.load_all()

        # Enable specific skills
        await manager.enable("file_ops")
        await manager.enable("web_search")
        ```
    """

    def __init__(
        self, skill_dirs: list[str] = None, prompt_manager=None, tool_registry=None
    ):
        """Initialize the skill manager.

        Args:
            skill_dirs: List of directories to search for skills. If None, will be determined at runtime.
            prompt_manager: Optional PromptManager for registering prompts
            tool_registry: Optional ToolRegistry for registering tools
        """
        self._user_skill_dirs = skill_dirs or []
        self.skill_dirs = self._resolve_skill_directories()
        self.prompt_manager = prompt_manager
        self.tool_registry = tool_registry
        self.registry = SkillRegistry()

        # Enabled skills
        self._enabled_skills: set[str] = set()
        # Skill configs
        self._skill_configs: dict[str, dict] = {}

    def _get_base_dir(self) -> Path:
        """获取程序基础目录。"""
        if getattr(sys, "frozen", False):
            # PyInstaller打包后的路径
            return Path(sys.executable).parent
        else:
            # 开发环境
            return Path(__file__).parent.parent.parent.parent

    def _get_user_data_dir(self) -> Path:
        """获取用户数据目录。"""
        if os.name == "nt":  # Windows
            appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
            return Path(appdata) / "Live2Oder"
        else:  # Linux/Mac
            return Path.home() / ".config" / "Live2Oder"

    def _ensure_user_dirs(self) -> None:
        """确保用户目录结构存在。"""
        user_dir = self._get_user_data_dir()
        skills_dir = user_dir / "skills"
        data_dir = user_dir / "data"

        skills_dir.mkdir(parents=True, exist_ok=True)
        data_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_skill_directories(self) -> list[str]:
        """解析并返回所有SKill目录路径。"""
        base_dir = self._get_base_dir()
        user_dir = self._get_user_data_dir()

        # 确保用户目录存在
        self._ensure_user_dirs()

        skill_dirs = []

        # 1. 添加用户指定的目录（优先级最高）
        for dir_path in self._user_skill_dirs:
            expanded_path = os.path.expanduser(os.path.expandvars(dir_path))
            if os.path.exists(expanded_path):
                skill_dirs.append(expanded_path)

        # 2. 添加用户数据目录中的SKills（支持热添加）
        user_skills_dir = user_dir / "skills"
        if user_skills_dir.exists():
            skill_dirs.append(str(user_skills_dir))

        # 3. 添加打包的内嵌SKills（开发环境或打包后）
        # 开发环境：./skills
        # 打包后：_internal/skills（PyInstaller）
        embedded_skills_dir = base_dir / "skills"
        if embedded_skills_dir.exists():
            skill_dirs.append(str(embedded_skills_dir))

        # 去重并保持顺序
        seen = set()
        unique_dirs = []
        for d in skill_dirs:
            if d not in seen:
                seen.add(d)
                unique_dirs.append(d)

        return unique_dirs

    def reload_skill_directories(self) -> None:
        """重新解析SKill目录（用于热添加后刷新）。"""
        self.skill_dirs = self._resolve_skill_directories()

    async def load_all(self) -> list[str]:
        """Load all available skills.

        Returns:
            List of successfully loaded skill names.
        """
        loaded = []
        for skill_dir in self.skill_dirs:
            if not os.path.exists(skill_dir):
                continue

            for item in os.listdir(skill_dir):
                path = os.path.join(skill_dir, item)
                if os.path.isdir(path):
                    try:
                        if await self._load_skill(path):
                            loaded.append(item)
                    except Exception as e:
                        print(f"Failed to load skill '{item}': {e}")

        return loaded

    async def _load_skill(self, path: str) -> bool:
        """Load a single skill from directory.

        Args:
            path: Path to the skill directory

        Returns:
            True if loaded successfully, False otherwise
        """
        yaml_path = os.path.join(path, "skill.yaml")
        if not os.path.exists(yaml_path):
            return False

        with open(yaml_path, "r", encoding="utf-8") as f:
            skill_def = yaml.safe_load(f)

        skill = self._create_skill_instance(path, skill_def)
        self.registry.register(skill)
        return True

    def _create_skill_instance(self, path: str, skill_def: dict) -> Skill:
        """Create skill instance from definition.

        Args:
            path: Path to the skill directory
            skill_def: Parsed skill.yaml definition

        Returns:
            Skill instance
        """
        name = skill_def["name"]
        config = self._skill_configs.get(name, {})

        # Check for builtin skill
        builtin_skill = self._get_builtin_skill(name)
        if builtin_skill:
            return builtin_skill(config)

        # External skill
        return ExternalSkill(path, skill_def, config)

    def _get_builtin_skill(self, name: str) -> Optional[type[Skill]]:
        """Get builtin skill class by name.

        Args:
            name: Skill name

        Returns:
            Skill class if found, None otherwise
        """
        builtin_skills = {
            "file_ops": "internal.skill.builtin.file_ops.FileOpsSkill",
            "web_search": "internal.skill.builtin.web_search.WebSearchSkill",
            "live2d_ctrl": "internal.skill.builtin.live2d_ctrl.Live2DCtrlSkill",
            "office": "internal.skill.builtin.office.OfficeSkill",
        }

        if name not in builtin_skills:
            return None

        module_path, class_name = builtin_skills[name].rsplit(".", 1)
        module = __import__(module_path, fromlist=[class_name])
        return getattr(module, class_name)

    async def enable(self, name: str) -> bool:
        """Enable a skill and register its tools/prompts.

        Args:
            name: Skill name

        Returns:
            True if enabled successfully
        """
        if name in self._enabled_skills:
            return True

        skill = self.registry.get(name)
        if not skill:
            return False

        if not await skill.initialize():
            return False

        # Register tools
        if self.tool_registry and hasattr(skill, "get_tool_instances"):
            for tool in skill.get_tool_instances():
                self.tool_registry.register(tool)

        # Register prompts
        if self.prompt_manager:
            for prompt in skill.prompts:
                # PromptManager needs to support skill prompts
                pass

        self._enabled_skills.add(name)
        return True

    async def disable(self, name: str) -> bool:
        """Disable a skill and unregister its tools/prompts.

        Args:
            name: Skill name

        Returns:
            True if disabled successfully
        """
        if name not in self._enabled_skills:
            return True

        skill = self.registry.get(name)
        if skill:
            # Unregister tools
            if self.tool_registry:
                for tool_def in skill.tools:
                    # ToolRegistry needs unregister method
                    pass

            await skill.shutdown()

        self._enabled_skills.discard(name)
        return True

    def is_enabled(self, name: str) -> bool:
        """Check if a skill is enabled.

        Args:
            name: Skill name

        Returns:
            True if skill is enabled
        """
        return name in self._enabled_skills

    def list_enabled(self) -> list[str]:
        """List all enabled skills.

        Returns:
            List of enabled skill names
        """
        return list(self._enabled_skills)

    def get_skill_config(self, name: str) -> dict:
        """Get skill configuration.

        Args:
            name: Skill name

        Returns:
            Skill configuration dictionary
        """
        return self._skill_configs.get(name, {})

    def set_skill_config(self, name: str, config: dict) -> None:
        """Set skill configuration.

        Args:
            name: Skill name
            config: Configuration dictionary
        """
        self._skill_configs[name] = config

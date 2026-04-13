import aiofiles
from typing import Any, Dict, List, Optional
from pathlib import Path


class PromptManager:
    """Prompt组合管理器，负责加载、管理和组合prompt模块"""

    _instance: Optional["PromptManager"] = None
    _modules: Dict[str, str] = {}
    _modules_dir: Path

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    async def load(cls, modules_dir: str | Path = "prompt_modules") -> "PromptManager":
        """加载所有prompt模块"""
        instance = cls()
        instance._modules_dir = Path(modules_dir)
        instance._modules = {}

        if instance._modules_dir.exists():
            await instance._load_modules_recursive(instance._modules_dir, "")

        return instance

    async def _load_modules_recursive(self, dir_path: Path, prefix: str):
        """递归加载目录下的所有prompt模块"""
        for item in dir_path.iterdir():
            if item.is_dir():
                new_prefix = f"{prefix}{item.name}/" if prefix else f"{item.name}/"
                await self._load_modules_recursive(item, new_prefix)
            elif item.is_file() and item.suffix == ".md":
                module_name = f"{prefix}{item.stem}" if prefix else item.stem
                async with aiofiles.open(item, encoding="utf-8") as f:
                    content = await f.read()
                    self._modules[module_name] = content.strip()

    def get_prompt_modules(self) -> Dict[str, str]:
        """获取所有可用的prompt模块"""
        return self._modules.copy()

    def has_module(self, module_path: str) -> bool:
        """检查是否存在指定的模块"""
        return module_path in self._modules

    def get_module(self, module_path: str) -> Optional[str]:
        """获取单个prompt模块"""
        return self._modules.get(module_path)

    async def compose_system_prompt(self, prompt_config: Any) -> str:
        """
        根据配置组合生成完整的系统提示词

        支持三种配置格式:
        1. 字符串: 直接返回字符串
        2. 字典 - 模块列表: {"modules": ["module1", "module2"]}
        3. 字典 - 混合模式: {"prefix": "...", "modules": [...], "suffix": "..."}
        """
        if isinstance(prompt_config, str):
            return prompt_config

        if isinstance(prompt_config, dict):
            parts: List[str] = []

            # 添加前缀
            if "prefix" in prompt_config and prompt_config["prefix"]:
                parts.append(str(prompt_config["prefix"]).strip())

            # 加载并组合模块
            if "modules" in prompt_config and isinstance(
                prompt_config["modules"], list
            ):
                for module_path in prompt_config["modules"]:
                    module_content = self.get_module(str(module_path))
                    if module_content:
                        parts.append(module_content)

            # 添加后缀
            if "suffix" in prompt_config and prompt_config["suffix"]:
                parts.append(str(prompt_config["suffix"]).strip())

            return "\n\n".join(parts) if parts else ""

        return str(prompt_config)

    async def render_module(
        self, module_path: str, context: Dict[str, Any] | None = None
    ) -> str:
        """
        渲染单个prompt模块，支持模板变量替换

        模板变量格式: {{variable_name}}
        """
        content = self.get_module(module_path)
        if not content:
            return ""

        if context:
            for key, value in context.items():
                placeholder = f"{{{{{key}}}}}"
                content = content.replace(placeholder, str(value))

        return content

    def list_modules_by_category(self) -> Dict[str, List[str]]:
        """按类别列出所有模块"""
        categories: Dict[str, List[str]] = {}

        for module_path in self._modules.keys():
            if "/" in module_path:
                category = module_path.split("/")[0]
            else:
                category = "other"

            if category not in categories:
                categories[category] = []
            categories[category].append(module_path)

        return categories

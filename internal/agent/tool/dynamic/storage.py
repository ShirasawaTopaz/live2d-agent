"""动态工具存储管理模块

管理动态生成工具的存储、索引和加载。
"""

import sys
import json
import importlib.util
from pathlib import Path
from typing import Dict, List, Optional, Type
from datetime import datetime

from internal.agent.tool.base import Tool
from internal.agent.tool.dynamic.versioning import VersionManager


class DynamicToolStorage:
    """动态工具存储管理器

    管理动态生成工具的存储、索引和加载。

    存储结构:
        storage_path/
            __init__.py
            .tools_index.json      # 工具元数据索引
            {tool_name}_tool.py     # 动态生成的工具文件
            versions/              # Version history
                version_index.json
                {tool_name}_v1_0_0_tool.py

    Attributes:
        storage_path: 存储目录路径
        index: 工具索引字典 {name: metadata}
        version_manager: Version manager for version history
        max_dynamic_tools: Maximum number of dynamic tools allowed
    """

    def __init__(
        self,
        storage_path: Optional[str] = None,
        max_dynamic_tools: int = 20,
    ):
        """初始化存储管理器

        Args:
            storage_path: 自定义存储路径，默认为模块内tools目录
            max_dynamic_tools: Maximum number of dynamic tools allowed (default: 20)
        """
        if storage_path is None:
            base_path = Path(__file__).parent
            self.storage_path = base_path / "tools"
        else:
            self.storage_path = Path(storage_path)

        self.index_path = self.storage_path / ".tools_index.json"
        self.index: Dict[str, dict] = {}
        self.version_manager = VersionManager(self.storage_path)
        self.max_dynamic_tools = max_dynamic_tools

        self._ensure_storage()
        self._load_index()

    def _ensure_storage(self):
        """确保存储目录和__init__.py存在"""
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # 创建__init__.py使目录成为Python包
        init_file = self.storage_path / "__init__.py"
        if not init_file.exists():
            init_file.write_text('"""Dynamic tools package."""\n')

    def _load_index(self):
        """加载工具索引"""
        if self.index_path.exists():
            try:
                with open(self.index_path, "r", encoding="utf-8") as f:
                    self.index = json.load(f)
            except Exception as e:
                print(f"Warning: Failed to load index: {e}")
                self.index = {}

    def _save_index(self):
        """保存工具索引"""
        try:
            with open(self.index_path, "w", encoding="utf-8") as f:
                json.dump(self.index, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Warning: Failed to save index: {e}")

    def check_limit_reached(self) -> tuple[bool, int]:
        """Check if the maximum number of dynamic tools has been reached.
        
        Returns:
            (limit_reached, current_count)
        """
        current = len(self.index)
        return current >= self.max_dynamic_tools, current

    def get_available_slots(self) -> int:
        """Get number of remaining slots for new dynamic tools."""
        return max(0, self.max_dynamic_tools - len(self.index))

    def save(self, name: str, code: str, metadata: Optional[dict] = None) -> Path:
        """保存工具代码

        If versioning is enabled (default), automatically adds a new version entry.

        Enforces the maximum dynamic tools limit - rejects new tools when limit reached.

        Returns:
            保存的文件路径
        """
        # Check limit before saving new tool
        if name not in self.index:
            limit_reached, current = self.check_limit_reached()
            if limit_reached:
                raise RuntimeError(
                    f"Maximum number of dynamic tools ({self.max_dynamic_tools}) reached. "
                    f"Current: {current}. Please delete some tools before creating new ones."
                )

        file_name = f"{name}_tool.py"
        file_path = self.storage_path / file_name

        # Check if this is an update and track version
        description = metadata.get("description", "") if metadata else ""
        if name in self.index:
            # Only add new version if code changed
            if self.version_manager.check_for_changes(name, code):
                self.version_manager.add_version(name, code, description)
        else:
            # First version
            self.version_manager.add_version(name, code, description or "Initial version")

        # 写入代码
        file_path.write_text(code, encoding="utf-8")

        # 更新索引
        latest_version = self.version_manager.get_latest_version(name)
        latest_version_str = latest_version.version if latest_version else None
        self.index[name] = {
            "file": file_name,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "metadata": metadata or {},
            "latest_version": latest_version_str,
        }
        self._save_index()

        return file_path

    def load(self, name: str) -> Optional[Type[Tool]]:
        """动态加载工具类

        Returns:
            工具类，如果加载失败则返回None
        """
        if name not in self.index:
            return None

        info = self.index[name]
        file_path = self.storage_path / info["file"]

        if not file_path.exists():
            return None

        try:
            # 动态加载模块
            module_name = f"internal.agent.tool.dynamic.tools.{name}_tool"
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if not spec or not spec.loader:
                return None

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # 查找Tool子类
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, Tool)
                    and attr is not Tool
                ):
                    return attr

            return None

        except Exception as e:
            print(f"Error loading tool {name}: {e}")
            return None

    def list(self) -> List[dict]:
        """列出所有动态工具"""
        return [{"name": name, **info} for name, info in self.index.items()]

    def delete(self, name: str) -> bool:
        """删除动态工具

        Args:
            name: 工具名称

        Returns:
            是否成功删除
        """
        if name not in self.index:
            return False

        info = self.index[name]
        file_path = self.storage_path / info["file"]

        # 删除文件
        if file_path.exists():
            file_path.unlink()

        # Delete all version history
        self.version_manager.delete_versions(name)

        # 更新索引
        del self.index[name]
        self._save_index()

        # 清理sys.modules
        module_name = f"internal.agent.tool.dynamic.tools.{name}_tool"
        if module_name in sys.modules:
            del sys.modules[module_name]

        return True

    def exists(self, name: str) -> bool:
        """检查工具是否存在"""
        return name in self.index

    def info(self, name: str) -> Optional[dict]:
        """获取工具信息"""
        if name not in self.index:
            return None
        return {"name": name, **self.index[name]}

    def load_all(self) -> List[Type[Tool]]:
        """加载所有动态工具

        Returns:
            所有已加载的工具类列表
        """
        tools = []
        for name in self.index.keys():
            tool_class = self.load(name)
            if tool_class:
                tools.append(tool_class)
        return tools

    def clear(self) -> int:
        """清空所有动态工具

        Returns:
            删除的工具数量
        """
        names = list(self.index.keys())
        count = 0
        for name in names:
            if self.delete(name):
                count += 1
        return count

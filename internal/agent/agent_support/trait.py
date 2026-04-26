from abc import ABC, abstractmethod
from typing import Any, MutableMapping, AsyncIterator, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from internal.prompt_manager.prompt_manager import PromptManager

from internal.config.config import AIModelConfig


class ModelTrait(ABC):
    """模型特征抽象基类，定义模型接口"""

    config: AIModelConfig
    history: list[MutableMapping[str, Any]] = []
    options: dict[str, Any] | None = None
    _tools_supported: bool = True
    _prompt_manager: Optional["PromptManager"] = None

    @classmethod
    async def resolve_prompt_manager(cls) -> "PromptManager":
        """获取或创建PromptManager实例"""
        if cls._prompt_manager is None:
            from internal.prompt_manager import PromptManager

            cls._prompt_manager = await PromptManager.load()
        return cls._prompt_manager

    async def _resolve_system_prompt(self) -> str:
        """解析系统提示词配置，返回完整字符串"""
        manager = await self.resolve_prompt_manager()
        return await manager.compose_system_prompt(self.config.system_prompt)

    async def _ensure_system_message(self) -> None:
        resolved_prompt = getattr(self, "_resolved_system_prompt", None)
        if not getattr(self, "_system_prompt_resolved", False) or not isinstance(
            resolved_prompt, str
        ):
            resolved_prompt = await self._resolve_system_prompt()
            setattr(self, "_resolved_system_prompt", resolved_prompt)
            setattr(self, "_system_prompt_resolved", True)

        if self.history and self.history[0].get("role") == "system":
            content = str(self.history[0].get("content", ""))
            if resolved_prompt and not content.startswith(resolved_prompt):
                separator = "\n\n" if content else ""
                self.history[0]["content"] = f"{resolved_prompt}{separator}{content}"
            return
        self.history.insert(0, {"role": "system", "content": resolved_prompt})

    @abstractmethod
    async def chat(self, message: Any, tools: list[dict] | None = None) -> dict:
        """发送聊天消息并获取完整响应"""
        pass

    @abstractmethod
    def stream_chat(
        self, message: Any, tools: list[dict] | None = None
    ) -> AsyncIterator[dict]:
        """发送聊天消息并获取流式响应
        逐块返回响应内容，最后一个块设置 done=True 表示生成完成
        返回格式: {"content": "累积内容", "done": False/True}
        """
        pass

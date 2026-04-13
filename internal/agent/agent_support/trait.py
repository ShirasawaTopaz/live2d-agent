from abc import ABC, abstractmethod
from typing import Any, Mapping, MutableMapping, AsyncIterator, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from internal.prompt_manager.prompt_manager import PromptManager

from internal.config.config import AIModelConfig


class ModelTrait(ABC):
    """模型特征抽象基类，定义模型接口"""

    config: AIModelConfig
    history: list[MutableMapping[str, Any]] = []
    options: Mapping[str, Any] | None = None
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

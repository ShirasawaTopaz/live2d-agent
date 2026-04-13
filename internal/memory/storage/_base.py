"""
Storage Base Interface - Reference Implementation
⚠️  This is reference design code, not yet production-ready
"""

from abc import ABC, abstractmethod
from typing import List

from internal.memory._types import SessionInfo, LongTermEntry


class BaseStorage(ABC):
    """存储后端抽象基类"""

    @abstractmethod
    async def save_session(self, session_id: str, data: dict) -> None:
        """保存会话数据"""
        pass

    @abstractmethod
    async def load_session(self, session_id: str) -> dict | None:
        """加载会话数据，返回None表示不存在"""
        pass

    @abstractmethod
    async def delete_session(self, session_id: str) -> bool:
        """删除会话，返回是否删除成功"""
        pass

    @abstractmethod
    async def list_sessions(self) -> List[SessionInfo]:
        """列出所有会话"""
        pass

    @abstractmethod
    async def save_long_term(self, entry: LongTermEntry) -> None:
        """保存长期记忆条目"""
        pass

    @abstractmethod
    async def query_long_term(self, query: str, limit: int = 10) -> List[LongTermEntry]:
        """查询长期记忆，按关键词匹配"""
        pass

    @abstractmethod
    async def delete_long_term(self, entry_id: str) -> bool:
        """删除长期记忆条目"""
        pass

    @abstractmethod
    async def init(self) -> None:
        """初始化存储，创建目录、表结构等"""
        pass

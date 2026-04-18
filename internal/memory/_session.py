"""
Multi-Session Manager - Reference Implementation
⚠️  This is reference design code, not yet production-ready
"""

import uuid
import logging
from datetime import datetime
from typing import Optional, List, Dict

from internal.memory._types import SessionInfo, ConversationTurn, Message
from internal.memory.storage._base import BaseStorage


logger = logging.getLogger(__name__)


class SessionManager:
    """多会话管理器
    管理多个独立的对话会话，支持创建、切换、删除、自动清理
    """

    def __init__(
        self,
        storage: BaseStorage,
        max_sessions: int = 10,
        auto_cleanup: bool = True,
    ):
        self.storage = storage
        self.max_sessions = max_sessions
        self.auto_cleanup = auto_cleanup

        self._current_session_id: Optional[str] = None
        self._sessions: Dict[str, List[ConversationTurn]] = {}
        self._session_info: Dict[str, SessionInfo] = {}

    @property
    def current_session_id(self) -> Optional[str]:
        return self._current_session_id

    @property
    def current_session(self) -> Optional[List[ConversationTurn]]:
        if self._current_session_id is None:
            return None
        return self._sessions.get(self._current_session_id)

    @property
    def current_info(self) -> Optional[SessionInfo]:
        if self._current_session_id is None:
            return None
        return self._session_info.get(self._current_session_id)

    async def new_session(self, title: Optional[str] = None) -> SessionInfo:
        """创建新会话，返回会话信息"""
        session_id = str(uuid.uuid4())[:8]
        now = datetime.now()

        info = SessionInfo(
            session_id=session_id,
            created_at=now,
            updated_at=now,
            title=title,
            message_count=0,
        )

        self._session_info[session_id] = info
        self._sessions[session_id] = []

        if self.auto_cleanup and len(self._session_info) > self.max_sessions:
            await self._cleanup_old_sessions()

        self._current_session_id = session_id
        await self._save_session(session_id)
        logger.info(f"Created new session: {session_id}")
        return info

    async def switch_session(self, session_id: str) -> bool:
        """切换到指定会话，返回是否切换成功"""
        if session_id not in self._session_info:
            # 尝试从存储加载
            loaded = await self._load_session(session_id)
            if not loaded:
                logger.warning(f"Session {session_id} not found")
                return False

        self._current_session_id = session_id
        logger.info(f"Switched to session: {session_id}")
        return True

    async def delete_current_session(self) -> bool:
        """删除当前会话"""
        if self._current_session_id is None:
            return False

        session_id = self._current_session_id
        await self.storage.delete_session(session_id)
        del self._sessions[session_id]
        del self._session_info[session_id]
        self._current_session_id = None

        logger.info(f"Deleted session: {session_id}")
        return True

    def list_sessions(self) -> List[SessionInfo]:
        """列出所有会话，按更新时间倒序"""
        return sorted(
            self._session_info.values(),
            key=lambda s: s.updated_at,
            reverse=True,
        )

    def add_turn(self, message: Message) -> ConversationTurn:
        """在当前会话添加一轮对话"""
        if self._current_session_id is None:
            raise RuntimeError("No active session, call new_session first")

        turn = ConversationTurn(message=message)
        self._sessions[self._current_session_id].append(turn)
        self._update_session_info()
        return turn

    def get_turns(self) -> List[ConversationTurn]:
        """获取当前会话所有轮次"""
        if self._current_session_id is None:
            return []
        return self._sessions[self._current_session_id]

    def get_messages(self) -> List[Message]:
        """获取当前会话所有消息（用于LLM调用）"""
        turns = self.get_turns()
        return [turn.message for turn in turns]

    def message_count(self) -> int:
        """获取当前会话消息数量"""
        if self._current_session_id is None:
            return 0
        return len(self._sessions[self._current_session_id])

    def estimate_total_tokens(self) -> int:
        """估算当前会话总token数"""
        if self._current_session_id is None:
            return 0
        total = 0
        for turn in self._sessions[self._current_session_id]:
            msg = turn.message
            content = msg.get("content", "")
            if not isinstance(content, str):
                content = str(content)
            total += len(content) // 4
        return total

    async def save_current(self) -> None:
        """保存当前会话到存储"""
        if self._current_session_id is not None:
            await self._save_session(self._current_session_id)

    async def load_all_sessions(self) -> None:
        """从存储加载所有会话信息"""
        infos = await self.storage.list_sessions()
        for info in infos:
            self._session_info[info.session_id] = info
            # 预加载会话内容到内存
            await self._load_session(info.session_id)
        logger.info(f"Loaded {len(infos)} sessions from storage")

    def _update_session_info(self) -> None:
        """更新当前会话信息"""
        if self._current_session_id is None:
            return
        info = self._session_info[self._current_session_id]
        info.updated_at = datetime.now()
        info.message_count = len(self._sessions[self._current_session_id])

    async def _save_session(self, session_id: str) -> None:
        """保存指定会话到存储"""
        info = self._session_info[session_id]
        turns = self._sessions[session_id]
        data = {
            "info": info.to_dict(),
            "turns": [turn.to_dict() for turn in turns],
        }
        await self.storage.save_session(session_id, data)

    async def _load_session(self, session_id: str) -> bool:
        """从存储加载会话"""
        data = await self.storage.load_session(session_id)
        if data is None:
            return False

        info = SessionInfo.from_dict(data["info"])
        turns = [ConversationTurn.from_dict(t) for t in data["turns"]]

        self._session_info[session_id] = info
        self._sessions[session_id] = turns
        return True

    async def _cleanup_old_sessions(self) -> None:
        """清理最旧的会话，保持数量不超过max_sessions"""
        sessions = sorted(
            self._session_info.values(),
            key=lambda s: s.updated_at,
        )

        while len(self._session_info) > self.max_sessions:
            oldest = sessions.pop(0)
            logger.info(f"Auto-cleaning up old session: {oldest.session_id}")
            await self.storage.delete_session(oldest.session_id)
            del self._sessions[oldest.session_id]
            del self._session_info[oldest.session_id]

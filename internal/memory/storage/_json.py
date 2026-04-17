"""
JSON Storage Backend - Reference Implementation
⚠️  This is reference design code, not yet production-ready
"""

import aiofiles
import json
import logging
from pathlib import Path
from typing import List

from internal.memory.storage._base import BaseStorage
from internal.memory._types import SessionInfo, LongTermEntry


logger = logging.getLogger(__name__)


class JSONStorage(BaseStorage):
    """JSON文件存储实现
    - 每个会话一个独立的JSON文件
    - 长期记忆存储在单独的目录中
    - 简单直观，易于调试，适合中小规模对话
    """

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.sessions_dir = self.data_dir / "sessions"
        self.long_term_dir = self.data_dir / "long_term"

    async def init(self) -> None:
        """初始化目录结构"""
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.long_term_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"JSONStorage initialized at {self.data_dir}")

    def _get_session_path(self, session_id: str) -> Path:
        return self.sessions_dir / f"{session_id}.json"

    def _get_long_term_path(self, entry_id: str) -> Path:
        return self.long_term_dir / f"{entry_id}.json"

    async def save_session(self, session_id: str, data: dict) -> None:
        """保存会话数据到JSON文件"""
        path = self._get_session_path(session_id)
        content = json.dumps(data, ensure_ascii=False, indent=2)
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(content)
        logger.debug(f"Saved session {session_id} to {path}")

    async def load_session(self, session_id: str) -> dict | None:
        """从JSON文件加载会话数据"""
        path = self._get_session_path(session_id)
        if not path.exists():
            return None
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            content = await f.read()
        data = json.loads(content)
        logger.debug(f"Loaded session {session_id} from {path}")
        return data

    async def delete_session(self, session_id: str) -> bool:
        """删除会话文件"""
        path = self._get_session_path(session_id)
        if path.exists():
            path.unlink()
            logger.debug(f"Deleted session {session_id}")
            return True
        return False

    async def list_sessions(self) -> List[SessionInfo]:
        """列出所有会话"""
        sessions: List[SessionInfo] = []
        for json_file in self.sessions_dir.glob("*.json"):
            try:
                async with aiofiles.open(json_file, "r", encoding="utf-8") as f:
                    content = await f.read()
                data = json.loads(content)
                info = SessionInfo.from_dict(data.get("info", {}))
                sessions.append(info)
            except Exception as e:
                logger.warning(f"Failed to parse session {json_file}: {e}")
                continue

        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        return sessions

    async def save_long_term(self, entry: LongTermEntry) -> None:
        """保存长期记忆到JSON文件"""
        path = self._get_long_term_path(entry.id)
        content = json.dumps(entry.to_dict(), ensure_ascii=False, indent=2)
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(content)
        logger.debug(f"Saved long term entry {entry.id}")

    async def query_long_term(self, query: str, limit: int = 10) -> List[LongTermEntry]:
        """查询长期记忆，简单关键词匹配"""
        results: List[LongTermEntry] = []
        query_lower = query.lower()

        for json_file in self.long_term_dir.glob("*.json"):
            try:
                async with aiofiles.open(json_file, "r", encoding="utf-8") as f:
                    content = await f.read()
                data = json.loads(content)
                entry = LongTermEntry.from_dict(data)
                # 简单关键词匹配：检查查询词是否出现在内容或关键词中
                if query_lower in entry.content.lower():
                    results.append(entry)
                elif any(query_lower in keyword.lower() for keyword in entry.keywords):
                    results.append(entry)
            except Exception as e:
                logger.warning(f"Failed to parse long term entry {json_file}: {e}")
                continue

        # 按创建时间倒序，返回前N个
        results.sort(key=lambda e: e.created_at, reverse=True)
        return results[:limit]

    async def delete_long_term(self, entry_id: str) -> bool:
        """删除长期记忆条目"""
        path = self._get_long_term_path(entry_id)
        if path.exists():
            path.unlink()
            return True
        return False

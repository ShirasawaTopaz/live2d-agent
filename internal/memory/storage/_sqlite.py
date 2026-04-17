"""
SQLite Storage Backend - Reference Implementation
⚠️  This is reference design code, not yet production-ready
"""

import aiosqlite
import json
import logging
from typing import List, Optional
from datetime import datetime

from internal.memory.storage._base import BaseStorage
from internal.memory._types import SessionInfo, LongTermEntry


logger = logging.getLogger(__name__)


class SQLiteStorage(BaseStorage):
    """SQLite存储实现
    - 单数据库文件
    - 支持高效查询和ACID事务
    - 适合大量历史数据管理
    """

    CREATE_TABLES_SQL = """
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        title TEXT,
        message_count INTEGER DEFAULT 0,
        is_compressed INTEGER DEFAULT 0,
        data_json TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS long_term (
        id TEXT PRIMARY KEY,
        content TEXT NOT NULL,
        keywords TEXT NOT NULL,
        source_session_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        metadata_json TEXT DEFAULT '{}'
    );

    CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at);
    CREATE INDEX IF NOT EXISTS idx_sessions_compressed ON sessions(is_compressed);
    CREATE INDEX IF NOT EXISTS idx_long_term_keywords ON long_term(keywords);
    CREATE INDEX IF NOT EXISTS idx_long_term_created ON long_term(created_at);
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def init(self) -> None:
        """初始化数据库，创建表结构"""
        self._db = await aiosqlite.connect(self.db_path)
        assert self._db is not None
        await self._db.executescript(self.CREATE_TABLES_SQL)
        await self._db.commit()
        logger.info(f"SQLiteStorage initialized at {self.db_path}")

    async def close(self) -> None:
        """关闭数据库连接"""
        if self._db:
            await self._db.close()
            self._db = None

    async def save_session(self, session_id: str, data: dict) -> None:
        """保存会话数据"""
        info = data.get("info", {})

        assert self._db is not None
        is_compressed = info.get("is_compressed", 0)
        data_json = json.dumps(data, ensure_ascii=False)
        await self._db.execute(
            """
            REPLACE INTO sessions
            (session_id, created_at, updated_at, title, message_count, is_compressed, data_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                session_id,
                info.get("created_at", datetime.now().isoformat()),
                info.get("updated_at", datetime.now().isoformat()),
                info.get("title"),
                info.get("message_count", 0),
                1 if is_compressed else 0,
                data_json,
            ),
        )
        await self._db.commit()
        logger.debug(f"Saved session {session_id} to SQLite")

    async def load_session(self, session_id: str) -> dict | None:
        """加载会话数据"""
        assert self._db is not None
        async with self._db.execute(
            """
            SELECT data_json FROM sessions WHERE session_id = ?
        """,
            (session_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            # 这里我们实际存储完整的JSON数据，简化实现
            data = json.loads(row[0])
            logger.debug(f"Loaded session {session_id} from SQLite")
            return data

    async def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        assert self._db is not None
        await self._db.execute(
            "DELETE FROM sessions WHERE session_id = ?", (session_id,)
        )
        await self._db.commit()
        logger.debug(f"Deleted session {session_id} from SQLite")
        return True

    async def list_sessions(self) -> List[SessionInfo]:
        """列出所有会话，按更新时间倒序"""
        assert self._db is not None
        sessions: List[SessionInfo] = []

        async with self._db.execute("""
            SELECT session_id, created_at, updated_at, title, message_count, is_compressed
            FROM sessions
            ORDER BY updated_at DESC
        """) as cursor:
            async for row in cursor:
                try:
                    info = SessionInfo(
                        session_id=row[0],
                        created_at=datetime.fromisoformat(row[1]),
                        updated_at=datetime.fromisoformat(row[2]),
                        title=row[3],
                        message_count=row[4],
                        is_compressed=bool(row[5] if len(row) > 5 else False),
                    )
                    sessions.append(info)
                except Exception as e:
                    logger.warning(f"Failed to parse session {row[0]}: {e}")
                    continue

        return sessions

    async def save_long_term(self, entry: LongTermEntry) -> None:
        """保存长期记忆"""
        assert self._db is not None
        import json

        keywords_str = ",".join(entry.keywords)
        metadata_json = json.dumps(entry.metadata, ensure_ascii=False)

        await self._db.execute(
            """
            REPLACE INTO long_term
            (id, content, keywords, source_session_id, created_at, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (
                entry.id,
                entry.content,
                keywords_str,
                entry.source_session_id,
                entry.created_at.isoformat(),
                metadata_json,
            ),
        )
        await self._db.commit()
        logger.debug(f"Saved long term entry {entry.id} to SQLite")

    async def query_long_term(self, query: str, limit: int = 10) -> List[LongTermEntry]:
        """查询长期记忆，使用LIKE匹配关键词和内容"""
        assert self._db is not None
        results: List[LongTermEntry] = []
        query_pattern = f"%{query.lower()}%"
        import json

        async with self._db.execute(
            """
            SELECT id, content, keywords, source_session_id, created_at, metadata_json
            FROM long_term
            WHERE lower(content) LIKE ? OR lower(keywords) LIKE ?
            ORDER BY created_at DESC
            LIMIT ?
        """,
            (query_pattern, query_pattern, limit),
        ) as cursor:
            async for row in cursor:
                try:
                    keywords = row[2].split(",") if row[2] else []
                    metadata = json.loads(row[5]) if row[5] else {}
                    entry = LongTermEntry(
                        id=row[0],
                        content=row[1],
                        keywords=keywords,
                        source_session_id=row[3],
                        created_at=datetime.fromisoformat(row[4]),
                        metadata=metadata,
                    )
                    results.append(entry)
                except Exception as e:
                    logger.warning(f"Failed to parse long term entry {row[0]}: {e}")
                    continue

        return results

    async def delete_long_term(self, entry_id: str) -> bool:
        """删除长期记忆条目"""
        assert self._db is not None
        await self._db.execute("DELETE FROM long_term WHERE id = ?", (entry_id,))
        await self._db.commit()
        return True

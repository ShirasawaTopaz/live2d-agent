from __future__ import annotations

import aiofiles
import aiofiles.os
import aiosqlite
import json
import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path

from internal.mcp.protocol import MCPContextChunk

logger = logging.getLogger(__name__)


def _message_content(message: object) -> str:
    if isinstance(message, dict):
        content = message.get("content")
        return content if isinstance(content, str) else ""
    content = getattr(message, "content", "")
    return content if isinstance(content, str) else ""


class MCPStorageBackend(ABC):
    """MCP存储后端抽象基类"""

    @abstractmethod
    async def load_chunk(self, chunk_id: str) -> MCPContextChunk | None:
        """加载分片"""
        ...

    @abstractmethod
    async def save_chunk(self, chunk: MCPContextChunk) -> None:
        """保存分片"""
        ...

    @abstractmethod
    async def list_chunks(self, scope_id: str) -> list[str]:
        """列出某个范围的所有分片ID"""
        ...

    @abstractmethod
    async def delete_chunk(self, chunk_id: str) -> None:
        """删除分片"""
        ...

    @abstractmethod
    async def search(
        self,
        query: str,
        scope_id: str | None = None,
        limit: int = 10,
    ) -> list[MCPContextChunk]:
        """搜索相关分片"""
        ...


class JSONFileBackend(MCPStorageBackend):
    """JSON文件存储后端

    每个分片保存为单独的JSON文件。
    """

    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _chunk_path(self, chunk_id: str) -> Path:
        return self.base_dir / f"{chunk_id}.json"

    async def load_chunk(self, chunk_id: str) -> MCPContextChunk | None:
        path = self._chunk_path(chunk_id)
        if not path.exists():
            return None

        try:
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                content = await f.read()
            data = json.loads(content)
            return MCPContextChunk.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load chunk {chunk_id}: {e}")
            return None

    async def save_chunk(self, chunk: MCPContextChunk) -> None:
        path = self._chunk_path(chunk.chunk_id)
        try:
            content = json.dumps(chunk.to_dict(), indent=2, ensure_ascii=False)
            async with aiofiles.open(path, "w", encoding="utf-8") as f:
                await f.write(content)
        except Exception as e:
            logger.error(f"Failed to save chunk {chunk.chunk_id}: {e}")
            raise

    async def list_chunks(self, scope_id: str) -> list[str]:
        chunks: list[str] = []
        for file in self.base_dir.glob("*.json"):
            chunk_id = file.stem
            try:
                chunk = await self.load_chunk(chunk_id)
                if chunk and chunk.scope_id == scope_id:
                    chunks.append(chunk_id)
            except Exception:
                continue
        return chunks

    async def delete_chunk(self, chunk_id: str) -> None:
        path = self._chunk_path(chunk_id)
        if path.exists():
            await aiofiles.os.remove(path)

    async def search(
        self,
        query: str,
        scope_id: str | None = None,
        limit: int = 10,
    ) -> list[MCPContextChunk]:
        """简单关键词搜索，遍历所有分片匹配关键词"""
        results: list[MCPContextChunk] = []
        query_lower = query.lower()

        for file in self.base_dir.glob("*.json"):
            chunk_id = file.stem
            chunk = await self.load_chunk(chunk_id)
            if chunk is None:
                continue

            if scope_id and chunk.scope_id != scope_id:
                continue

            # 简单关键词匹配
            if chunk.summary and query_lower in chunk.summary.lower():
                results.append(chunk)
            else:
                for msg in chunk.messages:
                    if query_lower in _message_content(msg).lower():
                        results.append(chunk)
                        break

            if len(results) >= limit:
                break

        return results[:limit]


class SQLiteBackend(MCPStorageBackend):
    """SQLite存储后端

    复用现有的SQLite存储基础设施。
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        """Initialize database connection and create tables if needed"""
        self._db = await aiosqlite.connect(self.db_path)
        assert self._db is not None
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS mcp_chunks (
                chunk_id TEXT PRIMARY KEY,
                scope_id TEXT NOT NULL,
                summary TEXT,
                total_tokens INTEGER NOT NULL,
                compressed INTEGER NOT NULL,
                start_time INTEGER NOT NULL,
                end_time INTEGER NOT NULL,
                data_json TEXT NOT NULL
            )
        """)

        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_mcp_scope ON mcp_chunks(scope_id)
        """)

        await self._db.commit()

    async def close(self) -> None:
        """Close database connection"""
        if self._db:
            await self._db.close()
            self._db = None

    async def load_chunk(self, chunk_id: str) -> MCPContextChunk | None:
        assert self._db is not None
        async with self._db.execute(
            "SELECT data_json FROM mcp_chunks WHERE chunk_id = ?", (chunk_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if row is None:
            return None

        try:
            data = json.loads(row[0])
            return MCPContextChunk.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to parse chunk {chunk_id}: {e}")
            return None

    async def save_chunk(self, chunk: MCPContextChunk) -> None:
        assert self._db is not None
        data_json = json.dumps(chunk.to_dict(), ensure_ascii=False)
        await self._db.execute(
            """
            REPLACE INTO mcp_chunks
            (chunk_id, scope_id, summary, total_tokens, compressed,
             start_time, end_time, data_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                chunk.chunk_id,
                chunk.scope_id,
                chunk.summary,
                chunk.total_tokens,
                1 if chunk.compressed else 0,
                chunk.start_time,
                chunk.end_time,
                data_json,
            ),
        )

        await self._db.commit()

    async def list_chunks(self, scope_id: str) -> list[str]:
        assert self._db is not None
        async with self._db.execute(
            "SELECT chunk_id FROM mcp_chunks WHERE scope_id = ? ORDER BY start_time",
            (scope_id,),
        ) as cursor:
            rows = await cursor.fetchall()

        return [row[0] for row in rows]

    async def delete_chunk(self, chunk_id: str) -> None:
        assert self._db is not None
        await self._db.execute("DELETE FROM mcp_chunks WHERE chunk_id = ?", (chunk_id,))
        await self._db.commit()

    async def search(
        self,
        query: str,
        scope_id: str | None = None,
        limit: int = 10,
    ) -> list[MCPContextChunk]:
        """SQLite全文搜索"""
        assert self._db is not None

        # 简单LIKE搜索在summary和data_json
        where = "WHERE (summary LIKE ? OR data_json LIKE ?)"
        params = [f"%{query}%", f"%{query}%"]

        if scope_id:
            where += " AND scope_id = ?"
            params.append(scope_id)

        sql = f"SELECT chunk_id FROM mcp_chunks {where} LIMIT {limit}"
        async with self._db.execute(sql, params) as cursor:
            rows = await cursor.fetchall()

        results: list[MCPContextChunk] = []
        for row in rows:
            chunk = await self.load_chunk(row[0])
            if chunk:
                results.append(chunk)

        return results

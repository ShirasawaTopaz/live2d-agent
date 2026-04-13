from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path

from internal.mcp.protocol import MCPContextChunk

logger = logging.getLogger(__name__)


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
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return MCPContextChunk.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load chunk {chunk_id}: {e}")
            return None

    async def save_chunk(self, chunk: MCPContextChunk) -> None:
        path = self._chunk_path(chunk.chunk_id)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(chunk.to_dict(), f, indent=2, ensure_ascii=False)
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
            os.remove(path)

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
                    if query_lower in msg.content.lower():
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
        self._init_db()

    def _init_db(self) -> None:
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
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

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_mcp_scope ON mcp_chunks(scope_id)
        """)

        conn.commit()
        conn.close()

    async def load_chunk(self, chunk_id: str) -> MCPContextChunk | None:
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT data_json FROM mcp_chunks WHERE chunk_id = ?", (chunk_id,)
        )
        row = cursor.fetchone()
        conn.close()

        if row is None:
            return None

        try:
            data = json.loads(row[0])
            return MCPContextChunk.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to parse chunk {chunk_id}: {e}")
            return None

    async def save_chunk(self, chunk: MCPContextChunk) -> None:
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        data_json = json.dumps(chunk.to_dict(), ensure_ascii=False)
        cursor.execute(
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

        conn.commit()
        conn.close()

    async def list_chunks(self, scope_id: str) -> list[str]:
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT chunk_id FROM mcp_chunks WHERE scope_id = ? ORDER BY start_time",
            (scope_id,),
        )
        rows = cursor.fetchall()
        conn.close()

        return [row[0] for row in rows]

    async def delete_chunk(self, chunk_id: str) -> None:
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM mcp_chunks WHERE chunk_id = ?", (chunk_id,))
        conn.commit()
        conn.close()

    async def search(
        self,
        query: str,
        scope_id: str | None = None,
        limit: int = 10,
    ) -> list[MCPContextChunk]:
        """SQLite全文搜索"""
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 简单LIKE搜索在summary和data_json
        where = "WHERE (summary LIKE ? OR data_json LIKE ?)"
        params = [f"%{query}%", f"%{query}%"]

        if scope_id:
            where += " AND scope_id = ?"
            params.append(scope_id)

        sql = f"SELECT chunk_id FROM mcp_chunks {where} LIMIT {limit}"
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()

        results: list[MCPContextChunk] = []
        for row in rows:
            chunk = await self.load_chunk(row[0])
            if chunk:
                results.append(chunk)

        return results

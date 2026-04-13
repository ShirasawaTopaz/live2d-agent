from __future__ import annotations

import logging
from typing import Any
import aiohttp

from internal.mcp.protocol import MCPContextChunk
from internal.mcp.backend import MCPStorageBackend
from internal.mcp.config import RemoteMCPConfig

logger = logging.getLogger(__name__)


class RemoteMCPBackend(MCPStorageBackend):
    """远程MCP服务存储后端

    通过HTTP API连接到外部MCP服务，所有存储操作代理到远程。
    支持混合模式：本地工作内存，长期存储由远程管理。
    """

    def __init__(self, config: RemoteMCPConfig) -> None:
        self.config = config
        self._session: aiohttp.ClientSession | None = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            connector = aiohttp.TCPConnector(ssl=self.config.verify_ssl)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
            )
        return self._session

    def _get_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers

    async def _call(
        self,
        method: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """调用远程RPC方法"""
        session = await self._ensure_session()
        endpoint = self.config.endpoint.rstrip("/") + "/v1/rpc"

        request = {
            "jsonrpc": "2.0",
            "id": "1",
            "method": method,
            "params": params,
        }

        try:
            async with session.post(
                endpoint,
                json=request,
                headers=self._get_headers(),
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(
                        f"Remote MCP error: status={resp.status}, response={text[:200]}"
                    )

                data = await resp.json()
                if "error" in data:
                    raise RuntimeError(f"Remote MCP error: {data['error']}")

                return data.get("result", {})

        except aiohttp.ClientError as e:
            logger.error(f"Remote MCP connection error: {e}")
            raise RuntimeError(f"Connection failed: {e}") from e

    async def load_chunk(self, chunk_id: str) -> MCPContextChunk | None:
        result = await self._call("chunk.load", {"chunk_id": chunk_id})
        if not result.get("found"):
            return None
        data = result.get("chunk", {})
        return MCPContextChunk.from_dict(data)

    async def save_chunk(self, chunk: MCPContextChunk) -> None:
        await self._call("chunk.save", {"chunk": chunk.to_dict()})

    async def list_chunks(self, scope_id: str) -> list[str]:
        result = await self._call("chunk.list", {"scope_id": scope_id})
        return result.get("chunk_ids", [])

    async def delete_chunk(self, chunk_id: str) -> None:
        await self._call("chunk.delete", {"chunk_id": chunk_id})

    async def search(
        self,
        query: str,
        scope_id: str | None = None,
        limit: int = 10,
    ) -> list[MCPContextChunk]:
        params = {"query": query, "limit": limit}
        if scope_id:
            params["scope_id"] = scope_id
        result = await self._call("context.search", params)
        chunks_data = result.get("chunks", [])
        return [MCPContextChunk.from_dict(data) for data in chunks_data]

    async def close(self) -> None:
        """关闭HTTP连接"""
        if self._session and not self._session.closed:
            await self._session.close()


class RemoteMCPManager:
    """完整远程MCP管理，所有操作代理到远程服务"""

    def __init__(self, config: RemoteMCPConfig) -> None:
        self.backend = RemoteMCPBackend(config)
        self.config = config

    async def create_session(self, session_id: str) -> dict[str, Any]:
        """创建新会话"""
        return await self.backend._call("session.create", {"session_id": session_id})

    async def get_context(
        self,
        session_id: str,
        scope_id: str,
        max_tokens: int,
        search_query: str | None = None,
    ) -> dict[str, Any]:
        """获取上下文"""
        params = {
            "session_id": session_id,
            "scope_id": scope_id,
            "max_tokens": max_tokens,
        }
        if search_query:
            params["search_query"] = search_query
        return await self.backend._call("context.get", params)

    async def add_message(
        self,
        session_id: str,
        scope_id: str,
        message: dict[str, Any],
    ) -> dict[str, Any]:
        """添加消息"""
        return await self.backend._call(
            "context.add",
            {
                "session_id": session_id,
                "scope_id": scope_id,
                "message": message,
            },
        )

    async def switch_scope(
        self,
        session_id: str,
        scope_id: str,
    ) -> dict[str, Any]:
        """切换范围"""
        return await self.backend._call(
            "session.switch_scope",
            {
                "session_id": session_id,
                "scope_id": scope_id,
            },
        )

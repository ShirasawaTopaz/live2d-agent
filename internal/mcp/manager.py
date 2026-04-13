from __future__ import annotations

import logging
import asyncio
from typing import Any

from internal.mcp.protocol import (
    MCPMessage,
    MCPContextChunk,
    MCPGetContextRequest,
    MCPGetContextResponse,
    MCPParticipant,
    MCPMode,
)
from internal.mcp.config import MCPConfig
from internal.mcp.compression import (
    CompressionStrategy,
    create_compression_strategy,
)
from internal.mcp.backend import MCPStorageBackend, JSONFileBackend, SQLiteBackend

logger = logging.getLogger(__name__)


class WorkingMemory:
    """工作内存 - 当前活跃对话"""

    def __init__(self, max_messages: int = 10) -> None:
        self.messages: list[MCPMessage] = []
        self.max_messages = max_messages

    def add(self, message: MCPMessage) -> None:
        self.messages.append(message)
        # 如果超过限制，保持最后N条（不删除，只限制展示）
        if len(self.messages) > self.max_messages * 2:
            self.messages = self.messages[-self.max_messages * 2 :]

    def get_all(self) -> list[MCPMessage]:
        return self.messages.copy()

    def clear(self) -> None:
        self.messages.clear()

    @property
    def count(self) -> int:
        return len(self.messages)

    @property
    def total_tokens(self) -> int:
        return sum(m.tokens or 0 for m in self.messages)


class MCPContextManager:
    """MCP上下文管理器 - 核心协调组件

    管理三层存储：
    1. 工作内存 - 当前轮次直接交互
    2. 近期上下文 - 未压缩完整消息
    3. 长期记忆 - 已压缩分片
    """

    def __init__(self, config: MCPConfig, data_dir: str = ".mcp") -> None:
        self.config = config
        self.data_dir = data_dir
        self._storage: MCPStorageBackend | None = None
        self._compression: CompressionStrategy | None = None
        self._working_memory: dict[str, WorkingMemory] = {}
        self._recent_chunks: dict[str, list[MCPContextChunk]] = {}
        self._current_scope_id: str = "default"
        self._current_session_id: str = "default"
        self._lock = asyncio.Lock()
        self._compression_task: asyncio.Task | None = None

        # 初始化存储和压缩策略
        self._init_storage()
        self._init_compression()

    def _init_storage(self) -> None:
        """初始化存储后端"""
        if self.config.mode == MCPMode.REMOTE:
            # 远程存储在remote.py处理
            # 这里由外部初始化注入
            return

        if self.config.storage_type == "sqlite":
            db_path = f"{self.data_dir}/mcp.db"
            self._storage = SQLiteBackend(db_path)
        else:
            self._storage = JSONFileBackend(f"{self.data_dir}/chunks")

        logger.info(f"MCP storage initialized: {self.config.storage_type}")

    def _init_compression(self) -> None:
        """初始化压缩策略"""
        self._compression = create_compression_strategy(
            self.config.compression_strategy
        )
        logger.info(f"MCP compression strategy: {self.config.compression_strategy}")

    def set_storage(self, storage: MCPStorageBackend) -> None:
        """注入自定义存储（用于远程后端）"""
        self._storage = storage

    def set_compression(self, compression: CompressionStrategy) -> None:
        """注入自定义压缩策略"""
        self._compression = compression

    async def add_message(
        self,
        message: MCPMessage,
        scope_id: str | None = None,
    ) -> None:
        """添加新消息到当前上下文"""
        async with self._lock:
            scope = scope_id or self._current_scope_id
            working = self._get_working_memory(scope)
            working.add(message)

            logger.debug(f"Added message to scope {scope}, total: {working.count}")

            # 检查是否需要自动压缩
            if (
                self.config.auto_compress
                and working.count >= self.config.compression_threshold_messages
                and self._compression_task is None
            ):
                # 后台异步压缩
                self._compression_task = asyncio.create_task(
                    self._trigger_compression_background(scope)
                )

    def _get_working_memory(self, scope_id: str) -> WorkingMemory:
        """获取或创建工作内存"""
        if scope_id not in self._working_memory:
            self._working_memory[scope_id] = WorkingMemory(
                self.config.max_working_messages
            )
        return self._working_memory[scope_id]

    def _get_recent_chunks(self, scope_id: str) -> list[MCPContextChunk]:
        """获取近期分片列表"""
        if scope_id not in self._recent_chunks:
            self._recent_chunks[scope_id] = []
        return self._recent_chunks[scope_id]

    async def get_context(
        self, request: MCPGetContextRequest | None = None
    ) -> MCPGetContextResponse:
        """获取组装好的上下文，供AI模型调用"""
        if request is None:
            request = MCPGetContextRequest(
                session_id=self._current_session_id,
                scope_id=self._current_scope_id,
                max_tokens=self.config.max_total_tokens,
            )

        async with self._lock:
            scope_id = request.scope_id

            # 1. 获取工作内存消息
            working = self._get_working_memory(scope_id)
            working_messages = working.get_all()

            # 2. 获取近期上下文
            recent_chunks = self._get_recent_chunks(scope_id)
            recent_messages: list[MCPMessage] = []
            recent_tokens = 0
            for chunk in recent_chunks:
                recent_messages.extend(chunk.messages)
                recent_tokens += chunk.total_tokens

            # 3. 如果需要，检索长期记忆
            long_term_messages: list[MCPMessage] = []
            if self.config.enable_long_term and request.search_query and self._storage:
                chunks = await self._storage.search(
                    request.search_query,
                    scope_id=scope_id,
                    limit=5,
                )
                for chunk in chunks:
                    if chunk.summary:
                        long_term_messages.append(
                            MCPMessage.create(
                                role=MCPParticipant.SYSTEM,
                                content=f"[相关历史摘要] {chunk.summary}",
                            )
                        )

            # 4. 组合所有消息，token限制
            all_messages = long_term_messages + recent_messages + working_messages
            total_tokens = sum(m.tokens or 0 for m in all_messages)

            # 如果超过限制，截断最早的消息
            truncated = False
            if total_tokens > request.max_tokens:
                truncated = True
                # 从前往后截断，保留最新
                while total_tokens > request.max_tokens and len(all_messages) > 1:
                    removed = all_messages.pop(0)
                    total_tokens -= removed.tokens or 0

            response = MCPGetContextResponse(
                messages=all_messages,
                chunks=recent_chunks
                + (
                    [chunk for chunk in []]  # 长期分片不返回完整
                ),
                total_tokens=total_tokens,
                truncated=truncated,
                has_more=truncated,
            )

            logger.debug(
                f"Context for {scope_id}: {len(response.messages)} messages, "
                f"{response.total_tokens} tokens, truncated={truncated}"
            )

            return response

    async def switch_scope(self, scope_id: str) -> None:
        """切换当前范围（场景/技能）"""
        async with self._lock:
            self._current_scope_id = scope_id
            logger.info(f"Switched to scope: {scope_id}")

            # 预加载分片
            if self._storage:
                chunk_ids = await self._storage.list_chunks(scope_id)
                recent: list[MCPContextChunk] = []
                for cid in chunk_ids[-5:]:  # 只加载最近5个
                    chunk = await self._storage.load_chunk(cid)
                    if chunk:
                        recent.append(chunk)
                self._recent_chunks[scope_id] = recent

    async def _trigger_compression_background(self, scope_id: str) -> None:
        """后台压缩任务"""
        try:
            await self.compress_pending(scope_id)
        except Exception as e:
            logger.error(f"Background compression failed: {e}")
        finally:
            self._compression_task = None

    async def compress_pending(self, scope_id: str) -> None:
        """压缩待处理的工作内存消息"""
        async with self._lock:
            working = self._get_working_memory(scope_id)
            if working.count <= self.config.max_working_messages:
                return

            # 取要压缩的旧消息
            compress_count = working.count - self.config.max_working_messages
            to_compress = working.messages[:compress_count]
            keep = working.messages[compress_count:]

            if not self._compression:
                logger.warning("No compression strategy, skipping compression")
                return

            # 执行压缩
            chunk = await self._compression.compress(
                scope_id=scope_id,
                messages=to_compress,
                target_tokens=self.config.max_recent_tokens,
            )

            # 添加到近期分片
            recent = self._get_recent_chunks(scope_id)
            recent.append(chunk)

            # 保存到存储
            if self._storage and self.config.enable_long_term:
                await self._storage.save_chunk(chunk)

            # 更新工作内存保留压缩后最新
            working.messages = keep

            logger.info(
                f"Compressed {len(to_compress)} messages into chunk {chunk.chunk_id}, "
                f"tokens: {chunk.total_tokens}"
            )

            # 如果近期分片太多，归档旧分片
            await self._archive_old_recent_chunks(scope_id)

    async def _archive_old_recent_chunks(self, scope_id: str) -> None:
        """归档旧的近期分片到长期存储"""
        recent = self._get_recent_chunks(scope_id)

        # 保持近期分片数量限制
        max_recent = 5
        if len(recent) > max_recent:
            # 旧分片已经存储，只需要从内存移除
            old_chunks = recent[:-max_recent]
            self._recent_chunks[scope_id] = recent[-max_recent:]
            logger.debug(f"Archived {len(old_chunks)} old chunks from memory")

    async def archive_all(self, scope_id: str | None = None) -> None:
        """归档所有未压缩消息"""
        target_scope = scope_id or self._current_scope_id
        await self.compress_pending(target_scope)
        await self._archive_old_recent_chunks(target_scope)

    async def clear_scope(self, scope_id: str | None = None) -> None:
        """清空指定范围"""
        target_scope = scope_id or self._current_scope_id
        async with self._lock:
            if target_scope in self._working_memory:
                self._working_memory[target_scope].clear()
            if target_scope in self._recent_chunks:
                self._recent_chunks[target_scope] = []
            logger.info(f"Cleared scope: {target_scope}")

    def current_scope(self) -> str:
        """获取当前范围ID"""
        return self._current_scope_id

    def convert_from_legacy_messages(
        self,
        legacy_messages: list[dict[str, Any]],
        scope_id: str | None = None,
    ) -> list[MCPMessage]:
        """从旧格式消息转换为MCP格式"""
        mcp_messages: list[MCPMessage] = []
        role_map = {
            "system": MCPParticipant.SYSTEM,
            "user": MCPParticipant.USER,
            "assistant": MCPParticipant.ASSISTANT,
            "tool": MCPParticipant.TOOL,
        }

        for msg in legacy_messages:
            role_str = msg.get("role", "user")
            role = role_map.get(role_str, MCPParticipant.USER)
            content = msg.get("content", "")
            if isinstance(content, list):
                # 多模态内容简化处理
                content = " ".join(
                    item.get("text", "") if isinstance(item, dict) else str(item)
                    for item in content
                )

            mcp_msg = MCPMessage.create(
                role=role,
                content=content,
                tokens=msg.get("tokens"),
                tool_name=msg.get("tool_name"),
                tool_call_id=msg.get("tool_call_id"),
                metadata=msg.get("metadata", {}),
            )
            mcp_messages.append(mcp_msg)

        return mcp_messages

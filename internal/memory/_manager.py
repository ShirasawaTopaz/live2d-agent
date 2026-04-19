"""
Memory System Main Manager - Reference Implementation
⚠️  This is reference design code, not yet production-ready
"""

import asyncio
import logging
import os
from collections.abc import Coroutine
from dataclasses import asdict
from typing import List, Optional

from internal.memory._types import (
    Message,
    SessionInfo,
    ConversationTurn,
    MemoryConfig,
)
from internal.memory._session import SessionManager
from internal.memory._context import ContextManager
from internal.memory._summary import Summarizer
from internal.memory._long_term import LongTermMemory
from internal.memory._archive import ArchiveCompressor
from internal.memory._importance import ImportanceScorer
from internal.memory._small_model_profile import (
    SmallModelMemoryProfile,
    classify_small_model_memory_profile,
)
from internal.memory._tool_offload import ToolResultOffloader
from internal.memory.storage._base import BaseStorage
from internal.memory.storage._json import JSONStorage
from internal.memory.storage._sqlite import SQLiteStorage

# MCP (Model Context Protocol) import
from internal.mcp import (
    MCPConfig,
    MCPContextManager,
    MCPMessage,
    MCPMode,
)
from internal.mcp.protocol import estimate_tokens
from internal.mcp.remote import RemoteMCPBackend


logger = logging.getLogger(__name__)


def create_storage(cfg: MemoryConfig) -> BaseStorage:
    """根据配置创建存储后端"""
    if cfg.storage_type == "json":
        return JSONStorage(cfg.data_dir)
    elif cfg.storage_type == "sqlite":
        db_path = os.path.join(cfg.data_dir, "memory.db")
        return SQLiteStorage(db_path)
    else:
        raise ValueError(f"Unknown storage type: {cfg.storage_type}")


class MemoryManager:
    """Memory系统主管理器
    协调SessionManager, ContextManager, Summarizer, LongTermMemory, ArchiveCompressor

    When MCP is enabled, delegates to MCPContextManager for enhanced context management.
    """

    def __init__(self, config: MemoryConfig):
        self.config = config
        self._storage: Optional[BaseStorage] = None
        self._session_manager: Optional[SessionManager] = None
        self._context_manager: Optional[ContextManager] = None
        self._summarizer: Optional[Summarizer] = None
        self._importance_scorer: Optional[ImportanceScorer] = None
        self._tool_offloader: Optional[ToolResultOffloader] = None
        self._long_term: Optional[LongTermMemory] = None
        self._archive_compressor: Optional[ArchiveCompressor] = None
        self._small_model_profile: Optional[SmallModelMemoryProfile] = None

        # MCP integration
        self._mcp: Optional[MCPContextManager] = None
        self._pending_mcp_tasks: set[asyncio.Task[None]] = set()

        self._initialized = False

    @property
    def storage(self) -> BaseStorage:
        assert self._storage is not None, "Memory not initialized, call init() first"
        return self._storage

    @property
    def session_manager(self) -> SessionManager:
        assert self._session_manager is not None
        return self._session_manager

    @property
    def context_manager(self) -> ContextManager:
        assert self._context_manager is not None
        return self._context_manager

    @property
    def summarizer(self) -> Summarizer:
        assert self._summarizer is not None
        return self._summarizer

    @property
    def importance_scorer(self) -> Optional[ImportanceScorer]:
        return self._importance_scorer

    @property
    def tool_offloader(self) -> Optional[ToolResultOffloader]:
        return self._tool_offloader

    @property
    def long_term(self) -> Optional[LongTermMemory]:
        return self._long_term

    @property
    def archive_compressor(self) -> Optional[ArchiveCompressor]:
        return self._archive_compressor

    async def init(self) -> None:
        """初始化所有组件"""
        if not self.config.enabled:
            logger.info("Memory system disabled by configuration")
            return

        self._small_model_profile = self._resolve_small_model_profile()
        self._log_small_model_profile_decision()
        setattr(self.config, "small_model_memory_profile", self._small_model_profile)

        # Check if MCP is enabled
        if self.config.use_mcp:
            # Initialize MCP context manager
            logger.info("Initializing MCP (Model Context Protocol)...")

            # Extract MCP configuration from memory config.
            # Keep legacy memory fields as fallbacks so existing config.json files still work.
            mcp_config = MCPConfig.from_dict(
                {
                    "enabled": self.config.use_mcp,
                    "mcp_mode": getattr(self.config, "mcp_mode", "local"),
                    "compression_strategy": getattr(
                        self.config, "compression_strategy", "summary"
                    ),
                    "max_working_messages": getattr(
                        self.config, "max_working_messages", self.config.max_messages
                    ),
                    "max_recent_tokens": getattr(
                        self.config, "max_recent_tokens", self.config.max_tokens
                    ),
                    "max_total_tokens": getattr(
                        self.config, "max_total_tokens", self.config.max_tokens
                    ),
                    "enable_long_term": self.config.enable_long_term,
                    "storage_type": self.config.storage_type,
                    "remote": getattr(self.config, "remote", {}),
                    "auto_compress": self.config.compress_on_startup,
                    "compression_threshold_messages": self.config.compression_threshold_messages,
                    "small_model_memory_profile": (
                        asdict(self._small_model_profile)
                        if self._small_model_profile is not None
                        else None
                    ),
                }
            )

            data_dir = self.config.data_dir.replace("/memory", "/mcp")
            self._mcp = MCPContextManager(mcp_config, data_dir=data_dir)

            # Check if remote MCP is configured
            # If full remote mode is used, setup remote backend
            if mcp_config.mode == MCPMode.REMOTE and mcp_config.remote.enabled:
                remote_backend = RemoteMCPBackend(mcp_config.remote)
                self._mcp.set_storage(remote_backend)

            # Switch to default scope, but always start each app launch with a
            # fresh active context instead of reusing the previously loaded one.
            await self._mcp.switch_scope("default")
            # NOTE: Do NOT clear scope here - preserve conversation history between app launches
            # If you need a fresh context, call reset_active_context() explicitly instead

            self._initialized = True
            logger.info("MemoryManager initialized with MCP successfully")
            return

        # Original initialization for legacy memory system

        # 创建存储
        self._storage = create_storage(self.config)
        await self._storage.init()

        # 创建核心组件
        self._context_manager = ContextManager(
            max_messages=self.config.max_messages,
            max_tokens=self.config.max_tokens,
            compression_threshold=self.config.compression_threshold_messages,
            preserve_recent_count=self.config.preserve_recent_count,
            token_trigger_ratio=self.config.token_trigger_ratio,
            profile=self._small_model_profile,
        )

        self._session_manager = SessionManager(
            storage=self._storage,
            max_sessions=self.config.max_sessions,
            auto_cleanup=self.config.auto_cleanup,
        )

        self._summarizer = Summarizer(
            model_name=self.config.compression_model,
            iterative_mode=getattr(self.config, "iterative_mode", True),
            profile=self._small_model_profile,
        )

        self._importance_scorer = ImportanceScorer()

        self._tool_offloader = ToolResultOffloader(
            data_dir=os.path.join(self.config.data_dir, "tool_offload")
        )

        # Compression metrics (Phase 4)
        self._compression_count: int = 0
        self._last_compression_info: Optional[dict] = None

        if self.config.enable_long_term:
            self._long_term = LongTermMemory(
                storage=self._storage,
                enabled=True,
                profile=self._small_model_profile,
            )

        # 创建长期归档压缩器
        if self.config.long_term_compression_enabled:
            self._archive_compressor = ArchiveCompressor(
                storage=self._storage,
                summarizer=self._summarizer,
                config=self.config,
            )

        # 从存储加载所有会话信息
        await self._session_manager.load_all_sessions()

        # 启动时始终创建一个新会话，避免重新打开应用时继续上次的活动上下文。
        # 已有会话仍然会被加载到内存并保留在存储中，仅不再自动恢复为当前会话。
        await self._session_manager.new_session("default")

        # 启动时自动压缩不活跃会话
        if (
            self.config.long_term_compression_enabled
            and self.config.compress_on_startup
            and self._archive_compressor is not None
        ):
            # Run in background to avoid blocking startup
            asyncio.create_task(self._background_auto_compress())

        self._initialized = True
        logger.info("MemoryManager initialized successfully (legacy mode)")

    async def _background_auto_compress(self) -> None:
        """Background task for auto-compression on startup"""
        await asyncio.sleep(2.0)  # Wait a bit for app to stabilize
        try:
            count = await self.compress_all_eligible()
            if count > 0:
                logger.info(
                    f"Background auto-compression completed: {count} sessions compressed"
                )
        except Exception as e:
            logger.error(f"Background auto-compression failed: {e}", exc_info=True)

    async def new_session(self, title: Optional[str] = None) -> SessionInfo:
        """创建新会话"""
        assert self._initialized
        return await self.session_manager.new_session(title)

    async def reset_active_context(self, title: Optional[str] = None) -> None:
        """清空当前活动上下文，并为后续对话准备一个干净状态。"""
        assert self._initialized

        if self._mcp is not None:
            await self._drain_pending_mcp_tasks()
            await self._mcp.clear_scope()
            return

        await self.session_manager.new_session(title)

    async def switch_session(self, session_id: str) -> bool:
        """切换会话"""
        assert self._initialized
        return await self.session_manager.switch_session(session_id)

    def list_sessions(self) -> List[SessionInfo]:
        """列出所有会话"""
        assert self._initialized
        return self.session_manager.list_sessions()

    async def delete_current_session(self) -> bool:
        """删除当前会话"""
        assert self._initialized
        success = await self.session_manager.delete_current_session()
        if success and not self.session_manager.list_sessions():
            await self.session_manager.new_session("default")
        return success

    def add_message(self, message: Message) -> ConversationTurn | None:
        """添加消息到当前会话

        When MCP is enabled, adds to MCP context and returns None.
        """
        assert self._initialized

        if self._mcp is not None:
            # Convert to MCP message
            from internal.mcp.protocol import MCPParticipant

            role_map = {
                "system": MCPParticipant.SYSTEM,
                "user": MCPParticipant.USER,
                "assistant": MCPParticipant.ASSISTANT,
                "tool": MCPParticipant.TOOL,
            }
            role_str = message.get("role", "user")
            role = role_map.get(role_str, MCPParticipant.USER)
            content = message.get("content", "")

            # Handle list content (multimodal)
            if isinstance(content, list):
                content = " ".join(
                    item.get("text", "") if isinstance(item, dict) else str(item)
                    for item in content
                )

            mcp_message = MCPMessage.create(
                role=role,
                content=content,
                tokens=message.get("tokens") or estimate_tokens(content),
                tool_name=message.get("tool_name"),
                tool_call_id=message.get("tool_call_id"),
                metadata=message.get("metadata", {}),
            )

            # Add to MCP context manager and keep track of pending writes so
            # reset/get-context operations can wait for them deterministically.
            self._track_mcp_task(self._mcp.add_message(mcp_message))
            return None

        # Legacy mode
        return self.session_manager.add_turn(message)

    async def get_current_messages(self) -> List[Message]:
        """获取当前会话所有消息

        When MCP is enabled, get messages from MCP context and convert to legacy format.
        """
        assert self._initialized

        if self._mcp is not None:
            await self._drain_pending_mcp_tasks()
            # Get context from MCP
            response = await self._mcp.get_context()
            # Convert back to legacy format
            legacy_messages: List[Message] = []
            for msg in response.messages:
                legacy_msg: Message = {
                    "role": msg.role.value,
                    "content": msg.content,
                    "tokens": msg.tokens,
                    "tool_name": msg.tool_name,
                    "tool_call_id": msg.tool_call_id,
                    "metadata": msg.metadata,
                }
                legacy_messages.append(legacy_msg)
            return legacy_messages

        # Legacy mode
        return self.session_manager.get_messages()

    def should_compress(self) -> bool:
        """检查是否需要压缩上下文

        MCP handles compression automatically in background.
        """
        if not self.config.compression_enabled:
            return False
        assert self._initialized

        if self._mcp is not None:
            # MCP auto-compresses in background, no need for manual trigger
            return False

        return self.context_manager.should_compress(self.session_manager)

    async def compress_current(
        self,
        summary_text: str,
    ) -> bool:
        """使用摘要压缩当前上下文"""
        assert self._initialized
        turns = self.session_manager.get_turns()
        if len(turns) <= self.config.compression_threshold_messages:
            return False

        start_idx = 0
        for i, turn in enumerate(turns):
            if turn.message.get("role", "") != "system":
                start_idx = i
                break

        preserve_count = self.config.preserve_recent_count
        if self._small_model_profile is not None and self._small_model_profile.enabled:
            preserve_count = self.context_manager.get_preserve_recent_count()
        end_idx = len(turns) - preserve_count

        if end_idx <= start_idx:
            return False

        original_count = len(turns)

        if self._importance_scorer and self._summarizer.iterative_mode:
            new_turns, summary_entry = self.summarizer.compress_with_iterative(
                turns, summary_text, start_idx, end_idx
            )
            method = "iterative"
        else:
            new_turns, summary_entry = self.summarizer.compress_old_messages(
                turns, summary_text, start_idx, end_idx
            )
            method = "full_reconstruction"

        assert self.session_manager._current_session_id is not None
        session_id = self.session_manager._current_session_id
        self.session_manager._sessions[session_id] = new_turns
        self.session_manager._update_session_info()
        await self.save_current()

        self._record_compression(original_count, len(new_turns), method)
        logger.info(f"Compressed context: {original_count} -> {len(new_turns)} messages ({method})")
        return True

    async def save_current(self) -> None:
        """保存当前会话到存储"""
        assert self._initialized
        if self._mcp is not None:
            # MCP handles persistence internally
            return
        await self.session_manager.save_current()

    async def inject_long_term(
        self,
        current_query: str,
        system_prompt: str,
        limit: int = 5,
    ) -> str:
        """注入相关长期记忆到system prompt"""
        if self.long_term is None or not self.config.enable_long_term:
            return system_prompt

        entries = await self.long_term.query_relevant(current_query, limit)
        if not entries:
            return system_prompt

        injection = self.long_term.build_injection_prompt(entries)
        return system_prompt + injection

    def _resolve_small_model_profile(self) -> SmallModelMemoryProfile | None:
        runtime_profile = getattr(self.config, "small_model_memory_profile", None)
        if isinstance(runtime_profile, SmallModelMemoryProfile):
            return runtime_profile

        model_config = getattr(self.config, "small_model_memory_model_config", None)
        if _looks_like_model_config(model_config):
            profile = classify_small_model_memory_profile(model_config)
            setattr(self.config, "small_model_memory_profile", profile)
            return profile

        return None

    def _log_small_model_profile_decision(self) -> None:
        profile = self._small_model_profile
        model_config = getattr(self.config, "small_model_memory_model_config", None)
        model_identifier = (
            getattr(model_config, "model", None)
            if _looks_like_model_config(model_config)
            else "unknown"
        )
        backend = (
            _get_model_backend_value(model_config)
            if _looks_like_model_config(model_config)
            else "unknown"
        )

        if profile is None:
            logger.info(
                "Small-model memory profile decision: fallback=legacy-default "
                "(reason=no-model-config backend=%s model=%s)",
                backend,
                model_identifier,
            )
            return

        if profile.enabled:
            logger.info(
                "Small-model memory profile decision: enabled "
                "(backend=%s model=%s reason=%s style=%s preserve_recent=%s summary_cap=%s injection=%s)",
                backend,
                model_identifier,
                profile.reason,
                profile.summary_style,
                profile.preserve_recent_count,
                profile.summary_length_cap,
                profile.injection_compactness,
            )
            return

        logger.info(
            "Small-model memory profile decision: fallback=legacy-default "
            "(backend=%s model=%s reason=%s)",
            backend,
            model_identifier,
            profile.reason,
        )

    async def estimate_total_tokens(self) -> int:
        """估算当前上下文token数"""
        assert self._initialized

        if self._mcp is not None:
            response = await self._mcp.get_context()
            return response.total_tokens

        messages = await self.get_current_messages()
        return self.context_manager.estimate_total_tokens(messages)

    def _track_mcp_task(self, coroutine: Coroutine[object, object, None]) -> None:
        task = asyncio.create_task(coroutine)
        self._pending_mcp_tasks.add(task)
        task.add_done_callback(self._pending_mcp_tasks.discard)

    async def _drain_pending_mcp_tasks(self) -> None:
        if not self._pending_mcp_tasks:
            return
        pending = tuple(self._pending_mcp_tasks)
        await asyncio.gather(*pending)

    def current_session_info(self) -> Optional[SessionInfo]:
        """获取当前会话信息"""
        assert self._initialized
        return self.session_manager.current_info

    # === Long-term archive compression API ===
    async def list_compressible_sessions(self) -> List[SessionInfo]:
        """List all sessions eligible for compression"""
        assert self._initialized
        if self._archive_compressor is None:
            return []
        return await self._archive_compressor.find_compressible_sessions()

    async def compress_session(self, session_id: str, summary_text: str) -> bool:
        """Compress a specific session with the given summary"""
        assert self._initialized
        if self._archive_compressor is None:
            return False
        return await self._archive_compressor.compress_session_with_summary(
            session_id, summary_text
        )

    async def compress_all_eligible(self) -> int:
        """Compress all eligible inactive sessions

        Returns number of sessions compressed.
        Currently uses lazy compression - just identifies candidates.
        Full compression happens when session is opened.
        """
        assert self._initialized
        if self._archive_compressor is None:
            return 0
        return await self._archive_compressor.compress_all_eligible()

    # === End long-term archive compression API ===

    # === Compression metrics and debug (Phase 4) ===
    def get_compression_stats(self) -> dict:
        """Get compression statistics"""
        return {
            "compression_count": self._compression_count,
            "last_compression": self._last_compression_info,
        }

    def _record_compression(self, original_count: int, compressed_count: int, method: str) -> None:
        """Record compression event for metrics"""
        self._compression_count += 1
        self._last_compression_info = {
            "original_count": original_count,
            "compressed_count": compressed_count,
            "method": method,
        }
        logger.debug(
            f"Compression #{self._compression_count}: {original_count} -> {compressed_count} messages ({method})"
        )


def _looks_like_model_config(value: object) -> bool:
    return (
        value is not None
        and hasattr(value, "model")
        and hasattr(value, "type")
        and hasattr(value, "config")
    )


def _get_model_backend_value(model_config: object) -> str:
    model_type = getattr(model_config, "type", None)
    if isinstance(model_type, str):
        return model_type
    value = getattr(model_type, "value", None)
    if isinstance(value, str):
        return value
    return "unknown"

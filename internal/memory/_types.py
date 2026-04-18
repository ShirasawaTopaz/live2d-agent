"""
Memory System Type Definitions - Reference Implementation
⚠️  This is reference design code, not yet production-ready
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, MutableMapping

Message = MutableMapping[str, Any]


class MemoryConfig:
    """Memory配置"""

    def __init__(self) -> None:
        self.enabled: bool = True
        self.storage_type: str = "json"  # json or sqlite
        self.data_dir: str = "./data/memory"
        self.max_messages: int = 20
        self.max_tokens: int = 4096
        self.compression_enabled: bool = True
        self.compression_model: str = "default"
        self.compression_threshold_messages: int = 15
        # Long-term storage compression settings
        self.long_term_compression_enabled: bool = True
        self.compression_cutoff_days: int = 7  # Don't compress if accessed within this many days
        self.compression_min_messages: int = 10  # Don't compress sessions with fewer messages
        self.compress_on_startup: bool = True  # Auto-compress during initialization
        # End long-term compression settings
        self.enable_long_term: bool = True
        self.long_term_storage: str = "sqlite"
        self.auto_cleanup: bool = True
        self.max_sessions: int = 10
        # MCP (Model Context Protocol) settings
        self.use_mcp: bool = False
        self.mcp_mode: str = "local"
        self.compression_strategy: str = "summary"
        self.max_working_messages: int = 10
        self.max_recent_tokens: int = 2048
        self.max_total_tokens: int = 4096
        self.remote: dict[str, Any] = {
            "enabled": False,
            "endpoint": "http://localhost:8080/v1",
            "api_key": None,
            "timeout": 30,
            "verify_ssl": True,
        }

    """Enable Model Context Protocol for enhanced context management"""

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryConfig":
        cfg = cls()
        cfg.enabled = data.get("enabled", True)
        cfg.storage_type = data.get("storage_type", "json")
        cfg.data_dir = data.get("data_dir", "./data/memory")
        cfg.max_messages = data.get("max_messages", 20)
        cfg.max_tokens = data.get("max_tokens", 4096)
        cfg.compression_enabled = data.get("compression_enabled", True)
        cfg.compression_model = data.get("compression_model", "default")
        cfg.compression_threshold_messages = data.get(
            "compression_threshold_messages", 15
        )
        # Long-term compression
        cfg.long_term_compression_enabled = data.get(
            "long_term_compression_enabled", True
        )
        cfg.compression_cutoff_days = data.get("compression_cutoff_days", 7)
        cfg.compression_min_messages = data.get("compression_min_messages", 10)
        cfg.compress_on_startup = data.get("compress_on_startup", True)
        # End long-term compression
        cfg.enable_long_term = data.get("enable_long_term", True)
        cfg.long_term_storage = data.get("long_term_storage", "sqlite")
        cfg.auto_cleanup = data.get("auto_cleanup", True)
        cfg.max_sessions = data.get("max_sessions", 10)
        cfg.use_mcp = data.get("use_mcp", False)
        cfg.mcp_mode = data.get("mcp_mode", "local")
        cfg.compression_strategy = data.get("compression_strategy", "summary")
        cfg.max_working_messages = data.get("max_working_messages", cfg.max_messages)
        cfg.max_recent_tokens = data.get("max_recent_tokens", cfg.max_tokens)
        cfg.max_total_tokens = data.get("max_total_tokens", cfg.max_tokens)
        remote = data.get("remote", None)
        if isinstance(remote, dict):
            cfg.remote = {
                "enabled": remote.get("enabled", False),
                "endpoint": remote.get("endpoint", "http://localhost:8080/v1"),
                "api_key": remote.get("api_key"),
                "timeout": remote.get("timeout", 30),
                "verify_ssl": remote.get("verify_ssl", True),
            }
        return cfg

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "storage_type": self.storage_type,
            "data_dir": self.data_dir,
            "max_messages": self.max_messages,
            "max_tokens": self.max_tokens,
            "compression_enabled": self.compression_enabled,
            "compression_model": self.compression_model,
            "compression_threshold_messages": self.compression_threshold_messages,
            "long_term_compression_enabled": self.long_term_compression_enabled,
            "compression_cutoff_days": self.compression_cutoff_days,
            "compression_min_messages": self.compression_min_messages,
            "compress_on_startup": self.compress_on_startup,
            "enable_long_term": self.enable_long_term,
            "long_term_storage": self.long_term_storage,
            "auto_cleanup": self.auto_cleanup,
            "max_sessions": self.max_sessions,
            "use_mcp": self.use_mcp,
            "mcp_mode": self.mcp_mode,
            "compression_strategy": self.compression_strategy,
            "max_working_messages": self.max_working_messages,
            "max_recent_tokens": self.max_recent_tokens,
            "max_total_tokens": self.max_total_tokens,
            "remote": self.remote,
        }


class MessageRole(str, Enum):
    """消息角色枚举，兼容OpenAI格式"""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class ConversationTurn:
    """单轮对话记录"""

    message: Message
    timestamp: datetime = field(default_factory=datetime.now)
    turn_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "turn_id": self.turn_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConversationTurn":
        return cls(
            message=data["message"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            turn_id=data.get("turn_id"),
        )


@dataclass
class CompressionInfo:
    """Long-term session compression information"""

    compressed_at: datetime
    original_message_count: int
    summary_entry: SummaryEntry
    is_compressed: bool = True

    def to_dict(self) -> dict:
        return {
            "compressed_at": self.compressed_at.isoformat(),
            "original_message_count": self.original_message_count,
            "summary_entry": self.summary_entry.to_dict(),
            "is_compressed": self.is_compressed,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CompressionInfo":
        return cls(
            compressed_at=datetime.fromisoformat(data["compressed_at"]),
            original_message_count=data["original_message_count"],
            summary_entry=SummaryEntry.from_dict(data["summary_entry"]),
            is_compressed=data.get("is_compressed", True),
        )


@dataclass
class SessionInfo:
    """会话信息"""

    session_id: str
    created_at: datetime
    updated_at: datetime
    title: str | None = None
    message_count: int = 0
    is_compressed: bool = False

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "title": self.title,
            "message_count": self.message_count,
            "is_compressed": self.is_compressed,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SessionInfo":
        return cls(
            session_id=data["session_id"],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            title=data.get("title"),
            message_count=data.get("message_count", 0),
            is_compressed=data.get("is_compressed", False),
        )


@dataclass
class SummaryEntry:
    """摘要记录"""

    content: str
    original_start_idx: int
    original_end_idx: int
    timestamp: datetime

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "original_start_idx": self.original_start_idx,
            "original_end_idx": self.original_end_idx,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SummaryEntry":
        return cls(
            content=data["content"],
            original_start_idx=data["original_start_idx"],
            original_end_idx=data["original_end_idx"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )


@dataclass
class LongTermEntry:
    """长期记忆条目"""

    id: str
    content: str
    keywords: list[str]
    source_session_id: str
    created_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "keywords": self.keywords,
            "source_session_id": self.source_session_id,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LongTermEntry":
        return cls(
            id=data["id"],
            content=data["content"],
            keywords=data.get("keywords", []),
            source_session_id=data["source_session_id"],
            created_at=datetime.fromisoformat(data["created_at"]),
            metadata=data.get("metadata", {}),
        )

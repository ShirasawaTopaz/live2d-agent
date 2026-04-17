from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


class MCPParticipant(enum.Enum):
    """MCP消息角色枚举"""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass(slots=True)
class MCPMessage:
    """MCP统一消息结构

    标准化所有对话消息的格式，支持元数据和token计数。
    """

    msg_id: str
    role: MCPParticipant
    content: str
    timestamp: int
    metadata: dict[str, Any] = field(default_factory=dict)
    tokens: int | None = None

    # 工具调用相关字段
    tool_name: str | None = None
    tool_call_id: str | None = None

    @classmethod
    def create(
        cls,
        role: MCPParticipant,
        content: str,
        tokens: int | None = None,
        metadata: dict[str, Any] | None = None,
        tool_name: str | None = None,
        tool_call_id: str | None = None,
    ) -> MCPMessage:
        """创建新消息，自动生成msg_id和timestamp"""
        now = int(datetime.now().timestamp() * 1000)
        return cls(
            msg_id=str(uuid.uuid4()),
            role=role,
            content=content,
            timestamp=now,
            metadata=metadata or {},
            tokens=tokens,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
        )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典用于序列化"""
        return {
            "msg_id": self.msg_id,
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
            "tokens": self.tokens,
            "tool_name": self.tool_name,
            "tool_call_id": self.tool_call_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MCPMessage:
        """从字典反序列化"""
        return cls(
            msg_id=data["msg_id"],
            role=MCPParticipant(data["role"]),
            content=data["content"],
            timestamp=data["timestamp"],
            metadata=data.get("metadata", {}),
            tokens=data.get("tokens"),
            tool_name=data.get("tool_name"),
            tool_call_id=data.get("tool_call_id"),
        )


@dataclass(slots=True)
class MCPContextChunk:
    """MCP上下文分片

    用于分层存储，每个分片代表一段压缩后的上下文。
    """

    chunk_id: str
    scope_id: str
    messages: list[Any]
    summary: str | None
    start_time: int
    end_time: int
    total_tokens: int
    compressed: bool
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        scope_id: str,
        messages: list[MCPMessage],
        summary: str | None = None,
        compressed: bool = False,
    ) -> MCPContextChunk:
        """创建新分片"""
        now = int(datetime.now().timestamp() * 1000)
        total_tokens = sum(m.tokens or 0 for m in messages)
        return cls(
            chunk_id=str(uuid.uuid4()),
            scope_id=scope_id,
            messages=messages,
            summary=summary,
            start_time=messages[0].timestamp if messages else now,
            end_time=messages[-1].timestamp if messages else now,
            total_tokens=total_tokens,
            compressed=compressed,
        )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        serialized_messages = [
            m.to_dict() if isinstance(m, MCPMessage) else m for m in self.messages
        ]
        return {
            "chunk_id": self.chunk_id,
            "scope_id": self.scope_id,
            "messages": serialized_messages,
            "summary": self.summary,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "total_tokens": self.total_tokens,
            "compressed": self.compressed,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MCPContextChunk:
        """从字典恢复"""
        messages = [
            MCPMessage.from_dict(m)
            if isinstance(m, dict) and {"msg_id", "timestamp"}.issubset(m.keys())
            else m
            for m in data["messages"]
        ]
        return cls(
            chunk_id=data["chunk_id"],
            scope_id=data["scope_id"],
            messages=messages,
            summary=data.get("summary"),
            start_time=data["start_time"],
            end_time=data["end_time"],
            total_tokens=data["total_tokens"],
            compressed=data.get("compressed", False),
            metadata=data.get("metadata", {}),
        )


@dataclass(slots=True)
class MCPGetContextRequest:
    """获取上下文请求"""

    session_id: str
    scope_id: str
    max_tokens: int
    include_summary: bool = True
    search_query: str | None = None  # 如果提供，会检索相关长期记忆


@dataclass(slots=True)
class MCPGetContextResponse:
    """获取上下文响应"""

    messages: list[MCPMessage]
    chunks: list[MCPContextChunk]
    total_tokens: int
    truncated: bool
    has_more: bool = False


@dataclass(slots=True)
class MCPAddMessageRequest:
    """添加消息请求"""

    session_id: str
    scope_id: str
    message: MCPMessage


@dataclass(slots=True)
class MCPCompressRequest:
    """压缩请求"""

    session_id: str
    scope_id: str
    messages: list[MCPMessage]
    target_tokens: int


@dataclass(slots=True)
class MCPCompressResponse:
    """压缩响应"""

    compressed_chunk: MCPContextChunk
    original_count: int
    compressed_count: int
    original_tokens: int
    compressed_tokens: int


class MCPMode(enum.Enum):
    """MCP运行模式"""

    LOCAL = "local"  # 完全本地处理
    HYBRID = "hybrid"  # 本地工作+长期远程
    REMOTE = "remote"  # 完全远程管理


class CompressionStrategyType(enum.Enum):
    """压缩策略类型"""

    SUMMARY = "summary"  # AI生成摘要
    SLIDING = "sliding"  # 滑动窗口保留最新
    EXTRACTION = "extraction"  # 抽取关键消息

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import MutableMapping, Any


Message = MutableMapping[str, Any]


class MessageRole(str, Enum):
    """消息角色枚举"""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class ConversationTurn:
    """
    对话回合，包含一条消息
    """

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
class SessionInfo:
    """会话信息"""

    session_id: str
    updated_at: datetime
    created_at: datetime = field(default_factory=datetime.now)
    title: str | None = None

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "updated_at": self.updated_at.isoformat(),
            "created_at": self.created_at.isoformat(),
            "title": self.title,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SessionInfo":
        return cls(
            session_id=data["session_id"],
            updated_at=datetime.fromisoformat(data["updated_at"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            title=data.get("title"),
        )


@dataclass
class SummaryEntry:
    """
    摘要条目，包含会话的摘要
    """

    session_id: str
    summary: str
    updated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "summary": self.summary,
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SummaryEntry":
        return cls(
            session_id=data["session_id"],
            summary=data["summary"],
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )


@dataclass
class LongTermMemory:
    """长期记忆"""

    # TODO: 实现长期记忆数据结构

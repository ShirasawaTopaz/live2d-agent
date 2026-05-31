"""Session type definitions for auto-routing system."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ClassificationResult:
    """Output from TopicClassifier.classify()."""

    topic: str
    confidence: float  # 0.0 - 1.0
    suggested_session_id: str | None = None
    # None means no existing session matched — router should create new


@dataclass
class Session:
    """Session metadata for auto-routing.

    This is separate from memory._types.SessionInfo.
    SessionInfo is the storage-layer record.
    Session is the routing-layer record with additional fields
    needed for topic classification and context switching.
    """

    session_id: str
    topic: str                     # Auto-identified topic label
    display_name: str              # User-editable name (defaults to topic)
    summary: str                   # 200-char session summary
    created_at: float
    last_active_at: float
    message_count: int
    context_snapshot: dict[str, Any] = field(default_factory=dict)
    # Key context variables inherited when switching from another session
    # e.g. {"language": "zh", "current_project": "live2oder", "user_name": "..."}

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "topic": self.topic,
            "display_name": self.display_name,
            "summary": self.summary,
            "created_at": self.created_at,
            "last_active_at": self.last_active_at,
            "message_count": self.message_count,
            "context_snapshot": self.context_snapshot,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Session":
        return cls(
            session_id=data["session_id"],
            topic=data.get("topic", ""),
            display_name=data.get("display_name", data.get("topic", "")),
            summary=data.get("summary", ""),
            created_at=data.get("created_at", 0.0),
            last_active_at=data.get("last_active_at", 0.0),
            message_count=data.get("message_count", 0),
            context_snapshot=data.get("context_snapshot", {}),
        )

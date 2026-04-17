"""Compatibility shim for the active memory type definitions."""

from internal.memory._types import (
    CompressionInfo,
    ConversationTurn,
    LongTermEntry,
    MemoryConfig,
    Message,
    MessageRole,
    SessionInfo,
    SummaryEntry,
)

__all__ = [
    "CompressionInfo",
    "ConversationTurn",
    "LongTermEntry",
    "MemoryConfig",
    "Message",
    "MessageRole",
    "SessionInfo",
    "SummaryEntry",
]

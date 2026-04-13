"""
Memory System for Live2oder - Reference Implementation
======================================================

⚠️  **NOTE: This is reference design code, not yet ready for production use**
⚠️  Prefix with '_' indicates this is reference implementation
Integration testing is still in progress

This provides:
- Full-featured memory system with conversation persistence
- Context window management with automatic compression
- Long-term memory storage with keyword search
- Multi-session management with auto cleanup
- Supports both JSON and SQLite storage backends

See `todo.md for complete design documentation.
"""

from internal.memory._types import (
    Message,
    MessageRole,
    ConversationTurn,
    SessionInfo,
    SummaryEntry,
    LongTermEntry,
    CompressionInfo,
    MemoryConfig,
)
from internal.memory._manager import (
    MemoryManager,
    create_storage,
)
from internal.memory._session import SessionManager
from internal.memory._context import ContextManager
from internal.memory._summary import Summarizer
from internal.memory._long_term import LongTermMemory
from internal.memory._archive import ArchiveCompressor
from internal.memory.storage._base import BaseStorage

__all__ = [
    # Types
    "Message",
    "MessageRole",
    "ConversationTurn",
    "SessionInfo",
    "SummaryEntry",
    "LongTermEntry",
    "CompressionInfo",
    # Main
    "MemoryManager",
    "MemoryConfig",
    "create_storage",
    # Components
    "SessionManager",
    "ContextManager",
    "Summarizer",
    "LongTermMemory",
    "ArchiveCompressor",
    # Storage
    "BaseStorage",
]

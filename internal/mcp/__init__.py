"""Model Context Protocol (MCP) for Live2oder

MCP provides standardized context management with:
- Three-layer storage: Working Memory -> Recent Context -> Long-Term Memory
- Pluggable compression strategies
- Multi-scope isolation for different scenarios
- Remote MCP service integration
"""

from internal.mcp.protocol import (
    MCPMessage,
    MCPContextChunk,
    MCPGetContextRequest,
    MCPGetContextResponse,
    MCPParticipant,
    MCPMode,
    CompressionStrategyType,
)
from internal.mcp.config import MCPConfig, RemoteMCPConfig
from internal.mcp.manager import MCPContextManager, WorkingMemory
from internal.mcp.compression import (
    CompressionStrategy,
    SlidingWindowCompression,
    ExtractionCompression,
    SummaryCompression,
    create_compression_strategy,
)
from internal.mcp.backend import (
    MCPStorageBackend,
    JSONFileBackend,
    SQLiteBackend,
)
from internal.mcp.remote import RemoteMCPBackend, RemoteMCPManager

__all__ = [
    # Protocol
    "MCPMessage",
    "MCPContextChunk",
    "MCPGetContextRequest",
    "MCPGetContextResponse",
    "MCPParticipant",
    "MCPMode",
    "CompressionStrategyType",
    # Config
    "MCPConfig",
    "RemoteMCPConfig",
    # Manager
    "MCPContextManager",
    "WorkingMemory",
    # Compression
    "CompressionStrategy",
    "SlidingWindowCompression",
    "ExtractionCompression",
    "SummaryCompression",
    "create_compression_strategy",
    # Backend
    "MCPStorageBackend",
    "JSONFileBackend",
    "SQLiteBackend",
    # Remote
    "RemoteMCPBackend",
    "RemoteMCPManager",
]

"""Regression coverage for Task 7 memory path consolidation."""

from internal.agent.register import ToolRegistry
from internal.memory import ContextManager as PackageContextManager
from internal.memory import MemoryConfig as PackageMemoryConfig
from internal.memory import SessionInfo as PackageSessionInfo
from internal.memory._context import ContextManager as UnderscoredContextManager
from internal.memory._types import MemoryConfig as UnderscoredMemoryConfig
from internal.memory._types import SessionInfo as UnderscoredSessionInfo
from internal.memory.context import ContextManager as LegacyContextManager
from internal.memory.types import MemoryConfig as LegacyMemoryConfig
from internal.memory.types import SessionInfo as LegacySessionInfo


def test_legacy_context_module_is_explicit_shim() -> None:
    assert LegacyContextManager is UnderscoredContextManager
    assert PackageContextManager is UnderscoredContextManager


def test_legacy_types_module_reexports_active_types() -> None:
    assert LegacyMemoryConfig is UnderscoredMemoryConfig
    assert LegacySessionInfo is UnderscoredSessionInfo
    assert PackageMemoryConfig is UnderscoredMemoryConfig
    assert PackageSessionInfo is UnderscoredSessionInfo


def test_tool_registry_has_no_sync_execute_bridge() -> None:
    registry = ToolRegistry()

    assert not hasattr(registry, "execute")

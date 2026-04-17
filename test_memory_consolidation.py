#!/usr/bin/env python3
"""Test script for memory module consolidation task"""

import sys
import traceback

print("Testing memory module consolidation...\n")

try:
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
    
    print("1. All imports succeeded ✓")
    
    # Test 1: legacy context is a shim
    assert LegacyContextManager is UnderscoredContextManager
    assert PackageContextManager is UnderscoredContextManager
    print("2. Legacy context module is explicit shim ✓")
    
    # Test 2: legacy types are shims
    assert LegacyMemoryConfig is UnderscoredMemoryConfig
    assert LegacySessionInfo is UnderscoredSessionInfo
    assert PackageMemoryConfig is UnderscoredMemoryConfig
    assert PackageSessionInfo is UnderscoredSessionInfo
    print("3. Legacy types module correctly reexports active types ✓")
    
    # Test 3: tool registry has no sync execute bridge
    registry = ToolRegistry()
    assert not hasattr(registry, 'execute')
    print("4. ToolRegistry has no unsafe sync/async execute() ✓")
    
    print("\n✅ ALL TESTS PASSED!")
    
except Exception as e:
    print(f"\n❌ TEST FAILED: {e}")
    traceback.print_exc()
    sys.exit(1)

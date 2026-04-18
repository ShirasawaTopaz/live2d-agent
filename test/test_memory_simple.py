#!/usr/bin/env python3
# Simplified test that only tests what we care about

import sys

# Enable UTF-8 output
if sys.version_info >= (3, 7):
    sys.stdout.reconfigure(encoding='utf-8')

print("Testing memory module structure...")
print()

# Test 1: Test internal.memory.context shim
print("1. Testing internal.memory.context...")
try:
    from internal.memory.context import ContextManager
    from internal.memory._context import ContextManager as ContextManagerUnderscore
    assert ContextManager is ContextManagerUnderscore
    print("   ✓ OK: context.py correctly re-exports from _context.py")
except Exception as e:
    print(f"   ✗ FAILED: {e}")
    sys.exit(1)

# Test 2: Test internal.memory.types shim
print("\n2. Testing internal.memory.types...")
try:
    from internal.memory.types import MemoryConfig, SessionInfo
    from internal.memory._types import MemoryConfig as MemoryConfigUnderscore
    from internal.memory._types import SessionInfo as SessionInfoUnderscore
    assert MemoryConfig is MemoryConfigUnderscore
    assert SessionInfo is SessionInfoUnderscore
    print("   ✓ OK: types.py correctly re-exports from _types.py")
except Exception as e:
    print(f"   ✗ FAILED: {e}")
    sys.exit(1)

# Test 3: Test package exports from underscore versions
print("\n3. Testing package-level exports...")
try:
    from internal.memory import ContextManager, MemoryConfig, SessionInfo
    from internal.memory._context import ContextManager as CMUnderscore
    from internal.memory._types import MemoryConfig as MCUnderscore
    from internal.memory._types import SessionInfo as SIUnderscore
    assert ContextManager is CMUnderscore
    assert MemoryConfig is MCUnderscore
    assert SessionInfo is SIUnderscore
    print("   ✓ OK: Package exports correctly use the underscore versions")
except Exception as e:
    print(f"   ✗ FAILED: {e}")
    sys.exit(1)

# Test 4: ToolRegistry - check no execute method
print("\n4. Testing ToolRegistry for execute method...")
try:
    from internal.agent.register import ToolRegistry
    registry = ToolRegistry()
    if hasattr(registry, 'execute'):
        print("   ✗ FAILED: ToolRegistry still has 'execute' method (unsafe sync/async bridge)")
        sys.exit(1)
    else:
        print("   ✓ OK: ToolRegistry has no unsafe sync/async 'execute' method")
except Exception as e:
    print(f"   ✗ FAILED: {e}")
    sys.exit(1)

print()
print("✅ ALL CHECKS PASSED! Consilidation complete.")
print()
print("Reference Matrix:")
print("| Module                 | Status                                      |")
print("|------------------------|---------------------------------------------|")
print("| _context.py            | ✓ Main runtime implementation - kept       |")
print("| context.py             | ✓ Compatibility shim - kept for backward   |")
print("|                        |   compatibility with existing code         |")
print("| _types.py              | ✓ Main runtime types - kept                |")
print("| types.py               | ✓ Compatibility shim - kept for backward   |")
print("|                        |   compatibility with existing code         |")
print()
print("ToolRegistry:")
print("| Unsafe sync/async execute() method | ✓ REMOVED |")

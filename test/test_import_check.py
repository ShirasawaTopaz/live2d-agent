#!/usr/bin/env python3
"""Check that all modified modules import correctly."""

import sys
print("Python version:", sys.version)
print()

print("Testing imports...")

# Check that all modified modules can be imported
try:
    from internal.memory.storage._json import JSONStorage
    print(f"✓ internal.memory.storage._json imported successfully ({JSONStorage.__name__})")
except Exception as e:
    print(f"✗ import _json failed: {e}")
    import traceback
    traceback.print_exc()

try:
    from internal.memory.storage._sqlite import SQLiteStorage
    print(f"✓ internal.memory.storage._sqlite imported successfully ({SQLiteStorage.__name__})")
except Exception as e:
    print(f"✗ import _sqlite failed: {e}")
    import traceback
    traceback.print_exc()

try:
    from internal.mcp.backend import JSONFileBackend, SQLiteBackend
    print(
        "✓ internal.mcp.backend imported successfully "
        f"({JSONFileBackend.__name__}, {SQLiteBackend.__name__})"
    )
except Exception as e:
    print(f"✗ import mcp.backend failed: {e}")
    import traceback
    traceback.print_exc()

try:
    import aiofiles
    print(f"✓ aiofiles version: {getattr(aiofiles, '__version__', 'unknown')}")
except Exception as e:
    print(f"✗ import aiofiles failed: {e}")

try:
    import aiosqlite
    print(f"✓ aiosqlite version: {aiosqlite.__version__}")
except Exception as e:
    print(f"✗ import aiosqlite failed: {e}")

print()
print("Import check complete.")

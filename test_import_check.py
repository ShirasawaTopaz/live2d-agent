#!/usr/bin/env python3
"""Check that all modified modules import correctly."""

import sys
print("Python version:", sys.version)
print()

print("Testing imports...")

# Check that all modified modules can be imported
try:
    from internal.memory.storage._json import JSONStorage
    print("✓ internal.memory.storage._json imported successfully")
except Exception as e:
    print(f"✗ import _json failed: {e}")
    import traceback
    traceback.print_exc()

try:
    from internal.memory.storage._sqlite import SQLiteStorage
    print("✓ internal.memory.storage._sqlite imported successfully")
except Exception as e:
    print(f"✗ import _sqlite failed: {e}")
    import traceback
    traceback.print_exc()

try:
    from internal.mcp.backend import JSONFileBackend, SQLiteBackend
    print("✓ internal.mcp.backend imported successfully (JSONFileBackend, SQLiteBackend)")
except Exception as e:
    print(f"✗ import mcp.backend failed: {e}")
    import traceback
    traceback.print_exc()

try:
    import aiofiles
    print(f"✓ aiofiles version: {aiofiles.__version__}")
except Exception as e:
    print(f"✗ import aiofiles failed: {e}")

try:
    import aiosqlite
    print(f"✓ aiosqlite version: {aiosqlite.__version__}")
except Exception as e:
    print(f"✗ import aiosqlite failed: {e}")

print()
print("Import check complete.")

"""Basic tests for dynamic skill loader functionality."""

import asyncio
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from internal.skill import SkillManager, DynamicSkillLoader


async def test_polling_watcher():
    """Test polling watcher detects new skills."""
    print("\nTest: Polling watcher detects new skills")
    print("-" * 50)

    # Create temp directory
    temp_dir = tempfile.mkdtemp()
    print(f"Created temp directory: {temp_dir}")

    try:
        # Create skill manager
        skill_manager = SkillManager(
            skill_dirs=[temp_dir],
            prompt_manager=None,
            tool_registry=None,
        )

        events = []

        def on_added(name, skill):
            events.append(("added", name))
            print(f"[EVENT] Skill added - {name}")

        # Create dynamic loader with polling
        loader = DynamicSkillLoader(
            skill_manager=skill_manager,
            on_skill_added=on_added,
            use_polling=True,
            poll_interval=0.5,  # Fast polling for testing
        )

        print("Starting watcher...")
        loader.watch([temp_dir])

        # Wait for initial scan
        print("Waiting for initial scan...")
        await asyncio.sleep(0.5)

        # Create a new skill
        skill_name = "test_dynamic_skill"
        skill_dir = os.path.join(temp_dir, skill_name)
        os.makedirs(skill_dir)

        skill_yaml = os.path.join(skill_dir, "skill.yaml")
        with open(skill_yaml, "w") as f:
            f.write(f"""
name: {skill_name}
version: 1.0.0
description: A dynamically created test skill
author: Test Suite

category: test
tags: [test, dynamic]

dependencies:
  python_packages: []
  system_commands: []
  skills: []

tools: []
""")

        print(f"Created skill: {skill_name}")
        print("Waiting for polling to detect...")

        # Wait for polling to detect
        await asyncio.sleep(1.0)

        # Check events
        if events:
            print(f"\n[PASS] Test passed! Detected {len(events)} event(s):")
            for event in events:
                print(f"  - {event[0]}: {event[1]}")
        else:
            print("\n✗ Test failed: No events detected")

        # Stop loader
        loader.stop()
        print("\nWatcher stopped")

        return len(events) > 0

    finally:
        # Cleanup
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        print(f"Cleaned up: {temp_dir}")


async def test_context_manager():
    """Test dynamic loader as context manager."""
    print("\nTest: Context manager")
    print("-" * 50)

    temp_dir = tempfile.mkdtemp()

    try:
        skill_manager = SkillManager(
            skill_dirs=[temp_dir],
            prompt_manager=None,
            tool_registry=None,
        )

        with DynamicSkillLoader(skill_manager, use_polling=True) as loader:
            loader.watch([temp_dir])
            print("[OK] Dynamic loader active in context")

        print("[OK] Dynamic loader stopped after context exit")
        return True

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


async def main():
    """Run all tests."""
    print("=" * 60)
    print("Dynamic Skill Loader Tests")
    print("=" * 60)

    results = []

    # Test 1: Polling watcher
    try:
        result = await test_polling_watcher()
        results.append(("Polling watcher", result))
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback

        traceback.print_exc()
        results.append(("Polling watcher", False))

    # Test 2: Context manager
    try:
        result = await test_context_manager()
        results.append(("Context manager", result))
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        results.append(("Context manager", False))

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    passed = sum(1 for _, r in results if r)
    total = len(results)
    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"  {status}: {name}")
    print(f"\nTotal: {passed}/{total} tests passed")

    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

"""Example of using SkillReloader for programmatic skill reload.

This example demonstrates the proper way to programmatically reload skills
using the SkillReloader class, which provides a clean, encapsulated interface
for skill reload operations.

Why use SkillReloader instead of directly manipulating skills?
-----------------------------------------------------------------------------

BEFORE (problematic approach):
    # Directly calling internal methods - violates encapsulation
    skill_manager.registry.unregister(name)
    skill_manager._load_skill(path)

    # Or worse - calling private methods on watcher
    watcher._handle_skill_changed(path)  # Private method!

AFTER (proper approach with SkillReloader):
    # Clean, encapsulated interface
    reloader = SkillReloader(skill_manager)
    success = await reloader.reload("my_skill")

    # Or reload by path
    success = await reloader.reload_by_path("/path/to/skill")

Benefits of SkillReloader:
1. Encapsulation - hides internal reload logic
2. Consistency - same logic used everywhere (watcher, manual reload, etc.)
3. Testability - easy to unit test
4. Maintainability - change logic in one place
5. Error handling - centralized error handling and recovery
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from internal.skill import SkillManager, SkillReloader


async def example_basic_reload():
    """Example: Basic skill reload by name."""
    print("\n" + "=" * 60)
    print("Example 1: Basic Skill Reload by Name")
    print("=" * 60)

    # Setup
    skill_manager = SkillManager(
        skill_dirs=["./skills"],
        prompt_manager=None,
        tool_registry=None,
    )

    # Load initial skills
    await skill_manager.load_all()

    # Create reloader
    reloader = SkillReloader(skill_manager)

    # Reload a specific skill
    skill_name = "file_ops"  # Replace with your skill name
    print(f"\nReloading skill: {skill_name}")

    success = await reloader.reload(skill_name)

    if success:
        print(f"✓ Successfully reloaded: {skill_name}")
    else:
        print(f"✗ Failed to reload: {skill_name}")

    return success


async def example_reload_by_path():
    """Example: Reload skill by directory path."""
    print("\n" + "=" * 60)
    print("Example 2: Reload Skill by Path")
    print("=" * 60)

    # Setup
    skill_manager = SkillManager(
        skill_dirs=["./skills"],
        prompt_manager=None,
        tool_registry=None,
    )

    await skill_manager.load_all()

    # Create reloader
    reloader = SkillReloader(skill_manager)

    # Reload by path
    skill_path = "./skills/weather_skill"  # Replace with your path
    print(f"\nReloading skill at path: {skill_path}")

    success = await reloader.reload_by_path(skill_path)

    if success:
        print(f"✓ Successfully reloaded skill at: {skill_path}")
    else:
        print(f"✗ Failed to reload skill at: {skill_path}")

    return success


async def example_with_callbacks():
    """Example: Using reload with custom callbacks."""
    print("\n" + "=" * 60)
    print("Example 3: Reload with Custom Callbacks")
    print("=" * 60)

    # Setup with callbacks
    def on_reload_start(name: str):
        print(f"  → Starting reload: {name}")

    def on_reload_complete(name: str, success: bool):
        status = "✓" if success else "✗"
        print(f"  {status} Reload complete: {name}")

    # Note: In real usage, you'd use HotReloadManager for callbacks
    # This example shows the pattern

    skill_manager = SkillManager(
        skill_dirs=["./skills"],
        prompt_manager=None,
        tool_registry=None,
    )

    await skill_manager.load_all()

    reloader = SkillReloader(skill_manager)

    # Simulate reload with callback pattern
    skill_name = "file_ops"
    on_reload_start(skill_name)

    success = await reloader.reload(skill_name)

    on_reload_complete(skill_name, success)

    return success


async def example_why_not_direct():
    """Example: Demonstrating why SkillReloader is better than direct manipulation."""
    print("\n" + "=" * 60)
    print("Example 4: Why SkillReloader vs Direct Manipulation")
    print("=" * 60)

    print("\n❌ BAD: Direct manipulation (violates encapsulation)")
    print("   skill_manager.registry.unregister('my_skill')")
    print("   skill_manager._load_skill('/path/to/skill')  # Private method!")
    print("   watcher._handle_skill_changed(path)  # Private method!")

    print("\n✅ GOOD: Using SkillReloader (clean encapsulation)")
    print("   reloader = SkillReloader(skill_manager)")
    print("   success = await reloader.reload('my_skill')")

    print("\nBenefits of SkillReloader:")
    print("  1. Encapsulation - internal logic hidden")
    print("  2. Consistency - same logic everywhere")
    print("  3. Testability - easy to unit test")
    print("  4. Maintainability - change in one place")

    return True


async def main():
    """Run all examples."""
    print("\n" + "=" * 70)
    print(" SkillReloader Examples")
    print(" Demonstrating proper skill reload patterns")
    print("=" * 70)

    examples = [
        ("Basic Reload by Name", example_basic_reload),
        ("Reload by Path", example_reload_by_path),
        ("With Callbacks", example_with_callbacks),
        ("Why Not Direct", example_why_not_direct),
    ]

    results = []
    for name, example_func in examples:
        try:
            result = await example_func()
            results.append((name, result))
        except Exception as e:
            print(f"\nError in {name}: {e}")
            import traceback

            traceback.print_exc()
            results.append((name, False))

    # Summary
    print("\n" + "=" * 70)
    print(" Summary")
    print("=" * 70)
    passed = sum(1 for _, r in results if r)
    total = len(results)
    for name, result in results:
        status = "✓" if result else "✗"
        print(f"  {status} {name}")
    print(f"\nTotal: {passed}/{total} examples completed")

    return passed == total


if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(0)

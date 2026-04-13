"""Example of using dynamic skill loading with hot-reload.

This example demonstrates how to:
1. Set up the skill system with dynamic loading
2. Watch for skill changes
3. Handle skill lifecycle events
4. Use both watchdog and polling-based watchers
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from internal.skill import (
    SkillManager,
    SkillSystemIntegration,
    DynamicSkillLoader,
)


async def main():
    """Main example function."""
    print("=" * 60)
    print("Dynamic Skill Loading Example")
    print("=" * 60)

    # Configuration
    skill_dirs = ["./skills", "./custom_skills"]

    # Create skill manager
    skill_manager = SkillManager(
        skill_dirs=skill_dirs,
        prompt_manager=None,  # Would be your PromptManager instance
        tool_registry=None,  # Would be your ToolRegistry instance
    )

    # Load initial skills
    print("\n1. Loading initial skills...")
    loaded = await skill_manager.load_all()
    print(f"   Loaded skills: {loaded}")

    # Create integration
    SkillSystemIntegration(
        skill_manager=skill_manager,
        tool_registry=None,  # Would be your ToolRegistry instance
    )

    # Define callbacks for dynamic loading events
    def on_skill_added(name: str, skill):
        print(f"   [Event] Skill added: {name}")

    def on_skill_removed(name: str):
        print(f"   [Event] Skill removed: {name}")

    def on_skill_reloaded(name: str, skill):
        print(f"   [Event] Skill reloaded: {name}")

    # Create dynamic loader
    print("\n2. Setting up dynamic loader...")
    dynamic_loader = DynamicSkillLoader(
        skill_manager=skill_manager,
        on_skill_added=on_skill_added,
        on_skill_removed=on_skill_removed,
        on_skill_reloaded=on_skill_reloaded,
        # use_polling=True,  # Uncomment to force polling mode
        poll_interval=2.0,
    )

    # Start watching
    print("   Starting to watch skill directories...")
    dynamic_loader.watch(skill_dirs)

    print("\n" + "=" * 60)
    print("Dynamic loader is now active!")
    print("Try these actions:")
    print("  1. Create a new skill directory in ./skills/")
    print("  2. Modify an existing skill.yaml file")
    print("  3. Delete a skill directory")
    print("=" * 60)

    # Keep running until interrupted
    print("\nPress Ctrl+C to stop...")
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n\nStopping...")

    # Stop watching
    dynamic_loader.stop()
    print("Dynamic loader stopped.")


if __name__ == "__main__":
    # Run the example
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Error: {e}")
        raise

"""Tests for DynamicSkillLoader event loop handling."""

from internal.skill import SkillManager
from internal.skill.dynamic_loader import DynamicSkillLoader


class TestDynamicSkillLoaderEventLoop:
    async def test_async_operations_scheduled_safely(self):
        """Verify _schedule_async exists and schedules safely from sync context."""
        loader = DynamicSkillLoader(
            skill_manager=SkillManager(
                skill_dirs=[],
                prompt_manager=None,
                tool_registry=None,
            ),
            use_polling=True,
            poll_interval=1.0,
        )

        loop = loader._get_loop()
        assert loop is not None, "_get_loop() should return an event loop"
        loader._loop = loop

        loader.skill_manager.registry._skills["fake"] = None
        loader.skill_manager.registry._metadata["fake"] = None
        loader.skill_manager._enabled_skills.add("fake")

        loader._on_skill_removed("fake")

        loader.stop()

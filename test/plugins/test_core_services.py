"""Core service plugins must mount, and must build lazily from config."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from internal.cordis import FiberState
from internal.plugins import app as plugin_app

SERVICE_IDS = (
    "logger",
    "timer",
    "config",
    "prompts",
    "sandbox",
    "tools",
    "memory",
    "rag",
    "mcp",
    "planner",
    "session",
    "scheduler",
    "skills",
    "input-box",
    "bubble-widget",
    "chat-history",
    "tray",
    "settings",
    "hotkey",
    "clipboard",
    "browser",
)


async def test_full_core_tree_mounts_active() -> None:
    context = await plugin_app.create_plugin_context(watch=False)
    try:
        await asyncio.sleep(0)
        report = {entry["id"]: entry for entry in context.loader.report()}
        for entry_id in SERVICE_IDS:
            assert entry_id in report, f"{entry_id} missing from the tree"
            assert report[entry_id]["state"] == FiberState.ACTIVE.value, report[entry_id]

        for entry_id in ("tools", "memory", "rag", "mcp", "planner", "session", "scheduler", "skills"):
            assert context.ctx.get(entry_id) is not None
    finally:
        await context.dispose()


async def test_tools_plugin_registers_default_tool_set() -> None:
    context = await plugin_app.create_plugin_context(watch=False)
    try:
        tools = context.ctx.get("tools")
        assert tools is not None
        names = set(tools.registry.tools)
        assert {"file", "web_search", "display_bubble_text", "trigger_motion"} <= names
        assert tools.definitions() is not None
    finally:
        await context.dispose()


async def test_tool_registration_is_undone_on_unload() -> None:
    context = await plugin_app.create_plugin_context(watch=False)
    ctx = context.ctx
    tools = ctx.get("tools")
    before = set(tools.registry.tools)

    def contributor(context):
        class Dummy:
            name = "dummy_probe"
            description = "probe"
            parameters = {"type": "object", "properties": {}}

            async def execute(self, **kwargs):
                return "ok"

        context.get("tools").register(Dummy(), owner=context)

    fiber = await ctx.load(contributor)
    assert "dummy_probe" in tools.registry.tools

    await fiber.dispose()
    assert "dummy_probe" not in tools.registry.tools
    assert set(tools.registry.tools) == before

    await context.dispose()


async def test_memory_and_rag_build_from_config(tmp_path: Path) -> None:
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "live2dSocket": "ws://example.test",
                "models": [],
                "memory": {"enabled": False},
                "rag": {"enabled": False},
                "planning": {"enabled": False},
            }
        ),
        encoding="utf-8",
    )

    context = await plugin_app.create_plugin_context(watch=False)
    try:
        await plugin_app.load_core_resources(context.ctx, str(config_file))

        memory = context.ctx.get("memory")
        rag = context.ctx.get("rag")
        planner = context.ctx.get("planner")
        assert memory.build() is None
        assert memory.enabled is False
        assert rag.build() is None
        assert rag.enabled is False
        assert planner.build() is None
        assert planner.enabled is False
    finally:
        await context.dispose()


async def test_skills_plugin_discovers_bundled_packages() -> None:
    context = await plugin_app.create_plugin_context(watch=False)
    try:
        skills = context.ctx.get("skills")
        assert skills is not None
        await asyncio.sleep(0)
        found = {skill.name for skill in skills.loaded.values()}
        assert {"example_skill", "weather_skill"} <= found
        assert skills.prompt_text()
    finally:
        await context.dispose()

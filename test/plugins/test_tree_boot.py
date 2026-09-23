"""Plugin tree boot tests: the tree must mount from ``cordis.yml``."""

from __future__ import annotations

import json
from pathlib import Path

from internal.cordis import FiberState
from internal.plugins import app as plugin_app


async def test_plugin_tree_mounts_from_default_config() -> None:
    context = await plugin_app.create_plugin_context(watch=False)
    try:
        report = context.loader.report()
        by_id = {entry["id"]: entry for entry in report}

        assert set(by_id) >= {"logger", "timer", "config", "prompts", "sandbox"}
        for entry_id in ("logger", "timer", "config", "prompts", "sandbox"):
            assert by_id[entry_id]["state"] == FiberState.ACTIVE.value, by_id[entry_id]

        assert context.ctx.get("logger") is not None
        assert context.ctx.get("timer") is not None
        assert context.ctx.get("config") is not None
        assert context.ctx.get("prompts") is not None
        assert context.ctx.get("sandbox") is not None
    finally:
        await context.dispose()


async def test_config_service_exposes_app_config(tmp_path: Path) -> None:
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"live2dSocket": "ws://example.test", "models": []}),
        encoding="utf-8",
    )

    context = await plugin_app.create_plugin_context(watch=False)
    try:
        config = await plugin_app.load_core_resources(context.ctx, str(config_file))
        assert config.live2dSocket == "ws://example.test"
        assert context.ctx.get("config").live2d_socket == "ws://example.test"
    finally:
        await context.dispose()


async def test_custom_tree_can_replace_a_slot(tmp_path: Path) -> None:
    tree = tmp_path / "cordis.json"
    tree.write_text(
        json.dumps(
            [
                {"id": "logger", "name": "internal.plugins.core.logger"},
                {"id": "greeter", "name": "./greeter.py"},
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "greeter.py").write_text(
        "def apply(ctx, config=None):\n    ctx.service('greeter', 'hello')\n",
        encoding="utf-8",
    )

    context = await plugin_app.create_plugin_context(tree, watch=False)
    try:
        assert context.ctx.get("greeter") == "hello"
        assert context.ctx.get("config") is None
    finally:
        await context.dispose()


async def test_dispose_releases_every_fiber() -> None:
    context = await plugin_app.create_plugin_context(watch=False)
    ctx = context.ctx
    await context.dispose()

    assert ctx.disposed is True
    assert ctx.get("logger") is None
    assert ctx.list_fibers() == []

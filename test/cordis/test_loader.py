"""Plugin tree loader and hot-reload tests."""

from __future__ import annotations

import asyncio
import json
import textwrap

from internal.cordis import Context, FiberState, PluginLoader, Service, load_entries_from_file


def _write(path, text: str) -> None:
    path.write_text(textwrap.dedent(text), encoding="utf-8")


def test_load_entries_from_json(tmp_path) -> None:
    config = tmp_path / "cordis.json"
    config.write_text(
        json.dumps(
            [
                {"id": "logger", "name": "internal.cordis.logger", "config": {"base": "t"}},
                {"id": "group", "group": "outputs", "children": [{"id": "child", "name": "x"}]},
                {"id": "off", "name": "y", "disabled": True},
            ]
        ),
        encoding="utf-8",
    )

    entries = load_entries_from_file(config)

    assert [entry.key for entry in entries] == ["logger", "group", "off"]
    assert entries[1].children[0].key == "child"
    assert entries[2].disabled is True


async def test_loader_mounts_entries_and_tracks_rev(tmp_path) -> None:
    plugin = tmp_path / "myplugin.py"
    _write(
        plugin,
        """
        from internal.cordis import Service

        class Greeter(Service):
            def __init__(self, ctx):
                super().__init__(ctx, 'greeter')

            def greet(self):
                return 'v1'
        """,
    )
    config = tmp_path / "cordis.json"
    config.write_text(
        json.dumps([{"id": "greeter", "name": "./myplugin.py"}]), encoding="utf-8"
    )

    ctx = Context(name="root")
    loader = PluginLoader(ctx, path=config, auto_watch=False)
    await loader.load()

    assert loader.rev == 1
    assert isinstance(ctx.get("greeter"), Service)
    assert ctx.get("greeter").greet() == "v1"
    assert loader.report()[0]["state"] == FiberState.ACTIVE.value

    await ctx.dispose()
    loader.stop_watching()


async def test_loader_reload_picks_up_new_code(tmp_path) -> None:
    plugin = tmp_path / "myplugin.py"
    _write(
        plugin,
        """
        from internal.cordis import Service

        class Greeter(Service):
            def __init__(self, ctx):
                super().__init__(ctx, 'greeter')

            def greet(self):
                return 'v1'
        """,
    )
    config = tmp_path / "cordis.json"
    config.write_text(json.dumps([{"id": "greeter", "name": "./myplugin.py"}]), encoding="utf-8")

    ctx = Context(name="root")
    loader = PluginLoader(ctx, path=config, auto_watch=False)
    await loader.load()
    assert ctx.get("greeter").greet() == "v1"

    _write(
        plugin,
        """
        from internal.cordis import Service

        class Greeter(Service):
            def __init__(self, ctx):
                super().__init__(ctx, 'greeter')

            def greet(self):
                return 'v2'
        """,
    )
    await loader.reload_entry("greeter")

    assert ctx.get("greeter").greet() == "v2"
    assert loader.rev >= 2

    await ctx.dispose()
    loader.stop_watching()


async def test_loader_marks_failed_plugin_without_crashing(tmp_path) -> None:
    plugin = tmp_path / "broken.py"
    _write(
        plugin,
        """
        def apply(ctx):
            raise RuntimeError('boom')
        """,
    )
    config = tmp_path / "cordis.json"
    config.write_text(json.dumps([{"id": "broken", "name": "./broken.py"}]), encoding="utf-8")

    ctx = Context(name="root")
    loader = PluginLoader(ctx, path=config, auto_watch=False)
    await loader.load()

    report = loader.report()[0]
    assert report["state"] in {FiberState.FAILED.value, "not-mounted"}
    assert report["error"]

    await ctx.dispose()
    loader.stop_watching()


async def test_loader_unresolvable_module_is_reported(tmp_path) -> None:
    config = tmp_path / "cordis.json"
    config.write_text(json.dumps([{"id": "missing", "name": "./nope.py"}]), encoding="utf-8")

    ctx = Context(name="root")
    loader = PluginLoader(ctx, path=config, auto_watch=False)
    await loader.load()

    assert "nope.py" in loader.report()[0]["error"]
    await ctx.dispose()
    loader.stop_watching()


async def test_hot_reload_detects_file_change(tmp_path) -> None:
    plugin = tmp_path / "hot.py"
    _write(plugin, "VALUE = 'v1'\n\ndef apply(ctx):\n    ctx.service('hot', VALUE)\n")
    config = tmp_path / "cordis.json"
    config.write_text(json.dumps([{"id": "hot", "name": "./hot.py"}]), encoding="utf-8")

    ctx = Context(name="root")
    loader = PluginLoader(ctx, path=config, auto_watch=False)
    await loader.load()
    assert ctx.get("hot") == "v1"

    await asyncio.sleep(0.01)
    _write(plugin, "VALUE = 'v2'\n\ndef apply(ctx):\n    ctx.service('hot', VALUE)\n")
    path = str(plugin.resolve())
    loader._mtimes[path] = 0.0
    await loader.handle_file_change(path)

    assert ctx.get("hot") == "v2"
    await ctx.dispose()
    loader.stop_watching()

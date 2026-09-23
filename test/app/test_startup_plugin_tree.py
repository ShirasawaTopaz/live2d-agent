"""End-to-end startup: ``Live2DAgentApp`` mounts the cordis plugin tree.

These tests run headless (Qt "offscreen" platform) and are skipped when the GUI
stack or a usable event loop is unavailable. They assert the migration
contract: the legacy entry point still starts, and the plugin tree is mounted
underneath it with every fiber active.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


@pytest.fixture(autouse=True)
def _offscreen_qt(monkeypatch, tmp_path: Path) -> Path:
    """Force the offscreen Qt backend and a throwaway plugin root."""
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    plugin_root = tmp_path / "userplugins"
    monkeypatch.setenv("LIVE2ODER_PLUGIN_ROOT", str(plugin_root))
    return plugin_root


def _write_config(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "live2dSocket": "ws://127.0.0.1:9/live2d",
                "models": [
                    {
                        "name": "probe",
                        "type": "online",
                        "apiBase": "http://127.0.0.1:9/v1",
                        "apiKey": "probe",
                        "model": "probe",
                    }
                ],
                "memory": {"enabled": False},
            }
        ),
        encoding="utf-8",
    )


class FakeClient:
    """Stands in for the Live2D websocket client (no socket is opened)."""

    async def send(self, payload) -> None:  # noqa: ANN001
        return None


class FakeWebSocket:
    """Minimal transport double so startup does not wait on a real socket."""

    def __init__(self) -> None:
        self.client = FakeClient()
        self.on_connect = None
        self.on_disconnect = None
        self.is_connected = True

    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        self.is_connected = False

    def start_receive_loop(self, queue) -> "asyncio.Task[None]":  # noqa: ANN001
        async def runner() -> None:
            _ = queue

        return asyncio.get_running_loop().create_task(runner())


async def test_live2d_agent_app_mounts_plugin_tree(tmp_path: Path, monkeypatch) -> None:
    from internal.app import bootstrap
    from internal.app.live2d_agent_app import Live2DAgentApp
    from internal.config.config import Config

    config_file = tmp_path / "config.json"
    _write_config(config_file)

    transport = FakeWebSocket()

    async def fake_create_websocket(_config):  # noqa: ANN001
        return transport

    monkeypatch.setattr(bootstrap, "create_websocket", fake_create_websocket)

    original_path = Config.DEFAULT_CONFIG_PATH
    Config.DEFAULT_CONFIG_PATH = str(config_file)

    app = Live2DAgentApp()
    try:
        await app.initialize()
    finally:
        Config.DEFAULT_CONFIG_PATH = original_path

    try:
        context = app.plugin_context
        assert context is not None, "Live2DAgentApp did not mount the plugin tree"

        ctx = context.ctx
        for service in (
            "logger",
            "config",
            "tools",
            "sandbox",
            "agent/loop",
            "outputs/bubble",
            "meta/self-evolution",
            "meta/diagnostics",
        ):
            assert ctx.get(service) is not None, f"service '{service}' missing"

        from internal.cordis import FiberState

        states = {entry["id"]: entry["state"] for entry in context.loader.report()}
        assert states["self-evolution"] == FiberState.ACTIVE.value
        assert states["output"] == FiberState.ACTIVE.value
        assert states["loop"] == FiberState.ACTIVE.value

        loop = ctx.get("agent/loop")
        assert loop.agent is app.agent
        output = ctx.get("outputs/bubble")
        assert output.widget is app.bubble_widget
    finally:
        await app.cleanup()

    assert app.plugin_context is None


async def test_startup_mounts_previously_installed_user_plugin(
    tmp_path: Path, _offscreen_qt: Path
) -> None:
    """A plugin installed in an earlier session is mounted at startup."""
    from internal.plugins.meta import plugin_templates

    source_dir = _offscreen_qt / "sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    source = source_dir / "startup_probe.py"
    source.write_text(
        plugin_templates.render("service", "startup_probe", description="probe"),
        encoding="utf-8",
    )
    (_offscreen_qt / "user_entries.json").write_text(
        json.dumps(
            [{"id": "user:startup_probe", "name": str(source), "config": {}, "disabled": False}]
        ),
        encoding="utf-8",
    )

    from internal.plugins import app as plugin_app

    context = await plugin_app.create_plugin_context(watch=False)
    try:
        await asyncio.sleep(0)
        service = context.ctx.get("startup-probe")
        assert service is not None
        assert service.ping() == "startup-probe ok"
        entry = context.loader.find("user:startup_probe")
        assert entry is not None and entry.fiber is not None
    finally:
        await context.dispose()

"""Runtime plugin self-evolution: author, mount, reload, roll back."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from internal.cordis import Context, FiberState
from internal.plugins import app as plugin_app
from internal.plugins.meta import plugin_templates
from internal.plugins.meta.evolution_tools import build_tools
from internal.plugins.meta.plugin_sandbox import PluginCodeSandbox, PluginPolicy


@pytest.fixture(autouse=True)
def _isolated_plugin_root(tmp_path_factory, monkeypatch) -> Path:
    """Keep user plugins out of the real APPDATA directory."""
    root = tmp_path_factory.mktemp("evoroot")
    monkeypatch.setenv("LIVE2ODER_PLUGIN_ROOT", str(root))
    return root


async def _context(tmp_path: Path) -> plugin_app.PluginContext:
    """Boot the real tree (config service included) on a helper context."""
    context = await plugin_app.create_plugin_context(watch=False)
    ctx = context.ctx
    for name in ("loader", "tools", "sandbox", "meta/self-evolution"):
        assert ctx.get(name) is not None, f"{name} missing"
    ctx.get("meta/self-evolution").configure(root=tmp_path / "plugins")
    return context


async def test_evolution_service_is_mounted_with_tools(tmp_path: Path) -> None:
    context = await _context(tmp_path)
    try:
        ctx = context.ctx
        evolution = ctx.get("meta/self-evolution")
        assert evolution is not None

        described = evolution.describe()
        assert described["allow_core_writes"] is False
        assert set(described["kinds"]) == {"tool", "service", "loop", "output", "prompt"}

        tools = ctx.get("tools")
        for tool_name in described["tools"]:
            assert tool_name in tools.registry.tools, tool_name
    finally:
        await context.dispose()


async def test_scaffold_renders_valid_plugin_code() -> None:
    sandbox = PluginCodeSandbox(allow_core_imports=True)
    for kind in ("tool", "service", "loop", "output", "prompt"):
        code = plugin_templates.render(kind, "probe_plugin", description=f"{kind} probe")
        result = sandbox.validate(code)
        assert result.ok, f"{kind}: {result.errors}"
        compile(code, f"{kind}.py", "exec")
        assert "def apply(ctx, config=None)" in code


async def test_install_mounts_plugin_and_appends_tree_entry(tmp_path: Path) -> None:
    context = await _context(tmp_path)
    try:
        ctx = context.ctx
        evolution = ctx.get("meta/self-evolution")
        owner = ctx.extend(name="evolver")

        scaffolding = evolution.scaffold("greet_probe", kind="service", description="probe")
        assert scaffolding["ok"] is True

        result = await evolution.install("greet_probe", scaffolding["code"], owner=owner)
        assert result["ok"] is True, result
        assert result["version"] == "1.0.0"
        assert result["entry_id"] == "user:greet_probe"

        await asyncio.sleep(0)
        await asyncio.sleep(0)

        service = ctx.get("greet-probe") or ctx.get("greet_probe")
        assert service is not None

        entry = context.loader.find("user:greet_probe")
        assert entry is not None
        assert entry.fiber is not None and entry.fiber.state is FiberState.ACTIVE

        saved = json.loads(
            (tmp_path / "plugins" / "user_entries.json").read_text(encoding="utf-8")
        )
        assert any(item["id"] == "user:greet_probe" for item in saved)
    finally:
        await context.dispose()


async def test_install_rejects_unsafe_code(tmp_path: Path) -> None:
    context = await _context(tmp_path)
    try:
        evolution = context.ctx.get("meta/self-evolution")
        malicious = (
            "import subprocess\n\n"
            "def apply(ctx, config=None):\n"
            "    subprocess.run(['echo', 'pwned'])\n"
        )
        result = await evolution.install("bad_plugin", malicious)

        assert result["ok"] is False
        assert "security validation failed" in result["error"]
        assert not (tmp_path / "plugins" / "sources" / "bad_plugin.py").exists()

        audit = evolution.audit(action="install-rejected")
        assert audit["count"] >= 1
    finally:
        await context.dispose()


async def test_reload_picks_up_new_plugin_code(tmp_path: Path) -> None:
    context = await _context(tmp_path)
    try:
        ctx = context.ctx
        evolution = ctx.get("meta/self-evolution")
        owner = ctx.extend(name="evolver")

        first = plugin_templates.render("service", "reload_probe", description="v1")
        assert (await evolution.install("reload_probe", first, owner=owner))["ok"] is True
        await _settle()
        assert _read_probe(ctx) == "reload-probe ok"

        second = first.replace('return "reload-probe ok"', 'return "v2 ok"')
        assert (await evolution.install("reload_probe", second, owner=owner))["ok"] is True
        await _settle()

        assert _read_probe(ctx) == "v2 ok"
        assert len(evolution.ensure_store().versions.get_versions("reload_probe")) == 2
    finally:
        await context.dispose()


async def test_rollback_restores_previous_version(tmp_path: Path) -> None:
    context = await _context(tmp_path)
    try:
        ctx = context.ctx
        evolution = ctx.get("meta/self-evolution")
        owner = ctx.extend(name="evolver")

        first = plugin_templates.render("service", "rollback_probe", description="v1")
        await evolution.install("rollback_probe", first, owner=owner)
        await _settle()
        assert _read_probe(ctx, "rollback_probe") == "rollback-probe ok"

        second = first.replace('return "rollback-probe ok"', 'return "broken"')
        await evolution.install("rollback_probe", second, owner=owner)
        await _settle()
        assert _read_probe(ctx, "rollback_probe") == "broken"

        versions = [info.version for info in evolution.ensure_store().versions.get_versions("rollback_probe")]
        result = await evolution.rollback("rollback_probe", versions[0])
        assert result["ok"] is True, result
        await _settle()

        assert _read_probe(ctx, "rollback_probe") == "rollback-probe ok"
    finally:
        await context.dispose()


async def test_toggle_disables_and_reenables_entry(tmp_path: Path) -> None:
    context = await _context(tmp_path)
    try:
        ctx = context.ctx
        evolution = ctx.get("meta/self-evolution")
        owner = ctx.extend(name="evolver")

        code = plugin_templates.render("service", "toggle_probe", description="toggle")
        await evolution.install("toggle_probe", code, owner=owner)
        await _settle()
        assert _read_probe(ctx, "toggle_probe") == "toggle-probe ok"

        disabled = await evolution.set_enabled("user:toggle_probe", False)
        assert disabled["ok"] is True
        await _settle()
        assert _read_probe(ctx, "toggle_probe") is None

        enabled = await evolution.set_enabled("user:toggle_probe", True)
        assert enabled["ok"] is True
        await _settle()
        assert _read_probe(ctx, "toggle_probe") == "toggle-probe ok"
    finally:
        await context.dispose()


async def test_status_and_diagnose_report_fiber_states(tmp_path: Path) -> None:
    context = await _context(tmp_path)
    try:
        evolution = context.ctx.get("meta/self-evolution")
        status = evolution.status()

        assert status["ok"] is True
        assert status["rev"] >= 0
        assert "meta/self-evolution" in status["services"]
        states = {fiber["state"] for fiber in status["fibers"]}
        assert "active" in states

        diagnose = evolution.diagnose()
        assert diagnose["ok"] is True
        assert diagnose["healthy"] is True
        assert diagnose["problems"] == []
    finally:
        await context.dispose()


async def test_pending_plugin_is_diagnosed_as_missing_service(tmp_path: Path) -> None:
    context = await _context(tmp_path)
    try:
        ctx = context.ctx
        evolution = ctx.get("meta/self-evolution")

        code = (
            "from internal.cordis import Service\n\n"
            'plugin_name = "needs_missing"\n'
            'inject = ["does-not-exist"]\n\n'
            "def apply(ctx, config=None):\n"
            '    ctx.service("needs-missing", object())\n'
        )
        assert (await evolution.install("needs_missing", code, mount=False))["ok"] is True

        loop = asyncio.get_running_loop()
        from internal.cordis import LoaderEntry

        entry = LoaderEntry(
            name=str(evolution.ensure_store().source_path("needs_missing")),
            id="user:needs_missing_probe",
        )
        fiber = await context.loader.mount_entry(entry, ctx)
        assert fiber is not None and fiber.state is FiberState.PENDING

        diagnose = evolution.diagnose()
        assert diagnose["healthy"] is False
        problem = next(p for p in diagnose["problems"] if p["id"] == "user:needs_missing_probe")
        assert problem["state"] == "pending"
        assert "does-not-exist" in problem["missing"]
        assert "missing services" in problem["hint"]
        _ = loop
    finally:
        await context.dispose()


def test_write_policy_blocks_core_without_opt_in(tmp_path: Path) -> None:
    policy = PluginPolicy(allow_core_writes=False)
    user_root = tmp_path / "plugins"
    core_root = tmp_path / "core"
    (user_root / "sources").mkdir(parents=True)
    core_root.mkdir()

    allowed = policy.check_target(user_root / "sources" / "x.py", user_root=user_root, core_root=core_root)
    assert allowed.ok is True

    denied = policy.check_target(core_root / "x.py", user_root=user_root, core_root=core_root)
    assert denied.ok is False
    assert "allow_core_writes" in denied.message

    outside = policy.check_target(tmp_path / "elsewhere.py", user_root=user_root, core_root=core_root)
    assert outside.ok is False

    opt_in = PluginPolicy(allow_core_writes=True)
    assert opt_in.check_target(core_root / "x.py", user_root=user_root, core_root=core_root).ok is True


async def test_evolution_tools_execute_through_registry(tmp_path: Path) -> None:
    context = await _context(tmp_path)
    try:
        ctx = context.ctx
        evolution = ctx.get("meta/self-evolution")
        tools = {tool.name: tool for tool in build_tools(evolution)}

        scaffold = json.loads(await tools["plugin_scaffold"].execute(name="tool_probe", kind="tool"))
        assert scaffold["ok"] is True

        installed = json.loads(
            await tools["plugin_install"].execute(
                name="tool_probe", code=scaffold["code"], kind="tool"
            )
        )
        assert installed["ok"] is True
        await _settle()

        registered = json.loads(await tools["plugin_status"].execute(entry_id="user:tool_probe"))
        assert registered["ok"] is True
        assert registered["entries"]

        audit = json.loads(await tools["plugin_audit"].execute(action="install"))
        assert audit["count"] >= 1
    finally:
        await context.dispose()


async def test_evolver_unload_leaves_plugin_mounted(tmp_path: Path) -> None:
    """The user plugin outlives the temporary authoring scope."""
    context = await _context(tmp_path)
    try:
        ctx = context.ctx
        evolution = ctx.get("meta/self-evolution")
        owner = ctx.extend(name="evolver")

        code = plugin_templates.render("service", "outlive_probe", description="outlive")
        await evolution.install("outlive_probe", code, owner=owner)
        await _settle()

        await owner.dispose()
        await _settle()

        entry = context.loader.find("user:outlive_probe")
        assert entry is not None
        assert entry.fiber is not None
        assert entry.fiber.context is not owner
        _ = Context
    finally:
        await context.dispose()


async def _settle() -> None:
    for _ in range(4):
        await asyncio.sleep(0)


def _read_probe(ctx, name: str = "reload_probe") -> str | None:
    service = ctx.get(name.replace("_", "-"))
    if service is None:
        return None
    return service.ping()

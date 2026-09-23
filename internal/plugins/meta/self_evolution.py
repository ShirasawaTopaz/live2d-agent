"""Meta plugin: runtime plugin authoring, reload, and rollback.

This is the capability behind the ``self-evolution`` skill. It lets the agent
create or rewrite cordis plugins at runtime:

* ``scaffold`` renders a skeleton from a template (no side effects),
* ``install`` validates the source, snapshots a version, writes it, appends a
  tree entry, and mounts it as a child fiber,
* ``reload`` hot-reloads an entry through the loader,
* ``rollback`` restores a previous version and reloads,
* ``enable``/``disable`` toggle an entry,
* ``status``/``diagnose`` report fiber states and missing dependencies,
* ``audit`` returns the evolution trail.

Safety layers: AST validation (:mod:`plugin_sandbox`), a write policy that
defaults to the user plugin directory, sandbox approval for core-directory
writes, version snapshots before every write, and one audit entry per action.
Every mount is spawned on the calling context, so unloading the caller also
cancels work that is still in flight.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
import time
from pathlib import Path
from typing import Any

from internal.cordis import Registry, Schema, Service
from internal.plugins.meta import plugin_templates
from internal.plugins.meta.evolution_store import EvolutionStore, StoredPlugin
from internal.plugins.meta.plugin_sandbox import PluginCodeSandbox, PluginPolicy

plugin_name = "meta/self-evolution"

module_schema = Schema.object(
    {
        "root": Schema.string().default(""),
        "allow_core_writes": Schema.boolean().default(False),
        "require_approval_for_core": Schema.boolean().default(True),
        "kinds": Schema.array(Schema.string()).default(
            ["tool", "service", "loop", "output", "prompt"]
        ),
    }
)

logger = logging.getLogger(__name__)

CORE_PLUGIN_ROOT = Path(__file__).resolve().parents[1]


class EvolutionService(Service):
    """Implements the self-evolution tool surface."""

    inject = ["loader", "tools", "sandbox"]

    def __init__(self, ctx: Any, name: str = "meta/self-evolution") -> None:
        super().__init__(ctx, name)
        self.root: Path | None = None
        self.allow_core_writes = False
        self.require_approval_for_core = True
        self.allowed_kinds = ["tool", "service", "loop", "output", "prompt"]
        self.store: EvolutionStore | None = None
        self.sandbox = PluginCodeSandbox(allow_core_imports=True)
        self.policy = PluginPolicy(allow_core_writes=False)

    # ------------------------------------------------------------------ wiring
    def configure(
        self,
        *,
        root: str | Path | None = None,
        allow_core_writes: bool | None = None,
        require_approval_for_core: bool | None = None,
        kinds: list[str] | None = None,
        loader: Any = None,
    ) -> EvolutionStore:
        if allow_core_writes is not None:
            self.allow_core_writes = bool(allow_core_writes)
        if require_approval_for_core is not None:
            self.require_approval_for_core = bool(require_approval_for_core)
        if kinds:
            self.allowed_kinds = list(kinds)
        if root:
            self.root = Path(root).expanduser()
        self.policy = PluginPolicy(allow_core_writes=self.allow_core_writes)
        self.store = EvolutionStore(self.root, loader=loader if loader is not None else self.loader)
        return self.store

    @property
    def loader(self) -> Any:
        return self.ctx.get("loader")

    def ensure_store(self) -> EvolutionStore:
        if self.store is None:
            self.configure()
        assert self.store is not None
        return self.store

    def log(self, action: str, **fields: Any) -> None:
        """Append an entry to the evolution audit trail."""
        self.ensure_store().log(action, **fields)

    # ---------------------------------------------------------------- scaffold
    def scaffold(
        self,
        name: str,
        kind: str = "service",
        description: str = "",
        service: str | None = None,
    ) -> dict[str, Any]:
        """Render a skeleton without writing anything."""
        store = self.ensure_store()
        ok, error = store.validate_name(name)
        if not ok:
            return {"ok": False, "error": error}
        if kind not in self.allowed_kinds:
            return {"ok": False, "error": f"kind must be one of {self.allowed_kinds}"}
        code = plugin_templates.render(
            kind, name, description=description, service=service
        )
        validation = self.sandbox.validate(code)
        return {
            "ok": validation.ok,
            "name": name,
            "kind": kind,
            "code": code,
            "errors": validation.errors,
            "target": str(store.source_path(name)),
        }

    # ----------------------------------------------------------------- install
    async def install(
        self,
        name: str,
        code: str,
        *,
        kind: str = "service",
        config: dict[str, Any] | None = None,
        mount: bool = True,
        owner: Any = None,
    ) -> dict[str, Any]:
        """Validate, snapshot, write, register in the tree, and mount."""
        store = self.ensure_store()
        ok, error = store.validate_name(name)
        if not ok:
            return {"ok": False, "error": error}

        validation = self.sandbox.validate(code)
        if not validation.ok:
            store.log("install-rejected", name=name, errors=validation.errors)
            return {"ok": False, "error": f"security validation failed: {validation.message}"}

        target = store.source_path(name)
        allowed = self.policy.check_target(
            target, user_root=store.sources_dir, core_root=CORE_PLUGIN_ROOT
        )
        if not allowed.ok:
            store.log("install-denied", name=name, errors=allowed.errors)
            return {"ok": False, "error": allowed.message}

        if not self._approve_core_write(target, store):
            store.log("install-not-approved", name=name, path=str(target))
            return {"ok": False, "error": "user approval was not granted"}

        previous = store.read_source(name)
        path, version = store.write_source(name, code)
        entry_id = store.append_entry(name, path, config or {})
        plugin = StoredPlugin(
            name=name,
            entry_id=entry_id,
            path=path,
            version=version,
            code_hash=store.hash_code(code),
            installed_at=time.time(),
            kind=kind,
        )
        store.record(plugin)
        store.log(
            "install",
            name=name,
            version=version,
            entry_id=entry_id,
            path=str(path),
            replaced=previous is not None,
            code=code,
        )

        mounted = mount and self.loader is not None
        if mounted:
            await self._mount(
                owner if owner is not None else self.ctx, name, path, entry_id, config or {}
            )
        return {
            "ok": True,
            "name": name,
            "version": version,
            "entry_id": entry_id,
            "path": str(path),
            "mounted": bool(mounted),
            "code": code,
        }

    async def _mount(
        self,
        scope: Any,
        name: str,
        path: Path,
        entry_id: str,
        config: dict[str, Any],
    ) -> None:
        from internal.cordis import LoaderEntry

        loader = self.loader
        if loader is None:
            return
        if loader.find(entry_id) is not None:
            await loader.reload_entry(entry_id)
            return
        entry = LoaderEntry(name=str(path), id=entry_id, config=config)
        await loader.mount_entry(entry, scope)

    # ------------------------------------------------------------------ reload
    async def reload(self, entry_id: str) -> dict[str, Any]:
        store = self.ensure_store()
        loader = self.loader
        if loader is None:
            return {"ok": False, "error": "no loader available"}
        entry = loader.find(entry_id)
        if entry is None:
            return {"ok": False, "error": f"unknown entry '{entry_id}'"}
        store.log("reload", entry=entry_id)
        try:
            await loader.reload_entry(entry_id)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "entry": entry_id, "rev": loader.rev}

    # ----------------------------------------------------------------- rollback
    async def rollback(self, name: str, version: str | None = None) -> dict[str, Any]:
        store = self.ensure_store()
        versions = store.versions.get_versions(name)
        if not versions:
            return {"ok": False, "error": f"no versions recorded for '{name}'"}
        target = version or versions[-1].version
        info = store.versions.get_version(name, target)
        if info is None:
            return {"ok": False, "error": f"version '{target}' not found for '{name}'"}
        if version is not None and versions[-1].version != target:
            code = store.versions.get_version_code(name, target)
            if code is None:
                return {"ok": False, "error": f"source for version '{target}' is missing"}
            store.write_source(name, code)
        plugin = store.get(name)
        entry_id = plugin.entry_id if plugin is not None else store.entry_id(name)
        store.log("rollback", name=name, version=target)
        reload_result: dict[str, Any] = {"ok": False, "error": "not mounted"}
        if self.loader is not None and self.loader.find(entry_id) is not None:
            reload_result = await self.reload(entry_id)
        return {
            "ok": True,
            "name": name,
            "version": target,
            "path": str(store.source_path(name)),
            "reload": reload_result,
        }

    # ------------------------------------------------------------ enable/disable
    async def set_enabled(self, entry_id: str, enabled: bool) -> dict[str, Any]:
        store = self.ensure_store()
        loader = self.loader
        if loader is None:
            return {"ok": False, "error": "no loader available"}
        if loader.find(entry_id) is None:
            return {"ok": False, "error": f"unknown entry '{entry_id}'"}
        loader.set_disabled(entry_id, not enabled)
        store.persist()
        store.log("enable" if enabled else "disable", entry=entry_id)
        result = await self.reload(entry_id)
        return {"ok": bool(result.get("ok", False)), "entry": entry_id, "enabled": enabled, **result}

    # ------------------------------------------------------------------ status
    def status(self, entry_id: str | None = None) -> dict[str, Any]:
        loader = self.loader
        ctx = self.ctx
        reports = [asdict(report) for report in Registry(ctx.root).report()]
        if entry_id:
            reports = [
                report for report in reports if report["id"] == entry_id or report["name"] == entry_id
            ]
        entries = loader.report() if loader is not None else []
        if entry_id:
            entries = [entry for entry in entries if entry["id"] == entry_id]
        return {
            "ok": True,
            "rev": getattr(loader, "rev", 0),
            "services": sorted(ctx.list_services()),
            "fibers": reports,
            "entries": entries,
            "installed": [plugin.to_dict() for plugin in self.ensure_store().installed.values()],
        }

    def diagnose(self) -> dict[str, Any]:
        """Explain every fiber that is not ACTIVE."""
        problems: list[dict[str, Any]] = []
        for report in Registry(self.ctx.root).report():
            if report.ok:
                continue
            problems.append(
                {
                    "name": report.name,
                    "id": report.id,
                    "state": report.state,
                    "inject": report.inject,
                    "missing": report.missing,
                    "scope": report.scope,
                    "hint": _hint_for(report.missing),
                }
            )
        return {"ok": True, "problems": problems, "healthy": not problems}

    # ------------------------------------------------------------------- audit
    def audit(self, action: str | None = None, limit: int = 200) -> dict[str, Any]:
        events = self.ensure_store().audit_events(action=action, limit=limit)
        return {"ok": True, "count": len(events), "events": events}

    def describe(self) -> dict[str, Any]:
        store = self.ensure_store()
        return {
            "root": str(store.root),
            "allow_core_writes": self.allow_core_writes,
            "require_approval_for_core": self.require_approval_for_core,
            "kinds": list(self.allowed_kinds),
            "tools": [
                "plugin_scaffold",
                "plugin_install",
                "plugin_reload",
                "plugin_rollback",
                "plugin_toggle",
                "plugin_status",
                "plugin_audit",
            ],
        }

    # ------------------------------------------------------------------ approval
    def _approve_core_write(self, target: Path, store: EvolutionStore) -> bool:
        if not self.allow_core_writes or not self.require_approval_for_core:
            return True
        if not str(target).startswith(str(CORE_PLUGIN_ROOT)):
            return True
        sandbox = self.ctx.get("sandbox")
        middleware = getattr(sandbox, "middleware", None)
        if middleware is None or not hasattr(middleware, "request_file_approval"):
            store.log("approval-unavailable", path=str(target))
            return False
        try:
            return bool(
                middleware.request_file_approval(
                    str(target), True, "self-evolution wants to rewrite a shipped plugin"
                )
            )
        except Exception:  # noqa: BLE001 - denial on failure
            logger.warning("core-write approval failed", exc_info=True)
            return False


def _task_id(task: Any) -> str:
    getter = getattr(task, "get_name", None)
    return str(getter()) if callable(getter) else "task"


def _hint_for(missing: list[str]) -> str:
    if not missing:
        return "plugin failed while loading; check its apply() for exceptions"
    return (
        "missing services "
        + ", ".join(missing)
        + "; mount a provider or remove the dependency from inject"
    )


def apply(ctx: Any, config: dict[str, Any] | None = None) -> None:
    service = EvolutionService(ctx, "meta/self-evolution")
    payload = config or {}
    service.configure(
        root=payload.get("root") or None,
        allow_core_writes=payload.get("allow_core_writes"),
        require_approval_for_core=payload.get("require_approval_for_core"),
        kinds=list(payload.get("kinds") or []) or None,
    )
    ctx.service("meta/self-evolution", service)
    from internal.plugins.meta.evolution_tools import register_evolution_tools

    register_evolution_tools(service, ctx)
    service.log("plugin-loaded", name=plugin_name, root=str(service.ensure_store().root))

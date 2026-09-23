"""Config-driven plugin tree loader with hot module reload support.

Layout of ``cordis.yml`` (also accepted: ``.yaml`` / ``.json``)::

    - id: logger
      name: internal.cordis.logger        # dotted path or ./relative/file.py
      config:
        base: live2oder
    - id: tools
      name: internal.plugins.core.tools
      disabled: false
    - group: outputs
      config: {}
      children:
        - id: typewriter
          name: internal.plugins.outputs.typewriter

Entries are mounted concurrently; load order is decided by ``inject``
dependencies, never by position in the file.
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import json
import logging
import sys
import threading
import time
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from .context import Context
from .errors import LoaderError
from .lifecycle import Fiber
from .plugin import Service

__all__ = ["LoaderEntry", "PluginLoader", "load_entries_from_file"]

_logger = logging.getLogger("cordis.loader")


@dataclass
class LoaderEntry:
    """One node of the plugin tree."""

    name: str
    id: str = ""
    config: dict[str, Any] = field(default_factory=dict)
    disabled: bool = False
    children: list["LoaderEntry"] = field(default_factory=list)
    parent: "LoaderEntry | None" = None
    fiber: Fiber | None = None
    error: str = ""

    @property
    def is_group(self) -> bool:
        return bool(self.children) and not self.name

    @property
    def key(self) -> str:
        return self.id or self.name.rsplit(":", 1)[-1].rsplit("/", 1)[-1].removesuffix(".py")

    def iter_entries(self) -> Iterable["LoaderEntry"]:
        yield self
        for child in self.children:
            yield from child.iter_entries()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "config": self.config,
            "disabled": self.disabled,
            "children": [child.to_dict() for child in self.children],
        }


class PluginLoader:
    """Reads the plugin tree, mounts fibers, and reloads changed plugins."""

    def __init__(
        self,
        ctx: Context,
        *,
        path: str | Path | None = None,
        entries: list[LoaderEntry] | None = None,
        poll_interval: float = 0.5,
        auto_watch: bool = True,
    ) -> None:
        self.ctx = ctx
        self.path = Path(path).resolve() if path is not None else None
        self.entries: list[LoaderEntry] = entries or []
        self.poll_interval = poll_interval
        self.auto_watch = auto_watch
        self.rev = 0
        self._overlay_entries: list[LoaderEntry] = []
        self._pending_entries: list[LoaderEntry] = []
        self._root_entries: list[LoaderEntry] = []
        self._reload_callbacks: list[Callable[[str], None]] = []
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._mtimes: dict[str, float] = {}
        self._lock = threading.Lock()
        self._module_files: dict[str, str] = {}
        ctx.service("loader", self)
        ctx.loader = self

    # ------------------------------------------------------------------ loading
    def read_config(self, path: str | Path | None = None) -> list[LoaderEntry]:
        target = Path(path).resolve() if path is not None else self.path
        if target is None:
            raise LoaderError("no cordis config path configured")
        entries = load_entries_from_file(target)
        self.path = target
        return entries

    def entries_from_data(self, data: Any) -> list[LoaderEntry]:
        if not isinstance(data, list):
            raise LoaderError("cordis config must be a list of entries")
        return [_parse_entry(item) for item in data]

    def attach_overlay(self, entries: list[LoaderEntry]) -> None:
        """Extra entries appended at runtime (e.g. user plugins).

        The shipped tree file stays read-only; callers persist overlay entries
        themselves so a runtime install never rewrites the composition file.
        """
        self._overlay_entries = list(entries)
        self._root_entries = list(self.entries) + list(entries)
        for entry in entries:
            self._pending_entries.append(entry)

    async def mount_overlay(self, parent: Context | None = None) -> None:
        """Mount every overlay entry that is not mounted yet."""
        pending, self._pending_entries = self._pending_entries, []
        if not pending:
            return
        await self.mount_entries(pending, parent)
        self._record_mtimes()

    async def load(self, path: str | Path | None = None, *, watch: bool | None = None) -> list[LoaderEntry]:
        """Read the config, mount every enabled entry, and optionally watch."""
        if path is not None or not self.entries:
            self.entries = self.read_config(path)
        self._root_entries = list(self.entries) + list(self._overlay_entries)
        await self.mount_entries(self.entries)
        self._record_mtimes()
        should_watch = self.auto_watch if watch is None else watch
        if should_watch and self.path is not None:
            self.start_watching()
        return self.entries

    async def mount_entries(self, entries: Iterable[LoaderEntry], parent: Context | None = None) -> None:
        ctx = parent if parent is not None else self.ctx
        for entry in entries:
            if entry.disabled:
                continue
            if entry.children:
                scope = ctx.extend(name=entry.id or "group", config=entry.config)
                await self.mount_entries(entry.children, scope)
                continue
            await self.mount_entry(entry, ctx)

    async def mount_entry(self, entry: LoaderEntry, parent: Context | None = None) -> Fiber | None:
        ctx = parent if parent is not None else self.ctx
        if entry.disabled:
            return None
        try:
            plugin = self.resolve(entry.name)
        except Exception as exc:  # noqa: BLE001 - a bad path must not kill the app
            entry.error = str(exc)
            _logger.error("cannot resolve plugin '%s': %s", entry.name, exc)
            self._report("load-failed", entry)
            return None
        try:
            fiber = await ctx.load(plugin, entry.config, name=entry.key, id=entry.id or entry.key)
        except Exception as exc:  # noqa: BLE001 - surface the failure but keep the tree
            entry.error = str(exc)
            _logger.error("plugin '%s' failed to load: %s", entry.name, exc)
            self._report("load-failed", entry)
            return None
        entry.fiber = fiber
        entry.error = ""
        self.rev += 1
        self._record_module_file(entry)
        self._report("loaded", entry)
        return fiber

    # ------------------------------------------------------------- module access
    def resolve(self, name: str) -> Any:
        """Resolve a module spec to a plugin value.

        Accepted forms: ``pkg.module``, ``pkg.module:attribute``, and
        ``./relative/file.py`` (relative to the config file). For a module that
        exposes no ``apply`` symbol, a single ``Service`` subclass acts as the
        plugin, so ``./my_service.py`` works like ``./my_service.py:MyService``.
        """
        module_name, attribute = _split_spec(name)
        module = self._import_module(module_name)
        if attribute:
            try:
                return getattr(module, attribute)
            except AttributeError as exc:
                raise LoaderError(f"module '{module_name}' has no attribute '{attribute}'") from exc
        apply_func = getattr(module, "apply", None)
        if callable(apply_func):
            return module
        plugin_symbol = getattr(module, "Plugin", None)
        if plugin_symbol is not None:
            return plugin_symbol
        candidates = [
            value
            for value in vars(module).values()
            if inspect.isclass(value) and issubclass(value, Service) and value is not Service
        ]
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            names = ", ".join(sorted(candidate.__name__ for candidate in candidates))
            raise LoaderError(
                f"module '{module_name}' exports several services ({names}); "
                f"use '{module_name}:<ClassName>' to pick one"
            )
        return module

    def _import_module(self, module_name: str) -> Any:
        path = self._module_path(module_name)
        if path is not None:
            return _import_from_file(path)
        try:
            return importlib.import_module(module_name)
        except ImportError as exc:
            raise LoaderError(f"cannot import '{module_name}': {exc}") from exc

    def _module_path(self, module_name: str) -> Path | None:
        if module_name.startswith(".") or module_name.endswith(".py"):
            base = self.path.parent if self.path is not None else Path.cwd()
            candidate = (base / module_name).resolve()
            if candidate.exists():
                return candidate
        if "/" in module_name or "\\" in module_name:
            candidate = Path(module_name)
            if candidate.is_absolute():
                return candidate if candidate.exists() else None
            base = self.path.parent if self.path is not None else Path.cwd()
            candidate = (base / module_name).resolve()
            if candidate.exists():
                return candidate
        return None

    def _record_module_file(self, entry: LoaderEntry) -> None:
        module_name = _split_spec(entry.name)[0]
        for key, module in list(sys.modules.items()):
            if module is None:
                continue
            if key != module_name and not key.startswith(f"{module_name}."):
                continue
            file = getattr(module, "__file__", None)
            if file:
                self._module_files[entry.key] = str(Path(file).resolve())
        top_module = sys.modules.get(module_name)
        file = getattr(top_module, "__file__", None) if top_module is not None else None
        if file is None:
            path = self._module_path(module_name)
            file = str(path) if path is not None else None
        if file:
            self._module_files[entry.key] = str(Path(file).resolve())

    def _all_module_files(self, entry: LoaderEntry) -> list[str]:
        module_name = _split_spec(entry.name)[0]
        files: list[str] = []
        for key, module in list(sys.modules.items()):
            if module is None:
                continue
            if key != module_name and not key.startswith(f"{module_name}."):
                continue
            file = getattr(module, "__file__", None)
            if file:
                files.append(str(Path(file).resolve()))
        recorded = self._module_files.get(entry.key)
        if recorded and recorded not in files:
            files.append(recorded)
        path = self._module_path(module_name)
        if path is not None:
            resolved = str(path.resolve())
            if resolved not in files:
                files.append(resolved)
        return files

    def entry_for_file(self, path: str | Path) -> LoaderEntry | None:
        target = str(Path(path).resolve())
        for entry in self.iter_entries():
            if entry.disabled or not entry.name:
                continue
            resolved = self._all_module_files(entry)
            if target in resolved:
                return entry
        for entry in self.iter_entries():
            if self._module_files.get(entry.key) == target:
                return entry
        return None

    def iter_entries(self) -> Iterable[LoaderEntry]:
        for entry in self._root_entries or self.entries:
            yield from entry.iter_entries()

    def find(self, key: str) -> LoaderEntry | None:
        for entry in self.iter_entries():
            if entry.key == key or entry.id == key:
                return entry
        return None

    def report(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for entry in self.iter_entries():
            if not entry.name:
                continue
            fiber = entry.fiber
            result.append(
                {
                    "id": entry.id or entry.key,
                    "name": entry.name,
                    "state": fiber.state.value if fiber is not None else "not-mounted",
                    "disabled": entry.disabled,
                    "error": entry.error,
                }
            )
        return result

    # ---------------------------------------------------------------- mutation
    async def reload_entry(self, key: str) -> Fiber | None:
        """Unload and remount one entry, returning the new fiber."""
        with self._lock:
            self.rev += 1
        entry = self.find(key)
        if entry is None:
            raise LoaderError(f"unknown plugin entry '{key}'")
        if entry.fiber is not None:
            await entry.fiber.dispose()
            entry.fiber = None
        _purge_module(entry.name)
        if entry.disabled:
            self._report("unloaded", entry)
            return None
        new_fiber = await self.mount_entry(entry, self._entry_parent_scope(entry))
        self._report("reloaded", entry)
        return new_fiber

    def _entry_parent_scope(self, entry: LoaderEntry) -> Context:
        scope = self.ctx
        chain: list[LoaderEntry] = []
        parent = entry.parent
        while parent is not None:
            chain.append(parent)
            parent = parent.parent
        for group in reversed(chain):
            scope = scope.extend(name=group.id or "group", config=group.config)
        return scope

    async def reload_all(self) -> None:
        for entry in list(self.iter_entries()):
            if entry.name and not entry.children:
                await self.reload_entry(entry.key)

    def set_disabled(self, key: str, disabled: bool) -> LoaderEntry:
        entry = self.find(key)
        if entry is None:
            raise LoaderError(f"unknown plugin entry '{key}'")
        entry.disabled = disabled
        self.rev += 1
        return entry

    def add_entry(self, entry: LoaderEntry) -> None:
        """Append an entry to the in-memory tree.

        The caller owns persistence (the self-evolution store writes its own
        overlay file), so a runtime install never rewrites ``cordis.yml``.
        """
        if self.find(entry.key) is not None:
            raise LoaderError(f"plugin entry '{entry.key}' already exists")
        self._root_entries.append(entry)
        self._overlay_entries.append(entry)
        entry.parent = None
        self.rev += 1

    def remove_entry(self, key: str) -> LoaderEntry:
        entry = self.find(key)
        if entry is None:
            raise LoaderError(f"unknown plugin entry '{key}'")
        siblings = entry.parent.children if entry.parent is not None else self._root_entries
        if entry in siblings:
            siblings.remove(entry)
        if entry in self._overlay_entries:
            self._overlay_entries.remove(entry)
        self.rev += 1
        return entry

    @property
    def overlay_entries(self) -> list[LoaderEntry]:
        return list(self._overlay_entries)

    # ------------------------------------------------------------------ watching
    def start_watching(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._watch_loop, name="cordis-hmr", daemon=True)
        self._thread.start()
        self._report("watch-started", None)

    def stop_watching(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
        self._thread = None

    def _watch_loop(self) -> None:
        while not self._stop_event.is_set():
            time.sleep(self.poll_interval)
            if self._stop_event.is_set():
                return
            try:
                changed = self._collect_changes()
            except Exception:  # noqa: BLE001
                _logger.exception("plugin watcher scan failed")
                continue
            if not changed:
                continue
            loop = getattr(self.ctx, "_loop", None)
            for path in changed:
                if loop is not None and loop.is_running():
                    loop.call_soon_threadsafe(self._schedule_reload, path)
                else:
                    self._schedule_reload(path)

    def _collect_changes(self) -> list[str]:
        changed: list[str] = []
        for path, previous in list(self._mtimes.items()):
            try:
                current = Path(path).stat().st_mtime
            except OSError:
                continue
            if current != previous:
                self._mtimes[path] = current
                changed.append(path)
        return changed

    def on_reload(self, callback: Callable[[str], None]) -> None:
        self._reload_callbacks.append(callback)

    def _schedule_reload(self, path: str) -> None:
        loop = getattr(self.ctx, "_loop", None)
        if loop is None or not loop.is_running():
            return
        loop.create_task(self.handle_file_change(path))

    async def handle_file_change(self, path: str) -> None:
        """Reload the plugin that owns ``path`` (config file or plugin module)."""
        resolved = str(Path(path).resolve())
        if self.path is not None and resolved == str(self.path):
            await self._reload_from_config()
            return
        entry = self.entry_for_file(resolved)
        if entry is None:
            self._report("ignored", None, path=resolved)
            return
        self._report("reload", entry, path=resolved)
        try:
            await self.reload_entry(entry.key)
        except Exception as exc:  # noqa: BLE001 - keep the old fiber on failure
            entry.error = str(exc)
            _logger.error("hot reload of '%s' failed: %s", entry.key, exc)

    async def _reload_from_config(self) -> None:
        try:
            new_entries = self.read_config()
        except Exception as exc:  # noqa: BLE001
            _logger.error("cannot read plugin config: %s", exc)
            return
        old = {entry.key: entry for entry in self.iter_entries() if entry.name}
        self._root_entries = list(new_entries) + list(self._overlay_entries)
        self.entries = new_entries
        for entry in self.iter_entries():
            if not entry.name or entry.disabled:
                continue
            previous = old.get(entry.key)
            if previous is None or previous.fiber is None:
                await self.mount_entry(entry, self._entry_parent_scope(entry))
            elif previous.config != entry.config or previous.name != entry.name:
                entry.fiber = previous.fiber
                await self.reload_entry(entry.key)
            else:
                entry.fiber = previous.fiber
        self.rev += 1
        self._record_mtimes()

    def _record_mtimes(self) -> None:
        self._mtimes = {}
        if self.path is not None and self.path.exists():
            self._mtimes[str(self.path)] = self.path.stat().st_mtime
        for entry in self.iter_entries():
            if not entry.name:
                continue
            for resolved in self._all_module_files(entry):
                try:
                    self._mtimes[resolved] = Path(resolved).stat().st_mtime
                except OSError:
                    continue

    def _report(self, kind: str, entry: LoaderEntry | None, **fields: Any) -> None:
        payload = {"kind": kind, "entry": entry.key if entry is not None else "", **fields}
        _logger.debug("loader event %s", payload)
        self.ctx.emit("loader/event", payload)
        for callback in list(self._reload_callbacks):
            try:
                callback(kind)
            except Exception:  # noqa: BLE001
                _logger.exception("loader reload callback failed")


def _parse_entry(data: Any, parent: LoaderEntry | None = None) -> LoaderEntry:
    if not isinstance(data, dict):
        raise LoaderError(f"invalid plugin entry: {data!r}")
    children_data = data.get("children") or data.get("plugins") or []
    group = data.get("group")
    name = str(data.get("name") or "")
    if group and not name:
        name = ""
    entry = LoaderEntry(
        name=name,
        id=str(data.get("id") or ""),
        config=data.get("config") or {},
        disabled=bool(data.get("disabled", False)),
        parent=parent,
    )
    if group and not entry.id:
        entry.id = str(group)
    entry.children = [_parse_entry(child, entry) for child in children_data]
    return entry


def _split_spec(spec: str) -> tuple[str, str]:
    """Split ``module:attribute`` without breaking Windows drive letters.

    ``C:\\path\\plugin.py:apply`` yields ``("C:\\path\\plugin.py", "apply")``,
    while a bare ``C:\\path\\plugin.py`` keeps its drive letter intact.
    """
    head, _sep, tail = spec.rpartition(":")
    if not head or len(head) == 1 and head.isalpha():
        return spec, ""
    if "\\" in tail or "/" in tail:
        return spec, ""
    return head, tail


def load_entries_from_file(path: Path) -> list[LoaderEntry]:
    text = path.read_text(encoding="utf-8")
    if path.suffix in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError as exc:  # pragma: no cover - yaml is an explicit dep
            raise LoaderError("PyYAML is required to read cordis.yml") from exc
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if data is None:
        return []
    if not isinstance(data, list):
        raise LoaderError("cordis config must be a list of entries")
    return [_parse_entry(item) for item in data]


def _import_from_file(path: Path) -> Any:
    """Execute a plugin file from source, bypassing the bytecode cache.

    Editors and test harnesses can write a file twice within the timestamp
    granularity that ``__pycache__`` validation relies on, which would silently
    reload stale bytecode. Compiling the source text directly keeps hot reload
    deterministic.
    """
    module_name = f"cordis_file_{abs(hash(str(path))) & 0xFFFFFF:x}"
    source = path.read_text(encoding="utf-8")
    code = compile(source, str(path), "exec")
    spec = importlib.util.spec_from_loader(module_name, loader=None)
    module = importlib.util.module_from_spec(spec) if spec is not None else types.ModuleType(module_name)
    module.__file__ = str(path)
    module.__loader__ = None
    sys.modules[module_name] = module
    try:
        exec(code, module.__dict__)  # noqa: S102 - plugin code is validated elsewhere
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


def _purge_module(name: str) -> None:
    """Drop a module and its submodules so the next import re-executes them."""
    module_name = _split_spec(name)[0]
    for key in list(sys.modules):
        if key == module_name or key.startswith(f"{module_name}."):
            sys.modules.pop(key, None)
    for key in list(sys.modules):
        if key.startswith("cordis_file_"):
            module = sys.modules.get(key)
            file = getattr(module, "__file__", None)
            if file and Path(file).name == Path(module_name).name:
                sys.modules.pop(key, None)

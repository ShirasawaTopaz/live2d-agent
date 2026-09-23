"""Storage for AI-authored plugins: sources, versions, and tree entries.

Layout under the plugin root (``%APPDATA%/Live2Oder/plugins`` by default)::

    <root>/
      sources/<plugin>.py        # live source file the loader mounts
      versions/version_index.json
      versions/<plugin>_v1_0_0_plugin.py
      evolution_audit.jsonl      # audit trail of every evolution action

Tree entries are appended to ``cordis.yml`` (or ``cordis.json``) through the
loader so the plugin tree stays the single composition source.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from internal.agent.tool.dynamic.audit import AuditLogger
from internal.agent.tool.dynamic.versioning import VersionManager

__all__ = ["EvolutionStore", "StoredPlugin", "default_plugin_root"]

_SAFE_NAME = re.compile(r"^[a-z][a-z0-9_]{1,48}$")


def default_plugin_root() -> Path:
    """User-writable plugin directory (mirrors SkillManager's data dir)."""
    override = os.environ.get("LIVE2ODER_PLUGIN_ROOT")
    if override:
        return Path(override).expanduser()
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "Live2Oder" / "plugins"
    return Path.home() / ".config" / "Live2Oder" / "plugins"


@dataclass(slots=True)
class StoredPlugin:
    """Bookkeeping for one plugin managed by the evolution service."""

    name: str
    entry_id: str
    path: Path
    version: str = ""
    code_hash: str = ""
    installed_at: float = 0.0
    kind: str = "function"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "entry_id": self.entry_id,
            "path": str(self.path),
            "version": self.version,
            "code_hash": self.code_hash,
            "installed_at": self.installed_at,
            "kind": self.kind,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StoredPlugin":
        return cls(
            name=str(data.get("name", "")),
            entry_id=str(data.get("entry_id", "")),
            path=Path(str(data.get("path", ""))),
            version=str(data.get("version", "")),
            code_hash=str(data.get("code_hash", "")),
            installed_at=float(data.get("installed_at", 0.0)),
            kind=str(data.get("kind", "function")),
        )


class EvolutionStore:
    """Filesystem + version + audit backing for plugin self-evolution."""

    def __init__(
        self,
        root: str | Path | None = None,
        *,
        loader: Any = None,
        audit_dir: str | Path | None = None,
    ) -> None:
        self.root = Path(root).expanduser() if root is not None else default_plugin_root()
        self.loader = loader
        self.sources_dir = self.root / "sources"
        self.index_path = self.root / "plugins_index.json"
        self.entries_path = self.root / "user_entries.json"
        self.installed: dict[str, StoredPlugin] = {}
        self._ensure_layout()
        self.audit = AuditLogger(log_dir=str(audit_dir or self.root))
        self.versions = VersionManager(self.root)
        self._load_index()
        if self.loader is not None:
            self.attach_loader(self.loader)

    # ------------------------------------------------------------------ layout
    def _ensure_layout(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.sources_dir.mkdir(parents=True, exist_ok=True)

    def _load_index(self) -> None:
        if not self.index_path.exists():
            return
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        for name, payload in (data or {}).items():
            try:
                self.installed[name] = StoredPlugin.from_dict(payload)
            except Exception:  # noqa: BLE001 - corrupt entries are ignored
                continue

    def _save_index(self) -> None:
        payload = {name: plugin.to_dict() for name, plugin in self.installed.items()}
        self.index_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ------------------------------------------------------------------- naming
    @staticmethod
    def validate_name(name: str) -> tuple[bool, str]:
        if not _SAFE_NAME.match(name or ""):
            return False, "plugin name must be lower_snake_case (2-49 chars, letters/digits/_)"
        return True, ""

    @staticmethod
    def hash_code(code: str) -> str:
        return hashlib.sha256(code.encode("utf-8")).hexdigest()[:12]

    def source_path(self, name: str) -> Path:
        return self.sources_dir / f"{name}.py"

    def entry_id(self, name: str) -> str:
        return f"user:{name}"

    # ------------------------------------------------------------------- writing
    def write_source(self, name: str, code: str) -> tuple[Path, str]:
        """Write the live source file and record a new version."""
        path = self.source_path(name)
        path.write_text(code, encoding="utf-8")
        info = self.versions.add_version(name, code, description="plugin install")
        return path, info.version

    def read_source(self, name: str) -> str | None:
        path = self.source_path(name)
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def record(self, plugin: StoredPlugin) -> None:
        self.installed[plugin.name] = plugin
        self._save_index()

    def forget(self, name: str) -> None:
        self.installed.pop(name, None)
        self._save_index()

    def get(self, name: str) -> StoredPlugin | None:
        return self.installed.get(name)

    # -------------------------------------------------------------------- tree
    def attach_loader(self, loader: Any) -> None:
        """Bind a loader and load the persisted overlay entries into it."""
        if loader is None:
            return
        self.loader = loader
        entries = self.load_entries()
        if entries:
            loader.attach_overlay(entries)

    def load_entries(self) -> list[Any]:
        """Read persisted user entries as loader entries."""
        if not self.entries_path.exists():
            return []
        try:
            data = json.loads(self.entries_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        from internal.cordis import LoaderEntry

        entries: list[LoaderEntry] = []
        for item in data or []:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            entries.append(
                LoaderEntry(
                    name=str(item["name"]),
                    id=str(item.get("id") or ""),
                    config=item.get("config") or {},
                    disabled=bool(item.get("disabled", False)),
                )
            )
        return entries

    def save_entries(self, entries: list[Any] | None = None) -> None:
        """Persist the overlay entries (defaults to the loader's current set)."""
        source = entries
        if source is None:
            if self.loader is None:
                return
            source = self.loader.overlay_entries
        payload = [entry.to_dict() for entry in source]
        self.entries_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def append_entry(self, name: str, module_path: Path, config: dict[str, Any] | None = None) -> str:
        """Append this plugin to the overlay tree and persist it."""
        entry_id = self.entry_id(name)
        if self.loader is None:
            return entry_id
        from internal.cordis import LoaderEntry

        existing = self.loader.find(entry_id)
        if existing is not None:
            existing.name = str(module_path)
            existing.config = dict(config or {})
            self.save_entries()
            return entry_id
        entry = LoaderEntry(name=str(module_path), id=entry_id, config=config or {})
        self.loader.add_entry(entry)
        self.save_entries()
        return entry_id

    def remove_entry(self, name: str) -> bool:
        if self.loader is None:
            return False
        entry_id = self.entry_id(name)
        if self.loader.find(entry_id) is None:
            return False
        self.loader.remove_entry(entry_id)
        self.save_entries()
        return True

    def persist(self) -> None:
        """Persist the current overlay entries (used after disable/enable)."""
        self.save_entries()

    # ------------------------------------------------------------------- audit
    def log(self, action: str, **fields: Any) -> None:
        payload = {"action": action, "timestamp": time.time(), **fields}
        try:
            self.audit._write_log("plugin_evolution", payload)
        except Exception:  # noqa: BLE001 - auditing must never break the action
            pass

    def audit_events(self, action: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        events = self.audit.get_all_events(event_type="plugin_evolution")
        if action:
            events = [event for event in events if event.get("action") == action]
        return events[-limit:]

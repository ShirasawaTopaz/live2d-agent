"""Meta plugin: hot module reload for the plugin tree (``meta/hmr``).

The loader already watches plugin files and the tree file; this plugin exposes
that capability as a service, forwards loader events as ``hmr/event``, and can
trigger a full reload on demand.
"""

from __future__ import annotations

from typing import Any

from internal.cordis import Schema, Service

plugin_name = "meta/hmr"

module_schema = Schema.object(
    {
        "watch": Schema.boolean().default(True),
    }
)


class HmrService(Service):
    """Service view over the loader's file watcher."""

    inject = ["loader"]

    def __init__(self, ctx: Any, name: str = "meta/hmr") -> None:
        super().__init__(ctx, name)
        self.watch = True

    @property
    def loader(self) -> Any:
        return self.ctx.get("loader")

    @property
    def watching(self) -> bool:
        loader = self.loader
        thread = getattr(loader, "_thread", None)
        return bool(thread is not None and thread.is_alive())

    def start(self) -> Any:
        loader = self.loader
        if loader is not None and self.watch:
            loader.start_watching()
        self.ctx.root.on("loader/event", self._on_loader_event)
        return None

    def stop(self) -> None:
        loader = self.loader
        if loader is not None:
            loader.stop_watching()

    def _on_loader_event(self, payload: dict[str, Any]) -> None:
        self.ctx.root.emit("hmr/event", payload)

    def reload_all(self) -> dict[str, Any]:
        loader = self.loader
        if loader is None:
            return {"ok": False, "error": "no loader available"}
        self.ctx.spawn(loader.reload_all())
        return {"ok": True, "entries": len(loader.report())}

    def reload(self, entry_id: str) -> dict[str, Any]:
        loader = self.loader
        if loader is None:
            return {"ok": False, "error": "no loader available"}
        if loader.find(entry_id) is None:
            return {"ok": False, "error": f"unknown entry '{entry_id}'"}
        self.ctx.spawn(loader.reload_entry(entry_id))
        return {"ok": True, "entry": entry_id}


def apply(ctx: Any, config: dict[str, Any] | None = None) -> None:
    service = HmrService(ctx, "meta/hmr")
    if isinstance(config, dict) and config.get("watch") is not None:
        service.watch = bool(config["watch"])
    ctx.service("meta/hmr", service)
    if service.watch:
        service.start()
    ctx.effect(service.stop)

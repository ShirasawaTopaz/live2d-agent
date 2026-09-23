"""Application plugin tree: everything that used to be hard-wired bootstrap.

``create_plugin_context()`` builds the root cordis context and mounts the tree
described by ``cordis.yml``. The legacy entry points in
``internal.app.bootstrap`` and ``internal.app.live2d_agent_app`` call into this
module so the same wiring serves both the old and the new call sites.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from internal.cordis import Context, PluginLoader

logger = logging.getLogger(__name__)

__all__ = [
    "CONFIG_FILE",
    "PluginContext",
    "bootstrap_core",
    "create_loader",
    "create_plugin_context",
    "load_core_resources",
    "plugin_tree_path",
]

CONFIG_FILE = "cordis.yml"


def plugin_tree_path(path: str | Path | None = None) -> Path:
    """Resolve the plugin tree file (explicit path, repo root, then package)."""
    if path is not None:
        return Path(path).resolve()
    repo_root = Path(__file__).resolve().parents[2]
    candidate = repo_root / CONFIG_FILE
    if candidate.exists():
        return candidate
    return Path(__file__).resolve().parent / CONFIG_FILE


class PluginContext:
    """Root context plus the loader that owns the plugin tree."""

    def __init__(self, ctx: Context, loader: PluginLoader) -> None:
        self.ctx = ctx
        self.loader = loader

    @property
    def config(self) -> Any:
        from internal.config.config import Config

        value = self.ctx.get("config")
        if value is not None and getattr(value, "value", None) is not None:
            return value.value
        return Config()

    def get(self, name: str, default: Any = None) -> Any:
        return self.ctx.get(name, default)

    async def dispose(self) -> None:
        self.loader.stop_watching()
        await self.ctx.dispose()


def create_loader(ctx: Context, path: str | Path | None = None, *, watch: bool = True) -> PluginLoader:
    return PluginLoader(ctx, path=plugin_tree_path(path), auto_watch=watch)


async def create_plugin_context(
    path: str | Path | None = None,
    *,
    watch: bool = True,
) -> PluginContext:
    """Create the root context, mount the tree, then mount persisted user plugins."""
    ctx = Context(name="root")
    loader = create_loader(ctx, path, watch=watch)
    await loader.load()
    evolution = ctx.get("meta/self-evolution")
    if evolution is not None and getattr(evolution, "store", None) is None:
        try:
            evolution.ensure_store()
        except Exception:  # noqa: BLE001 - user plugins stay optional
            logger.warning("could not prepare the self-evolution store", exc_info=True)
    if loader._pending_entries:
        await loader.mount_overlay()
    return PluginContext(ctx, loader)


async def load_core_resources(ctx: Context, config_path: str | None = None) -> Any:
    """Load ``config.json`` and prompt modules through their services."""
    config_service = ctx.get("config")
    if config_service is None:
        raise RuntimeError("config service is missing from the plugin tree")
    config = await config_service.load(config_path)
    prompts = ctx.get("prompts")
    if prompts is not None:
        await prompts.load()
    ctx.emit("app/resources-loaded", config)
    return config


async def bootstrap_core(
    path: str | Path | None = None,
    config_path: str | None = None,
    *,
    watch: bool = True,
) -> PluginContext:
    """Mount the plugin tree and load config/prompts in the documented order."""
    context = await create_plugin_context(path, watch=watch)
    try:
        await load_core_resources(context.ctx, config_path)
    except Exception:
        await context.dispose()
        raise
    return context

"""A small pure-Python port of the cordis plugin kernel.

The kernel is intentionally independent from the rest of ``live2oder`` so it can
be unit tested on its own::

    from internal.cordis import Context, Service

    ctx = Context(name="root")
    await ctx.load(my_plugin)
    await ctx.dispose()

Concepts (mirroring cordis):

* ``Context`` – a node in the plugin tree; owns services, listeners, effects.
* ``Service`` – a plugin that exposes a named capability via ``ctx.service``.
* ``Fiber`` – the runtime handle of one loaded plugin instance, with a state
  machine ``PENDING → LOADING → ACTIVE → UNLOADING → DISPOSED`` (``FAILED`` on
  an ``apply`` error).
* ``inject`` – a live dependency list: a plugin stays ``PENDING`` until every
  listed service exists, unloads when one disappears, and reloads when it
  comes back.
* events – ``emit`` / ``parallel`` / ``serial`` / ``bail`` / ``waterfall``.
"""

from __future__ import annotations

from .context import Context, ContextOptions, service_stop_effect
from .errors import (
    ConfigError,
    CordisError,
    DisposedError,
    LoaderError,
    ServiceError,
    ValidationError,
)
from .events import EventManager
from .lifecycle import EffectScope, Fiber, FiberState, maybe_await
from .loader import LoaderEntry, PluginLoader, load_entries_from_file
from .logger import LoggerService
from .plugin import Service, is_plugin, plugin_name
from .registry import FiberReport, Registry
from .schema import Schema, validate_config
from .timer import TimerService

__all__ = [
    "Context",
    "ContextOptions",
    "ConfigError",
    "CordisError",
    "DisposedError",
    "EffectScope",
    "EventManager",
    "Fiber",
    "FiberReport",
    "FiberState",
    "LoaderEntry",
    "LoaderError",
    "LoggerService",
    "PluginLoader",
    "Registry",
    "Schema",
    "Service",
    "ServiceError",
    "TimerService",
    "ValidationError",
    "is_plugin",
    "load_entries_from_file",
    "maybe_await",
    "plugin_name",
    "service_stop_effect",
    "validate_config",
]

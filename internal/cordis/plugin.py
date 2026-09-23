"""Plugin shapes and the :class:`Service` base class."""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from .lifecycle import maybe_await
from .schema import Schema

__all__ = [
    "Service",
    "plugin_name",
    "is_plugin",
    "FabricatedRuntime",
    "normalize_plugin",
    "PluginRuntime",
]


def plugin_name(plugin: Any) -> str:
    """Best-effort display name for a plugin."""
    explicit = getattr(plugin, "plugin_name", None)
    if isinstance(explicit, str) and explicit:
        return explicit
    name = getattr(plugin, "name", None)
    if isinstance(name, str) and name:
        return name
    if inspect.isclass(plugin):
        return plugin.__name__
    if isinstance(plugin, Service):
        return type(plugin).__name__
    if callable(plugin):
        return getattr(plugin, "__qualname__", getattr(plugin, "__name__", repr(plugin)))
    return repr(plugin)


def _normalize_inject(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, Iterable):
        return [str(item) for item in raw]
    return [str(raw)]


def is_plugin(plugin: Any) -> bool:
    """Return True when ``plugin`` matches one of the supported shapes."""
    if plugin is None:
        return False
    if isinstance(plugin, Service):
        return True
    if inspect.ismodule(plugin):
        return callable(getattr(plugin, "apply", None))
    if inspect.isclass(plugin):
        return True
    if callable(plugin):
        return True
    return callable(getattr(plugin, "apply", None))


@dataclass(slots=True)
class PluginRuntime:
    """Normalised view over one of the three supported plugin shapes."""

    source: Any
    name: str
    inject: list[str] = field(default_factory=list)
    schema: Schema | None = None
    id: str | None = None
    kind: str = "function"
    function: Callable[..., Any] | None = None

    @property
    def display_name(self) -> str:
        return self.name

    def ensure_ready(self, ctx: Any, config: Any) -> None:
        """Prepare the runtime before its services are checked."""
        _ = ctx, config

    def apply(self, ctx: Any, config: Any) -> Any:
        if self.kind == "function":
            assert self.function is not None
            return _call_with_config(self.function, ctx, config)
        if self.kind == "object":
            method = getattr(self.source, "apply", None)
            if not callable(method):
                raise TypeError(f"plugin {self.name!r} has no apply method")
            return _call_with_config(method, ctx, config)
        if self.kind == "service":
            return self.source.apply(ctx, config)
        if self.kind == "service-object":
            self._register_service(ctx, self.source)
            return None
        if self.kind == "module":
            method = getattr(self.source, "apply", None)
            if not callable(method):
                raise TypeError(f"module plugin {self.name!r} has no apply function")
            return _call_with_config(method, ctx, config)
        raise TypeError(f"unsupported plugin kind {self.kind!r}")

    @staticmethod
    def _register_service(ctx: Any, service: Any) -> None:
        """Register a class-shaped service inside its own fiber scope.

        ``ctx.get`` walks the tree (ancestors first, then descendant fibers),
        so the service is reachable from ancestors, siblings, and descendants
        while its lifetime stays bound to the owning fiber.
        """
        ctx.service(service.name, service)
        start = getattr(service, "start", None)
        if callable(start):
            return start()
        return None


@dataclass(slots=True)
class FabricatedRuntime(PluginRuntime):
    """A class-shaped plugin that produces an instance when loaded."""

    cls: type = object
    accepts_config: bool = False
    instance: Any = None

    def ensure_ready(self, ctx: Any, config: Any) -> None:
        if self.instance is not None:
            return
        instance = _instantiate(self.cls, ctx, config if self.accepts_config else None)
        self.instance = instance
        self.source = instance

    @property
    def display_name(self) -> str:
        if self.instance is not None:
            return plugin_name(self.instance)
        return self.name

    def apply(self, ctx: Any, config: Any) -> Any:
        if self.instance is None:
            self.ensure_ready(ctx, config)
        instance = self.instance
        if self.kind == "service-class":
            self._register_service(ctx, instance)
            return None
        if isinstance(instance, Service):
            self._register_service(ctx, instance)
            return None
        method = getattr(instance, "apply", None)
        if callable(method):
            return _call_with_config(method, ctx, config)
        return None


def normalize_plugin(plugin: Any) -> PluginRuntime:
    """Turn any accepted plugin shape into a :class:`PluginRuntime`."""
    inject = _normalize_inject(getattr(plugin, "inject", None))
    schema = _resolve_schema(plugin)
    explicit_id = getattr(plugin, "id", None)

    if isinstance(plugin, Service):
        return PluginRuntime(
            source=plugin,
            name=plugin_name(plugin),
            inject=inject or _normalize_inject(getattr(plugin, "inject", None)),
            schema=schema,
            id=explicit_id,
            kind="service",
        )

    if inspect.ismodule(plugin):
        module_schema = _resolve_schema(plugin)
        return PluginRuntime(
            source=plugin,
            name=plugin_name(plugin),
            inject=_normalize_inject(getattr(plugin, "inject", None)) or inject,
            schema=module_schema if module_schema is not None else schema,
            id=explicit_id,
            kind="module",
        )

    if inspect.isclass(plugin):
        is_service = issubclass(plugin, Service)
        return FabricatedRuntime(
            source=plugin,
            name=plugin_name(plugin),
            inject=inject,
            schema=schema,
            id=explicit_id,
            kind="service-class" if is_service else "class",
            cls=plugin,
            accepts_config=False if is_service else _accepts_config(plugin),
        )

    if callable(plugin) and not callable(getattr(plugin, "apply", None)):
        return PluginRuntime(
            source=plugin,
            name=plugin_name(plugin),
            inject=inject,
            schema=schema,
            id=explicit_id,
            kind="function",
            function=plugin,
        )

    if callable(getattr(plugin, "apply", None)):
        return PluginRuntime(
            source=plugin,
            name=plugin_name(plugin),
            inject=inject,
            schema=schema,
            id=explicit_id,
            kind="object",
        )

    raise TypeError(f"unsupported plugin value: {plugin!r}")


def _resolve_schema(target: Any) -> Schema | None:
    """Read ``schema``/``module_schema``/``Config`` and normalise it."""
    schema = (
        getattr(target, "schema", None)
        or getattr(target, "module_schema", None)
        or getattr(target, "Config", None)
    )
    if isinstance(schema, type) and issubclass(schema, Schema):
        return schema()  # type: ignore[call-arg]
    if isinstance(schema, Schema):
        return schema
    return None


def _accepts_config(target: Any) -> bool:
    try:
        signature = inspect.signature(target.__init__ if inspect.isclass(target) else target)
    except (TypeError, ValueError):  # pragma: no cover - builtins
        return False
    parameters = signature.parameters
    if "config" in parameters:
        return True
    return any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )


def _instantiate(cls: type, ctx: Any, config: Any) -> Any:
    if config is None:
        return cls(ctx)
    try:
        return cls(ctx, config)
    except TypeError:
        return cls(ctx)


def _call_with_config(function: Callable[..., Any], ctx: Any, config: Any) -> Any:
    if _accepts_config(function):
        return function(ctx, config)
    return function(ctx)


class Service:
    """Base class for plugins that expose a named capability.

    Subclasses register themselves by calling ``super().__init__(ctx, name)``.
    An instance of :class:`Service` is itself a plugin, which is why
    ``ctx.plugin(MyService)`` works: the kernel instantiates it with a scoped
    context, registers the service, and unregisters it on unload.
    """

    inject: list[str] = []

    def __init__(self, ctx: Any, name: str) -> None:
        self.ctx = ctx
        self.name = name
        self.config = getattr(ctx, "config", None)

    async def apply(self, ctx: Any, config: Any) -> None:
        """Register the service and run the optional ``start`` hook."""
        ctx.service(self.name, self)
        self.config = config if config is not None else self.config
        method = getattr(self, "start", None)
        if callable(method):
            await maybe_await(method())

    def stop(self) -> Any:
        """Optional hook invoked before the service registration is removed."""
        return None

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"<{type(self).__name__} name={self.name!r}>"

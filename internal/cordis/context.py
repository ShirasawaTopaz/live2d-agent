"""The cordis :class:`Context` — services, events, effects, and plugins.

A context is a node in a tree. Services and event listeners live on the node
that declared them and are visible to descendants; a node is torn down when
its owner (a fiber or the application root) unloads.
"""

from __future__ import annotations

import asyncio
import inspect
import itertools
import logging
from collections.abc import Callable
from typing import Any, Iterable

from .errors import CordisError, DisposedError
from .events import EventManager, NextHandler, collect_scopes
from .lifecycle import EffectScope, Fiber, FiberState, maybe_await
from .plugin import is_plugin, normalize_plugin

__all__ = ["Context", "ContextOptions", "service_stop_effect"]

_logger = logging.getLogger("cordis")

_DRAIN_LIMIT = 64
_MISSING = object()
_order_counter = itertools.count()


def _next_order() -> int:
    return next(_order_counter)


class ContextOptions:
    """Construction options for a context node."""

    __slots__ = ("parent", "state", "name", "fiber", "isolate")

    def __init__(
        self,
        parent: "Context | None" = None,
        *,
        state: dict[str, Any] | None = None,
        name: str = "",
        fiber: Fiber | None = None,
        isolate: bool = False,
    ) -> None:
        self.parent = parent
        self.state = state if state is not None else (parent.store if parent is not None else {})
        self.name = name
        self.fiber = fiber
        self.isolate = isolate


class Context:
    """Runtime scope handed to every plugin's ``apply`` function."""

    def __init__(
        self,
        options: ContextOptions | None = None,
        *,
        parent: "Context | None" = None,
        config: Any = None,
        state: dict[str, Any] | None = None,
        name: str = "",
        fiber: Fiber | None = None,
        isolate: bool = False,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        if options is None:
            options = ContextOptions(parent, state=state, name=name, fiber=fiber, isolate=isolate)
        self.parent: Context | None = options.parent
        self._service_parent: Context | None = None if options.isolate else options.parent
        self.config = config if config is not None else getattr(options.parent, "config", None)
        self.store: dict[str, Any] = options.state
        self._name = options.name
        self._fiber: Fiber | None = options.fiber
        self._loop = loop if loop is not None else getattr(options.parent, "_loop", None)
        self._services: dict[str, Any] = {}
        self._service_disposers: list[Callable[[], Any]] = []
        self._event_handlers: dict[str, list[Callable[..., Any]]] = {}
        self._effect_scope = EffectScope()
        self._fibers: list[Fiber] = []
        self._pending: list[Fiber] = []
        self._order: int = _next_order()
        self._disposed = False
        self.events = EventManager(self)
        self.loader: Any = getattr(options.parent, "loader", None)

    # -------------------------------------------------------------- identity
    @property
    def name(self) -> str:
        if self._name:
            return self._name
        fiber = self._fiber
        return fiber.name if fiber is not None else "<root>"

    @property
    def fiber(self) -> Fiber | None:
        return self._fiber

    @property
    def root(self) -> "Context":
        node: Context = self
        while node.parent is not None:
            node = node.parent
        return node

    @property
    def disposed(self) -> bool:
        return self._disposed

    @property
    def effects(self) -> EffectScope:
        return self._effect_scope

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"<Context {self.name}>"

    def extend(
        self,
        *,
        config: Any = None,
        state: dict[str, Any] | None = None,
        name: str = "",
        fiber: Fiber | None = None,
        isolate: bool = False,
    ) -> "Context":
        """Create a child node inheriting services, store, and event chain."""
        self._assert_alive()
        return Context(
            parent=self,
            config=config,
            state=state,
            name=name,
            fiber=fiber,
            isolate=isolate,
        )

    def isolate(self) -> "Context":
        """Child node that stops inheriting services (events still bubble)."""
        return self.extend(isolate=True)

    def _assert_alive(self) -> None:
        if self._disposed:
            raise DisposedError(self)

    # -------------------------------------------------------------- services
    def get(self, name: str, default: Any = None) -> Any:
        """Resolve a service through the tree.

        Ancestors win, then the subtree of already-mounted fibers is searched so
        a consumer can see a service provided by a sibling that was mounted
        earlier. This mirrors cordis, where services flow through the plugin
        tree rather than a global registry.
        """
        node: Context | None = self
        while node is not None:
            if name in node._services:
                return node._services[name]
            node = node._service_parent
        found = _find_in_subtree(self.root, name)
        if found is not _MISSING:
            return found
        return default

    def has(self, name: str) -> bool:
        return self.get(name, _MISSING) is not _MISSING

    def require(self, name: str) -> Any:
        value = self.get(name, _MISSING)
        if value is _MISSING:
            raise CordisError(f"service '{name}' is not available")
        return value

    def list_services(self) -> list[str]:
        """Every service registered anywhere in the tree."""
        seen: dict[str, None] = {}
        for scope in collect_scopes(self.root):
            for key in scope._services:
                seen.setdefault(key, None)
        return list(seen)

    def service(self, name: str, value: Any = _MISSING) -> Any:
        """Register a service, or decorate a class/instance that provides one.

        ``ctx.service('greeter', instance)`` returns a disposer.
        ``@ctx.service('greeter')`` applied to a class or instance registers it
        when the decorated object is loaded.
        """
        self._assert_alive()
        if value is _MISSING:
            def decorator(target: Any) -> Any:
                if inspect.isclass(target):
                    def apply_service(instance: Any, ctx: Context, config: Any = None) -> Any:
                        _ = config
                        ctx.service(name, instance)
                        start = getattr(instance, "start", None)
                        if callable(start):
                            return start()
                        return None

                    namespace = {"inject": [name], "apply": apply_service}
                    return type(target.__name__, (target,), namespace)
                self.service(name, target)
                return target

            return decorator
        if value is None:
            raise CordisError(f"service '{name}' cannot be None")

        def disposer() -> None:
            if self._services.get(name) is value:
                self._services.pop(name, None)
            if disposer in self._service_disposers:
                self._service_disposers.remove(disposer)
            self._retry_pending()

        self._services[name] = value
        self._service_disposers.append(disposer)
        self._effect_scope.push(disposer)
        self._retry_pending()
        return disposer

    def unset(self, name: str) -> None:
        value = self._services.pop(name, _MISSING)
        if value is _MISSING:
            return
        for disposer in list(self._service_disposers):
            disposer()
        self._retry_pending()

    # ----------------------------------------------------------------- effects
    def effect(self, disposable: Any) -> Any:
        """Register an effect and return its disposer.

        The argument is either a callable that disposes the resource, or an
        object exposing ``dispose()``/``close()``. Cordis returns the disposer
        from the registration helper; this Python port takes it directly to
        avoid the "did it run?" ambiguity of the callback form.
        """
        self._assert_alive()
        if disposable is None:
            return None
        if inspect.iscoroutine(disposable):
            raise CordisError(
                "ctx.effect() expects a disposer; use ctx.spawn() to run a coroutine"
            )
        if callable(disposable):
            disposer = disposable
        else:
            disposer = getattr(disposable, "dispose", None) or getattr(disposable, "close", None)
            if not callable(disposer):
                raise CordisError(f"object {disposable!r} cannot be used as an effect")
        self._effect_scope.push(disposer)
        return disposer

    def spawn(self, coroutine: Any) -> asyncio.Task[Any]:
        """Run a coroutine on the kernel loop, cancelling it on unload."""
        self._assert_alive()
        loop = self._resolve_loop()
        if loop is None:
            raise CordisError("no running event loop; cannot spawn")
        task = loop.create_task(coroutine)
        self._effect_scope.push(lambda: task.cancel())
        return task

    def _resolve_loop(self) -> asyncio.AbstractEventLoop | None:
        loop = self._loop
        if loop is not None and not loop.is_closed():
            return loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return None
        self._loop = loop
        return loop

    # ------------------------------------------------------------------ events
    def on(self, name: str, listener: Callable[..., Any] | None = None) -> Any:
        """Subscribe to an event.

        The handler is stored on the context you call this on (so descendants
        that emit the event can reach it), while the subscription is owned by
        the calling context as an effect: unloading the calling plugin removes
        the listener, even when it was registered on ``ctx.root``.
        """
        self._assert_alive()
        if listener is None:
            def decorator(target: Callable[..., Any]) -> Callable[..., Any]:
                self.on(name, target)
                return target

            return decorator
        return _register_listener(self, name, listener)

    def on_root(self, name: str, listener: Callable[..., Any] | None = None) -> Any:
        """Alias of :meth:`on` kept for readability at call sites."""
        return self.on(name, listener)

    def off(self, name: str, listener: Callable[..., Any]) -> None:
        node: Context | None = self
        while node is not None:
            registered = node._event_handlers.get(name)
            if registered and listener in registered:
                registered.remove(listener)
                if not registered:
                    node._event_handlers.pop(name, None)
                return
            node = node._service_parent or node.parent

    def emit(self, name: str, *args: Any) -> None:
        self.events.emit(name, *args)

    async def parallel(self, name: str, *args: Any) -> list[Any]:
        return await self.events.parallel(name, *args)

    async def serial(self, name: str, *args: Any) -> Any:
        return await self.events.serial(name, *args)

    def bail(self, name: str, *args: Any) -> Any:
        return self.events.bail(name, *args)

    async def bail_async(self, name: str, *args: Any) -> Any:
        return await self.events.bail_async(name, *args)

    async def waterfall(self, name: str, *args: Any, next: NextHandler | None = None) -> Any:
        return await self.events.waterfall(name, *args, next=next)

    def listeners(self, name: str) -> list[Callable[..., Any]]:
        return self.events.listeners(name)

    # ----------------------------------------------------------------- plugins
    def plugin(
        self,
        plugin: Any,
        config: Any = None,
        *,
        name: str | None = None,
        id: str | None = None,
        inject: Iterable[str] | None = None,
    ) -> Fiber:
        """Mount a plugin as a child fiber."""
        self._assert_alive()
        if not is_plugin(plugin):
            raise TypeError(f"{plugin!r} is not a plugin")
        runtime = normalize_plugin(plugin)
        if name is not None:
            runtime.name = name
        if id is not None:
            runtime.id = id
        if inject is not None:
            runtime.inject = [str(item) for item in inject]

        scope = self.extend(name=runtime.name)
        fiber = Fiber(scope, runtime, config)
        scope._fiber = fiber
        self._fibers.append(fiber)
        self._pending.append(fiber)
        fiber.start()
        return fiber

    def mount(self, plugin: Any, config: Any = None, **options: Any) -> Fiber:
        """Alias of :meth:`plugin` used by loader code for readability."""
        return self.plugin(plugin, config, **options)

    def unload(self, fiber: Fiber) -> None:
        if fiber in self._fibers:
            self._fibers.remove(fiber)
        if fiber in self._pending:
            self._pending.remove(fiber)
        scope = fiber.context
        if scope is not None and scope.parent is self:
            scope.parent = None
            scope._service_parent = None

    async def load(self, plugin: Any, config: Any = None, **options: Any) -> Fiber:
        """Mount a plugin and wait until its ``apply`` finished."""
        fiber = self.plugin(plugin, config, **options)
        await fiber.wait_ready()
        return fiber

    async def start(self) -> None:
        """Load every pending fiber whose dependencies are satisfied."""
        await self._drain_pending()

    async def _drain_pending(self) -> None:
        for _ in range(_DRAIN_LIMIT):
            ready = [
                fiber
                for fiber in list(self._pending)
                if all(self.get(service) is not None for service in fiber.inject)
            ]
            if not ready:
                return
            for fiber in ready:
                if fiber.state is FiberState.PENDING:
                    fiber.start()
            await asyncio.sleep(0)

    def list_fibers(self) -> list[Fiber]:
        """Every fiber mounted anywhere in this context's subtree."""
        return _collect_fibers(self)

    def _retry_pending(self) -> None:
        for fiber in list(self._pending):
            if fiber.state is not FiberState.PENDING:
                continue
            if not all(self.get(service) is not None for service in fiber.inject):
                continue
            loop = self._resolve_loop()
            if loop is not None and loop.is_running():
                fiber.start()

    # ---------------------------------------------------------------- teardown
    async def dispose(self) -> None:
        """Unload every fiber, then undo services, listeners, and effects."""
        if self._disposed:
            return
        self._disposed = True
        for fiber in list(self._fibers):
            await fiber.dispose()
        self._fibers.clear()
        self._pending.clear()
        await self._teardown()

    async def _teardown(self) -> None:
        self._event_handlers = {}
        disposers = self._effect_scope.unwrap()
        services = dict(self._services)
        self._services.clear()
        for value in services.values():
            stop = getattr(value, "stop", None)
            if callable(stop):
                try:
                    await maybe_await(stop())
                except Exception:  # noqa: BLE001 - teardown must continue
                    _logger.exception("service '%r' stop hook failed", value)
        self._service_disposers.clear()
        from .lifecycle import run_disposers

        await run_disposers(disposers)

    def stop(self) -> asyncio.Task[Any] | None:
        """Schedule disposal on the kernel loop."""
        loop = self._resolve_loop()
        if loop is None or not loop.is_running():
            return None
        return loop.create_task(self.dispose())


def service_stop_effect(instance: Any) -> Callable[[], Any] | None:
    """Return an effect that calls ``instance.stop()`` when it unloads."""
    stop = getattr(instance, "stop", None)
    if not callable(stop):
        return None

    def stop_effect() -> Any:
        return stop()

    return stop_effect


def _register_listener(
    context: "Context",
    name: str,
    listener: Callable[..., Any],
) -> Callable[[], None]:
    """Store a handler on its own context and own the subscription as an effect."""
    handlers = context._event_handlers.setdefault(name, [])
    handlers.append(listener)

    def disposer() -> None:
        registered = context._event_handlers.get(name)
        if not registered:
            return
        if listener in registered:
            registered.remove(listener)
        if not registered:
            context._event_handlers.pop(name, None)

    context._effect_scope.push(disposer)
    return disposer


def _find_in_subtree(node: "Context", name: str, _seen: set[int] | None = None) -> Any:
    seen = _seen if _seen is not None else set()
    if id(node) in seen:
        return _MISSING
    seen.add(id(node))
    for fiber in list(node._fibers):
        scope = fiber.context
        if scope is None or id(scope) in seen:
            continue
        if name in scope._services:
            return scope._services[name]
        seen.add(id(scope))
        nested = _find_in_subtree(scope, name, seen)
        if nested is not _MISSING:
            return nested
    return _MISSING


def _collect_fibers(node: "Context", _seen: set[int] | None = None) -> list[Fiber]:
    seen = _seen if _seen is not None else set()
    if id(node) in seen:
        return []
    seen.add(id(node))
    found: list[Fiber] = []
    for fiber in list(node._fibers):
        found.append(fiber)
        if fiber.context is not None:
            found.extend(_collect_fibers(fiber.context, seen))
    return found

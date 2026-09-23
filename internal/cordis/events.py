"""Event dispatch: emit, parallel, serial, bail, and waterfall.

Listener resolution walks the context chain from the root down to the
innermost scope, so a listener registered on an ancestor sees events emitted
by descendants. Listeners registered with ``ctx.on`` are automatically removed
when their context unloads.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any, Callable, Iterable

__all__ = ["EventManager", "Listener", "NextHandler", "collect_scopes"]

_logger = logging.getLogger("cordis")

Listener = Callable[..., Any]
NextHandler = Callable[[], Any]


class EventManager:
    """Event API attached to every :class:`~internal.cordis.context.Context`."""

    def __init__(self, context: Any) -> None:
        self.context = context

    # ------------------------------------------------------------------ plan
    def listeners(self, name: str) -> list[Listener]:
        """Return listeners for ``name``, ancestors first, then descendants.

        The scope chain is walked from the root down to the emitting context,
        then the emitting context's subtree is appended, and everything is
        ordered by scope creation time. An ancestor's listener therefore always
        runs before a descendant's, which is what waterfall middleware ordering
        requires. ``Context.on`` owns every subscription as an effect of the
        subscribing context, so unloading removes it wherever it lives.
        """
        scopes: list[Any] = []
        chain: list[Any] = []
        node: Any = self.context
        while node is not None:
            chain.append(node)
            node = getattr(node, "parent", None)
        visible: set[int] = set()
        for scope in reversed(chain):
            visible.add(id(scope))
            scopes.append(scope)
            _collect_scopes(scope, scopes, visible)
        scopes.sort(key=lambda scope: getattr(scope, "_order", 0))
        ordered: list[Listener] = []
        for scope in scopes:
            handlers = getattr(scope, "_event_handlers", None)
            if handlers:
                ordered.extend(handlers.get(name, ()))
        return ordered

    def has_listeners(self, name: str) -> bool:
        return bool(self.listeners(name))

    # ------------------------------------------------------------ dispatching
    def emit(self, name: str, *args: Any) -> None:
        """Synchronous broadcast; return values and awaitables are ignored."""
        for listener in self.listeners(name):
            try:
                result = listener(*args)
            except Exception:  # noqa: BLE001 - a broken listener must not kill the app
                _logger.exception("listener for '%s' failed", name)
                continue
            if inspect.isawaitable(result):
                _close_orphan_awaitable(result, name)

    async def parallel(self, name: str, *args: Any) -> list[Any]:
        """Run every listener concurrently and collect their results."""
        pending: list[Any] = []
        for listener in self.listeners(name):
            try:
                result = listener(*args)
            except Exception:  # noqa: BLE001
                _logger.exception("listener for '%s' failed", name)
                continue
            pending.append(result)
        results: list[Any] = []
        for result in pending:
            if inspect.isawaitable(result):
                try:
                    results.append(await result)
                except Exception:  # noqa: BLE001
                    _logger.exception("async listener for '%s' failed", name)
            else:
                results.append(result)
        return results

    async def serial(self, name: str, *args: Any) -> Any:
        """Run listeners in order until one returns a meaningful value."""
        for listener in self.listeners(name):
            result = listener(*args)
            if inspect.isawaitable(result):
                result = await result
            if _meaningful(result):
                return result
        return None

    def bail(self, name: str, *args: Any) -> Any:
        """Synchronous ``serial``: first meaningful return value wins."""
        for listener in self.listeners(name):
            result = listener(*args)
            if inspect.isawaitable(result):
                _close_orphan_awaitable(result, name)
                continue
            if _meaningful(result):
                return result
        return None

    async def bail_async(self, name: str, *args: Any) -> Any:
        """``bail`` that also awaits async listeners."""
        return await self.serial(name, *args)

    async def waterfall(self, name: str, *args: Any, next: NextHandler | None = None) -> Any:
        """Middleware-style dispatch where each listener may call ``next()``.

        A listener that returns without calling ``next()`` vetoes the rest of
        the chain, including the default handler.
        """
        default: NextHandler = next if next is not None else (lambda: None)
        listeners = self.listeners(name)

        async def invoke(index: int) -> Any:
            if index >= len(listeners):
                return await _maybe_await(default())
            listener = listeners[index]

            async def step() -> Any:
                return await invoke(index + 1)

            result = listener(*args, step)
            return await _maybe_await(result)

        return await invoke(0)


def collect_scopes(node: Any, found: list[Any] | None = None, seen: set[int] | None = None) -> list[Any]:
    """Every context node in ``node``'s subtree, depth first."""
    result = found if found is not None else []
    marks = seen if seen is not None else set()
    if id(node) in marks:
        return result
    marks.add(id(node))
    result.append(node)
    for fiber in list(getattr(node, "_fibers", ()) or ()):
        scope = fiber.context
        if scope is not None:
            collect_scopes(scope, result, marks)
    return result


def _collect_scopes(node: Any, found: list[Any], seen: set[int] | None = None) -> list[Any]:
    marks = seen if seen is not None else set()
    for fiber in list(getattr(node, "_fibers", ()) or ()):
        scope = fiber.context
        if scope is None or id(scope) in marks:
            continue
        marks.add(id(scope))
        found.append(scope)
        _collect_scopes(scope, found, marks)
    return found


def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return value

    async def _wrap() -> Any:
        return value

    return _wrap()


def _meaningful(value: Any) -> bool:
    return value is not None and value is not False


def _close_orphan_awaitable(value: Any, name: str) -> None:
    """Awaitables returned from sync dispatch cannot be awaited here."""
    close = getattr(value, "close", None)
    if callable(close):
        close()
    _logger.debug("ignored awaitable returned by listener for '%s'", name)


def describe_listeners(listeners: Iterable[Listener]) -> list[str]:
    return [getattr(listener, "__qualname__", repr(listener)) for listener in listeners]

"""Lifecycle primitives: effect scopes, fibers, and their state machine.

Naming follows the cordis vocabulary used by DeepSeek Harness:

* **effect** – a registration that is undone when its owner unloads.
* **fiber** – the runtime handle of one loaded plugin instance.
* **dispose** – teardown of a fiber, its effects, children, and services.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from enum import Enum
from typing import Any, Callable, Iterable

from .errors import CordisError

__all__ = [
    "FiberState",
    "Disposable",
    "Disposer",
    "EffectScope",
    "Fiber",
    "maybe_await",
    "is_awaitable",
]

_logger = logging.getLogger("cordis")


class FiberState(Enum):
    """Lifecycle states of a loaded plugin instance."""

    PENDING = "pending"
    LOADING = "loading"
    ACTIVE = "active"
    UNLOADING = "unloading"
    DISPOSED = "disposed"
    FAILED = "failed"

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return self.value


Disposable = Callable[[], Any] | Any
Disposer = Callable[[], Any]


def is_awaitable(value: Any) -> bool:
    return inspect.isawaitable(value)


async def maybe_await(value: Any) -> Any:
    """Await ``value`` when it is awaitable, otherwise return it unchanged."""
    if inspect.isawaitable(value):
        return await value
    return value


class EffectScope:
    """Collects disposers and unwinds them in reverse registration order."""

    __slots__ = ("_disposers", "_disposed")

    def __init__(self) -> None:
        self._disposers: list[Disposer] = []
        self._disposed = False

    @property
    def disposed(self) -> bool:
        return self._disposed

    @property
    def size(self) -> int:
        return len(self._disposers)

    @property
    def disposers(self) -> tuple[Disposer, ...]:
        return tuple(self._disposers)

    def push(self, disposable: Disposable) -> None:
        """Register a disposer or a disposable object."""
        if self._disposed:
            raise CordisError("effect scope is already disposed")
        disposer = self._as_disposer(disposable)
        if disposer is None:
            return
        self._disposers.append(disposer)

    def discard(self, disposable: Disposable) -> None:
        disposer = self._as_disposer(disposable)
        if disposer is not None and disposer in self._disposers:
            self._disposers.remove(disposer)

    @staticmethod
    def _as_disposer(disposable: Disposable) -> Disposer | None:
        if disposable is None:
            return None
        if callable(disposable):
            return disposable
        dispose = getattr(disposable, "dispose", None)
        if callable(dispose):
            return dispose
        close = getattr(disposable, "close", None)
        if callable(close):
            return close
        raise CordisError(f"object {disposable!r} cannot be used as an effect")

    def unwrap(self) -> list[Disposer]:
        """Take every disposer, leaving the scope unusable."""
        disposers = list(self._disposers)
        self._disposers.clear()
        self._disposed = True
        return disposers

    async def dispose(self) -> None:
        """Run every disposer in reverse order.

        Async disposers are started in reverse order and then awaited
        concurrently, matching cordis semantics.
        """
        if self._disposed:
            return
        disposers = self.unwrap()
        await run_disposers(disposers)


async def run_disposers(disposers: Iterable[Disposer]) -> None:
    """Run disposers in reverse registration order."""
    pending: list[Any] = []
    for disposer in reversed(list(disposers)):
        try:
            result = disposer()
        except Exception:  # noqa: BLE001 - teardown must not abort siblings
            _logger.exception("effect disposer failed")
            continue
        if inspect.isawaitable(result):
            pending.append(result)
    for result in pending:
        try:
            await result
        except Exception:  # noqa: BLE001 - teardown must not abort siblings
            _logger.exception("async effect disposer failed")


class Fiber:
    """Runtime handle for one loaded plugin instance."""

    def __init__(self, context: Any, runtime: Any, config: Any = None) -> None:
        self.context = context
        self.runtime = runtime
        self.config = config
        self.state = FiberState.PENDING
        self.task: asyncio.Task[Any] | None = None
        self.disposables: list[Disposable] = []
        self.children: list["Fiber"] = []
        self.error: BaseException | None = None
        self._ready: asyncio.Future[None] | None = None
        self._id = id(self)

    # --------------------------------------------------------------- naming
    @property
    def name(self) -> str:
        display = getattr(self.runtime, "display_name", None)
        if display:
            return str(display)
        return str(getattr(self.runtime, "name", repr(self.runtime)))

    @property
    def id(self) -> str:
        value = getattr(self.runtime, "id", None) or getattr(self.runtime, "name", "")
        return str(value)

    @property
    def inject(self) -> list[str]:
        return list(getattr(self.runtime, "inject", ()) or ())

    @property
    def parent(self) -> "Fiber | None":
        node = getattr(self.context, "parent", None)
        return getattr(node, "_fiber", None) if node is not None else None

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"<Fiber {self.name} {self.state}>"

    # -------------------------------------------------------------- lifecycle
    def ready(self, loop: asyncio.AbstractEventLoop | None = None) -> asyncio.Future[None]:
        """Stable future resolved once the fiber reaches a terminal state."""
        _ = loop
        if self._ready is None:
            self._ready = asyncio.Future()
        return self._ready

    async def wait_ready(self) -> None:
        """Wait until ``apply`` finished, then raise if it failed."""
        await _wait_for_ready(self)
        if self.state is FiberState.FAILED:
            if self.error is not None:
                raise CordisError(
                    f"plugin '{self.name}' failed to load: {self.error}"
                ) from self.error
            raise CordisError(f"plugin '{self.name}' failed to load")

    def start(self) -> asyncio.Task[Any] | None:
        """Schedule loading. Returns the task when an event loop is running."""
        if self.state is not FiberState.PENDING:
            return self.task
        self.state = FiberState.LOADING
        loop = _get_loop(self.context)
        if loop is None or not loop.is_running():
            self.state = FiberState.PENDING
            return None
        self.task = loop.create_task(self._load(), name=f"cordis:{self.name}")
        return self.task

    async def _load(self) -> None:
        runtime = self.runtime
        context = self.context
        try:
            missing = [name for name in self.inject if context.get(name) is None]
            if missing:
                self.state = FiberState.PENDING
                return
            if runtime.schema is not None:
                from .schema import validate_config

                self.config = validate_config(runtime.schema, self.config)
            runtime.ensure_ready(context, self.config)
            await maybe_await(runtime.apply(context, self.config))
            instance = getattr(runtime, "instance", None)
            if instance is not None:
                from .context import service_stop_effect

                stop_effect = service_stop_effect(instance)
                if stop_effect is not None:
                    context.effect(stop_effect)
            self.state = FiberState.ACTIVE
            self._resolve_ready()
        except asyncio.CancelledError:
            self.state = FiberState.DISPOSED
            self._resolve_ready()
            raise
        except Exception as exc:  # noqa: BLE001 - surface as FAILED
            self.state = FiberState.FAILED
            _logger.error("plugin '%s' failed to load: %s", self.name, exc)
            self._resolve_ready(exc)
            await self._teardown()
            raise

    def _resolve_ready(self, error: BaseException | None = None) -> None:
        if error is not None:
            self.error = error
        ready = self._ready
        if ready is None:
            ready = asyncio.Future()
            self._ready = ready
        if ready.done():
            return
        ready.set_result(None)

    async def dispose(self) -> None:
        """Fully unload this plugin: children first, then own effects."""
        if self.state in (FiberState.DISPOSED, FiberState.FAILED):
            return
        self.state = FiberState.UNLOADING
        task = self.task
        if task is not None and not task.done():
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        await self._teardown()
        self.state = FiberState.DISPOSED
        self._resolve_ready()
        for disposable in self.disposables:
            await _dispose_value(disposable)
        self.disposables.clear()

    async def _teardown(self) -> None:
        for child in list(self.children):
            await child.dispose()
        self.children.clear()
        context = self.context
        parent = getattr(context, "parent", None)
        if parent is not None and self in getattr(parent, "_fibers", []):
            parent._fibers.remove(self)
        await context.dispose()

    def append(self, disposable: Disposable) -> None:
        self.disposables.append(disposable)


async def _dispose_value(disposable: Any) -> None:
    if disposable is None:
        return
    dispose = getattr(disposable, "dispose", None)
    if callable(dispose):
        await maybe_await(dispose())
        return
    if callable(disposable):
        await maybe_await(disposable())


async def _wait_for_ready(fiber: Fiber) -> None:
    ready = fiber._ready
    if ready is not None and not ready.done():
        try:
            await ready
        except Exception:  # noqa: BLE001 - surfacing happens in the caller
            return
        return
    task = fiber.task
    if task is not None and not task.done():
        try:
            await asyncio.shield(task)
        except Exception:  # noqa: BLE001 - surfacing happens in the caller
            pass


def _get_loop(context: Any) -> asyncio.AbstractEventLoop | None:
    loop = getattr(context, "_loop", None)
    if loop is not None and not loop.is_closed():
        return loop
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None

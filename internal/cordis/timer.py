"""Timer service, mirroring ``@deepseek-ai/cordis-plugin-timer``."""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from .plugin import Service

__all__ = ["TimerService", "apply"]


class TimerService(Service):
    """Provides ``ctx.timer``: ``timeout``, ``interval``, and ``sleep``.

    Every scheduled callback is registered as an effect, so timers are
    cancelled automatically when the owning plugin unloads.
    """

    def __init__(self, ctx: Any, name: str = "timer") -> None:
        super().__init__(ctx, name)

    def timeout(self, callback: Callable[[], Any], delay: float = 0.0) -> Callable[[], None]:
        handle: list[asyncio.Task[Any]] = []

        async def runner() -> None:
            await asyncio.sleep(max(0.0, delay))
            result = callback()
            if asyncio.iscoroutine(result):
                await result

        loop = self.ctx._resolve_loop()
        if loop is None:
            raise RuntimeError("timer service requires a running event loop")
        task = loop.create_task(runner())
        handle.append(task)

        def cancel() -> None:
            for item in handle:
                if not item.done():
                    item.cancel()
            handle.clear()

        return cancel

    def interval(self, callback: Callable[[], Any], delay: float) -> Callable[[], None]:
        stopped = False

        async def runner() -> None:
            while not stopped:
                await asyncio.sleep(max(0.0, delay))
                if stopped:
                    return
                result = callback()
                if asyncio.iscoroutine(result):
                    await result

        loop = self.ctx._resolve_loop()
        if loop is None:
            raise RuntimeError("timer service requires a running event loop")
        task = loop.create_task(runner())

        def cancel() -> None:
            nonlocal stopped
            stopped = True
            if not task.done():
                task.cancel()

        return cancel

    async def sleep(self, delay: float) -> None:
        await asyncio.sleep(max(0.0, delay))


def apply(ctx: Any, config: Any = None) -> None:
    """Function-shaped entry point for the ``core/timer`` plugin slot."""
    _ = config
    service = TimerService(ctx, "timer")
    ctx.service("timer", service)

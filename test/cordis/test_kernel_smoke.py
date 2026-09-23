"""Smoke checks for the pure-Python cordis kernel."""

from __future__ import annotations

import asyncio
from typing import Any

from internal.cordis import Context, FiberState, Service


async def test_context_mounts_function_plugin() -> None:
    ctx = Context(name="root")
    calls: list[str] = []

    def plugin(context, config=None):
        calls.append("apply")
        context.effect(lambda: calls.append("dispose"))

    fiber = await ctx.load(plugin)
    assert fiber.state is FiberState.ACTIVE
    assert calls == ["apply"]

    await ctx.dispose()
    assert calls == ["apply", "dispose"]


async def test_service_plugin_is_registered_and_removed() -> None:
    ctx = Context(name="root")

    class Greeter(Service):
        def __init__(self, context: Context) -> None:
            super().__init__(context, "greeter")
            self.stopped = False

        def greet(self, who: str) -> str:
            return f"hello {who}"

        def stop(self) -> None:
            self.stopped = True

    fiber = await ctx.load(Greeter)
    assert ctx.get("greeter") is not None
    assert ctx.get("greeter").greet("world") == "hello world"
    greeter = ctx.get("greeter")

    await fiber.dispose()
    assert ctx.get("greeter") is None
    assert fiber.state is FiberState.DISPOSED
    assert greeter.stopped is True


async def test_inject_keeps_fiber_pending_until_service_arrives() -> None:
    ctx = Context(name="root")
    loaded: list[str] = []

    def consumer(context, config=None):
        loaded.append("loaded")

    consumer.inject = ["timer"]  # type: ignore[attr-defined]

    fiber = ctx.plugin(consumer)
    await asyncio.sleep(0)
    assert fiber.state is FiberState.PENDING
    assert loaded == []

    ctx.service("timer", object())
    await ctx.start()
    assert fiber.state is FiberState.ACTIVE
    assert loaded == ["loaded"]

    ctx.unset("timer")
    await asyncio.sleep(0)
    assert ctx.get("timer") is None


async def test_waterfall_short_circuit() -> None:
    from internal.cordis import Context as Ctx

    ctx = Ctx(name="root")
    seen: dict[str, Any] = {}

    def plugin(context):
        # Listener 1 (outermost): upper-cases whatever the downstream chain returns.
        async def wrapper(value, next):
            return (await next()).upper()

        context.on("demo", wrapper)
        # Listener 2 (innermost): vetoes "blocked" without calling next().
        context.on(
            "demo",
            lambda value, next: "** blocked **" if value == "blocked" else next(),
        )
        seen["scope"] = context

    await ctx.load(plugin)
    scope = seen["scope"]

    assert await scope.waterfall("demo", "hello", next=lambda: "hello") == "HELLO"
    assert await scope.waterfall("demo", "blocked", next=lambda: "blocked") == "** BLOCKED **"
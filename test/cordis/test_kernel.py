"""Effect, service, event, schema, and fiber semantics."""

from __future__ import annotations

import asyncio

import pytest

from internal.cordis import (
    Context,
    FiberState,
    Schema,
    Service,
    ValidationError,
    validate_config,
)


# --------------------------------------------------------------------- effects
async def test_effects_unwind_in_reverse_order() -> None:
    ctx = Context(name="root")
    order: list[str] = []

    def plugin(context, config=None):
        context.effect(lambda: order.append("first"))
        context.effect(lambda: order.append("second"))

    fiber = await ctx.load(plugin)
    await fiber.dispose()

    assert order == ["second", "first"]


async def test_async_disposers_are_awaited() -> None:
    ctx = Context(name="root")
    done: list[str] = []

    def plugin(context, config=None):
        async def disposer() -> None:
            await asyncio.sleep(0)
            done.append("async")

        context.effect(disposer)

    fiber = await ctx.load(plugin)
    await fiber.dispose()

    assert done == ["async"]


async def test_effect_rejects_non_disposables() -> None:
    ctx = Context(name="root")

    with pytest.raises(Exception):
        ctx.effect(object())

    def _make_coroutine():
        async def body():
            return None

        return body()

    def plugin(context, config=None):
        coroutine = _make_coroutine()
        with pytest.raises(Exception):
            context.effect(coroutine)
        coroutine.close()

    fiber = await ctx.load(plugin)
    assert fiber.state is FiberState.ACTIVE


async def test_spawn_is_cancelled_on_unload() -> None:
    ctx = Context(name="root")
    cancelled = asyncio.Event()

    def plugin(context, config=None):
        async def worker() -> None:
            try:
                await asyncio.sleep(30)
            finally:
                cancelled.set()

        context.spawn(worker())

    fiber = await ctx.load(plugin)
    await fiber.dispose()
    await asyncio.sleep(0.05)

    assert cancelled.is_set()


# -------------------------------------------------------------------- services
async def test_service_is_visible_to_descendant_plugins() -> None:
    ctx = Context(name="root")

    class Timer(Service):
        def __init__(self, context):
            super().__init__(context, "timer")

    waited: list[str] = []

    def consumer(context, config=None):
        assert context.get("timer") is not None
        waited.append("ok")

    consumer.inject = ["timer"]  # type: ignore[attr-defined]

    await ctx.load(Timer)
    fiber = ctx.plugin(consumer)
    await asyncio.sleep(0)
    await ctx.start()

    assert fiber.state is FiberState.ACTIVE
    assert waited == ["ok"]


async def test_dependency_disappearance_unloads_consumer() -> None:
    ctx = Context(name="root")
    states: list[str] = []

    class Timer(Service):
        def __init__(self, context):
            super().__init__(context, "timer")

    def consumer(context, config=None):
        states.append("loaded")

    consumer.inject = ["timer"]  # type: ignore[attr-defined]

    timer_fiber = await ctx.load(Timer)
    consumer_fiber = ctx.plugin(consumer)
    await asyncio.sleep(0)
    await ctx.start()
    assert consumer_fiber.state is FiberState.ACTIVE

    await timer_fiber.dispose()
    await asyncio.sleep(0)

    assert ctx.get("timer") is None
    assert states == ["loaded"]


async def test_unset_service_is_idempotent() -> None:
    ctx = Context(name="root")
    ctx.service("x", 1)
    ctx.unset("x")
    ctx.unset("x")
    assert ctx.get("x") is None


async def test_service_rejects_none() -> None:
    ctx = Context(name="root")
    with pytest.raises(Exception):
        ctx.service("bad", None)


async def test_disposed_context_rejects_registration() -> None:
    ctx = Context(name="root")
    await ctx.dispose()
    with pytest.raises(Exception):
        ctx.service("late", 1)


# ---------------------------------------------------------------------- events
async def test_emit_broadcasts_to_ancestors() -> None:
    ctx = Context(name="root")
    seen: list[str] = []

    def plugin(context, config=None):
        context.root.on("tick", lambda value: seen.append(value))

    await ctx.load(plugin)

    assert ctx.listeners("tick")
    ctx.emit("tick", "a")
    ctx.emit("tick", "b")

    assert seen == ["a", "b"]


async def test_emit_survives_listener_failure() -> None:
    ctx = Context(name="root")
    seen: list[str] = []

    def plugin(context, config=None):
        context.root.on("boom", lambda: (_ for _ in ()).throw(RuntimeError("bad")))
        context.root.on("boom", lambda: seen.append("second"))

    await ctx.load(plugin)
    ctx.emit("boom")

    assert seen == ["second"]


async def test_serial_returns_first_meaningful_value() -> None:
    ctx = Context(name="root")

    def plugin(context, config=None):
        context.root.on("pick", lambda: None)
        context.root.on("pick", lambda: "first")
        context.root.on("pick", lambda: "second")

    await ctx.load(plugin)

    assert await ctx.serial("pick") == "first"
    assert ctx.bail("pick") == "first"


async def test_parallel_awaits_every_listener() -> None:
    ctx = Context(name="root")
    seen: list[str] = []

    def plugin(context, config=None):
        async def slow() -> str:
            await asyncio.sleep(0.01)
            seen.append("slow")
            return "slow"

        async def fast() -> str:
            seen.append("fast")
            return "fast"

        context.root.on("work", slow)
        context.root.on("work", fast)

    await ctx.load(plugin)
    results = await ctx.parallel("work")

    assert results == ["slow", "fast"]
    assert set(seen) == {"slow", "fast"}


async def test_listeners_are_removed_when_plugin_unloads() -> None:
    ctx = Context(name="root")

    def plugin(context, config=None):
        context.on("ping", lambda: None)

    fiber = await ctx.load(plugin)
    assert ctx.listeners("ping")

    await fiber.dispose()

    assert ctx.listeners("ping") == []


async def test_waterfall_default_runs_without_listeners() -> None:
    ctx = Context(name="root")
    assert await ctx.waterfall("nothing", next=lambda: 42) == 42


# ---------------------------------------------------------------------- schema
def test_schema_applies_defaults_and_rejects_unknown_keys() -> None:
    schema = Schema.object(
        {
            "enabled": Schema.boolean().default(True),
            "mode": Schema.union(["local", "remote"]).default("local"),
            "port": Schema.natural().min(1).max(65535),
        }
    )

    assert validate_config(schema, {"port": 9}) == {"enabled": True, "mode": "local", "port": 9}

    with pytest.raises(ValidationError):
        validate_config(schema, {"port": 0, "nope": 1})


def test_schema_required_and_types() -> None:
    schema = Schema.object({"name": Schema.string().required(), "tags": Schema.array(Schema.string())})

    assert validate_config(schema, {"name": "n", "tags": ["a"]}) == {"name": "n", "tags": ["a"]}
    with pytest.raises(ValidationError):
        validate_config(schema, {})
    with pytest.raises(ValidationError):
        validate_config(schema, {"name": 3})


async def test_plugin_config_is_validated_on_load() -> None:
    ctx = Context(name="root")

    def plugin(context, config=None):
        _ = config

    plugin.schema = Schema.object({"size": Schema.integer().default(3)})  # type: ignore[attr-defined]

    fiber = await ctx.load(plugin, {})
    assert fiber.config == {"size": 3}

    bad = ctx.plugin(plugin, {"size": "big"})
    with pytest.raises(Exception):
        await bad.wait_ready()
    assert bad.state is FiberState.FAILED


# ---------------------------------------------------------------------- fibers
async def test_fiber_states_and_double_dispose() -> None:
    ctx = Context(name="root")
    calls: list[str] = []

    def plugin(context, config=None):
        calls.append("apply")

    fiber = await ctx.load(plugin)
    assert fiber.state is FiberState.ACTIVE

    await fiber.dispose()
    assert fiber.state is FiberState.DISPOSED

    await fiber.dispose()
    assert calls == ["apply"]


async def test_failed_plugin_records_error() -> None:
    ctx = Context(name="root")

    def plugin(context, config=None):
        raise RuntimeError("nope")

    fiber = ctx.plugin(plugin)
    await asyncio.sleep(0)
    assert fiber.state is FiberState.FAILED
    assert "nope" in str(fiber.error)

    with pytest.raises(Exception):
        await fiber.wait_ready()


async def test_query_pending_fiber_for_missing_service() -> None:
    ctx = Context(name="root")

    def plugin(context, config=None):
        raise AssertionError("must not run")

    plugin.inject = ["never"]  # type: ignore[attr-defined]

    fiber = ctx.plugin(plugin)
    await asyncio.sleep(0)

    assert fiber.state is FiberState.PENDING
    report = ctx.list_fibers()
    assert fiber in report

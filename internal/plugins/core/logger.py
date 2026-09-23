"""Core plugin: structured logging (``ctx.logger``)."""

from __future__ import annotations

from typing import Any

from internal.cordis import LoggerService, Schema

plugin_name = "logger"

module_schema = Schema.object(
    {
        "base": Schema.string().default("live2oder"),
    }
)


def apply(ctx: Any, config: dict[str, Any] | None = None) -> None:
    base = str((config or {}).get("base") or "live2oder")
    service = LoggerService(ctx, "logger", base=base)
    ctx.service("logger", service)
    stop = getattr(service, "stop", None)
    if callable(stop):
        ctx.effect(stop)

"""Core plugin: timer helpers (``ctx.timer``)."""

from __future__ import annotations

from typing import Any

from internal.cordis import TimerService

plugin_name = "timer"


def apply(ctx: Any, config: dict[str, Any] | None = None) -> None:
    _ = config
    ctx.service("timer", TimerService(ctx, "timer"))

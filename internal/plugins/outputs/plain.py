"""Plugin slot: whole-chunk bubble output (``outputs/bubble``).

Same contract as ``internal.plugins.outputs.typewriter`` without the
per-character scrolling animation. Enable it in place of the typewriter module
when output should appear at once (for example while narrating with TTS).
"""

from __future__ import annotations

from typing import Any

from internal.cordis import Schema

from .typewriter import PlainBubbleOutput

plugin_name = "outputs/plain"

module_schema = Schema.object(
    {
        "char_interval_ms": Schema.natural().default(30),
    }
)


def apply(ctx: Any, config: dict[str, Any] | None = None) -> None:
    service = PlainBubbleOutput(ctx, "outputs/bubble")
    if isinstance(config, dict):
        service.char_interval_ms = int(config.get("char_interval_ms") or 30)
    ctx.service("outputs/bubble", service)

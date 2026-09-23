"""Plugin slot: bubble output (``outputs/bubble``).

The output contract is deliberately small so implementations can be swapped by
editing ``cordis.yml``. Every implementation receives the same waterfall event
``bubble/stream``, so other plugins can transform or veto a chunk before it is
rendered:

* ``outputs.typewriter`` – the scrolling-text module: Qt bubble rendering
  character by character, paced by the widget's typewriter timer and kept in
  sync with TTS audio by :class:`BubbleTimingController`.
* ``outputs/plain`` – whole-chunk rendering, no per-character pacing.

The animation policy lives in a pure helper (:func:`typewriter_enabled`) so it
can be unit tested without a Qt event loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from internal.cordis import Schema, Service

plugin_name = "outputs/typewriter"

module_schema = Schema.object(
    {
        "char_interval_ms": Schema.natural().default(30),
        "enabled": Schema.boolean().default(True),
    }
)


@dataclass(slots=True)
class BubbleChunk:
    """One piece of assistant output handed to the bubble service."""

    text: str
    done: bool = False
    duration_ms: int = 0
    bubble_id: int = 0
    text_color: int = 0xFFFFFF
    text_frame_color: int = 0x000000


def typewriter_enabled(widget: Any, *, enabled: bool, voice_client: Any) -> bool:
    """The scrolling-text module is used unless explicitly disabled or reused.

    When a TTS client is active the :class:`BubbleTimingController` owns the
    pacing (it synchronises the scroll position with audio), so the widget's own
    character timer is left off to avoid two competing rhythms.
    """
    if not enabled or widget is None:
        return False
    if voice_client is not None and getattr(voice_client, "enabled", True):
        return False
    return hasattr(widget, "start_typewriter")


class TypewriterBubbleOutput(Service):
    """Renders assistant output as scrolling text in the Qt bubble widget."""

    inject = ["ui/bubble-widget"]

    def __init__(self, ctx: Any, name: str = "outputs/bubble") -> None:
        super().__init__(ctx, name)
        self.widget: Any = None
        self.timing: Any = None
        self.char_interval_ms = 30
        self.use_typewriter = True

    def attach(self, widget: Any = None, timing: Any = None) -> None:
        """Bind the widget explicitly, or pick it up from ``ui/bubble-widget``."""
        if widget is None:
            widget_service = self.ctx.get("ui/bubble-widget")
            widget = getattr(widget_service, "widget", None)
        if timing is None:
            agent_loop = self.ctx.get("agent/loop")
            timing = getattr(getattr(agent_loop, "agent", None), "bubble_timing", None)
        self.widget = widget
        self.timing = timing
        self.use_typewriter = typewriter_enabled(
            widget,
            enabled=self._option("enabled", True),
            voice_client=getattr(timing, "voice_client", None),
        )

    def _option(self, key: str, default: Any) -> Any:
        config = self.config
        if isinstance(config, dict):
            return config.get(key, default)
        return default

    async def begin(self, chunk: BubbleChunk) -> None:
        if self.widget is None:
            return
        self.widget.clear()
        self.widget.show()

    async def stream(self, chunk: BubbleChunk) -> None:
        chunk = await self.ctx.waterfall("bubble/stream", chunk, next=lambda: chunk)
        if chunk is None:
            return
        if self.widget is None:
            return
        self.widget.set_text(chunk.text)

    async def finish(self, text: str, duration_ms: int = 0) -> None:
        if self.widget is None:
            return
        if self.timing is not None:
            await self.timing.finish_stream(text, self.widget)
            return
        self.widget.set_text(text)
        if duration_ms:
            self.widget.show_with_duration(duration_ms)

    def start_scrolling(self, text: str) -> bool:
        """Start the widget's character timer; returns whether it started."""
        if self.widget is None or not self.use_typewriter:
            return False
        start = getattr(self.widget, "start_typewriter", None)
        if not callable(start):
            return False
        start(text)
        return True


class PlainBubbleOutput(TypewriterBubbleOutput):
    """Whole-chunk rendering without character pacing."""

    plugin_name = "outputs/plain"

    def attach(self, widget: Any = None, timing: Any = None) -> None:
        super().attach(widget, timing)
        self.use_typewriter = False


def apply(ctx: Any, config: dict[str, Any] | None = None) -> None:
    service = TypewriterBubbleOutput(ctx, "outputs/bubble")
    if isinstance(config, dict):
        service.char_interval_ms = int(config.get("char_interval_ms") or 30)
    ctx.service("outputs/bubble", service)

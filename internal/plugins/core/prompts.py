"""Core plugin: modular prompts (``ctx.prompts``)."""

from __future__ import annotations

from typing import Any

from internal.cordis import Schema, Service
from internal.prompt_manager import PromptManager

plugin_name = "prompts"

module_schema = Schema.object({})


class PromptService(Service):
    """Wraps :class:`PromptManager` for plugin consumers."""

    def __init__(self, ctx: Any, name: str = "prompts") -> None:
        super().__init__(ctx, name)

    async def load(self) -> None:
        await PromptManager.load()

    @property
    def manager(self) -> Any:
        return PromptManager


def apply(ctx: Any, config: dict[str, Any] | None = None) -> None:
    _ = config
    ctx.service("prompts", PromptService(ctx, "prompts"))

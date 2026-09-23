"""Core plugin: retrieval augmented generation (``ctx.rag``)."""

from __future__ import annotations

from typing import Any

from internal.cordis import Schema, Service
from internal.rag.rag import RAGManager

plugin_name = "rag"

module_schema = Schema.object({})


class RagService(Service):
    """Owns the optional :class:`RAGManager` instance."""

    def __init__(self, ctx: Any, name: str = "rag") -> None:
        super().__init__(ctx, name)
        self.manager: RAGManager | None = None

    @property
    def enabled(self) -> bool:
        return self.manager is not None and self.manager.is_enabled

    def build(self, config: Any = None) -> RAGManager | None:
        resolved = config if config is not None else self._config_from_app()
        if resolved is None or not getattr(resolved, "enabled", False):
            self.manager = None
            return None
        if self.manager is None:
            manager = RAGManager(resolved)
            if not manager.initialize():
                self.manager = None
                return None
            self.manager = manager
        return self.manager

    def retrieve(self, query: str) -> list[Any]:
        if self.manager is None:
            return []
        return list(self.manager.retrieve(query))

    def _config_from_app(self) -> Any:
        config_service = self.ctx.get("config")
        if config_service is None:
            return None
        return getattr(config_service, "rag", None)


def apply(ctx: Any, config: dict[str, Any] | None = None) -> None:
    service = RagService(ctx, "rag")
    if isinstance(config, dict):
        service.config = config
    ctx.service("rag", service)

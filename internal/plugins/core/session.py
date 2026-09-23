"""Core plugin: session routing (``ctx.session``)."""

from __future__ import annotations

from typing import Any

from internal.cordis import Schema, Service
from internal.session.session_manager import SessionManager
from internal.session.session_store import SessionStore
from internal.session.topic_classifier import TopicClassifier

plugin_name = "session"

module_schema = Schema.object({})


class SessionService(Service):
    """Owns the session auto-router (topic detection + session store)."""

    def __init__(self, ctx: Any, name: str = "session") -> None:
        super().__init__(ctx, name)
        self.manager: SessionManager | None = None
        self.data_dir = "./data/sessions"

    @property
    def enabled(self) -> bool:
        return self.manager is not None

    def build(self, config: Any = None) -> SessionManager | None:
        resolved = config if config is not None else self._config_from_app()
        if resolved is None or not getattr(resolved, "enabled", False):
            self.manager = None
            return None
        data_dir = getattr(resolved, "data_dir", self.data_dir) or self.data_dir
        self.data_dir = data_dir
        store = SessionStore(data_dir=data_dir)
        classifier = TopicClassifier(embedding_model=None)
        memory_service = self.ctx.get("memory")
        memory_manager = getattr(memory_service, "manager", None)
        self.manager = SessionManager(
            session_store=store,
            classifier=classifier,
            memory_manager=memory_manager,
        )
        return self.manager

    async def ensure(self) -> SessionManager | None:
        manager = self.manager if self.manager is not None else self.build()
        if manager is None:
            return None
        await manager.initialize()
        return manager

    def _config_from_app(self) -> Any:
        config_service = self.ctx.get("config")
        if config_service is None:
            return None
        return getattr(config_service, "session", None)


def apply(ctx: Any, config: dict[str, Any] | None = None) -> None:
    service = SessionService(ctx, "session")
    if isinstance(config, dict):
        service.config = config
    ctx.service("session", service)

"""Core plugin: file/network sandbox middleware (``ctx.sandbox``)."""

from __future__ import annotations

from typing import Any

from internal.cordis import Schema, Service
from internal.agent.sandbox import SandboxConfig, SandboxMiddleware, default_sandbox

plugin_name = "sandbox"

module_schema = Schema.object({})


class SandboxService(Service):
    """Exposes the :class:`SandboxMiddleware` used by tool plugins."""

    def __init__(self, ctx: Any, name: str = "sandbox") -> None:
        super().__init__(ctx, name)
        self.middleware: SandboxMiddleware = default_sandbox

    def configure(self, config: SandboxConfig | None) -> SandboxMiddleware:
        if config is None:
            self.middleware = default_sandbox
        else:
            self.middleware = SandboxMiddleware(config)
        return self.middleware


def apply(ctx: Any, config: dict[str, Any] | None = None) -> None:
    _ = config
    service = SandboxService(ctx, "sandbox")
    config_service = ctx.get("config")
    if config_service is not None and getattr(config_service, "sandbox", None) is not None:
        service.configure(config_service.sandbox)
    ctx.service("sandbox", service)

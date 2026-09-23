"""Meta plugin: plugin tree diagnostics (``meta/diagnostics``).

Answers the two questions that come up whenever a freshly added plugin "does
nothing": is its fiber ``PENDING`` because a service is missing, or did it fail
while loading?
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from internal.cordis import Registry, Schema, Service

plugin_name = "meta/diagnostics"

module_schema = Schema.object({})


class DiagnosticsService(Service):
    """Read-only view over fiber states and registered services."""

    inject = ["loader"]

    def __init__(self, ctx: Any, name: str = "meta/diagnostics") -> None:
        super().__init__(ctx, name)

    def fibers(self, state: str | None = None) -> list[dict[str, Any]]:
        reports = [asdict(report) for report in Registry(self.ctx.root).report()]
        if state:
            reports = [report for report in reports if report["state"] == state]
        return reports

    def pending(self) -> list[dict[str, Any]]:
        return self.fibers("pending")

    def failed(self) -> list[dict[str, Any]]:
        return self.fibers("failed")

    def services(self) -> list[str]:
        return sorted(self.ctx.list_services())

    def loader_entries(self) -> list[dict[str, Any]]:
        loader = self.ctx.get("loader")
        return loader.report() if loader is not None else []

    def report(self) -> dict[str, Any]:
        return {
            "rev": getattr(self.ctx.get("loader"), "rev", 0),
            "services": self.services(),
            "entries": self.loader_entries(),
            "pending": self.pending(),
            "failed": self.failed(),
        }


def apply(ctx: Any, config: dict[str, Any] | None = None) -> None:
    _ = config
    ctx.service("meta/diagnostics", DiagnosticsService(ctx, "meta/diagnostics"))

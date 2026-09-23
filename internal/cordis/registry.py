"""Plugin registry used for diagnostics and hot-reload bookkeeping."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .lifecycle import Fiber, FiberState

__all__ = ["Registry", "FiberReport"]


@dataclass(slots=True)
class FiberReport:
    """Read-only snapshot of one fiber, used by ``plugin_status`` tooling."""

    name: str
    id: str
    state: str
    inject: list[str]
    missing: list[str]
    scope: str = ""

    @property
    def ok(self) -> bool:
        return self.state == FiberState.ACTIVE.value


class Registry:
    """Walk a context tree and report every mounted fiber."""

    def __init__(self, root: Any) -> None:
        self.root = root

    def _walk(self, node: Any) -> Iterable[Any]:
        yield node
        for fiber in list(getattr(node, "_fibers", ()) or ()):
            scope = fiber.context
            if scope is not None:
                yield from self._walk(scope)

    def fibers(self) -> list[Fiber]:
        found: list[Fiber] = []
        for node in self._walk(self.root):
            for fiber in list(getattr(node, "_fibers", ()) or ()):
                if fiber not in found:
                    found.append(fiber)
        return found

    def nodes(self) -> list[Any]:
        return list(self._walk(self.root))

    def report(self) -> list[FiberReport]:
        reports: list[FiberReport] = []
        for fiber in self.fibers():
            runtime = fiber.runtime
            inject = list(getattr(runtime, "inject", ()) or ())
            node = fiber.context
            missing = [name for name in inject if node.get(name) is None]
            reports.append(
                FiberReport(
                    name=fiber.name,
                    id=fiber.id or fiber.name,
                    state=fiber.state.value,
                    inject=inject,
                    missing=missing,
                    scope=self._ancestry(node),
                )
            )
        return reports

    def pending(self) -> list[FiberReport]:
        return [item for item in self.report() if item.state == FiberState.PENDING.value]

    def failed(self) -> list[FiberReport]:
        return [item for item in self.report() if item.state == FiberState.FAILED.value]

    def find(self, key: str) -> Fiber | None:
        for fiber in self.fibers():
            if key in {fiber.id, fiber.name}:
                return fiber
        return None

    @staticmethod
    def _ancestry(node: Any) -> str:
        names: list[str] = []
        current = node
        while current is not None:
            names.append(getattr(current, "name", "?"))
            current = getattr(current, "parent", None)
        return "/".join(reversed(names))

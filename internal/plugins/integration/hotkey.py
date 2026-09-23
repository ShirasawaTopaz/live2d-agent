"""Integration plugins: hotkeys, clipboard monitor, browser automation."""

from __future__ import annotations

from typing import Any, Callable

from internal.cordis import Schema, Service

plugin_name = "integration/hotkey"

module_schema = Schema.object({})


class HotkeyService(Service):
    """Owns the global hotkey manager and its registered shortcuts."""

    def __init__(self, ctx: Any, name: str = "integration/hotkey") -> None:
        super().__init__(ctx, name)
        self.manager: Any = None
        self.factory: Callable[[], Any] | None = None
        self._bindings: list[tuple[str, Callable[[], None]]] = []
        self._registered: list[tuple[str, Callable[[], None]]] = []

    @property
    def attached(self) -> bool:
        return self.manager is not None

    def attach(self, manager: Any) -> Any:
        self.manager = manager
        for combo, callback in self._bindings:
            self.register(combo, callback)
        return manager

    def default_bindings(self) -> tuple[str, str]:
        from internal.integration import HotkeyManager

        return HotkeyManager.DEFAULT_SUMMON, HotkeyManager.DEFAULT_CLIP_PROCESS

    def bind(self, combo: str, callback: Callable[[], None]) -> None:
        """Declare a binding; it is registered once a manager is attached."""
        self._bindings.append((combo, callback))
        if self.manager is not None:
            self.register(combo, callback)

    def register(self, combo: str, callback: Callable[[], None]) -> bool:
        if self.manager is None:
            return False
        try:
            self.manager.register(combo, callback)
        except Exception:  # noqa: BLE001 - hotkeys are best effort
            return False
        self._registered.append((combo, callback))
        return True

    def create(self) -> Any:
        if self.manager is None:
            if self.factory is None:
                from internal.integration import HotkeyManager

                self.factory = HotkeyManager
            self.attach(self.factory())
        return self.manager

    def stop(self) -> None:
        manager = self.manager
        self.manager = None
        if manager is None:
            return
        unregister = getattr(manager, "unregister", None)
        for combo, callback in self._registered:
            if callable(unregister):
                try:
                    unregister(combo)
                except Exception:  # noqa: BLE001
                    continue
            else:
                _ = callback
        self._registered.clear()


def apply(ctx: Any, config: dict[str, Any] | None = None) -> None:
    _ = config
    service = HotkeyService(ctx, "integration/hotkey")
    ctx.service("integration/hotkey", service)
    ctx.effect(service.stop)

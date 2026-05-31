"""Global hotkey registration.

Uses PySide6 QShortcut where available, falls back to pynput.
Stores keybindings in config.json.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class HotkeyBinding:
    """A parsed hotkey binding."""
    modifiers: set[str] = field(default_factory=set)
    key: str = ""

    @classmethod
    def from_string(cls, shortcut: str) -> "HotkeyBinding":
        parts = shortcut.strip().split("+")
        modifiers: set[str] = set()
        key = ""
        for part in parts:
            normalized = part.strip().capitalize()
            if normalized in {"Ctrl", "Control"}:
                modifiers.add("Ctrl")
            elif normalized in {"Shift"}:
                modifiers.add("Shift")
            elif normalized in {"Alt"}:
                modifiers.add("Alt")
            elif normalized in {"Meta", "Win", "Cmd", "Super"}:
                modifiers.add("Meta")
            else:
                key = part.strip()
        return cls(modifiers=modifiers, key=key)


class HotkeyManager:
    """Manages global hotkey registrations."""

    DEFAULT_SUMMON = "Ctrl+Shift+Space"
    DEFAULT_CLIP_PROCESS = "Ctrl+Shift+C"

    def __init__(self):
        self._bindings: dict[str, Any] = {}

    @staticmethod
    def default_bindings() -> dict[str, str]:
        return {
            "Ctrl+Shift+Space": "toggle_input_box",
            "Ctrl+Shift+C": "clipboard_quick_process",
        }

    def register(self, shortcut: str, callback: Callable[[], None]) -> bool:
        if shortcut in self._bindings:
            logger.warning("Hotkey '%s' already registered", shortcut)
            return False

        # Try Qt native first
        if self._register_qt(shortcut, callback):
            logger.info("Hotkey registered (Qt): %s", shortcut)
            return True

        # Fall back to pynput
        binding = HotkeyBinding.from_string(shortcut)
        if self._register_pynput(binding, callback):
            logger.info("Hotkey registered (pynput): %s", shortcut)
            return True

        logger.warning("Failed to register hotkey '%s'", shortcut)
        return False

    def unregister(self, shortcut: str) -> None:
        handle = self._bindings.pop(shortcut, None)
        if handle is not None:
            self._release_handle(handle)
            logger.debug("Hotkey unregistered: %s", shortcut)

    def register_all(self, bindings: dict[str, Callable[[], None]]) -> None:
        for shortcut, callback in bindings.items():
            self.register(shortcut, callback)

    def unregister_all(self) -> None:
        for shortcut in list(self._bindings.keys()):
            self.unregister(shortcut)

    def _register_qt(self, shortcut: str, callback: Callable[[], None]) -> bool:
        try:
            from PySide6.QtWidgets import QApplication
            from PySide6.QtGui import QShortcut, QKeySequence

            app = QApplication.instance()
            if app is None:
                return False

            key_seq = QKeySequence(shortcut)
            qsc = QShortcut(key_seq, None)
            qsc.setContext(3)  # Qt.ApplicationShortcut
            qsc.activated.connect(callback)

            self._bindings[shortcut] = qsc
            return True
        except Exception:
            logger.debug("Qt hotkey registration failed for '%s'", shortcut, exc_info=True)
            return False

    def _register_pynput(self, binding: HotkeyBinding, callback: Callable[[], None]) -> bool:
        try:
            import pynput.keyboard as kb
        except ImportError:
            logger.debug("pynput not available")
            return False

        modifier_map = {
            "Ctrl": kb.Key.ctrl_l,
            "Shift": kb.Key.shift_l,
            "Alt": kb.Key.alt_l,
            "Meta": kb.Key.cmd_l,
        }

        key_map: dict[str, Any] = {
            "Space": kb.Key.space,
            "Enter": kb.Key.enter,
            "Tab": kb.Key.tab,
            "Escape": kb.Key.esc,
            "Backspace": kb.Key.backspace,
        }

        for i in range(1, 13):
            key_map[f"F{i}"] = getattr(kb.Key, f"f{i}", None)

        pressed: set[Any] = set()
        required_mods: set[Any] = {modifier_map[m] for m in binding.modifiers if m in modifier_map}

        target_key = key_map.get(binding.key)
        if target_key is None and len(binding.key) == 1:
            try:
                target_key = kb.KeyCode.from_char(binding.key.lower())
            except Exception:
                pass

        if target_key is None:
            logger.debug("Cannot map key '%s' for pynput", binding.key)
            return False

        def on_press(key: Any) -> None:
            if key in required_mods or key in modifier_map.values():
                pressed.add(key)
            elif key == target_key or (
                hasattr(key, "char") and getattr(key, "char", None) == binding.key.lower()
            ):
                pressed.add("__target__")
            if "__target__" in pressed and required_mods.issubset(pressed):
                try:
                    callback()
                except Exception:
                    logger.exception("Hotkey callback failed")

        def on_release(key: Any) -> None:
            pressed.discard(key)
            pressed.discard("__target__")

        listener = kb.Listener(on_press=on_press, on_release=on_release)
        listener.start()
        self._bindings[f"pynput:{binding.key}"] = (listener, required_mods, binding.key)
        return True

    def _release_handle(self, handle: Any) -> None:
        if isinstance(handle, tuple) and len(handle) == 3:
            listener = handle[0]
            try:
                listener.stop()
            except Exception:
                pass

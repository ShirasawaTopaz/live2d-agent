"""Unit tests for HotkeyManager."""

from unittest.mock import MagicMock
from internal.integration.hotkey import HotkeyManager, HotkeyBinding


class TestHotkeyBinding:
    def test_parse_ctrl_shift_space(self):
        binding = HotkeyBinding.from_string("Ctrl+Shift+Space")
        assert binding.modifiers == {"Ctrl", "Shift"}
        assert binding.key == "Space"

    def test_parse_simple(self):
        binding = HotkeyBinding.from_string("F5")
        assert binding.modifiers == set()
        assert binding.key == "F5"

    def test_parse_ctrl_c(self):
        binding = HotkeyBinding.from_string("Ctrl+C")
        assert binding.modifiers == {"Ctrl"}
        assert binding.key == "C"


class TestHotkeyManager:
    def setup_method(self):
        self.manager = HotkeyManager()

        def mock_register_qt(shortcut: str, callback):
            self.manager._bindings[shortcut] = MagicMock()
            return True

        self.manager._register_qt = mock_register_qt

    def test_register_binding(self):
        callback = MagicMock()
        result = self.manager.register("Ctrl+Shift+Space", callback)
        assert isinstance(result, bool)

    def test_register_duplicate(self):
        cb1 = MagicMock()
        cb2 = MagicMock()
        self.manager.register("Ctrl+K", cb1)
        result = self.manager.register("Ctrl+K", cb2)
        assert result is False

    def test_unregister(self):
        cb = MagicMock()
        self.manager.register("Ctrl+J", cb)
        self.manager.unregister("Ctrl+J")
        result = self.manager.register("Ctrl+J", cb)
        assert result is True

    def test_default_bindings(self):
        defaults = HotkeyManager.default_bindings()
        assert "Ctrl+Shift+Space" in defaults
        assert "Ctrl+Shift+C" in defaults

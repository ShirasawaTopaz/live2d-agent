"""External integrations: clipboard, browser, hotkeys."""

from internal.integration.clipboard import ClipboardMonitor, ClipAction, MiniActionBar

try:
    from internal.integration.browser import BrowserController, register_browser_tools
except ImportError:
    BrowserController = None  # type: ignore
    register_browser_tools = None  # type: ignore

try:
    from internal.integration.hotkey import HotkeyManager
except ImportError:
    HotkeyManager = None  # type: ignore

__all__ = [
    "ClipboardMonitor",
    "ClipAction",
    "MiniActionBar",
    "BrowserController",
    "register_browser_tools",
    "HotkeyManager",
]

# External Integrations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add clipboard quick-processing with mini action bar, browser control tools for the Agent, and global hotkey support for summon/hide.

**Architecture:** `internal/integration/` package with three independent components. `ClipboardMonitor` hooks `QClipboard.dataChanged`. `BrowserController` wraps existing Playwright MCP tools as Agent Tools. `HotkeyManager` registers system-wide shortcuts via Qt or pynput. All wired into `input_box.py` and `live2d_agent_app.py`.

**Tech Stack:** PySide6 QClipboard, Playwright, pynput (optional fallback for hotkeys)

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `internal/integration/__init__.py` | Package exports |
| Create | `internal/integration/clipboard.py` | ClipboardMonitor + mini action bar |
| Create | `internal/integration/browser.py` | BrowserController → Agent Tools |
| Create | `internal/integration/hotkey.py` | HotkeyManager global shortcuts |
| Modify | `internal/ui/input_box.py` | Add hotkey registration, clipboard hook |
| Modify | `internal/app/live2d_agent_app.py` | Initialize integration modules |
| Create | `test/integration/__init__.py` | Test package marker |
| Create | `test/integration/test_clipboard.py` | Clipboard unit tests |
| Create | `test/integration/test_hotkey.py` | Hotkey unit tests |
| Create | `test/integration/test_browser.py` | Browser tool tests |

---

### Task 1: Integration Package Init

**Files:**
- Create: `internal/integration/__init__.py`

- [ ] **Step 1: Create `internal/integration/__init__.py`**

```python
"""External integrations: clipboard, browser, hotkeys."""

from internal.integration.clipboard import ClipboardMonitor, ClipAction, MiniActionBar
from internal.integration.browser import BrowserController, register_browser_tools
from internal.integration.hotkey import HotkeyManager

__all__ = [
    "ClipboardMonitor",
    "ClipAction",
    "MiniActionBar",
    "BrowserController",
    "register_browser_tools",
    "HotkeyManager",
]
```

- [ ] **Step 2: Commit**

```bash
git add internal/integration/__init__.py
git commit -m "feat(integration): add package init"
```

---

### Task 2: Clipboard Monitor

**Files:**
- Create: `internal/integration/clipboard.py`
- Create: `test/integration/__init__.py`
- Create: `test/integration/test_clipboard.py`

- [ ] **Step 1: Create `test/integration/__init__.py`** (empty)

```python
"""Tests for external integrations module."""
```

- [ ] **Step 2: Write tests in `test/integration/test_clipboard.py`**

```python
"""Unit tests for ClipboardMonitor and ClipAction."""

import pytest
from internal.integration.clipboard import ClipAction, ClipboardMonitor


class TestClipAction:
    """Tests for ClipAction configuration."""

    def test_create_action(self):
        action = ClipAction(
            id="translate",
            label="翻译",
            prompt_template="请将以下内容翻译成中文:\n{text}",
        )
        assert action.id == "translate"
        assert action.label == "翻译"

    def test_resolve_prompt(self):
        action = ClipAction(
            id="summarize",
            label="总结",
            prompt_template="总结以下内容:\n{text}",
        )
        resolved = action.resolve_prompt("这是一段很长的文字")
        assert "这是一段很长的文字" in resolved
        assert "总结以下内容" in resolved

    def test_default_actions(self):
        actions = ClipAction.defaults()
        assert len(actions) >= 4
        ids = {a.id for a in actions}
        assert "summarize" in ids
        assert "translate" in ids
        assert "rewrite" in ids
        assert "explain_code" in ids


class TestClipboardMonitorConfig:
    """Tests for ClipboardMonitor configuration."""

    def test_default_actions_set(self):
        monitor = ClipboardMonitor()
        assert len(monitor.actions) >= 4

    def test_custom_actions(self):
        custom = [
            ClipAction(id="mock_action", label="Mock", prompt_template="{text}"),
        ]
        monitor = ClipboardMonitor(actions=custom)
        assert len(monitor.actions) == 1
        assert monitor.actions[0].id == "mock_action"

    def test_enabled_default(self):
        monitor = ClipboardMonitor()
        assert monitor.enabled is False  # Must be explicitly started

    def test_set_enabled(self):
        monitor = ClipboardMonitor()
        monitor.set_enabled(True)
        assert monitor.enabled is True
        monitor.set_enabled(False)
        assert monitor.enabled is False
```

- [ ] **Step 3: Run to verify failure**

```bash
cd D:/Source/live2oder && poetry run pytest test/integration/test_clipboard.py -v
```
Expected: FAIL

- [ ] **Step 4: Implement `internal/integration/clipboard.py`**

```python
"""Clipboard monitoring and mini action bar for quick text processing.

Flow:
  User copies text (Ctrl+C) → ClipboardMonitor detects → MiniActionBar
  pops up near mouse with action buttons → User clicks → Agent processes
  → Result written back to clipboard + balloon notification.
"""

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ClipAction:
    """A quick action available on the clipboard mini bar."""

    id: str                      # "translate", "summarize", etc.
    label: str                   # Display text on button
    prompt_template: str         # "{text}" placeholder for clipboard content

    def resolve_prompt(self, text: str) -> str:
        """Fill the prompt template with clipboard text."""
        return self.prompt_template.replace("{text}", text)

    @staticmethod
    def defaults() -> list["ClipAction"]:
        """Built-in default actions."""
        return [
            ClipAction(
                id="summarize",
                label="📝 总结",
                prompt_template="请用简洁的中文总结以下内容，保留关键信息:\n\n{text}",
            ),
            ClipAction(
                id="translate",
                label="🌐 翻译",
                prompt_template="请将以下内容翻译成中文:\n\n{text}",
            ),
            ClipAction(
                id="rewrite",
                label="🔄 改写",
                prompt_template="请改写以下内容，保持原意但使表达更流畅专业:\n\n{text}",
            ),
            ClipAction(
                id="explain_code",
                label="💻 解释代码",
                prompt_template="请解释以下代码的作用和工作原理:\n\n{text}",
            ),
        ]


class MiniActionBar:
    """Frameless popup widget shown near mouse position.

    Displays action buttons for the clipboard content.
    Auto-dismisses after ~2 seconds of inactivity.
    """

    def __init__(self, actions: list[ClipAction], on_action: Any = None):
        self.actions = actions
        self.on_action = on_action  # Callable[[ClipAction, str], None]
        self._widget: Any = None
        self._dismiss_timer: Any = None

    def show(self, clipboard_text: str) -> None:
        """Show the mini action bar near the mouse cursor."""
        try:
            from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QApplication
            from PySide6.QtCore import Qt, QTimer, QPoint
        except ImportError:
            logger.warning("PySide6 not available, MiniActionBar disabled")
            return

        # Kill existing widget
        self.dismiss()

        self._widget = QWidget()
        self._widget.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.Popup
        )
        self._widget.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self._widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self._widget.setStyleSheet(
            "QWidget { background: #2d2d2d; border: 1px solid #555; border-radius: 6px; padding: 4px; }"
        )

        layout = QHBoxLayout(self._widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Dismiss button
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #999; border: none; font-size: 14px; }"
            "QPushButton:hover { color: #fff; }"
        )
        close_btn.clicked.connect(self.dismiss)
        layout.addWidget(close_btn)

        for action in self.actions:
            btn = QPushButton(action.label)
            btn.setStyleSheet(
                "QPushButton { background: #3a3a3a; color: #ddd; border: none; "
                "border-radius: 4px; padding: 4px 10px; font-size: 12px; }"
                "QPushButton:hover { background: #4a6a9a; color: #fff; }"
            )
            btn.clicked.connect(
                lambda checked=False, a=action, t=clipboard_text: self._on_click(a, t)
            )
            layout.addWidget(btn)

        self._widget.adjustSize()

        # Position near mouse cursor
        cursor_pos = QApplication.instance().screens()[0].cursor().pos() if QApplication.instance() else QPoint(100, 100)
        self._widget.move(cursor_pos + QPoint(10, 10))

        self._widget.show()

        # Auto-dismiss after 3 seconds
        self._dismiss_timer = QTimer(self._widget)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self.dismiss)
        self._dismiss_timer.start(3000)

    def _on_click(self, action: ClipAction, text: str) -> None:
        """Handle action button click."""
        self.dismiss()
        if self.on_action is not None:
            self.on_action(action, text)

    def dismiss(self) -> None:
        """Dismiss the popup."""
        if self._dismiss_timer is not None:
            self._dismiss_timer.stop()
            self._dismiss_timer = None
        if self._widget is not None:
            self._widget.close()
            self._widget.deleteLater()
            self._widget = None


class ClipboardMonitor:
    """Monitors clipboard for text changes.

    When the app is visible and new text is copied, shows the mini action bar.
    Security: only monitors when explicitly enabled (app visible).
    """

    def __init__(self, actions: list[ClipAction] | None = None):
        self.actions = actions or ClipAction.defaults()
        self.enabled = False
        self._clipboard: Any = None
        self._last_text: str = ""
        self._on_action_callback: Any = None

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable clipboard monitoring."""
        self.enabled = enabled
        if enabled:
            self._start()
        else:
            self._stop()

    def set_on_action(self, callback: Any) -> None:
        """Set callback: callable(ClipAction, str) -> None."""
        self._on_action_callback = callback

    def _start(self) -> None:
        """Start listening to clipboard changes."""
        try:
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is None:
                return
            self._clipboard = app.clipboard()
            if self._clipboard is not None:
                self._clipboard.dataChanged.connect(self._on_clipboard_change)
                logger.debug("ClipboardMonitor started")
        except Exception:
            logger.warning("Failed to start ClipboardMonitor", exc_info=True)

    def _stop(self) -> None:
        """Stop listening."""
        if self._clipboard is not None:
            try:
                self._clipboard.dataChanged.disconnect(self._on_clipboard_change)
            except Exception:
                pass
            self._clipboard = None
            logger.debug("ClipboardMonitor stopped")

    def _on_clipboard_change(self) -> None:
        """Handle clipboard data change."""
        if not self.enabled or self._clipboard is None:
            return

        try:
            from PySide6.QtWidgets import QApplication
            from PySide6.QtCore import QMimeData
        except ImportError:
            return

        mime_data = self._clipboard.mimeData()
        if mime_data is None or not mime_data.hasText():
            return

        text = mime_data.text().strip()
        if not text or len(text) < 3:
            return

        # Don't re-trigger on same text
        if text == self._last_text:
            return
        self._last_text = text

        logger.debug("Clipboard changed: %d chars", len(text))

        # Show mini action bar
        bar = MiniActionBar(self.actions, on_action=self._handle_action)
        bar.show(text)

    def _handle_action(self, action: ClipAction, text: str) -> None:
        """Forward the action+text to the registered callback."""
        logger.info("Clipboard action '%s' selected (%d chars)", action.id, len(text))
        if self._on_action_callback is not None:
            self._on_action_callback(action, text)
```

- [ ] **Step 5: Run tests**

```bash
cd D:/Source/live2oder && poetry run pytest test/integration/test_clipboard.py -v
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add internal/integration/clipboard.py test/integration/__init__.py test/integration/test_clipboard.py
git commit -m "feat(integration): add ClipboardMonitor with mini action bar"
```

---

### Task 3: Browser Controller

**Files:**
- Create: `internal/integration/browser.py`
- Create: `test/integration/test_browser.py`

- [ ] **Step 1: Write tests in `test/integration/test_browser.py`**

```python
"""Unit tests for BrowserController."""

import pytest
from internal.integration.browser import BrowserController, BrowserTool


class TestBrowserController:
    """Tests for BrowserController without an actual browser."""

    def setup_method(self):
        self.controller = BrowserController(headless=True)

    def test_tools_registered(self):
        tools = self.controller.get_tools()
        tool_names = {t.name for t in tools}
        assert "browser_open" in tool_names
        assert "browser_extract" in tool_names
        assert "browser_click" in tool_names
        assert "browser_type" in tool_names
        assert "browser_search" in tool_names
        assert "browser_screenshot" in tool_names

    def test_tool_parameters(self):
        tools = {t.name: t for t in self.controller.get_tools()}
        open_tool = tools["browser_open"]
        assert "url" in open_tool.parameters

        search_tool = tools["browser_search"]
        assert "query" in search_tool.parameters

    def test_describe_tools(self):
        descriptions = self.controller.describe_tools()
        assert isinstance(descriptions, str)
        assert "browser_open" in descriptions
```

- [ ] **Step 2: Run to verify failure**

```bash
cd D:/Source/live2oder && poetry run pytest test/integration/test_browser.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement `internal/integration/browser.py`**

```python
"""Browser control tools for the Agent.

Wraps Playwright for browser automation. Exposes tools that the Agent
can call to navigate, extract, click, type, search, and screenshot.

Architecture:
  BrowserController ──► Playwright (sync API, run via asyncio.to_thread)
                              │
                              └──► Tool definitions ──► Agent ToolRegistry
"""

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class BrowserTool:
    """Tool definition for Agent registration."""
    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)


class BrowserController:
    """High-level browser automation controller.

    Uses Playwright's sync API wrapped in asyncio.to_thread for
    non-blocking execution. Provides methods that map 1:1 to
    Agent Tool definitions.
    """

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._browser: Any = None
        self._page: Any = None
        self._playwright: Any = None
        self._initialized = False

    # ── Tool registry ──────────────────────────────────────

    def get_tools(self) -> list[BrowserTool]:
        """Return all browser tools for Agent registration."""
        return [
            BrowserTool(
                name="browser_open",
                description="打开浏览器并导航到指定URL，返回页面文本内容",
                parameters={"url": {"type": "string", "description": "要打开的网页URL"}},
            ),
            BrowserTool(
                name="browser_extract",
                description="从当前浏览器页面提取指定CSS选择器的内容",
                parameters={"selector": {"type": "string", "description": "CSS选择器"}},
            ),
            BrowserTool(
                name="browser_click",
                description="点击浏览器页面中的指定元素",
                parameters={"selector": {"type": "string", "description": "CSS选择器"}},
            ),
            BrowserTool(
                name="browser_type",
                description="在输入框中输入文本",
                parameters={
                    "selector": {"type": "string", "description": "输入框的CSS选择器"},
                    "text": {"type": "string", "description": "要输入的文本"},
                },
            ),
            BrowserTool(
                name="browser_search",
                description="在搜索引擎中搜索并返回前5条结果",
                parameters={"query": {"type": "string", "description": "搜索关键词"}},
            ),
            BrowserTool(
                name="browser_screenshot",
                description="截取当前页面或元素的截图（用于视觉模型分析）",
                parameters={
                    "selector": {
                        "type": "string",
                        "description": "CSS选择器（可选，不指定则截全页）",
                    },
                },
            ),
            BrowserTool(
                name="browser_scroll",
                description="滚动页面",
                parameters={
                    "direction": {
                        "type": "string",
                        "enum": ["up", "down"],
                        "description": "滚动方向",
                    },
                },
            ),
            BrowserTool(
                name="browser_close",
                description="关闭浏览器",
                parameters={},
            ),
        ]

    def describe_tools(self) -> str:
        """Return a human-readable description of all tools."""
        lines: list[str] = []
        for tool in self.get_tools():
            params = ", ".join(tool.parameters.keys())
            lines.append(f"- {tool.name}({params}): {tool.description}")
        return "\n".join(lines)

    # ── Lifecycle ─────────────────────────────────────────

    async def initialize(self) -> None:
        """Launch a headless (or headed) Playwright browser."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("playwright not installed, browser tools unavailable")
            raise

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        self._page = await self._browser.new_page()
        self._initialized = True
        logger.info("BrowserController initialized (headless=%s)", self.headless)

    async def shutdown(self) -> None:
        """Close browser and clean up."""
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()
        self._initialized = False
        logger.info("BrowserController shut down")

    # ── Tool implementations ───────────────────────────

    async def open(self, url: str) -> str:
        """Navigate to URL and return page text content."""
        await self._ensure_initialized()
        await self._page.goto(url, wait_until="domcontentloaded", timeout=15000)
        content = await self._page.inner_text("body")
        title = await self._page.title()
        return f"页面标题: {title}\n\n页面内容:\n{content[:5000]}"

    async def extract(self, selector: str) -> str:
        """Extract text content from element(s) matching selector."""
        await self._ensure_initialized()
        elements = await self._page.query_selector_all(selector)
        if not elements:
            return f"未找到匹配 '{selector}' 的元素"
        texts: list[str] = []
        for el in elements[:10]:
            text = await el.inner_text()
            texts.append(text)
        return "\n---\n".join(texts)

    async def click(self, selector: str) -> str:
        """Click an element and return what happened."""
        await self._ensure_initialized()
        try:
            await self._page.click(selector, timeout=5000)
            return f"已点击 '{selector}'"
        except Exception as e:
            return f"点击失败: {e}"

    async def type_text(self, selector: str, text: str) -> str:
        """Type text into an input element."""
        await self._ensure_initialized()
        await self._page.fill(selector, text, timeout=5000)
        return f"已在 '{selector}' 中输入文本"

    async def search(self, query: str) -> str:
        """Search via Google and return top results."""
        await self._ensure_initialized()
        search_url = f"https://www.google.com/search?q={query}"
        await self._page.goto(search_url, wait_until="domcontentloaded", timeout=15000)

        # Extract search result snippets
        try:
            results = await self._page.query_selector_all("h3")
            items: list[str] = []
            for i, h3 in enumerate(results[:5]):
                title = await h3.inner_text()
                items.append(f"{i+1}. {title}")
            return "\n".join(items) if items else "未找到搜索结果"
        except Exception:
            return "搜索结果提取失败"

    async def screenshot(self, selector: str | None = None) -> bytes:
        """Take a screenshot. Returns PNG bytes."""
        await self._ensure_initialized()
        if selector is not None:
            element = await self._page.query_selector(selector)
            if element is not None:
                return await element.screenshot()
        return await self._page.screenshot()

    async def scroll(self, direction: str) -> str:
        """Scroll the page up or down."""
        await self._ensure_initialized()
        amount = 500 if direction == "down" else -500
        await self._page.evaluate(f"window.scrollBy(0, {amount})")
        return f"页面已向{'下' if direction == 'down' else '上'}滚动"

    async def close_browser(self) -> str:
        """Close the browser."""
        if self._page is not None:
            await self._page.close()
            self._page = None
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        self._initialized = False
        return "浏览器已关闭"

    # ── Internal ──────────────────────────────────────

    async def _ensure_initialized(self) -> None:
        if not self._initialized:
            await self.initialize()


def register_browser_tools(
    controller: BrowserController,
    tool_registry: Any,
) -> None:
    """Register all browser tools into the Agent's ToolRegistry.

    Args:
        controller: An initialized BrowserController instance.
        tool_registry: Agent's ToolRegistry instance.
    """
    from internal.agent.tool.base import Tool

    tool_map = {
        "browser_open": controller.open,
        "browser_extract": controller.extract,
        "browser_click": controller.click,
        "browser_type": controller.type_text,
        "browser_search": controller.search,
        "browser_scroll": controller.scroll,
        "browser_close": controller.close_browser,
    }

    for bt in controller.get_tools():
        if bt.name not in tool_map:
            continue

        handler = tool_map[bt.name]

        class _BrowserTool(Tool):
            name = bt.name
            description = bt.description
            parameters = bt.parameters

            async def execute(self, **kwargs: Any) -> str:
                return await handler(**kwargs)

        tool_registry.register(_BrowserTool())

    logger.info("Registered %d browser tools", len(controller.get_tools()))
```

- [ ] **Step 4: Run tests**

```bash
cd D:/Source/live2oder && poetry run pytest test/integration/test_browser.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add internal/integration/browser.py test/integration/test_browser.py
git commit -m "feat(integration): add BrowserController with 8 tools for Agent"
```

---

### Task 4: Global Hotkeys

**Files:**
- Create: `internal/integration/hotkey.py`
- Create: `test/integration/test_hotkey.py`

- [ ] **Step 1: Write tests in `test/integration/test_hotkey.py`**

```python
"""Unit tests for HotkeyManager."""

import pytest
from unittest.mock import MagicMock
from internal.integration.hotkey import HotkeyManager, HotkeyBinding


class TestHotkeyBinding:
    """Tests for HotkeyBinding."""

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
    """Tests for HotkeyManager registration."""

    def setup_method(self):
        self.manager = HotkeyManager()

    def test_register_binding(self):
        callback = MagicMock()
        result = self.manager.register("Ctrl+Shift+Space", callback)
        assert isinstance(result, bool)

    def test_register_duplicate(self):
        cb1 = MagicMock()
        cb2 = MagicMock()
        self.manager.register("Ctrl+K", cb1)
        result = self.manager.register("Ctrl+K", cb2)
        assert result is False  # Already registered

    def test_unregister(self):
        cb = MagicMock()
        self.manager.register("Ctrl+J", cb)
        self.manager.unregister("Ctrl+J")
        # Re-register should succeed now
        result = self.manager.register("Ctrl+J", cb)
        assert result is True

    def test_register_all(self):
        cb = MagicMock()
        bindings = {
            "Ctrl+Shift+Space": cb,
        }
        self.manager.register_all(bindings)
        # Clean up
        self.manager.unregister_all()

    def test_default_bindings(self):
        defaults = HotkeyManager.default_bindings()
        assert "Ctrl+Shift+Space" in defaults
        assert "Ctrl+Shift+C" in defaults
```

- [ ] **Step 2: Run to verify failure**

```bash
cd D:/Source/live2oder && poetry run pytest test/integration/test_hotkey.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement `internal/integration/hotkey.py`**

```python
"""Global hotkey registration.

Uses PySide6 QHotkey where available, falls back to pynput.
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
    modifiers: set[str] = field(default_factory=set)  # {"Ctrl", "Shift", "Alt"}
    key: str = ""  # "Space", "C", "F5", etc.

    @classmethod
    def from_string(cls, shortcut: str) -> "HotkeyBinding":
        """Parse a shortcut string like 'Ctrl+Shift+Space'."""
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
    """Manages global hotkey registrations.

    Tries Qt-native first, falls back to pynput.
    """

    DEFAULT_SUMMON = "Ctrl+Shift+Space"
    DEFAULT_CLIP_PROCESS = "Ctrl+Shift+C"

    def __init__(self):
        self._bindings: dict[str, Any] = {}  # shortcut_str → callback or QHotkey

    @staticmethod
    def default_bindings() -> dict[str, str]:
        """Return default shortcut → action mapping."""
        return {
            "Ctrl+Shift+Space": "toggle_input_box",
            "Ctrl+Shift+C": "clipboard_quick_process",
        }

    def register(self, shortcut: str, callback: Callable[[], None]) -> bool:
        """Register a global hotkey. Returns True if successful."""
        if shortcut in self._bindings:
            logger.warning("Hotkey '%s' already registered", shortcut)
            return False

        binding = HotkeyBinding.from_string(shortcut)

        # Try Qt native first
        if self._register_qt(shortcut, callback):
            logger.info("Hotkey registered (Qt): %s", shortcut)
            return True

        # Fall back to pynput
        if self._register_pynput(binding, callback):
            logger.info("Hotkey registered (pynput): %s", shortcut)
            return True

        logger.warning("Failed to register hotkey '%s'", shortcut)
        return False

    def unregister(self, shortcut: str) -> None:
        """Unregister a hotkey."""
        handle = self._bindings.pop(shortcut, None)
        if handle is not None:
            self._release_handle(handle)
            logger.debug("Hotkey unregistered: %s", shortcut)

    def register_all(self, bindings: dict[str, Callable[[], None]]) -> None:
        """Register multiple hotkeys at once."""
        for shortcut, callback in bindings.items():
            self.register(shortcut, callback)

    def unregister_all(self) -> None:
        """Unregister all hotkeys."""
        for shortcut in list(self._bindings.keys()):
            self.unregister(shortcut)

    # ── Qt backend ───────────────────────────────────────────

    def _register_qt(self, shortcut: str, callback: Callable[[], None]) -> bool:
        """Try registering via PySide6 QShortcut (app-level)."""
        try:
            from PySide6.QtWidgets import QApplication
            from PySide6.QtGui import QShortcut, QKeySequence

            app = QApplication.instance()
            if app is None:
                return False

            key_seq = QKeySequence(shortcut)
            qsc = QShortcut(key_seq, None)  # Application-level shortcut
            qsc.setContext(3)  # Qt.ApplicationShortcut
            qsc.activated.connect(callback)

            self._bindings[shortcut] = qsc
            return True
        except Exception:
            logger.debug("Qt hotkey registration failed for '%s'", shortcut, exc_info=True)
            return False

    def _register_pynput(
        self, binding: HotkeyBinding, callback: Callable[[], None]
    ) -> bool:
        """Fall back to pynput for global hotkeys."""
        try:
            import pynput.keyboard as kb
        except ImportError:
            logger.debug("pynput not available")
            return False

        # Map modifier names to pynput keys
        modifier_map = {
            "Ctrl": kb.Key.ctrl_l,
            "Shift": kb.Key.shift_l,
            "Alt": kb.Key.alt_l,
            "Meta": kb.Key.cmd_l,
        }

        # Map common key names to pynput keys
        key_map: dict[str, Any] = {
            "Space": kb.Key.space,
            "Enter": kb.Key.enter,
            "Tab": kb.Key.tab,
            "Escape": kb.Key.esc,
            "Backspace": kb.Key.backspace,
        }

        # For function keys
        for i in range(1, 13):
            key_map[f"F{i}"] = getattr(kb.Key, f"f{i}", None)

        pressed: set[Any] = set()
        required_mods: set[Any] = {modifier_map[m] for m in binding.modifiers if m in modifier_map}

        target_key = key_map.get(binding.key)
        if target_key is None and len(binding.key) == 1:
            target_key = binding.key.lower() if hasattr(kb.KeyCode, "from_char") else None

        if target_key is None:
            logger.debug("Cannot map key '%s' for pynput", binding.key)
            return False

        listener_ref: list[Any] = [None]

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
        listener_ref[0] = listener

        self._bindings[f"pynput:{binding.key}"] = (listener, required_mods, binding.key)
        return True

    # ── Internal ───────────────────────────────────

    def _release_handle(self, handle: Any) -> None:
        """Release a hotkey handle (QShortcut or pynput listener)."""
        if isinstance(handle, tuple) and len(handle) == 3:
            listener = handle[0]
            try:
                listener.stop()
            except Exception:
                pass
        # Qt QShortcut handles auto-cleanup on destruction
```

- [ ] **Step 4: Run tests**

```bash
cd D:/Source/live2oder && poetry run pytest test/integration/test_hotkey.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add internal/integration/hotkey.py test/integration/test_hotkey.py
git commit -m "feat(integration): add HotkeyManager with Qt and pynput backends"
```

---

### Task 5: Wire into App and Input Box

**Files:**
- Modify: `internal/ui/input_box.py`
- Modify: `internal/app/live2d_agent_app.py`
- Modify: `config.example.json`

- [ ] **Step 1: Add hotkey and clipboard integration to `internal/app/live2d_agent_app.py`**

In `Live2DAgentApp.__init__`, add:

```python
        self.hotkey_manager: Any = None
        self.clipboard_monitor: Any = None
        self.browser_controller: Any = None
```

Add after `_setup_tray_and_window()` in `initialize()`:

```python
    async def _initialize_integrations(self) -> None:
        """Initialize integration modules (hotkeys, clipboard, browser)."""
        integration_config = getattr(self.config, "integration", None)
        if integration_config is None:
            logger.info("No integration config, using defaults")
            integration_config = {}

        # Hotkeys
        hotkeys_enabled = getattr(integration_config, "hotkeys_enabled", True)
        if hotkeys_enabled:
            from internal.integration import HotkeyManager
            self.hotkey_manager = HotkeyManager()
            self.hotkey_manager.register(
                HotkeyManager.DEFAULT_SUMMON,
                self._on_hotkey_summon,
            )
            self.hotkey_manager.register(
                HotkeyManager.DEFAULT_CLIP_PROCESS,
                self._on_hotkey_clipboard_process,
            )
            logger.info("Hotkeys registered")

        # Clipboard
        clipboard_enabled = getattr(integration_config, "clipboard_enabled", True)
        if clipboard_enabled:
            from internal.integration import ClipboardMonitor
            self.clipboard_monitor = ClipboardMonitor()
            self.clipboard_monitor.set_on_action(self._on_clipboard_action)
            self.clipboard_monitor.set_enabled(True)
            logger.info("Clipboard monitor started")

        # Browser (lazy — only initialize when first called)
        self._browser_initializing = False

    async def _ensure_browser(self) -> Any:
        """Lazy-initialize the browser controller."""
        if self.browser_controller is None and not self._browser_initializing:
            self._browser_initializing = True
            try:
                from internal.integration import BrowserController, register_browser_tools
                self.browser_controller = BrowserController(headless=True)
                await self.browser_controller.initialize()
                if self.agent is not None:
                    register_browser_tools(
                        self.browser_controller,
                        self.agent.tool_registry,
                    )
                logger.info("Browser controller initialized and tools registered")
            except Exception:
                logger.warning("Browser controller init failed (playwright missing?)", exc_info=True)
            finally:
                self._browser_initializing = False
        return self.browser_controller

    def _on_hotkey_summon(self) -> None:
        """Toggle input box visibility."""
        if self.input_box is not None:
            if self.input_box.isVisible():
                self.hide_input_box()
            else:
                self.show_input_box()

    def _on_hotkey_clipboard_process(self) -> None:
        """Process selected text or clipboard content."""
        if self.input_box is None:
            return
        try:
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is None:
                return
            clipboard = app.clipboard()
            if clipboard is None:
                return
            text = clipboard.text().strip()
            if text:
                self.input_box.text_edit.setText(text)
                self.show_input_box()
        except Exception:
            logger.warning("Clipboard quick process failed", exc_info=True)

    def _on_clipboard_action(self, action: Any, text: str) -> None:
        """Handle a clipboard action: send to Agent and write result back."""
        prompt = action.resolve_prompt(text)
        if self.input_box is not None:
            self.input_box.text_edit.setText(prompt)
            self.show_input_box()
```

Call `await self._initialize_integrations()` in `initialize()` after `_setup_tray_and_window()`.

- [ ] **Step 2: Update input box visibility change to toggle clipboard monitoring**

In `FloatingInputBox` or in `_on_hotkey_summon`, toggle the clipboard monitor when visibility changes:

```python
    def on_visibility_changed(self, is_visible: bool) -> None:
        logger.debug("输入框可见性变化: %s", is_visible)
        if self.clipboard_monitor is not None:
            self.clipboard_monitor.set_enabled(is_visible)
```

- [ ] **Step 3: Update `config.example.json`**

```json
    "integration": {
        "hotkeys_enabled": true,
        "clipboard_enabled": true,
        "browser_headless": true
    }
```

- [ ] **Step 4: Run all integration tests**

```bash
cd D:/Source/live2oder && poetry run pytest test/integration/ -v
```
Expected: ALL PASS

- [ ] **Step 5: Run full test suite**

```bash
cd D:/Source/live2oder && poetry run pytest test/ -v --timeout=30
```
Expected: No regressions

- [ ] **Step 6: Commit**

```bash
git add internal/app/live2d_agent_app.py internal/ui/input_box.py config.example.json
git commit -m "feat(integration): wire clipboard, browser, and hotkeys into app"
```

---

### Task 6: Manual Verification

- [ ] **Step 1: Verify hotkeys**

Run the app and test:
1. `Ctrl+Shift+Space` → toggles input box visibility
2. `Ctrl+Shift+C` → copies current selection to input box and shows window

- [ ] **Step 2: Verify clipboard mini bar**

1. Copy some text elsewhere (e.g., a paragraph from a browser)
2. Verify the mini action bar pops up near the mouse
3. Click "翻译" → verify text appears in input box

- [ ] **Step 3: Verify browser tools**

1. In chat, type: "帮我用浏览器打开 example.com 然后返回页面标题"
2. Verify the Agent calls `browser_open` tool and returns the page title

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix(integration): address issues found during manual verification"
```

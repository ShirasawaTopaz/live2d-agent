"""Browser control tools for the Agent.

Wraps Playwright for browser automation. Exposes tools that the Agent
can call to navigate, extract, click, type, search, and screenshot.
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
    """High-level browser automation controller."""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._browser: Any = None
        self._page: Any = None
        self._playwright: Any = None
        self._initialized = False

    def get_tools(self) -> list[BrowserTool]:
        return [
            BrowserTool(name="browser_open", description="打开浏览器并导航到指定URL，返回页面文本内容",
                        parameters={"url": {"type": "string", "description": "要打开的网页URL"}}),
            BrowserTool(name="browser_extract", description="从当前浏览器页面提取指定CSS选择器的内容",
                        parameters={"selector": {"type": "string", "description": "CSS选择器"}}),
            BrowserTool(name="browser_click", description="点击浏览器页面中的指定元素",
                        parameters={"selector": {"type": "string", "description": "CSS选择器"}}),
            BrowserTool(name="browser_type", description="在输入框中输入文本",
                        parameters={"selector": {"type": "string"}, "text": {"type": "string"}}),
            BrowserTool(name="browser_search", description="在搜索引擎中搜索并返回前5条结果",
                        parameters={"query": {"type": "string"}}),
            BrowserTool(name="browser_screenshot", description="截取页面或元素的截图",
                        parameters={"selector": {"type": "string", "description": "CSS选择器（可选）"}}),
            BrowserTool(name="browser_scroll", description="滚动页面",
                        parameters={"direction": {"type": "string", "enum": ["up", "down"]}}),
            BrowserTool(name="browser_close", description="关闭浏览器", parameters={}),
        ]

    def describe_tools(self) -> str:
        lines: list[str] = []
        for tool in self.get_tools():
            params = ", ".join(tool.parameters.keys())
            lines.append(f"- {tool.name}({params}): {tool.description}")
        return "\n".join(lines)

    async def initialize(self) -> None:
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
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()
        self._initialized = False
        logger.info("BrowserController shut down")

    async def open(self, url: str) -> str:
        await self._ensure_initialized()
        await self._page.goto(url, wait_until="domcontentloaded", timeout=15000)
        content = await self._page.inner_text("body")
        title = await self._page.title()
        return f"页面标题: {title}\n\n页面内容:\n{content[:5000]}"

    async def extract(self, selector: str) -> str:
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
        await self._ensure_initialized()
        try:
            await self._page.click(selector, timeout=5000)
            return f"已点击 '{selector}'"
        except Exception as e:
            return f"点击失败: {e}"

    async def type_text(self, selector: str, text: str) -> str:
        await self._ensure_initialized()
        await self._page.fill(selector, text, timeout=5000)
        return f"已在 '{selector}' 中输入文本"

    async def search(self, query: str) -> str:
        await self._ensure_initialized()
        search_url = f"https://www.google.com/search?q={query}"
        await self._page.goto(search_url, wait_until="domcontentloaded", timeout=15000)
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
        await self._ensure_initialized()
        if selector is not None:
            element = await self._page.query_selector(selector)
            if element is not None:
                return await element.screenshot()
        return await self._page.screenshot()

    async def scroll(self, direction: str) -> str:
        await self._ensure_initialized()
        amount = 500 if direction == "down" else -500
        await self._page.evaluate(f"window.scrollBy(0, {amount})")
        return f"页面已向{'下' if direction == 'down' else '上'}滚动"

    async def close_browser(self) -> str:
        if self._page is not None:
            await self._page.close()
            self._page = None
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        self._initialized = False
        return "浏览器已关闭"

    async def _ensure_initialized(self) -> None:
        if not self._initialized:
            await self.initialize()


def register_browser_tools(controller: BrowserController, tool_registry: Any) -> None:
    """Register all browser tools into the Agent's ToolRegistry."""
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

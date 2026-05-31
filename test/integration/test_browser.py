"""Unit tests for BrowserController."""

import pytest
from internal.integration.browser import BrowserController


class TestBrowserController:
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

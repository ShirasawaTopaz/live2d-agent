"""Unit tests for ClipboardMonitor and ClipAction."""

import pytest
from internal.integration.clipboard import ClipAction, ClipboardMonitor


class TestClipAction:
    def test_create_action(self):
        action = ClipAction(id="translate", label="翻译",
                            prompt_template="请将以下内容翻译成中文:\n{text}")
        assert action.id == "translate"
        assert action.label == "翻译"

    def test_resolve_prompt(self):
        action = ClipAction(id="summarize", label="总结",
                            prompt_template="总结以下内容:\n{text}")
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
    def test_default_actions_set(self):
        monitor = ClipboardMonitor()
        assert len(monitor.actions) >= 4

    def test_custom_actions(self):
        custom = [ClipAction(id="mock_action", label="Mock", prompt_template="{text}")]
        monitor = ClipboardMonitor(actions=custom)
        assert len(monitor.actions) == 1
        assert monitor.actions[0].id == "mock_action"

    def test_enabled_default(self):
        monitor = ClipboardMonitor()
        assert monitor.enabled is False

    def test_set_enabled(self):
        monitor = ClipboardMonitor()
        monitor.set_enabled(True)
        assert monitor.enabled is True
        monitor.set_enabled(False)
        assert monitor.enabled is False

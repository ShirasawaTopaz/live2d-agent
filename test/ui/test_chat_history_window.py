import pytest
pytest.importorskip("PySide6")
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from internal.ui.chat_history_window import ChatHistoryWindow


@pytest.fixture
def qt_app():
    app = QApplication.instance()
    if app is None:
        import sys
        app = QApplication(sys.argv)
    return app


def test_window_title(qt_app):
    w = ChatHistoryWindow()
    assert "Chat History" in w.windowTitle()


def test_add_user_message(qt_app):
    w = ChatHistoryWindow()
    msg = {"role": "user", "content": "hello", "message_id": "1", "timestamp": 1000.0}
    w.add_message(msg)
    assert w._message_count() == 1


def test_add_assistant_message(qt_app):
    w = ChatHistoryWindow()
    msg = {
        "role": "assistant",
        "content": "hi there",
        "message_id": "2",
        "timestamp": 1001.0,
        "token_count": {"input": 10, "output": 20, "total": 30},
    }
    w.add_message(msg)
    assert w._message_count() == 1


def test_token_status_bar(qt_app):
    w = ChatHistoryWindow()
    msg = {
        "role": "assistant",
        "content": "reply",
        "message_id": "1",
        "timestamp": 1000.0,
        "token_count": {"input": 5, "output": 15, "total": 20},
    }
    w.add_message(msg)
    assert "5" in w._status_label.text()
    assert "15" in w._status_label.text()


def test_message_count_increment(qt_app):
    w = ChatHistoryWindow()
    w.add_message({"role": "user", "content": "a", "message_id": "1", "timestamp": 1.0})
    w.add_message({"role": "assistant", "content": "b", "message_id": "2", "timestamp": 2.0})
    w.add_message({"role": "user", "content": "c", "message_id": "3", "timestamp": 3.0})
    assert w._message_count() == 3


def test_clear_messages(qt_app):
    w = ChatHistoryWindow()
    w.add_message({"role": "user", "content": "x", "message_id": "1", "timestamp": 1.0})
    w.clear_messages()
    assert w._message_count() == 0


def test_set_model_name(qt_app):
    w = ChatHistoryWindow()
    w.set_model_name("gemma3:1b")
    assert "gemma3:1b" in w._status_label.text()


def test_empty_state(qt_app):
    w = ChatHistoryWindow()
    w.add_message({"role": "user", "content": "test", "message_id": "1", "timestamp": 1.0})
    assert w._message_count() == 1

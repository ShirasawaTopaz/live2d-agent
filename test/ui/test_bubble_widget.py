import os
import sys

import pytest

pytest.importorskip("PySide6")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from internal.ui.bubble_widget import BubbleWidget


@pytest.fixture
def qt_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_sync_scroll_to_audio_is_noop(qt_app):
    widget = BubbleWidget()
    widget.sync_scroll_to_audio(lambda: 500, duration_ms=1000)
    widget.clear_audio_scroll_sync()


def test_bubble_theme_stylesheet_applied(qt_app):
    widget = BubbleWidget()
    widget.set_theme("light")
    style = widget._browser.styleSheet()
    assert "color: #333" in style


def test_bubble_inner_browser_created(qt_app):
    widget = BubbleWidget()
    from PySide6.QtWidgets import QTextBrowser
    assert isinstance(widget._browser, QTextBrowser)


def test_bubble_renders_markdown(qt_app):
    widget = BubbleWidget()
    widget.set_text("**bold** text")
    html = widget._browser.toHtml()
    assert "font-weight:700" in html
    assert "bold" in html
    assert widget.displayed_text == "**bold** text"


def test_bubble_typewriter_shows_text(qt_app):
    widget = BubbleWidget()
    widget.start_typewriter("hello")
    assert widget.char_index == 0
    assert widget.displayed_text == ""
    widget._on_typewriter_tick()
    assert widget.char_index == 1
    assert widget.displayed_text == "h"


def test_bubble_theme_applies_to_browser(qt_app):
    widget = BubbleWidget()
    widget.set_theme("light")
    assert widget._theme == "light"

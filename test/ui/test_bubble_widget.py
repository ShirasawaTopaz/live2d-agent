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


def test_audio_scroll_sync_maps_audio_position_to_scroll_offset(qt_app):
    widget = BubbleWidget()
    widget.resize(200, widget.height())
    widget.set_text("x" * 200)
    widget._scroll_target_x = -100.0

    position = {"value": 500}

    widget.sync_scroll_to_audio(lambda: position["value"], duration_ms=1000)
    target_scroll_x = widget._scroll_target_x

    assert widget.scroll_x == target_scroll_x * 0.5

    position["value"] = 1000
    widget._sync_scroll_to_audio()

    assert widget.scroll_x == target_scroll_x
